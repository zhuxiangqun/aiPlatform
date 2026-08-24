"""P0-b Claude Code 会话/记忆导入测试。

解析器单测（真实 JSONL 格式）+ 导入集成（fake MemoryManager）。
"""

import json

import pytest

from core.harness.memory.import_claude_sessions import (
    _extract_text,
    find_claude_sessions,
    import_claude_sessions,
    parse_claude_session,
)


def _session_line(rec_type: str, content, ts: str = "2026-03-19T17:46:19.467Z"):
    return json.dumps({"type": rec_type, "timestamp": ts, "content": content})


@pytest.fixture
def session_file(tmp_path):
    p = tmp_path / "ses_test123.jsonl"
    lines = [
        _session_line("user", "build an auth module"),
        _session_line("assistant", "I'll create auth.py with JWT support"),
        _session_line("user", [{"type": "text", "text": "add refresh tokens"}],
                      ts="2026-03-19T17:50:00.000Z"),
        _session_line("assistant", "Added refresh token rotation"),
        # 系统噪音（应跳过）
        _session_line("user", "<system-reminder>\n\n[SYSTEM DIRECTIVE: SINGLE TASK]"),
        # 连续 user（应丢弃前一个无响应的）
        _session_line("user", "orphan question"),
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


# ── 解析器 ────────────────────────────────────────────────────

def test_extract_text_string():
    assert _extract_text("hello") == "hello"


def test_extract_text_block_list():
    content = [{"type": "text", "text": "hi"}, {"type": "tool_use", "name": "Bash"},
               {"type": "tool_result", "content": "output"}]
    text = _extract_text(content)
    assert "hi" in text
    assert "[tool: Bash]" in text
    assert "[tool_result: output]" in text


def test_extract_text_none():
    assert _extract_text(None) == ""


def test_parse_claude_session_basic(session_file):
    turns = parse_claude_session(session_file)
    # 2 个完整轮次（user+assistant 配对）；系统噪音跳过；孤儿 user 丢弃
    assert len(turns) == 2
    assert turns[0].user_text == "build an auth module"
    assert "JWT" in turns[0].assistant_text
    assert turns[1].user_text == "add refresh tokens"
    assert "rotation" in turns[1].assistant_text
    assert turns[0].source_file == str(session_file)
    assert turns[0].session_id == "ses_test123"


def test_parse_claude_session_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_claude_session(tmp_path / "nope.jsonl")


def test_parse_claude_session_bad_json(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text("{not json}\n" + _session_line("user", "valid") + "\n" +
                 _session_line("assistant", "ok"), encoding="utf-8")
    turns = parse_claude_session(p)
    assert len(turns) == 1  # 坏行跳过，好行正常配对


# ── 查找 ──────────────────────────────────────────────────────

def test_find_claude_sessions(tmp_path):
    d = tmp_path / "projects"
    d.mkdir()
    (d / "a.jsonl").write_text("", encoding="utf-8")
    (d / "b.jsonl").write_text("", encoding="utf-8")
    found = find_claude_sessions(str(d))
    assert len(found) == 2


# ── 导入集成 ──────────────────────────────────────────────────

class FakeMemoryManager:
    def __init__(self):
        self.saved = []

    async def save_interaction(self, user_message, assistant_message, stability="medium",
                               is_critical=False, session_id=None, metadata=None):
        self.saved.append({
            "user": user_message, "assistant": assistant_message,
            "session_id": session_id, "metadata": metadata,
        })


@pytest.mark.asyncio
async def test_import_claude_sessions(session_file, tmp_path):
    mm = FakeMemoryManager()
    result = await import_claude_sessions(mm, session_files=[session_file], max_sessions=10)
    assert result["imported"] == 1
    assert result["sessions"] == 1
    assert result["turns"] == 2
    assert result["errors"] == []
    assert len(mm.saved) == 2
    first = mm.saved[0]
    assert first["user"] == "build an auth module"
    assert first["session_id"] == "claude:ses_test123"
    assert first["metadata"]["source"] == "claude_import"
    assert first["metadata"]["provenance"].startswith("claude:")


@pytest.mark.asyncio
async def test_import_claude_sessions_error_isolation(tmp_path):
    mm = FakeMemoryManager()
    missing = tmp_path / "missing.jsonl"
    result = await import_claude_sessions(mm, session_files=[missing])
    assert result["imported"] == 0
    assert len(result["errors"]) == 1  # 单会话失败不抛整体


@pytest.mark.asyncio
async def test_import_empty_session_is_skipped(tmp_path):
    mm = FakeMemoryManager()
    p = tmp_path / "empty.jsonl"
    p.write_text(_session_line("user", "only user no assistant"), encoding="utf-8")
    result = await import_claude_sessions(mm, session_files=[p])
    assert result["imported"] == 0
    assert result["skipped"] == 1
    assert mm.saved == []
