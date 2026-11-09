#!/usr/bin/env python3
"""Refuse promoting D26 → E without pilot dual-sign exit (Wave2 hard rule).

Usage:
  python3 scripts/security_d26_promote_check.py
  python3 scripts/security_d26_promote_check.py --propose-e   # exit 1 unless pilot passed

Never edits YAML. Never sets security_certification.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
DIMS = ROOT / "reports" / "security" / "security_quality_dimensions.yaml"
AUTHZ = ROOT / "aiPlat-platform" / "builder" / "artifact_authz_smoke.py"


def _load_authz():
    name = "artifact_authz_smoke_d26"
    spec = importlib.util.spec_from_file_location(name, AUTHZ)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _d26_status(doc: Dict[str, Any]) -> str:
    for dim in doc.get("dimensions") or []:
        if isinstance(dim, dict) and dim.get("id") == "D26":
            return str(dim.get("status") or "")
    return ""


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--propose-e",
        action="store_true",
        help="Fail unless pilot exit allows D26 promotion to E",
    )
    parser.add_argument("--path", default="", help="Override authz pilot ledger")
    args = parser.parse_args(argv)

    doc = yaml.safe_load(DIMS.read_text(encoding="utf-8")) or {}
    status = _d26_status(doc)
    authz = _load_authz()
    ledger = Path(args.path) if args.path else None
    state = authz.load_pilot_state(ledger)
    ev = authz.evaluate_pilot_exit(state)
    promote_ok = bool(ev.get("d26_promote_allowed"))

    # Integrity: if YAML already claims E, pilot must have passed
    yaml_e_without_pilot = status == "E" and not promote_ok

    out = {
        "schema": "eval.security_d26_promote_check.v1",
        "d26_status": status,
        "pilot_status": ev.get("status"),
        "d26_promote_allowed": promote_ok,
        "yaml_e_without_pilot": yaml_e_without_pilot,
        "ok": (not yaml_e_without_pilot)
        and (not args.propose_e or promote_ok),
        "security_certification": False,
        "honesty": (
            "Promotion requires dual-sign pilot exit with pinned samples. "
            "Do not edit YAML status to E alone."
        ),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
