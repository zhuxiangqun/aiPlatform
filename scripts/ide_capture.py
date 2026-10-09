#!/usr/bin/env python3
"""IDE/Cursor/CC bypass capture CLI — stdin JSON → Team Brain (+ optional Wiki).

Usage:
  echo '{"prompt":"fix auth","tools":["grep"],"result":"jwt check","success":true,"tags":["cursor"]}' \\
    | python3 scripts/ide_capture.py

  # Cursor / CC hooks.json command:
  #   python3 /path/to/aiPlatform/scripts/ide_capture.py --from-hook

Env:
  AIPLAT_CAPTURE_URL  — if set, POST JSON to this URL instead of in-process import
  AIPLAT_HOME         — shared_memory / learnings root
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict


def _read_payload(from_hook: bool) -> Dict[str, Any]:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"prompt": raw.strip()[:500], "result": "", "success": True, "source": "stdin"}

    if not isinstance(data, dict):
        return {"prompt": str(data)[:500], "success": True}

    # Cursor sessionEnd / stop hook shapes → normalize
    if from_hook:
        prompt = (
            data.get("prompt")
            or data.get("user_prompt")
            or data.get("last_prompt")
            or data.get("input")
            or ""
        )
        result = (
            data.get("result")
            or data.get("output")
            or data.get("assistant_message")
            or data.get("response")
            or data.get("summary")
            or ""
        )
        tools = data.get("tools") or data.get("tool_names") or []
        if isinstance(tools, str):
            tools = [tools]
        status = str(data.get("status") or data.get("outcome") or "").lower()
        success = data.get("success")
        if success is None:
            success = status not in ("error", "failed", "failure", "aborted")
        return {
            "prompt": str(prompt)[:2000],
            "result": str(result)[:4000],
            "tools": list(tools)[:20] if isinstance(tools, list) else [],
            "success": bool(success),
            "tags": data.get("tags") if isinstance(data.get("tags"), list) else ["hook"],
            "source": str(data.get("source") or "cursor_hook"),
            "session_id": str(data.get("session_id") or data.get("conversation_id") or ""),
            "write_wiki": bool(data.get("write_wiki", False)),
        }
    return data


def _post_http(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ingest_local(payload: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    core = root / "aiPlat-core"
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))
    from core.harness.memory.ide_capture import ingest_ide_capture

    return ingest_ide_capture(
        prompt=str(payload.get("prompt") or ""),
        result=str(payload.get("result") or ""),
        tools=payload.get("tools") if isinstance(payload.get("tools"), list) else None,
        success=bool(payload.get("success", True)),
        tags=payload.get("tags") if isinstance(payload.get("tags"), list) else None,
        source=str(payload.get("source") or "ide"),
        session_id=str(payload.get("session_id") or ""),
        write_wiki=bool(payload.get("write_wiki", False)),
    )


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="IDE capture → Team Brain")
    parser.add_argument("--from-hook", action="store_true", help="normalize Cursor/CC hook stdin JSON")
    parser.add_argument("--write-wiki", action="store_true", help="also write session wiki page")
    args = parser.parse_args(argv)

    payload = _read_payload(args.from_hook)
    if args.write_wiki:
        payload["write_wiki"] = True
    if not payload.get("prompt") and not payload.get("result"):
        print(json.dumps({"ok": False, "reason": "empty_stdin"}, ensure_ascii=False))
        return 1

    url = (os.environ.get("AIPLAT_CAPTURE_URL") or "").strip()
    try:
        out = _post_http(url, payload) if url else _ingest_local(payload)
    except (urllib.error.URLError, OSError, ImportError, Exception) as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "reason": str(e)[:300]}, ensure_ascii=False))
        return 2

    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
