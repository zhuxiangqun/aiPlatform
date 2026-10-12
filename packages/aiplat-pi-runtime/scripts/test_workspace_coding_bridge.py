#!/usr/bin/env python3
"""Unit checks for workspace_coding_bridge (no pi/Ollama required)."""
from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "python" / "workspace_coding_bridge.py"


def _load():
    spec = importlib.util.spec_from_file_location("workspace_coding_bridge", BRIDGE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()

    # Default: flag off
    os.environ.pop("AIPLAT_PI_CODING_EXECUTOR", None)
    assert mod.is_enabled() is False
    skipped = mod.run_workspace_coding_via_pi(prompt="noop")
    assert skipped.get("skipped") is True, skipped
    assert skipped.get("ok") is False, skipped
    assert skipped.get("reason") == "disabled", skipped

    # Sandbox: without ALLOW_HOST, preferred_cwd is ignored → temp under TMPDIR/root
    os.environ.pop("AIPLAT_PI_CODING_ALLOW_HOST", None)
    with tempfile.TemporaryDirectory() as td:
        os.environ["AIPLAT_PI_CODING_SANDBOX_ROOT"] = td
        cwd = mod.resolve_coding_cwd(preferred_cwd="/tmp")
        assert str(cwd).startswith(td), (cwd, td)
        assert cwd.is_dir()

    # ALLOW_HOST + valid preferred_cwd → use preferred
    with tempfile.TemporaryDirectory() as host_td:
        os.environ["AIPLAT_PI_CODING_ALLOW_HOST"] = "1"
        cwd = mod.resolve_coding_cwd(preferred_cwd=host_td)
        assert Path(cwd).resolve() == Path(host_td).resolve(), (cwd, host_td)

        # ALLOW_HOST but empty preferred → still temp sandbox
        os.environ["AIPLAT_PI_CODING_SANDBOX_ROOT"] = host_td
        cwd2 = mod.resolve_coding_cwd(preferred_cwd="")
        assert str(cwd2).startswith(host_td), cwd2
        assert Path(cwd2).resolve() != Path(host_td).resolve()

    os.environ.pop("AIPLAT_PI_CODING_ALLOW_HOST", None)
    os.environ.pop("AIPLAT_PI_CODING_SANDBOX_ROOT", None)
    os.environ.pop("AIPLAT_PI_CODING_EXECUTOR", None)
    print("PASS: workspace_coding_bridge unit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
