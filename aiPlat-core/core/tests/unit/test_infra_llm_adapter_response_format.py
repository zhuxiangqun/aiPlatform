"""InfraLLMAdapter must copy LLMConfig.response_format onto ChatRequest."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.adapters.llm.base import LLMConfig
from core.harness.infrastructure.infra_llm_adapter import InfraLLMAdapter
from infra.llm.schemas import ChatResponse


@pytest.mark.asyncio
async def test_generate_copies_response_format_to_chat_request():
    mock_client = MagicMock()
    mock_client.achat = AsyncMock(
        return_value=ChatResponse(content='{"a":1}', model="m", usage={})
    )
    adapter = InfraLLMAdapter(mock_client, model="m")
    fmt = {"type": "json_object"}
    cfg = LLMConfig(model="m", temperature=0.0, max_tokens=32, response_format=fmt)

    await adapter.generate([{"role": "user", "content": "x"}], config=cfg)

    req = mock_client.achat.call_args.args[0]
    assert req.response_format == fmt
