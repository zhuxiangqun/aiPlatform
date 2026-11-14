#!/usr/bin/env python3
"""Security improvement plan closeout inventory (engineering vs ops).

Exit 0 = all engineering artifacts present (not certification).
Exit 1 = missing engineering files.
Never sets security_certification / accuracy_claim.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]

# Engineering must-exist paths (plan P0–P2 code/docs)
ENGINEERING: List[Tuple[str, str]] = [
    ("P0-1", "scripts/security-attack-sim.py"),
    ("P0-1", "scripts/tests/test_security_attack_sim.py"),
    ("P0-3a", "aiPlat-platform/builder/artifact_security_manifest.py"),
    ("P0-3b", "aiPlat-platform/builder/artifact_authz_smoke.py"),
    ("P0-3b", "reports/security/P0-3b-authz-pilot.md"),
    ("P0-3b", "scripts/security_authz_pilot_cli.py"),
    ("D01-tm", "security/templates/artifact_threat_model.v1.yaml"),
    ("D01-tm", "reports/security/P0-threat-model-artifact.md"),
    ("P0-4", "aiPlat-platform/builder/pi_bundle_export.py"),
    ("P0-IR", "reports/security/P0-IR-runbook.md"),
    ("P1-1-text", "aiPlat-core/core/apps/eval/service/security_text_live_p1.py"),
    ("P1-1-tr", "aiPlat-core/core/apps/eval/service/security_tool_retrieval_live_p1.py"),
    ("P1-2", "aiPlat-core/core/apps/eval/service/security_p1_judge_session.py"),
    ("P1-3", "aiPlat-core/core/apps/eval/service/security_dynamic_p13.py"),
    ("P1-4", "aiPlat-core/core/apps/eval/service/security_p1_4_kvm_escape.py"),
    ("P1-IR", "reports/security/P1-IR-tabletop-drill.md"),
    ("P2-1", "aiPlat-platform/builder/artifact_sbom_attest.py"),
    ("P2-1", "security/keys/mcp_plugin_allowlist.json"),
    ("P2-2", "reports/security/P2-2-external-pentest-rfp.md"),
    ("P2-3", "reports/security/P2-3-formal-ir-disclosure-draft.md"),
    ("plan", "reports/security/aiplat-security-improvement-plan-2026-11-09.md"),
    ("ops", "reports/security/ops-closeout-checklist-2026-11-09.md"),
    ("ops", "scripts/security_plan_closeout_check.py"),
    ("ops", "scripts/security_ops_audit.py"),
    ("ops", "scripts/run_security_p1_units.py"),
    ("P0-2", "reports/security/P0-2-fail-closed-cutover.md"),
    ("dims", "reports/security/security_quality_dimensions.yaml"),
    ("dims", "reports/security/security-quality-dimensions.md"),
    ("dims", "docs/reference/security/security-dimension-crosswalk.md"),
    ("dims", "scripts/security_dimensions_report.py"),
    ("P0-IR", "scripts/security_ir_contacts.py"),
    ("P0-IR", "security/ir/contacts.example.yaml"),
    ("P0-IR", "security/ir/contacts.local.yaml.example"),
]

UNIT_SUITES: List[str] = [
    "scripts/tests/test_security_attack_sim.py",
    "scripts/tests/test_security_ir_contacts.py",
    "scripts/tests/test_security_ops_audit.py",
    "scripts/tests/test_security_authz_pilot_cli.py",
    "scripts/tests/test_security_dimensions_report.py",
    "aiPlat-platform/tests/test_artifact_security_manifest.py",
    "aiPlat-platform/tests/test_artifact_sbom_attest.py",
    "aiPlat-platform/tests/test_artifact_authz_smoke.py",
    "aiPlat-core/core/tests/unit/test_apps/test_security_text_live_p1.py",
    "aiPlat-core/core/tests/unit/test_apps/test_security_tool_retrieval_live_p1.py",
    "aiPlat-core/core/tests/unit/test_apps/test_security_p1_judge_session.py",
    "aiPlat-core/core/tests/unit/test_apps/test_security_dynamic_p13.py",
    "aiPlat-core/core/tests/unit/test_apps/test_security_p1_4_kvm_escape.py",
]

OPS_PENDING: List[Dict[str, str]] = [
    {
        "id": "ops-p0-2",
        "item": "Production fail-closed grayscale cutover + audit",
        "owner": "Platform Security / Ops",
    },
    {
        "id": "ops-p0-ir",
        "item": "Fill security/ir/contacts.local.yaml (python3 scripts/security_ir_contacts.py)",
        "owner": "IR Lead",
    },
    {
        "id": "ops-p0-3b",
        "item": "Authz pilot live samples + Security Owner exit approval",
        "owner": "Product Security",
    },
    {
        "id": "ops-p1-1-live",
        "item": "True model live for text + tool/retrieval families",
        "owner": "Eval + QA",
    },
    {
        "id": "ops-p1-2",
        "item": "Human gold/judge calibration dual-review samples",
        "owner": "Security Owner + QA",
    },
    {
        "id": "ops-p1-3",
        "item": "Staging/prod black-box P1-3 dynamic probes",
        "owner": "Platform Eng",
    },
    {
        "id": "ops-p1-ir",
        "item": "P1-IR tabletop drill with scoring (contacts filled)",
        "owner": "IR Lead",
    },
    {
        "id": "ops-p1-4",
        "item": "Real KVM GuestChannel + human_review for covered",
        "owner": "Infra / Platform Security",
    },
    {
        "id": "ops-p2-1",
        "item": "syft/cosign production hardening + Ed25519 pubkey ceremony",
        "owner": "Platform Security",
    },
    {
        "id": "ops-p2-2",
        "item": "Issue RFP / select external pentest vendor",
        "owner": "Security Owner / Exec",
    },
    {
        "id": "ops-p2-3",
        "item": "Security mailbox + formal IR/cert project decision",
        "owner": "Exec Sponsor",
    },
]


def check_engineering() -> Dict[str, Any]:
    """check_engineering。
    """
    missing: List[Dict[str, str]] = []
    present: List[Dict[str, str]] = []
    for item_id, rel in ENGINEERING:
        path = ROOT / rel
        row = {"id": item_id, "path": rel}
        if path.is_file():
            present.append(row)
        else:
            missing.append(row)
    suites_ok = [(s, (ROOT / s).is_file()) for s in UNIT_SUITES]
    return {
        "present": present,
        "missing": missing,
        "unit_suites": [{"path": s, "ok": ok} for s, ok in suites_ok],
        "unit_suites_ok": all(ok for _, ok in suites_ok),
    }


def p0_ir_contacts_filled() -> Dict[str, Any]:
    """Prefer YAML SoT (security/ir/contacts.local.yaml); markdown TBD no longer authoritative."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from security_ir_contacts import load_contacts  # type: ignore

        c = load_contacts()
        return {
            "ok": bool(c.get("filled")),
            "detail": "contacts_filled" if c.get("filled") else "contacts_not_filled",
            "path": c.get("path"),
            "errors": c.get("errors") or ([c.get("error")] if c.get("error") else []),
        }
    except Exception as e:
        return {"ok": False, "detail": f"contacts_check_error:{type(e).__name__}"}


