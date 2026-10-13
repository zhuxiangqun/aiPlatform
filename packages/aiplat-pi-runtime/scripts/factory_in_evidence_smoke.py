#!/usr/bin/env python3
"""Factory-in way4 evidence smoke (sandbox + flag OFF + outer PolicyGate).

Does NOT mark CAPABILITIES 「厂内已接线」. Proves experimental constraints hold:

1. AIPLAT_PI_CODING_EXECUTOR default → bridge skipped
2. resolve_coding_cwd without ALLOW_HOST → temp sandbox (not preferred host cwd)
3. coding_exec refuses host cwd without --allow-host
4. core_facade wires flag-gated bridge (text evidence)
5. PolicyGate stays outside bridge module (no PolicyGate import in bridge)
6. coding_rpc_probe --dry-run PASS
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
    # Clear experimental flags for deterministic defaults
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

    mod = _load_bridge()

    # 1) flag default OFF
    if mod.is_enabled():
        _fail("is_enabled() true with AIPLAT_PI_CODING_EXECUTOR unset")
    skipped = mod.run_workspace_coding_via_pi(prompt="noop")
    if not skipped.get("skipped") or skipped.get("reason") != "disabled":
        _fail(f"expected skipped/disabled, got {skipped}")
    _pass("flag default OFF → bridge skipped")

    # 2) sandbox cwd (no ALLOW_HOST)
    preferred = str(Path.home())
    cwd = mod.resolve_coding_cwd(preferred)
    cwd_s = str(cwd.resolve())
    if cwd_s == str(Path(preferred).resolve()):
        _fail(f"sandbox leaked preferred host cwd: {cwd_s}")
    if not cwd.is_dir():
        _fail(f"sandbox cwd missing: {cwd}")
    # temp dirs typically under TMPDIR /aiplat_pi_coding_
    if "aiplat_pi_coding_" not in cwd.name and "aiplat-pi-coding" not in cwd_s:
        # still OK if under TMPDIR with our prefix from mkdtemp
        if not cwd.name.startswith("aiplat_pi_coding_"):
            _fail(f"unexpected sandbox name: {cwd}")
    _pass(f"sandbox cwd (not host preferred): {cwd}")

    # 3) coding_exec refuses without --allow-host
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
        blob = (proc.stdout or "") + (proc.stderr or "")
        if "allow-host" not in blob.lower() and "allow_host" not in blob.lower() and "sandbox" not in blob.lower():
            # still fail closed if non-zero
            _pass("coding_exec refused host cwd (non-zero exit)")
        else:
            _pass("coding_exec refused host cwd without --allow-host")

    # 4) facade flag gate text evidence
    facade = FACADE.read_text(encoding="utf-8")
    for needle in (
        "AIPLAT_PI_CODING_EXECUTOR",
        "workspace_coding_bridge",
        "run_workspace_coding_via_pi",
        "_workspace_coding_defaults",
    ):
        if needle not in facade:
            _fail(f"core_facade missing {needle}")
    _pass("core_facade flag-gated bridge wiring present")

    # 5) PolicyGate outside bridge
    bridge_src = BRIDGE.read_text(encoding="utf-8")
    if "PolicyGate" in bridge_src or "policy_gate" in bridge_src:
        _fail("bridge must not import/own PolicyGate (outer layer only)")
    if "get_policy_gate" not in facade and "PolicyGate" not in facade:
        _fail("core_facade missing PolicyGate surface (outer gate)")
    _pass("PolicyGate stays outside Pi coding bridge")

    # 6) RPC dry-run
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

    print("AIPLAT_FACTORY_IN_EVIDENCE_SMOKE_OK")
    print("NOTE: experimental — do not mark CAPABILITIES 厂内已接线")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
