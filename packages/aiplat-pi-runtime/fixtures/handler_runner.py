#!/usr/bin/env python3
"""Wrap skill-dir handler.py execute(params) → JSON stdin/stdout protocol."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import sys
from pathlib import Path

_SKILL_DIR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")


def _load_execute(handler_path: Path):
    spec = importlib.util.spec_from_file_location("aiplat_handler", handler_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {handler_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "execute", None)
    if fn is None:
        raise RuntimeError("handler.py missing top-level execute()")
    return fn


async def _run(fn, params: dict):
    result = fn(params)
    if asyncio.iscoroutine(result):
        result = await result
    return result


def main() -> int:
    handler_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("handler.py").resolve()
    # Only skills/<safe-name>/handler.py — never fixtures/ or arbitrary trees.
    if (
        handler_path.name != "handler.py"
        or handler_path.parent.parent.name != "skills"
        or not _SKILL_DIR.fullmatch(handler_path.parent.name)
    ):
        print(
            json.dumps({"ok": False, "error": "handler path refused"}, ensure_ascii=False),
        )
        return 2
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        fn = _load_execute(handler_path)
        result = asyncio.run(_run(fn, params))
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, default=str))
        return 0
    except Exception as exc:  # noqa: broad — protocol boundary
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
