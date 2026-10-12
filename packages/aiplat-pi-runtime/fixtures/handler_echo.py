#!/usr/bin/env python3
"""Phase 0 / 1b smoke handler: JSON stdin → JSON stdout.

Protocol:
  stdin:  {"skill": "<name>", "params": {...}}
  stdout: {"ok": true, "result": {...}}  exit 0
          {"ok": false, "error": "..."}  exit != 0
"""
from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"invalid_json: {exc}"}, ensure_ascii=False))
        return 2
    skill = str(data.get("skill") or "")
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    out = {
        "ok": True,
        "result": {
            "echo": True,
            "skill": skill,
            "params": params,
            "marker": "AIPLAT_HANDLER_ECHO_OK",
        },
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
