"""Unit tests for KB query → syscall_events telemetry."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from kb.query_telemetry import record_kb_query_syscall, summarize_kb_query_result


def test_summarize_kb_query_result_items():
    out = {
        "kb": {
            "items": [
                {"source": "doc-a.md", "score": 0.9, "text": "hello " * 50},
                {"doc_id": "b", "snippet": "snip"},
            ]
        }
    }
    s = summarize_kb_query_result(out)
    assert s["count"] == 2
    assert len(s["items"]) == 2
    assert s["items"][0]["source"] == "doc-a.md"
    assert len(s["items"][0]["text"]) <= 200
    assert s.get("citations")


def test_summarize_kb_query_result_empty():
    assert summarize_kb_query_result(None)["count"] == 0
    assert summarize_kb_query_result({})["count"] == 0
    assert summarize_kb_query_result({"kb": {"count": 3}})["count"] == 3


def test_record_kb_query_syscall_calls_store():
    """Inject store — do not import CoreFacade (Py3.9 kanban | union breaks)."""
    captured: List[Dict[str, Any]] = []

    class _Store:
        async def add_syscall_event(self, event: Dict[str, Any]) -> None:
            captured.append(event)

    ok = asyncio.run(
        record_kb_query_syscall(
            question="什么是交付清单？",
            collection_id="default",
            tenant_id="t1",
            actor_id="u1",
            out={"kb": {"items": [{"source": "a.md", "text": "x"}]}},
            store=_Store(),
        )
    )
    assert ok is True
    assert len(captured) == 1
    ev = captured[0]
    assert ev["kind"] == "knowledge_retrieve"
    assert ev["name"] == "platform_kb_retrieve"
    assert "kb_retrieve" in ev["name"]
    assert ev["status"] == "ok"
    assert ev["tenant_id"] == "t1"
    assert ev["args"]["question"].startswith("什么是")
    assert ev["result"]["count"] == 1


def test_record_kb_query_syscall_soft_fail():
    class _Boom:
        async def add_syscall_event(self, event: Dict[str, Any]) -> None:
            raise RuntimeError("write failed")

    ok = asyncio.run(
        record_kb_query_syscall(
            question="q",
            out={"kb": {"items": []}},
            store=_Boom(),
        )
    )
    assert ok is False


def test_record_kb_query_syscall_no_store():
    class _Empty:
        pass

    ok = asyncio.run(
        record_kb_query_syscall(question="q", out={}, store=_Empty())
    )
    assert ok is False
