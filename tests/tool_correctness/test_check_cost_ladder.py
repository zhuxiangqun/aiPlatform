"""Self-test for scripts/check_cost_ladder.py (E4/O1 cost-ladder ratchet)."""

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
        "# ladder-ok: L6 — unit test fixture only, rungs 1-5 infeasible\n"
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


def test_short_ladder_ok_rejected(ladder, tmp_path, monkeypatch):
    fake_py = tmp_path / "short_ok.py"
    fake_py.write_text(
        "# ladder-ok: too short\n"
        "async def sys_short_ladder(x):\n"
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
    errors, _ = ladder.check(staged_only=False)
    assert any("sys_short_ladder" in e for e in errors), errors


def test_caps_name_alone_insufficient(ladder, tmp_path, monkeypatch):
    fake_py = tmp_path / "caps_only.py"
    fake_py.write_text(
        "async def sys_caps_only_fixture(x):\n    return x\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ladder, "SYSCALL_ROOT", tmp_path)
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setattr(ladder, "SYSCALL_BASELINE", empty)
    monkeypatch.setattr(ladder, "MCP_BASELINE", empty)
    monkeypatch.setattr(ladder, "MCP_SEED_DIRS", [])
    monkeypatch.setattr(ladder, "_caps_text", lambda: "sys_caps_only_fixture mentioned")
    errors, _ = ladder.check(staged_only=False)
    assert any("sys_caps_only_fixture" in e for e in errors), errors


def test_proof_template_allows_new(ladder, tmp_path, monkeypatch):
    proof = """
why_not_1_extend: cannot extend existing file tool — needs multi-vendor protocol surface
why_not_2_cli:    CLI+SOP cannot expose dynamic tool discovery to third-party agents
why_not_3_tool:   thin Tool would duplicate dozens of remote methods and break updates
why_not_4_plugin: plugins cannot ship shared protocol client used by multiple tenants
rung:             Syscall
blast_radius:     failure blocks agent tool path; token cost high; permission via PolicyGate
"""
    fake_py = tmp_path / "proof_syscall.py"
    fake_py.write_text(
        proof + "\nasync def sys_proof_template_fixture(x):\n    return x\n",
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
    assert not any("sys_proof_template_fixture" in e for e in errors), errors
    assert any("sys_proof_template_fixture" in w for w in warnings)


def test_temporary_ladder_ok_expired(ladder, tmp_path, monkeypatch):
    fake_py = tmp_path / "temp_ok.py"
    fake_py.write_text(
        "# ladder-ok: temporary until 2020-01-01 — emergency bridge for incident\n"
        "async def sys_temp_expired(x):\n"
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
    errors, _ = ladder.check(staged_only=False)
    assert any("sys_temp_expired" in e for e in errors), errors


def test_parse_ladder_ok_helpers(ladder):
    ok, err = ladder.parse_ladder_ok("# ladder-ok: enough characters here for gate")
    assert ok and not err
    ok, err = ladder.parse_ladder_ok("# ladder-ok: short")
    assert not ok
