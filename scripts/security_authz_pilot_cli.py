#!/usr/bin/env python3
"""P0-3b authz pilot Ops CLI (stdlib + importlib; no platform package install).

Commands:
  --status              Evaluate current ledger (AIPLAT_AUTHZ_PILOT_PATH / ~/.aiplat)
  --dry-run-exit        Simulate 2×3 pass + owner → show exit criteria (does not write)
  --probe               Live HTTP probes (--base-url --app-type [--sample-id] [--record])
  --approve             Record Security Owner approval (--owner NAME [--note TEXT])

Exit 0 on success for status/dry-run; probe/approve return 1 on fail/not-passed.
Never sets security_certification. Dry-run ≠ live pilot exit.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "aiPlat-platform" / "builder" / "artifact_authz_smoke.py"


def _load():
    # Register before exec_module — Py3.9 dataclasses need sys.modules entry.
    name = "artifact_authz_smoke_cli"
    spec = importlib.util.spec_from_file_location(name, MOD)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load:{MOD}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def cmd_status(authz, args: argparse.Namespace) -> int:
    path = Path(args.path) if args.path else None
    state = authz.load_pilot_state(path)
    ev = authz.evaluate_pilot_exit(state)
    out = {
        "schema": "eval.security_authz_pilot_status.v1",
        "ledger_path": str(path or authz._pilot_path()),
        "started_at": state.started_at,
        "sample_count": len(state.samples),
        "owner_name": state.owner_name or "(unset)",
        "owner_approval": state.owner_approval or "(unset)",
        "evaluation": ev,
        "security_certification": False,
        "honesty": "Ledger status ≠ live sample proof ≠ certification.",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_dry_run_exit(authz, _args: argparse.Namespace) -> int:
    """Fixture ledger proving exit math; never touches real AIPLAT_AUTHZ_PILOT_PATH."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "authz_pilot.json"
        state = authz.PilotState(started_at="2026-01-01")
        for app_type in ("crud", "report"):
            for i in range(1, 4):
                smoke = {
                    "sample_id": f"{app_type}-s{i}",
                    "app_type": app_type,
                    "status": "pass",
                    "negatives_blocked": True,
                    "evidence": "dry-run fixture",
                }
                authz.record_pilot_sample(smoke, path=path)
        state = authz.load_pilot_state(path)
        before = authz.evaluate_pilot_exit(state)
        # Approve in temp ledger only
        after = authz.approve_pilot_exit(
            owner_name="dry-run-owner",
            note="fixture only — not a real exit",
            path=path,
        )
        out = {
            "schema": "eval.security_authz_pilot_dry_run.v1",
            "before_owner": before,
            "after_owner": after,
            "ok": after.get("status") == "passed",
            "security_certification": False,
            "honesty": (
                "Dry-run exit math only. Does not write real ledger. "
                "≠ live samples ≠ Owner approval ≠ certification."
            ),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["ok"] else 1


def cmd_probe(authz, args: argparse.Namespace) -> int:
    smoke = authz.run_authz_smoke(
        base_url=args.base_url,
        app_type=args.app_type,
        sample_id=args.sample_id or "",
    )
    recorded = None
    if args.record:
        path = Path(args.path) if args.path else None
        state = authz.record_pilot_sample(smoke, path=path)
        recorded = {
            "sample_count": len(state.samples),
            "status": state.status,
            "ledger": str(path or authz._pilot_path()),
        }
    out: Dict[str, Any] = {
        "schema": "eval.security_authz_pilot_probe.v1",
        "smoke": smoke,
        "recorded": recorded,
        "security_certification": False,
        "honesty": "Probe result is sample evidence only; pilot exit still needs Owner.",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if smoke.get("status") == "pass" else 1


def cmd_approve(authz, args: argparse.Namespace) -> int:
    path = Path(args.path) if args.path else None
    result = authz.approve_pilot_exit(
        owner_name=args.owner,
        note=args.note or "",
        path=path,
    )
    out = {
        "schema": "eval.security_authz_pilot_approve.v1",
        "result": result,
        "security_certification": False,
        "honesty": "Owner note recorded; status=passed only if samples also satisfy §1.2.",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "passed" else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="P0-3b authz pilot Ops CLI")
    parser.add_argument("--path", default="", help="Override ledger JSON path")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true")
    g.add_argument("--dry-run-exit", action="store_true")
    g.add_argument("--probe", action="store_true")
    g.add_argument("--approve", action="store_true")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--app-type", default="", choices=["", "crud", "report"])
    parser.add_argument("--sample-id", default="")
    parser.add_argument("--record", action="store_true", help="Persist probe into ledger")
    parser.add_argument("--owner", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)

    authz = _load()
    if args.status:
        return cmd_status(authz, args)
    if args.dry_run_exit:
        return cmd_dry_run_exit(authz, args)
    if args.probe:
        if not args.base_url or not args.app_type:
            print("FAIL: --probe requires --base-url and --app-type", file=sys.stderr)
            return 2
        return cmd_probe(authz, args)
    if args.approve:
        if not args.owner.strip():
            print("FAIL: --approve requires --owner", file=sys.stderr)
            return 2
        return cmd_approve(authz, args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
