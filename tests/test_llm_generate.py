"""Test sys_llm_generate auto-resolves model when called with None and no model_name.

Regression test for: sys_llm_generate (non-streaming) missing best_model_for_purpose fallback
that sys_llm_generate_stream (streaming) already had.

See: llm.py:755-760 — the 3-line fix added to sync with llm.py:1387-1389.
"""

import pytest
from core.harness.syscalls.llm import sys_llm_generate


@pytest.mark.asyncio
async def test_generate_auto_resolves_model():
    """sys_llm_generate(None, messages) should resolve via best_model_for_purpose('chat')."""
    result = await sys_llm_generate(
        None,
        [{"role": "user", "content": "say ok"}],
        max_tokens=5,
        temperature=0,
    )
    assert result is not None
    content = result.get("content", "") if isinstance(result, dict) else str(result)
    assert len(content) > 0, f"Expected non-empty content, got: {content!r}"


@pytest.mark.asyncio
async def test_generate_no_model_no_name():
    """Regression: model=None, model_name='' should NOT raise RuntimeError."""
    result = await sys_llm_generate(
        None,
        [{"role": "user", "content": "1+1=?"}],
        max_tokens=3,
    )
    assert result is not None
