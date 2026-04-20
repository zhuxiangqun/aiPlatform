import os


def test_llm_message_guard_converts_tool_role():
    from core.harness.syscalls.llm import _guard_messages

    msgs, stats = _guard_messages(
        [
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "tool output"},
            {"role": "assistant", "content": "ok"},
        ]
    )
    assert stats["converted_roles"] >= 1
    assert msgs[0]["role"] == "system"  # inserted
    assert any(m["role"] == "system" and "TOOL_RESULT" in m["content"] for m in msgs)


def test_llm_message_guard_merges_adjacent_roles():
    from core.harness.syscalls.llm import _guard_messages

    msgs, stats = _guard_messages(
        [
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
            {"role": "assistant", "content": "c"},
            {"role": "assistant", "content": "d"},
        ]
    )
    assert stats["merged_messages"] == 2
    assert len([m for m in msgs if m["role"] == "user"]) == 1
    assert len([m for m in msgs if m["role"] == "assistant"]) == 1


def test_llm_message_guard_truncates_long_messages(monkeypatch):
    from core.harness.syscalls.llm import _guard_messages

    monkeypatch.setenv("AIPLAT_LLM_MESSAGE_MAX_CHARS", "10")
    msgs, stats = _guard_messages([{"role": "user", "content": "0123456789ABC"}])
    assert stats["truncated_messages"] == 1
    # marker may exceed max_chars when max is very small; ensure content is truncated with marker
    assert "truncated" in msgs[1]["content"]
