"""Self-test for scripts/check_cost_ladder.py (E4 cost-ladder ratchet)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_cost_ladder.py"


@pytest.fixture(scope="module")
def ladder():
    spec = importlib.util.spec_from_file_location("check_cost_ladder", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_baselines_exist(ladder):
    assert ladder.SYSCALL_BASELINE.is_file()
    assert ladder.MCP_BASELINE.is_file()
    assert ladder.load_baseline(ladder.SYSCALL_BASELINE)


def test_scan_syscalls_nonempty(ladder):
    found = ladder.scan_syscalls()
    assert any(k.endswith(":sys_llm_generate") or "sys_llm_generate" in k for k in found) or len(found) >= 10


def test_check_clean_against_baseline(ladder):
    errors, _warnings = ladder.check(staged_only=False)
    assert errors == [], errors


def test_new_syscall_without_justification_fails(ladder, tmp_path, monkeypatch):
    """Simulate a new syscall key beyond baseline → error unless CAPABILITIES / ladder-ok."""
    fake_py = tmp_path / "fake_syscall.py"
    fake_py.write_text("async def sys_totally_new_ladder_test(x):\n    return x\n", encoding="utf-8")
    monkeypatch.setattr(ladder, "SYSCALL_ROOT", tmp_path)
    # Empty baseline → every scanned key is "new"
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setattr(ladder, "SYSCALL_BASELINE", empty)
    monkeypatch.setattr(ladder, "MCP_BASELINE", empty)
    monkeypatch.setattr(ladder, "MCP_SEED_DIRS", [])
    monkeypatch.setattr(ladder, "_caps_text", lambda: "")
    errors, _ = ladder.check(staged_only=False)
    assert any("sys_totally_new_ladder_test" in e for e in errors), errors


def test_ladder_ok_comment_allows_new(ladder, tmp_path, monkeypatch):
    fake_py = tmp_path / "ok_syscall.py"
    fake_py.write_text(
        "# ladder-ok: L6 — unit test fixture only\n"
        "async def sys_ladder_ok_fixture(x):\n"
        "    return x\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ladder, "SYSCALL_ROOT", tmp_path)
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setattr(ladder, "SYSCALL_BASELINE", empty)
    monkeypatch.setattr(ladder, "MCP_BASELINE", empty)
    monkeypatch.setattr(ladder, "MCP_SEED_DIRS", [])
    monkeypatch.setattr(ladder, "_caps_text", lambda: "")
    errors, warnings = ladder.check(staged_only=False)
    assert not any("sys_ladder_ok_fixture" in e for e in errors), errors
    assert any("sys_ladder_ok_fixture" in w for w in warnings)
