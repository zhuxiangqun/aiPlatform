"""response_format must reach OpenAI-compatible create kwargs (structured JSON hard-decode)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infra.llm.providers.openai_compatible import OpenAICompatibleClient
from infra.llm.schemas import ChatRequest, LLMConfig, Message


def _cfg() -> LLMConfig:
    return LLMConfig(
        provider="openai",
        api_key="sk-test",
        base_url="http://127.0.0.1:9/v1",
        model="gpt-test",
        timeout=5,
    )


def _mock_completion(content: str = '{"ok":true}'):
    choice = MagicMock()
    choice.message.content = content
    choice.message.reasoning_content = None
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.id = "chatcmpl-test"
    resp.model = "gpt-test"
    resp.choices = [choice]
    usage = MagicMock()
    usage.prompt_tokens = 1
    usage.completion_tokens = 2
    usage.total_tokens = 3
    resp.usage = usage
    return resp


def test_execute_chat_forwards_json_schema_response_format():
    client = OpenAICompatibleClient(_cfg())
    client._pool = None
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = _mock_completion()

    fmt = {
        "type": "json_schema",
        "json_schema": {
            "name": "output",
            "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
        },
    }
    req = ChatRequest(
        model="gpt-test",
        messages=[Message(role="user", content="return json")],
        temperature=0.0,
        max_tokens=64,
        timeout=0,  # skip httpx Timeout import in offline unit test
        response_format=fmt,
    )
    out = client._execute_chat(mock_openai, req)
    assert out.content == '{"ok":true}'
    kwargs = mock_openai.chat.completions.create.call_args.kwargs
    assert kwargs.get("response_format") == fmt


def test_execute_chat_omits_response_format_when_unset():
    client = OpenAICompatibleClient(_cfg())
    client._pool = None
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = _mock_completion("hi")

    req = ChatRequest(
        model="gpt-test",
        messages=[Message(role="user", content="hi")],
        temperature=0.0,
        max_tokens=8,
        timeout=0,
    )
    client._execute_chat(mock_openai, req)
    kwargs = mock_openai.chat.completions.create.call_args.kwargs
    assert "response_format" not in kwargs
