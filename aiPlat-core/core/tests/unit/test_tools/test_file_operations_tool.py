import os

import pytest


@pytest.mark.asyncio
async def test_file_operations_read_dedup_and_mtime_guard(tmp_path, monkeypatch):
    from core.apps.tools.base import FileOperationsTool

    root = tmp_path / "repo"
    root.mkdir()
    p = root / "a.txt"
    p.write_text("hello", encoding="utf-8")

    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS", str(root))
    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOW_WRITE", "true")

    tool = FileOperationsTool()

    r1 = await tool.execute({"operation": "read", "path": str(p), "max_bytes": 1000})
    assert r1.success is True
    assert r1.output == "hello"
    assert r1.metadata.get("cache_hit") is False
    mtime1 = r1.metadata.get("mtime")
    assert isinstance(mtime1, float)

    r2 = await tool.execute({"operation": "read", "path": str(p), "max_bytes": 1000})
    assert r2.success is True
    assert r2.metadata.get("cache_hit") is True

    # write with expected mtime ok
    r3 = await tool.execute({"operation": "write", "path": str(p), "content": "world", "expected_mtime": mtime1})
    assert r3.success is True

    # second write with stale mtime should fail
    r4 = await tool.execute({"operation": "write", "path": str(p), "content": "x", "expected_mtime": mtime1})
    assert r4.success is False
    assert "mtime mismatch" in (r4.error or "")


@pytest.mark.asyncio
async def test_file_operations_binary_refused_by_default(tmp_path, monkeypatch):
    from core.apps.tools.base import FileOperationsTool

    root = tmp_path / "repo"
    root.mkdir()
    p = root / "bin.dat"
    p.write_bytes(b"\x00\x01\x02binary")

    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS", str(root))

    tool = FileOperationsTool()
    r = await tool.execute({"operation": "read", "path": str(p), "max_bytes": 1000})
    assert r.success is False
    assert "binary" in (r.error or "")

    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOW_BINARY_READ", "true")
    r2 = await tool.execute({"operation": "read", "path": str(p), "max_bytes": 1000})
    # read_text(errors=replace) will produce a string; just ensure it succeeds
    assert r2.success is True


@pytest.mark.asyncio
async def test_file_operations_denylist_segments(tmp_path, monkeypatch):
    from core.apps.tools.base import FileOperationsTool

    root = tmp_path / "repo"
    root.mkdir()
    secret_dir = root / ".ssh"
    secret_dir.mkdir()
    p = secret_dir / "id_rsa"
    p.write_text("secret", encoding="utf-8")

    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS", str(root))
    tool = FileOperationsTool()
    r = await tool.execute({"operation": "read", "path": str(p), "max_bytes": 1000})
    assert r.success is False
    assert "denied" in (r.error or "").lower()

    # override denylist to allow .ssh (not recommended, but for policy flexibility)
    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_DENYLIST_SEGMENTS", ".git")
    r2 = await tool.execute({"operation": "read", "path": str(p), "max_bytes": 1000})
    assert r2.success is True

    # cleanup env for other tests
    os.environ.pop("AIPLAT_FILE_OPERATIONS_DENYLIST_SEGMENTS", None)

