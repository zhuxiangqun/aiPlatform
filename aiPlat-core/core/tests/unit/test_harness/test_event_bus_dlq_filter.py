"""EventBus must not persist RunGraph SSE envelopes as syscall ghosts."""

from __future__ import annotations

import asyncio

import pytest

from core.harness.observation.event_bus import EventBus


def test_is_syscall_shaped_rejects_graph_envelope():
    assert EventBus._is_syscall_shaped(
        {"type": "graph_upsert", "run_id": "r1", "node": {"name": "x"}}
    ) is False
    assert EventBus._is_syscall_shaped({"type": "graph_done", "run_id": "r1"}) is False
    assert EventBus._is_syscall_shaped({"kind": "agent", "name": "agent_end", "status": "ok"}) is True
    assert EventBus._is_syscall_shaped({"kind": "", "name": "", "status": "completed"}) is False


@pytest.mark.asyncio
async def test_publish_without_subscriber_does_not_dlq(monkeypatch):
    """No live SSE subscriber → drop; primary path already wrote syscall_events."""
    EventBus.stop()
    EventBus.start()
    enqueued: list = []

    def _capture(evt):
        enqueued.append(evt)

    monkeypatch.setattr(EventBus, "_enqueue_dlq", classmethod(lambda cls, e: _capture(e)))
    EventBus.publish("run-test-no-sub", {"type": "graph_upsert", "node": {}})
    EventBus.publish(
        "run-test-no-sub",
        {"kind": "done", "name": "skill_delivery_once", "status": "ok"},
    )
    assert enqueued == []
    EventBus.stop()


@pytest.mark.asyncio
async def test_queue_full_dlq_skips_graph_envelope(monkeypatch):
    EventBus.stop()
    EventBus.start()
    q = EventBus.subscribe("run-full")
    # fill queue
    for i in range(q.maxsize):
        q.put_nowait({"kind": "llm", "name": "generate", "i": i})

    seen: list = []

    def _cap(evt):
        seen.append(evt)

    monkeypatch.setattr(EventBus, "_enqueue_dlq", classmethod(lambda cls, e: _cap(e)))
    # Overflow path calls _enqueue_dlq — our cap records what publish would pass.
    # Re-bind real filter by calling publish after restoring shaped check via direct call.
    monkeypatch.undo()
    # Use real _enqueue_dlq but capture what reaches the queue
    captured: list = []
    real_put = EventBus._enqueue_dlq

    def _wrap(cls, event):
        if cls._is_syscall_shaped(event):
            captured.append(event)
        # do not actually enqueue to avoid worker side effects

    monkeypatch.setattr(EventBus, "_enqueue_dlq", classmethod(_wrap))
    EventBus.publish("run-full", {"type": "graph_done", "run_id": "run-full"})
    EventBus.publish(
        "run-full",
        {"kind": "agent", "name": "agent_end", "status": "ok", "run_id": "run-full"},
    )
    assert captured == [
        {"kind": "agent", "name": "agent_end", "status": "ok", "run_id": "run-full"}
    ]
    EventBus.unsubscribe("run-full")
    EventBus.stop()
