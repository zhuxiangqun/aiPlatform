#!/usr/bin/env python3
"""Validate Wave3+ evidence cards (JSON schema-lite; ≠ certification).

Required top-level fields:
  schema, wave, card_id, environment, result, recorded_at_utc, security_certification

result ∈ {pass, fail, unknown, pending}
security_certification must be false
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ALLOWED_RESULTS = frozenset({"pass", "fail", "unknown", "pending"})
REQUIRED = (
    "schema",
    "wave",
    "card_id",
    "environment",
    "result",
    "recorded_at_utc",
    "security_certification",
)


def validate_card(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for key in REQUIRED:
        if key not in payload:
            errors.append(f"missing:{key}")
    if payload.get("security_certification") is not False:
        errors.append("security_certification_must_be_false")
    result = payload.get("result")
    if result is not None and result not in ALLOWED_RESULTS:
        errors.append(f"bad_result:{result}")
    wave = payload.get("wave")
    if wave is not None and not isinstance(wave, int):
        errors.append("wave_must_be_int")
    return errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate security evidence cards")
    parser.add_argument("--validate", required=True, help="Path to card JSON")
    args = parser.parse_args(argv)
    path = Path(args.validate)
    if not path.is_file():
        print(json.dumps({"ok": False, "error": f"missing:{path}"}))
        return 1
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"json:{exc}"}))
        return 1
    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "error": "not_object"}))
        return 1
    errors = validate_card(payload)
    out = {
        "ok": not errors,
        "path": str(path),
        "errors": errors,
        "security_certification": False,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
