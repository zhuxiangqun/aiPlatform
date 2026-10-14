#!/usr/bin/env python3
"""Factory-in way4 merge-close evidence smoke.

Proves §⓪ disposition (2026-10-14 blank_not_proven):

1. core_facade no longer wires Workspace Execute → Pi bridge
2. Offline bridge still defaults OFF / sandbox cwd
3. coding_exec refuses host cwd without --allow-host
4. PolicyGate not owned by bridge module
5. coding_rpc_probe --dry-run PASS (archived offline tool)

Does NOT mark CAPABILITIES 「厂内已接线」.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PKG = Path(__file__).resolve().parents[1]
BRIDGE = PKG / "python" / "workspace_coding_bridge.py"
FACADE = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
CODING_EXEC = PKG / "scripts" / "coding_exec.py"
PROBE = PKG / "scripts" / "coding_rpc_probe.py"


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _pass(msg: str) -> None:
    print(f"PASS: {msg}")


def _load_bridge():
    import importlib.util

    spec = importlib.util.spec_from_file_location("aiplat_workspace_coding_bridge", BRIDGE)
    if spec is None or spec.loader is None:
        _fail(f"cannot load bridge: {BRIDGE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    for k in (
        "AIPLAT_PI_CODING_EXECUTOR",
        "AIPLAT_PI_CODING_ALLOW_HOST",
        "AIPLAT_PI_CODING_SANDBOX_ROOT",
    ):
        os.environ.pop(k, None)

    if not BRIDGE.is_file():
        _fail(f"missing {BRIDGE}")
    if not FACADE.is_file():
        _fail(f"missing {FACADE}")

    # 1) merge-close: facade must NOT call Pi coding bridge
    facade = FACADE.read_text(encoding="utf-8")
    for banned in (
        "run_workspace_coding_via_pi",
        "workspace_coding_bridge",
        "AIPLAT_PI_CODING_EXECUTOR",
    ):
        if banned in facade:
            _fail(f"core_facade still references {banned} (expected merge-closed)")
    if "merge-closed" not in facade and "FACTORY_IN_EXPERIMENT" not in facade:
        _fail("core_facade missing merge-close comment pointing at FACTORY_IN_EXPERIMENT")
    _pass("core_facade Workspace Execute Pi bypass removed (merge-closed)")

    mod = _load_bridge()

    # 2) offline bridge still defaults OFF
    if mod.is_enabled():
        _fail("is_enabled() true with AIPLAT_PI_CODING_EXECUTOR unset")
    skipped = mod.run_workspace_coding_via_pi(prompt="noop")
    if not skipped.get("skipped") or skipped.get("reason") != "disabled":
        _fail(f"expected skipped/disabled, got {skipped}")
    _pass("offline bridge flag default OFF → skipped")

    # 3) sandbox cwd (no ALLOW_HOST)
    preferred = str(Path.home())
    cwd = mod.resolve_coding_cwd(preferred)
    if str(cwd.resolve()) == str(Path(preferred).resolve()):
        _fail(f"sandbox leaked preferred host cwd: {cwd}")
    if not cwd.is_dir() or not cwd.name.startswith("aiplat_pi_coding_"):
        _fail(f"unexpected sandbox cwd: {cwd}")
    _pass(f"sandbox cwd (not host preferred): {cwd}")

    # 4) coding_exec refuses without --allow-host
    with tempfile.TemporaryDirectory(prefix="aiplat_factory_host_") as td:
        proc = subprocess.run(
            [
                sys.executable,
                str(CODING_EXEC),
                "--cwd",
                td,
                "--prompt",
                "echo factory_in_evidence",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            _fail("coding_exec allowed host cwd without --allow-host")
        _pass("coding_exec refused host cwd without --allow-host")

    # 5) PolicyGate outside bridge
    bridge_src = BRIDGE.read_text(encoding="utf-8")
    if "PolicyGate" in bridge_src or "policy_gate" in bridge_src:
        _fail("bridge must not import/own PolicyGate (outer layer only)")
    if "get_policy_gate" not in facade and "PolicyGate" not in facade:
        _fail("core_facade missing PolicyGate surface (outer gate)")
    _pass("PolicyGate stays outside archived Pi coding bridge")

    # 6) RPC dry-run (archived offline tool)
    if not PROBE.is_file():
        _fail(f"missing {PROBE}")
    probe = subprocess.run(
        [sys.executable, str(PROBE), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )
    if probe.returncode != 0:
        _fail(f"coding_rpc_probe --dry-run failed: {probe.stderr or probe.stdout}")
    if "PASS: dry-run get_state" not in (probe.stdout or ""):
        _fail(f"dry-run missing PASS marker: {probe.stdout}")
    _pass("coding_rpc_probe --dry-run")

    print("AIPLAT_FACTORY_IN_MERGE_CLOSE_SMOKE_OK")
    print("NOTE: merge-closed — do not mark CAPABILITIES 厂内已接线")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
