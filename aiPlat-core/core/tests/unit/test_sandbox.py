"""Tests for sandbox.py — process isolation for pipeline stages."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "aiPlat-core"))

import pytest

from core.harness.execution.sandbox import (
    SandboxResult, StageSandbox, _SIGNAL_NAMES
)


class TestSandboxResult:
    def test_result_construction(self):
        r = SandboxResult(success=True, output="hello", error="", exit_code=0)
        assert r.success is True
        assert r.output == "hello"

    def test_result_failure(self):
        r = SandboxResult(success=False, output="", error="timeout", exit_code=124)
        assert r.success is False
        assert r.error == "timeout"

    def test_result_elapsed(self):
        r = SandboxResult(success=True, output="ok", elapsed_seconds=5.2)
        assert r.elapsed_seconds == 5.2


class TestStageSandbox:
    def test_default_config(self):
        sb = StageSandbox()
        assert sb._timeout == 600
        assert sb._memory_limit_mb == 1024
        assert sb._max_processes == 100

    def test_custom_timeout(self):
        sb = StageSandbox(timeout_seconds=30)
        assert sb._timeout == 30

    def test_custom_memory(self):
        sb = StageSandbox(memory_limit_mb=512)
        assert sb._memory_limit_mb == 512

    def test_signal_names_populated(self):
        assert len(_SIGNAL_NAMES) >= 4
        assert any("CPU" in v for v in _SIGNAL_NAMES.values())

    def test_stderr_default(self):
        r = SandboxResult(success=False, output="err", stderr="traceback")
        assert "traceback" in r.stderr
