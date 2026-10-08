"""W4: kb_qa_retrieve routes to sys_crag_retrieve."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_kb_qa_retrieve_delegates_to_crag(monkeypatch):
    calls = {}

    async def _fake_crag(query, **kwargs):
        calls["query"] = query
        calls["kwargs"] = kwargs
        return ("hit text", [{"doc_id": "d1", "text": "hit", "page_idx": 1}])

    monkeypatch.setattr(
        "core.harness.syscalls.retrieval_crag.sys_crag_retrieve",
        _fake_crag,
        raising=True,
    )
    from core.api.facades.kb_facade import kb_qa_retrieve

    text, cites = await kb_qa_retrieve(
        "什么是RAG", doc_ids=["a"], tenant_id="t1", collection_id="c1", top_k=4,
    )
    assert text == "hit text"
    assert cites[0]["doc_id"] == "d1"
    assert calls["query"] == "什么是RAG"
    assert calls["kwargs"]["tenant_id"] == "t1"
    assert calls["kwargs"]["collection_id"] == "c1"
    assert calls["kwargs"]["top_k"] == 4
