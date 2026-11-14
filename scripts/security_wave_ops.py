#!/usr/bin/env python3
"""Security Wave 1–4 engineering gates (honest; ≠ certification).

Wave1 engineering checks (auto):
  - W1-0 attack-sim unreachable → non-zero exit
  - W1-3 contacts.local.yaml is gitignored pattern
  - W1-5 dimensions ledger_ok; release/claim gates wired as CLI

Ops-only cards under reports/security/evidence/ are validated for presence
of templates, not for filled human evidence.

Exit 0 when engineering checks pass. Never sets security_certification.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "reports" / "security" / "evidence"


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def check_w1_0_attack_sim_unreachable() -> Dict[str, Any]:
    """check_w1_0_attack_sim_unreachable。
    """
    proc = _run(
        [sys.executable, str(ROOT / "scripts" / "security-attack-sim.py"), "http://127.0.0.1:9"]
    )
    archived = EVIDENCE / "wave1" / "attack-sim-unreachable-127.0.0.1-9.json"
    ok = proc.returncode != 0 and archived.is_file()
    return {
        "id": "W1-0",
        "ok": ok,
        "exit_code": proc.returncode,
        "archived": str(archived.relative_to(ROOT)) if archived.is_file() else None,
        "detail": "unreachable must FAIL (non-zero); archive required",
    }


def check_w1_3_ir_gitignore() -> Dict[str, Any]:
    """check_w1_3_ir_gitignore。
    """
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    pattern_ok = "*.local.yaml" in gi or "contacts.local.yaml" in gi
    example = ROOT / "security" / "ir" / "contacts.local.yaml.example"
    tracked_local = False
    ls = _run(["git", "ls-files", "security/ir/contacts.local.yaml"])
    if ls.returncode == 0 and (ls.stdout or "").strip():
        tracked_local = True
    return {
        "id": "W1-3",
        "ok": bool(pattern_ok and example.is_file() and not tracked_local),
        "gitignore_local_yaml": pattern_ok,
        "example_present": example.is_file(),
        "contacts_local_tracked": tracked_local,
        "detail": "contacts.local.yaml must stay untracked; example for CI/schema",
    }


def check_w1_5_gates() -> Dict[str, Any]:
    """check_w1_5_gates。
    """
    ledger = _run(
        [sys.executable, str(ROOT / "scripts" / "security_dimensions_report.py")]
    )
    # stdout is JSON; exit 0 when ledger_ok
    try:
        payload = json.loads(ledger.stdout or "{}")
    except json.JSONDecodeError:
        payload = {}
    ledger_ok = bool(payload.get("ledger_ok") or payload.get("schema_ok"))
    # release/claim should be callable and typically fail honestly today
    rel = _run(
        [
            sys.executable,
            str(ROOT / "scripts" / "security_dimensions_report.py"),
            "--release-gate",
        ]
    )
    claim = _run(
        [
            sys.executable,
            str(ROOT / "scripts" / "security_dimensions_report.py"),
            "--claim-gate",
        ]
    )
    return {
        "id": "W1-5",
        "ok": ledger.returncode == 0 and ledger_ok and rel.returncode in (0, 1) and claim.returncode in (0, 1),
        "ledger_exit": ledger.returncode,
        "ledger_ok": ledger_ok,
        "release_exit": rel.returncode,
        "claim_exit": claim.returncode,
        "release_ok": payload.get("release_ok"),
        "coverage_ok": payload.get("coverage_ok"),
        "detail": "CI uses ledger; publish uses --release-gate; claim uses --claim-gate",
    }


def check_wave1_templates() -> Dict[str, Any]:
    """check_wave1_templates。
    """
    needed = [
        EVIDENCE / "wave1" / "README.md",
        EVIDENCE / "wave1" / "staging-fail-closed-card.md",
        EVIDENCE / "wave1" / "prod-profile-audit-card.md",
        EVIDENCE / "wave1" / "staging-attack-sim-card.md",
        EVIDENCE / "wave1" / "profile-matrix-dry-run.json",
    ]
    missing = [str(p.relative_to(ROOT)) for p in needed if not p.is_file()]
    return {
        "id": "W1-templates",
        "ok": not missing,
        "missing": missing,
    }


def check_w1_publish_gates_wrapper() -> Dict[str, Any]:
    """check_w1_publish_gates_wrapper。
    """
    script = ROOT / "scripts" / "security_publish_gates.py"
    if not script.is_file():
        return {"id": "W1-5-wrapper", "ok": False, "detail": "missing security_publish_gates.py"}
    ledger = _run([sys.executable, str(script), "--mode", "ledger"])
    release = _run([sys.executable, str(script), "--mode", "release"])
    claim = _run([sys.executable, str(script), "--mode", "claim"])
    return {
        "id": "W1-5-wrapper",
        "ok": ledger.returncode == 0 and release.returncode == 1 and claim.returncode == 1,
        "ledger_exit": ledger.returncode,
        "release_exit": release.returncode,
        "claim_exit": claim.returncode,
        "detail": "ledger must pass; release/claim must fail honestly while gaps block",
    }


def check_wave2_pilot_fields() -> Dict[str, Any]:
    """Import authz smoke and assert PilotSample has git_commit/build_id."""
    import importlib.util

    mod_path = ROOT / "aiPlat-platform" / "builder" / "artifact_authz_smoke.py"
    name = "artifact_authz_smoke_wave_ops"
    spec = importlib.util.spec_from_file_location(name, mod_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    fields = getattr(mod.PilotSample, "__annotations__", {})
    ok = "git_commit" in fields and "build_id" in fields
    # evaluate rejects pass samples without commit/build
    state = mod.PilotState(started_at="2026-11-10")
    for i in range(3):
        state.samples.append(
            mod.PilotSample(
                sample_id=f"c{i}",
                app_type="crud",
                authz_status="pass",
                negatives_blocked=True,
                git_commit="",
                build_id="",
            )
        )
    for i in range(3):
        state.samples.append(
            mod.PilotSample(
                sample_id=f"r{i}",
                app_type="report",
                authz_status="pass",
                negatives_blocked=True,
                git_commit="deadbeef",
                build_id="build-1",
            )
        )
    ev = mod.evaluate_pilot_exit(state)
    # crud missing commit → types not ready
    crud_ok = bool((ev.get("types") or {}).get("crud", {}).get("ok"))
    return {
        "id": "W2-fields",
        "ok": ok and crud_ok is False,
        "has_git_commit_field": "git_commit" in fields,
        "has_build_id_field": "build_id" in fields,
        "crud_ok_without_commit": crud_ok,
        "detail": "pass samples require git_commit+build_id for pilot exit",
    }


def check_wave3_card_schema() -> Dict[str, Any]:
    """check_wave3_card_schema。
    """
    script = ROOT / "scripts" / "security_evidence_card.py"
    template = EVIDENCE / "wave3" / "text-family-live.card.json"
    if not script.is_file() or not template.is_file():
        return {"id": "W3-schema", "ok": False, "detail": "missing script or template"}
    proc = _run([sys.executable, str(script), "--validate", str(template)])
    return {
        "id": "W3-schema",
        "ok": proc.returncode == 0,
        "exit": proc.returncode,
        "stderr": (proc.stderr or "")[:200],
    }


def check_wave4_artifacts() -> Dict[str, Any]:
    """check_wave4_artifacts。
    """
    needed = [
        EVIDENCE / "wave4" / "README.md",
        EVIDENCE / "wave4" / "ir-tabletop-scorecard.schema.json",
        EVIDENCE / "wave4" / "sbom-ceremony-checklist.md",
        EVIDENCE / "wave4" / "kvm-guest-probe-card.md",
        ROOT / "reports" / "security" / "P2-2-external-pentest-rfp.md",
        ROOT / "reports" / "security" / "P1-IR-tabletop-drill.md",
    ]
    missing = [str(p.relative_to(ROOT)) for p in needed if not p.is_file()]
    return {"id": "W4-assets", "ok": not missing, "missing": missing}


def run_wave1() -> Dict[str, Any]:
    """run_wave1。
    """
    checks = [
        check_w1_0_attack_sim_unreachable(),
        check_w1_3_ir_gitignore(),
        check_w1_5_gates(),
        check_w1_publish_gates_wrapper(),
        check_wave1_templates(),
    ]
    return {
        "wave": 1,
        "ok": all(c.get("ok") for c in checks),
        "checks": checks,
        "security_certification": False,
    }


def run_wave2() -> Dict[str, Any]:
    """run_wave2。
    """
    checks = [check_wave2_pilot_fields()]
    tpl = EVIDENCE / "wave2" / "README.md"
    checks.append(
        {
            "id": "W2-readme",
            "ok": tpl.is_file(),
            "path": str(tpl.relative_to(ROOT)) if tpl.is_file() else None,
        }
    )
    return {
        "wave": 2,
        "ok": all(c.get("ok") for c in checks),
        "checks": checks,
        "security_certification": False,
    }


def run_wave3() -> Dict[str, Any]:
    """run_wave3。
    """
    checks = [check_wave3_card_schema()]
    for name in ("text-family-live.card.json", "staging-tenant-blackbox.card.json", "README.md"):
        p = EVIDENCE / "wave3" / name
        checks.append({"id": f"W3-{name}", "ok": p.is_file()})
    return {
        "wave": 3,
        "ok": all(c.get("ok") for c in checks),
        "checks": checks,
        "security_certification": False,
    }


def run_wave4() -> Dict[str, Any]:
    """run_wave4。
    """
    checks = [check_wave4_artifacts()]
    return {
        "wave": 4,
        "ok": all(c.get("ok") for c in checks),
        "checks": checks,
        "security_certification": False,
    }


def main(argv: Optional[List[str]] = None) -> int:
    """main。

    Args:
        argv: argv 参数。
    """
    parser = argparse.ArgumentParser(description="Security wave engineering gates")
    parser.add_argument("--wave1", action="store_true")
    parser.add_argument("--wave2", action="store_true")
    parser.add_argument("--wave3", action="store_true")
    parser.add_argument("--wave4", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    if not any([args.wave1, args.wave2, args.wave3, args.wave4, args.all]):
        args.all = True

    reports: List[Dict[str, Any]] = []
    if args.all or args.wave1:
        reports.append(run_wave1())
    if args.all or args.wave2:
        reports.append(run_wave2())
    if args.all or args.wave3:
        reports.append(run_wave3())
    if args.all or args.wave4:
        reports.append(run_wave4())

    payload = {
        "schema": "eval.security_wave_ops.v1",
        "ok": all(r.get("ok") for r in reports),
        "waves": reports,
        "security_certification": False,
        "honesty": "Engineering gates only; Ops cards may still be empty.",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
