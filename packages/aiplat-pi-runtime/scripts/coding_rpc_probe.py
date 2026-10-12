#!/usr/bin/env python3
"""Way-4 factory-in probe: Pi RPC coding executor (opt-in, not wired to engine).

Modes:
  --dry-run   Start pi RPC, get_state, shutdown (no LLM turn)
  --live      Optional prompt turn (needs model + credentials / Ollama)

Sandbox: cwd must be under TMPDIR or AIPLAT_PI_CODING_SANDBOX_ROOT unless
AIPLAT_PI_CODING_ALLOW_HOST=1.

Examples:
  python3 packages/aiplat-pi-runtime/scripts/coding_rpc_probe.py --dry-run
  AIPLAT_PI_MODEL=ollama/qwen2.5:3b \\
    python3 packages/aiplat-pi-runtime/scripts/coding_rpc_probe.py --live \\
    --message 'Reply with exactly AIPLAT_PI_RPC_OK'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from pi_rpc_client import (  # noqa: E402
    PiRpcError,
    PiRpcSession,
    assert_sandbox_cwd,
    resolve_pi_bin,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Pi RPC coding probe (factory-in experiment)")
    ap.add_argument("--dry-run", action="store_true", help="get_state only, no LLM")
    ap.add_argument("--live", action="store_true", help="send one prompt and wait")
    ap.add_argument("--cwd", default="", help="working dir (default: temp sandbox)")
    ap.add_argument("--message", default="Reply with exactly AIPLAT_PI_RPC_OK and nothing else.")
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()

    if not args.dry_run and not args.live:
        ap.error("specify --dry-run and/or --live")

    try:
        pi_bin = resolve_pi_bin()
    except PiRpcError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 2

    tmp_owner = None
    if args.cwd:
        cwd = assert_sandbox_cwd(args.cwd)
    else:
        tmp_owner = tempfile.TemporaryDirectory(prefix="aiplat-pi-coding-")
        cwd = assert_sandbox_cwd(tmp_owner.name)
        # Minimal file so coding tools have something to see
        Path(cwd, "README.txt").write_text("aiPlat Pi coding sandbox probe\n", encoding="utf-8")

    model = (os.environ.get("AIPLAT_PI_MODEL") or "").strip()
    print(f"pi={pi_bin}")
    print(f"cwd={cwd}")
    print(f"model={model or '(unset)'}")

    try:
        with PiRpcSession(cwd=cwd, model=model) as session:
            if args.dry_run:
                rec = session.command({"type": "get_state"}, timeout_s=30.0)
                data = rec.get("data") if isinstance(rec.get("data"), dict) else {}
                print("PASS: dry-run get_state")
                print(json.dumps({"keys": sorted(data.keys())[:20], "success": rec.get("success")}, ensure_ascii=False))

            if args.live:
                if not model:
                    print("FAIL: --live requires AIPLAT_PI_MODEL", file=sys.stderr)
                    return 2
                result = session.prompt_and_wait(args.message, timeout_s=args.timeout)
                if not result.ok:
                    print(f"FAIL: live prompt: {result.error}", file=sys.stderr)
                    return 1
                print(f"PASS: live settled elapsed_ms={result.elapsed_ms}")
                print(result.text[:2000] if result.text else "(empty text)")
                if "AIPLAT_PI_RPC_OK" in args.message and "AIPLAT_PI_RPC_OK" not in result.text:
                    print("WARN: expected token AIPLAT_PI_RPC_OK not in assistant text", file=sys.stderr)
                    return 1
    except PiRpcError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    finally:
        if tmp_owner is not None:
            tmp_owner.cleanup()

    print("PASS: coding_rpc_probe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
