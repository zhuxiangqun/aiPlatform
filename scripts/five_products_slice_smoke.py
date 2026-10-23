#!/usr/bin/env python3
"""WP4 smoke for fp-internal-bundle-pi-diag-001 (no production path changes).

Runs: export → synthetic Pi RUNLOG → evidence ingest/report → signoff validation.
Writes under reports/five-products/slice-fp-internal-bundle-pi-diag-001/.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "aiPlat-core"))

from core.apps.fde.service.slice_bundle_export import export_slice_bundle
from core.apps.fde.service.slice_evidence import (
    build_slice_diagnosis_report,
    ingest_slice_evidence,
    validate_slice_signoff_reports,
)

SCENE = "fp-internal-bundle-pi-diag-001"
SLICE = WORKSPACE / "reports" / "five-products" / f"slice-{SCENE}"
SAMPLE = WORKSPACE / "packages" / "aiplat-pi-runtime" / "fixtures" / "sample-app"


def main() -> int:
    SLICE.mkdir(parents=True, exist_ok=True)
    (SLICE / "RUNLOG").mkdir(exist_ok=True)
    bundle_out = SLICE / "bundle"

    exp = export_slice_bundle(
        scenario_id=SCENE,
        app_home=str(SAMPLE),
        out_dir=str(bundle_out),
        runtime_mode="thin",
    )
    if not exp.get("ok"):
        print("EXPORT_FAIL", exp)
        return 1

    meta = exp.get("export_meta") or {}
    build = meta.get("build") if isinstance(meta.get("build"), dict) else {}
    bundle_version = (
        exp.get("bundle_id")
        or build.get("bundle_version")
        or meta.get("bundle_version")
        or "unknown"
    )

    run_id = f"smoke-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    runlog = {
        "run_id": run_id,
        "bundle_version": str(bundle_version),
        "runtime_version": "pi-thin-smoke",
        "events": [{"type": "smoke_start"}, {"type": "smoke_ok"}],
        "note": "synthetic Pi run for slice smoke; replace with live pi -e output in full WP4",
    }
    (SLICE / "RUNLOG" / "pi-run.jsonl").write_text(
        json.dumps(runlog, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    ing = ingest_slice_evidence(
        scenario_id=SCENE,
        run_id=run_id,
        bundle_version=str(bundle_version),
        runtime_version="pi-thin-smoke",
        events=list(runlog["events"]),
        asset_versions={"bundle_version": str(bundle_version)},
        aiplat_reachable=True,
    )
    if not ing.get("ok"):
        print("INGEST_FAIL", ing)
        return 1

    rep = build_slice_diagnosis_report(scenario_id=SCENE, ingest_id=ing["ingest_id"])
    if not rep.get("ok"):
        print("REPORT_FAIL", rep)
        return 1

    diag_path = SLICE / "DIAGNOSIS_REPORT.md"
    diag_path.write_text(
        "\n".join(
            [
                f"# Diagnosis report `{rep['report_id']}`",
                "",
                f"- scenario: `{SCENE}`",
                f"- status: **{rep.get('status')}**",
                f"- run_id: `{rep.get('run_id')}`",
                f"- bundle_version: `{rep.get('bundle_version')}`",
                f"- freshness: `{rep.get('freshness')}`",
                "",
                "```json",
                json.dumps(rep, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    gate = validate_slice_signoff_reports(
        {"scenario_id": SCENE, "evidence_report_ids": [rep["report_id"]]}
    )
    if not gate.get("ok"):
        print("SIGNOFF_GATE_FAIL", gate)
        return 1

    (SLICE / "ACCEPTANCE.md").write_text(
        "\n".join(
            [
                f"# Acceptance `{SCENE}`",
                "",
                f"- decision: accepted (smoke)",
                f"- evidence_report_ids: `{rep['report_id']}`",
                f"- signed_at: {datetime.now(timezone.utc).isoformat()}",
                f"- note: smoke path; full WP4 still requires live Pi + fault injection",
                "",
            ]
        ),
        encoding="utf-8",
    )

    versions = {
        "scene_id": SCENE,
        "bundle_id": exp.get("bundle_id"),
        "out_dir": exp.get("out_dir"),
        "report_id": rep.get("report_id"),
        "run_id": run_id,
        "smoke_at": datetime.now(timezone.utc).isoformat(),
    }
    (SLICE / "VERSIONS.md").write_text(
        "# VERSIONS\n\n```json\n" + json.dumps(versions, indent=2) + "\n```\n",
        encoding="utf-8",
    )

    print("SMOKE_OK", json.dumps(versions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
