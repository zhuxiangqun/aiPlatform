#!/usr/bin/env python3
"""Factory-in experiment (way 4): optional Pi print-mode coding exec.

NOT the default coding_closed_loop path. Does not replace ReActLoop / PolicyGate.

Usage:
  AIPLAT_PI_MODEL=ollama/qwen2.5:3b \\
    python3 packages/aiplat-pi-runtime/scripts/coding_exec.py \\
      --cwd /tmp/work --prompt "Create hello.txt with hi" --allow-host

Safety:
  - Refuses host cwd unless --allow-host or AIPLAT_PI_CODING_ALLOW_HOST=1
  - Prefer running inside your own Docker/sandbox and pass that cwd
  - PolicyGate / done_verify must wrap this from aiPlat (caller responsibility)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def resolve_pi_bin() -> str:
    override = (os.getenv("AIPLAT_PI_BIN") or "").strip()
    if override:
        return override
    found = shutil.which("pi")
    if found:
        return found
    raise FileNotFoundError("pi CLI not found on PATH (set AIPLAT_PI_BIN)")


def build_pi_cmd(
    *,
    pi_bin: str,
    model: str,
    prompt: str,
    extension: Optional[str] = None,
) -> List[str]:
    cmd = [
        pi_bin,
        "-p",
        "--no-session",
        "--mode",
        "text",
        "--model",
        model,
        "--no-builtin-tools",
        "-t",
        "read,write,edit,bash",
    ]
    if extension:
        cmd.extend(["-e", extension])
    cmd.append(prompt)
    return cmd


def run_coding_exec(
    *,
    cwd: Path,
    prompt: str,
    model: str,
    allow_host: bool = False,
    extension: Optional[str] = None,
    timeout_sec: int = 300,
) -> Dict[str, Any]:
    cwd = cwd.resolve()
    if not cwd.is_dir():
        return {"ok": False, "error": f"cwd not a directory: {cwd}"}

    if not allow_host and not _env_truthy("AIPLAT_PI_CODING_ALLOW_HOST"):
        return {
            "ok": False,
            "error": (
                "host cwd refused — pass --allow-host for local experiment, "
                "or set AIPLAT_PI_CODING_ALLOW_HOST=1 after isolating the workdir "
                "(Docker/sandbox). PolicyGate must wrap this caller-side."
            ),
            "cwd": str(cwd),
        }

    if not model.strip():
        return {"ok": False, "error": "AIPLAT_PI_MODEL / --model required"}

    try:
        pi_bin = resolve_pi_bin()
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    cmd = build_pi_cmd(
        pi_bin=pi_bin, model=model.strip(), prompt=prompt, extension=extension
    )
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env={**os.environ},
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout_sec}s", "cwd": str(cwd)}
    except OSError as e:
        return {"ok": False, "error": f"spawn failed: {e}", "cwd": str(cwd)}

    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "cwd": str(cwd),
        "model": model.strip(),
        "text": out.strip(),
        "cmd": cmd[:-1] + ["<prompt>"],
        "executor": "pi_print",
        "experiment": "factory_in_way4",
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Optional Pi coding exec (factory-in way 4)")
    p.add_argument("--cwd", required=True, help="Working directory for pi tools")
    p.add_argument("--prompt", required=True, help="Coding task prompt")
    p.add_argument(
        "--model",
        default=os.getenv("AIPLAT_PI_MODEL", "").strip(),
        help="provider/id (default AIPLAT_PI_MODEL)",
    )
    p.add_argument(
        "--extension",
        default="",
        help="Optional pi -e path (export package or aiplat-pi-runtime)",
    )
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument(
        "--allow-host",
        action="store_true",
        help="Allow running against host cwd (experiment only)",
    )
    args = p.parse_args(argv)

    result = run_coding_exec(
        cwd=Path(args.cwd),
        prompt=args.prompt,
        model=args.model,
        allow_host=bool(args.allow_host),
        extension=(args.extension or None),
        timeout_sec=int(args.timeout),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
