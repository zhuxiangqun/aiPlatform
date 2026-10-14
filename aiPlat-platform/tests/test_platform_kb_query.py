"""Unit tests for structured platform KB retrieve shaping."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, patch

from kb.platform_query import (
    execute_platform_kb_query,
    _ensure_item_text,
    _extract_keywords,
)


def test_ensure_item_text_fills_from_snippet():
    rows = _ensure_item_text([{"doc_id": "d1", "snippet": "hello world"}])
    assert rows[0]["text"] == "hello world"
    assert rows[0]["doc_id"] == "d1"


def test_extract_keywords_chinese():
    kws = _extract_keywords("知识库有哪些文档关于少年中国")
    assert any("知识库" in k or "文档" in k or "少年" in k for k in kws)


def test_execute_platform_kb_query_shapes_kb_and_items():
    fake = {
        "answer": "命中 1 条",
        "items": [{"doc_id": "docA", "snippet": "少年中国", "score": 0.9}],
        "citations": [{"doc_id": "docA", "page_idx": 1}],
        "retrieval_mode": "fts_or_like",
        "generation_mode": "fallback",
        "mode": "local_keyword+fallback",
    }

    def _norm(*, tenant_id: str, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        assert tenant_id == "t1"
        assert isinstance(data, dict)
        out = dict(data)
        out["citations"] = list(data.get("citations") or [])
        return out

    with patch("kb.platform_query._retrieve_local", return_value=fake):
        out = asyncio.run(
            execute_platform_kb_query(
                tenant_id="t1",
                collection_id="default",
                question="少年中国说什么",
                limit=3,
                normalize_citations=_norm,
            )
        )

    assert out["ok"] is True
    assert out["status"] == "completed"
    assert out["skill_id"] == "platform_kb_local"
    assert out["answer"] == "命中 1 条"
    assert isinstance(out["kb"], dict)
    assert out["kb"]["items"][0]["text"] == "少年中国"
    assert out["items"][0]["doc_id"] == "docA"
    assert out["citations"][0]["doc_id"] == "docA"


def test_execute_platform_kb_query_crag_opt_in(monkeypatch):
    monkeypatch.setenv("AIPLAT_KB_QUERY_CRAG", "1")
    fake = {
        "answer": "crag",
        "items": [{"doc_id": "x", "snippet": "y", "score": 0.8}],
        "citations": [],
        "retrieval_mode": "crag_unified",
        "generation_mode": "fallback",
        "mode": "crag",
    }

    with patch(
        "kb.intelligence.query.query_elements",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        out = asyncio.run(
            execute_platform_kb_query(
                tenant_id="t1",
                collection_id="default",
                question="q",
                limit=2,
            )
        )
    assert out["skill_id"] == "query_elements"
    assert out["items"][0]["text"] == "y"
