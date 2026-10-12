#!/usr/bin/env python3
"""Unit checks for coding_exec (no pi/Ollama required)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "coding_exec.py"


def _load():
    spec = importlib.util.spec_from_file_location("coding_exec", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--cwd",
                td,
                "--prompt",
                "noop",
                "--model",
                "ollama/x",
            ],
            capture_output=True,
            text=True,
        )
        data = json.loads(proc.stdout or "{}")
        assert proc.returncode != 0, data
        assert "host cwd refused" in str(data.get("error", "")), data

    mod = _load()
    built = mod.build_pi_cmd(
        pi_bin="pi", model="ollama/qwen2.5:3b", prompt="hi", extension=None
    )
    assert built[0] == "pi"
    assert "-p" in built
    assert "read,write,edit,bash" in built
    print("PASS: coding_exec unit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
