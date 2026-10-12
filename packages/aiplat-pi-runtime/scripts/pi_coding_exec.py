#!/usr/bin/env python3
"""Factory-in way-4 helper: run one Pi print-mode coding turn in a workdir.

Opt-in only. Does **not** replace StageRunner/ReActLoop or PolicyGate.
Callers must place PolicyGate / done_verify / review_gate **outside** this process
and run against a sandboxed cwd (temp dir / container mount), never bare prod roots.

Env:
  AIPLAT_PI_MODEL   provider/id (default ollama/qwen2.5:3b)
  AIPLAT_PI_BIN     path to `pi` (default: PATH lookup)

Exit: 0 on success; non-zero on failure. Prints Pi stdout/stderr to this process.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def resolve_pi_bin() -> str:
    override = (os.environ.get("AIPLAT_PI_BIN") or "").strip()
    if override:
        return override
    found = shutil.which("pi")
    if not found:
        raise SystemExit("pi CLI not found (install @earendil-works/pi-coding-agent or set AIPLAT_PI_BIN)")
    return found


def run_coding_turn(
    *,
    cwd: Path,
    prompt: str,
    model: str,
    timeout_s: float,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cwd = cwd.resolve()
    if not cwd.is_dir():
        raise SystemExit(f"cwd not a directory: {cwd}")
    pi = resolve_pi_bin()
    cmd = [
        pi,
        "-p",
        "--no-session",
        "--mode",
        "text",
        "--model",
        model,
        *(extra_args or []),
        prompt,
    ]
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        env={**os.environ},
        check=False,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cwd", required=True, help="Sandboxed working directory for Pi")
    p.add_argument("--prompt", required=True, help="Coding task for one print-mode turn")
    p.add_argument(
        "--model",
        default=(os.environ.get("AIPLAT_PI_MODEL") or "ollama/qwen2.5:3b").strip(),
        help="provider/id model spec",
    )
    p.add_argument("--timeout", type=float, default=180.0)
    p.add_argument(
        "--expect",
        default="",
        help="If set, require this substring in combined stdout+stderr",
    )
    args = p.parse_args(argv)

    try:
        proc = run_coding_turn(
            cwd=Path(args.cwd),
            prompt=args.prompt,
            model=args.model,
            timeout_s=args.timeout,
        )
    except subprocess.TimeoutExpired:
        print("FAIL: pi coding turn timed out", file=sys.stderr)
        return 2

    out = (proc.stdout or "") + (proc.stderr or "")
    sys.stdout.write(proc.stdout or "")
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        print(f"FAIL: pi exit {proc.returncode}", file=sys.stderr)
        return proc.returncode or 1
    if args.expect and args.expect not in out:
        print(f"FAIL: expected substring missing: {args.expect!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