def main() -> int:
    """main。
    """
    eng = check_engineering()
    contacts = p0_ir_contacts_filled()
    report = {
        "schema": "eval.security_plan_closeout.v1",
        "ok": not eng["missing"] and eng["unit_suites_ok"],
        "engineering": eng,
        "ops_pending": OPS_PENDING,
        "ops_pending_count": len(OPS_PENDING),
        "p0_ir_contacts": contacts,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "Engineering inventory only. Ops pending does not fail this script "
            "unless --strict-ops. ≠ security certification."
        ),
    }
    strict_ops = "--strict-ops" in sys.argv
    if strict_ops and (not contacts["ok"] or OPS_PENDING):
        report["ok"] = False
        report["strict_ops_blocked"] = True

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if eng["missing"]:
        print(
            f"FAIL: missing {len(eng['missing'])} engineering artifacts",
            file=sys.stderr,
        )
        return 1
    if not eng["unit_suites_ok"]:
        print("FAIL: unit suite files missing", file=sys.stderr)
        return 1
    if strict_ops and not report["ok"]:
        print("FAIL: --strict-ops (contacts TBD or ops pending)", file=sys.stderr)
        return 1
    print(
        f"OK engineering closeout; ops_pending={len(OPS_PENDING)}; "
        f"contacts={contacts['detail']}; cert=false",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
