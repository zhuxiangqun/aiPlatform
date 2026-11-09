#!/usr/bin/env python3
"""Ops-facing security audit (report-only by default).

Checks:
  - IR contacts filled (SoT file)
  - Policy fail-mode / profile consistency (best-effort import or env heuristic)
  - Hard-floor escape window
  - P2-1 HMAC/Ed25519 / allowlist presence
  - Closeout engineering inventory

Exit 0 always unless --strict (then any failing check → 1).
Never sets security_certification.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_future(raw: str) -> Optional[bool]:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        # tolerate Z
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt > datetime.now(timezone.utc)
    except Exception:
        return False


def check_ir_contacts() -> Dict[str, Any]:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from security_ir_contacts import load_contacts  # type: ignore

        return load_contacts()
    except Exception as e:
        return {"ok": False, "filled": False, "error": type(e).__name__}


def check_fail_closed() -> Dict[str, Any]:
    profile = (os.getenv("AIPLAT_PROFILE") or os.getenv("AIPLAT_ENV") or "").strip().lower()
    explicit = (os.getenv("AIPLAT_POLICY_FAIL_MODE") or "").strip().lower()
    until = (os.getenv("AIPLAT_POLICY_FAIL_OPEN_UNTIL") or "").strip()
    # Prefer core audit when importable
    try:
        sys.path.insert(0, str(ROOT / "aiPlat-core"))
        from core.harness.infrastructure.gates.policy_gate import (  # type: ignore
            audit_policy_fail_mode_config,
        )

        snap = dict(audit_policy_fail_mode_config())
        snap["source"] = "policy_gate.audit_policy_fail_mode_config"
        snap["ok"] = bool(snap.get("ok", True))
        # Treat drift / open without until as not ok for prodish
        warnings = list(snap.get("warnings") or snap.get("issues") or [])
        if profile in ("production", "prod", "staging", "stage", "preprod"):
            eff = str(snap.get("effective") or snap.get("effective_mode") or "").lower()
            if "open" in eff and not until:
                snap["ok"] = False
                warnings.append("prodish_open_without_until")
        snap["warnings"] = warnings
        snap["security_certification"] = False
        return snap
    except Exception as e:
        # Env heuristic
        prodish = profile in ("production", "prod", "staging", "stage", "preprod")
        expected = "closed" if prodish else ("ask" if profile else "(unset)")
        ok = True
        issues: List[str] = []
        if prodish and explicit in ("open",) and not until:
            ok = False
            issues.append("prodish_explicit_open_without_until")
        if prodish and not profile:
            issues.append("profile_unset")
        return {
            "ok": ok,
            "source": "env_heuristic",
            "profile": profile or "(unset)",
            "explicit_fail_mode": explicit or "(unset)",
            "expected_default": expected,
            "open_until": until or "(unset)",
            "issues": issues,
            "import_error": type(e).__name__,
            "security_certification": False,
        }


def check_hard_floor() -> Dict[str, Any]:
    flag = (os.getenv("AIPLAT_HARD_FLOOR_DISABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    until = (os.getenv("AIPLAT_HARD_FLOOR_DISABLED_UNTIL") or "").strip()
    future = _iso_future(until)
    ok = True
    issues: List[str] = []
    if flag and future is not True:
        ok = False
        issues.append("hard_floor_disabled_without_valid_until")
    return {
        "ok": ok,
        "disabled_flag": flag,
        "until": until or "(unset)",
        "until_in_future": future,
        "issues": issues,
        "security_certification": False,
    }


def check_p2_1_keys() -> Dict[str, Any]:
    hmac = bool((os.getenv("AIPLAT_ARTIFACT_MANIFEST_HMAC_SECRET") or "").strip())
    ed_seed = bool((os.getenv("AIPLAT_ARTIFACT_MANIFEST_ED25519_SEED") or "").strip())
    ed_key = bool((os.getenv("AIPLAT_ARTIFACT_MANIFEST_ED25519_KEY") or "").strip())
    pub = ROOT / "security" / "keys" / "artifact-manifest-ci.pub"
    allow = ROOT / "security" / "keys" / "mcp_plugin_allowlist.json"
    profile = (os.getenv("AIPLAT_PROFILE") or os.getenv("AIPLAT_ENV") or "").strip().lower()
    prodish = profile in ("production", "prod", "staging", "stage", "preprod")
    issues: List[str] = []
    if prodish and not (hmac or ed_seed or ed_key):
        issues.append("prodish_no_signing_secret")
    if not allow.is_file():
        issues.append("allowlist_missing")
    return {
        "ok": not issues,
        "hmac_configured": hmac,
        "ed25519_configured": ed_seed or ed_key,
        "pubkey_file_present": pub.is_file(),
        "allowlist_present": allow.is_file(),
        "issues": issues,
        "security_certification": False,
    }


def check_engineering_closeout() -> Dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "security_plan_closeout_check.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        payload = {"ok": False, "error": "closeout_json_parse_failed"}
    return {
        "ok": proc.returncode == 0 and bool(payload.get("ok")),
        "exit_code": proc.returncode,
        "ops_pending_count": payload.get("ops_pending_count"),
        "missing": (payload.get("engineering") or {}).get("missing"),
        "security_certification": False,
    }


def simulate_profile_matrix() -> Dict[str, Any]:
    """Dry-run expected fail-mode defaults per profile (P0-2 cutover aid).

    Does not mutate process env permanently; restores after each row.
    """
    saved = {
        k: os.environ.get(k)
        for k in (
            "AIPLAT_PROFILE",
            "AIPLAT_ENV",
            "AIPLAT_POLICY_FAIL_MODE",
            "AIPLAT_POLICY_FAIL_OPEN_UNTIL",
            "AIPLAT_POLICY_FAIL_CRITICAL_MODE",
        )
    }
    rows: List[Dict[str, Any]] = []
    scenarios = [
        {"profile": "production", "explicit": None, "until": None, "expect": "closed"},
        {"profile": "staging", "explicit": None, "until": None, "expect": "closed"},
        {"profile": "development", "explicit": None, "until": None, "expect": "ask"},
        {
            "profile": "production",
            "explicit": "open",
            "until": None,
            "expect": "closed",  # open not honored without UNTIL
        },
        {
            "profile": "production",
            "explicit": "open",
            "until": "2099-01-01T00:00:00Z",
            "expect": "open",
        },
    ]
    try:
        sys.path.insert(0, str(ROOT / "aiPlat-core"))
        from core.harness.infrastructure.gates.policy_gate import (  # type: ignore
            audit_policy_fail_mode_config,
            resolve_policy_fail_mode,
        )

        for sc in scenarios:
            for k in saved:
                if saved[k] is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = saved[k]
            os.environ["AIPLAT_PROFILE"] = sc["profile"]
            os.environ.pop("AIPLAT_ENV", None)
            if sc["explicit"]:
                os.environ["AIPLAT_POLICY_FAIL_MODE"] = sc["explicit"]
            else:
                os.environ.pop("AIPLAT_POLICY_FAIL_MODE", None)
            if sc["until"]:
                os.environ["AIPLAT_POLICY_FAIL_OPEN_UNTIL"] = sc["until"]
            else:
                os.environ.pop("AIPLAT_POLICY_FAIL_OPEN_UNTIL", None)
            os.environ.pop("AIPLAT_POLICY_FAIL_CRITICAL_MODE", None)
            effective = resolve_policy_fail_mode(critical=True)
            snap = audit_policy_fail_mode_config()
            # Row ok = effective mode matches expect. Drift is informational
            # (prod open-with-UNTIL is intentional grayscale and still flags drift).
            rows.append(
                {
                    "profile": sc["profile"],
                    "explicit": sc["explicit"] or "(unset)",
                    "until": sc["until"] or "(unset)",
                    "effective_critical": effective,
                    "expect": sc["expect"],
                    "ok": effective == sc["expect"],
                    "drift": bool(snap.get("drift_fail_open_in_prodish")),
                }
            )
    except Exception as e:
        return {
            "ok": False,
            "error": type(e).__name__,
            "rows": rows,
            "security_certification": False,
        }
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return {
        "ok": all(r.get("ok") for r in rows),
        "rows": rows,
        "security_certification": False,
        "honesty": "Matrix is local dry-run ≠ production cutover proof.",
    }


def run_ops_audit() -> Dict[str, Any]:
    checks = {
        "ir_contacts": check_ir_contacts(),
        "fail_closed": check_fail_closed(),
        "hard_floor": check_hard_floor(),
        "p2_1_keys": check_p2_1_keys(),
        "engineering_closeout": check_engineering_closeout(),
    }
    failing = [k for k, v in checks.items() if not v.get("ok")]
    return {
        "schema": "eval.security_ops_audit.v1",
        "at": _now(),
        "ok": not failing,
        "failing_checks": failing,
        "checks": checks,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "Ops audit report-only. Passing ≠ production proven ≠ certification. "
            "Use --strict to fail CI when any check fails."
        ),
    }


def main() -> int:
    if "--profile-matrix" in sys.argv:
        matrix = simulate_profile_matrix()
        print(json.dumps(matrix, ensure_ascii=False, indent=2))
        print(
            f"profile_matrix ok={matrix.get('ok')} cert=false",
            file=sys.stderr,
        )
        return 0 if matrix.get("ok") else 1

    report = run_ops_audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    strict = "--strict" in sys.argv
    if strict and not report["ok"]:
        print(
            f"FAIL --strict: {','.join(report['failing_checks'])}",
            file=sys.stderr,
        )
        return 1
    print(
        f"ops_audit ok={report['ok']} failing={report['failing_checks']} cert=false",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
