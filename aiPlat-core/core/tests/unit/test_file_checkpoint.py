"""Tests for L1-D4: filesystem-level FileCheckpoint (Hermes physical safety net).

Covers:
  - checkpoint_file() stores content, dedups identical versions, skips large/missing
  - list/get/restore round-trip
  - disabled via env var
  - retention prune
  - auto-checkpoint wiring in sys_file_write / sys_file_edit
  - CoreFacade wrappers
"""

import pytest
import sys
import os

sys.path.insert(0, "aiPlat-core")

from core.harness.execution import file_checkpoint as fc


@pytest.fixture
def cp_env(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "CHECKPOINT_ROOT", str(tmp_path / "cp"))
    monkeypatch.setenv("AIPLAT_FILE_CHECKPOINT_ENABLED", "true")
    return tmp_path


class TestCheckpointFile:
    def test_missing_file_returns_none(self, cp_env):
        assert fc.checkpoint_file(str(cp_env / "nope.txt")) is None

    def test_stores_and_lists(self, cp_env):
        f = cp_env / "a.py"
        f.write_text("v1")
        cid = fc.checkpoint_file(str(f), session_id="s1", reason="test")
        assert cid
        items = fc.list_file_checkpoints(session_id="s1")
        assert len(items) == 1
        assert items[0]["reason"] == "test"
        assert items[0]["size"] == 2

    def test_dedup_identical_content(self, cp_env):
        f = cp_env / "a.py"
        f.write_text("same")
        c1 = fc.checkpoint_file(str(f), session_id="s1")
        c2 = fc.checkpoint_file(str(f), session_id="s1")  # unchanged → dedup
        assert c1 is not None
        assert c2 is None
        assert len(fc.list_file_checkpoints(session_id="s1")) == 1

    def test_new_version_creates_new_checkpoint(self, cp_env):
        f = cp_env / "a.py"
        f.write_text("v1")
        fc.checkpoint_file(str(f), session_id="s1")
        f.write_text("v2")
        fc.checkpoint_file(str(f), session_id="s1")
        assert len(fc.list_file_checkpoints(session_id="s1")) == 2

    def test_skips_large_file(self, cp_env, monkeypatch):
        monkeypatch.setattr(fc, "MAX_FILE_BYTES", 10)
        f = cp_env / "big.txt"
        f.write_text("x" * 100)
        assert fc.checkpoint_file(str(f), session_id="s1") is None

    def test_disabled_returns_none(self, cp_env, monkeypatch):
        monkeypatch.setenv("AIPLAT_FILE_CHECKPOINT_ENABLED", "false")
        f = cp_env / "a.py"
        f.write_text("v1")
        assert fc.checkpoint_file(str(f), session_id="s1") is None


class TestRestore:
    def test_restore_round_trip(self, cp_env):
        f = cp_env / "code.py"
        f.write_text("good version")
        cid = fc.checkpoint_file(str(f), session_id="s1")
        f.write_text("CORRUPTED")  # simulate a bad edit
        result = fc.restore_file_checkpoint(cid, session_id="s1")
        assert result["success"] is True
        assert f.read_text() == "good version"

    def test_restore_missing_checkpoint(self, cp_env):
        result = fc.restore_file_checkpoint("deadbeef", session_id="s1")
        assert result["success"] is False
        assert result["error"] == "checkpoint_not_found"

    def test_get_returns_content(self, cp_env):
        f = cp_env / "a.py"
        f.write_text("hello content")
        cid = fc.checkpoint_file(str(f), session_id="s1")
        got = fc.get_file_checkpoint(cid, session_id="s1")
        assert got["content"] == "hello content"


class TestPrune:
    def test_retention_bound(self, cp_env, monkeypatch):
        monkeypatch.setattr(fc, "MAX_CHECKPOINTS_PER_PATH", 3)
        f = cp_env / "a.py"
        for i in range(6):
            f.write_text(f"version-{i}")
            fc.checkpoint_file(str(f), session_id="s1")
        items = fc.list_file_checkpoints(session_id="s1")
        assert len(items) == 3  # pruned to newest 3


class TestSyscallWiring:
    @pytest.mark.asyncio
    async def test_sys_file_edit_auto_checkpoints(self, cp_env, monkeypatch):
        from core.harness.syscalls import file as fsys
        monkeypatch.chdir(cp_env)  # workspace root = cp_env
        fpath = str(cp_env / "prog.py")

        r1 = await fsys.sys_file_write(fpath, "def f(): return 1\n")
        assert r1["success"]
        r2 = await fsys.sys_file_edit(fpath, "return 1", "return 2")
        assert r2["success"]

        cps = fc.list_file_checkpoints()
        assert len(cps) >= 1
        assert any(c["reason"] == "sys_file_edit" for c in cps)


class TestFacade:
    def test_facade_list_get_restore(self, cp_env):
        from core.api import core_facade
        f = cp_env / "a.py"
        f.write_text("original")
        cid = fc.checkpoint_file(str(f), session_id="s1")
        assert core_facade.list_file_checkpoints(session_id="s1")
        assert core_facade.get_file_checkpoint(cid, "s1")["content"] == "original"
        f.write_text("bad")
        assert core_facade.restore_file_checkpoint(cid, "s1")["success"] is True
        assert f.read_text() == "original"
