"""Session → Wiki worker (opt-in, no KnowledgeSynthesizer)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.harness.memory.session_wiki import (
    session_wiki_enabled,
    session_wiki_worker_hook,
    write_session_wiki_page,
)


def test_write_rejects_short_summary():
    out = write_session_wiki_page("t", "too short")
    assert out["ok"] is False
    assert out["reason"] == "summary_too_short"


def test_write_calls_wiki_engine(monkeypatch):
    seen = {}

    def fake_write_page(**kwargs):
        seen.update(kwargs)
        return "/tmp/wiki/session.md"

    monkeypatch.setattr(
        "core.harness.knowledge.wiki_engine.write_page",
        fake_write_page,
    )
    summary = "A" * 80
    out = write_session_wiki_page("JWT fix", summary, session_id="s1", source="ide")
    assert out["ok"] is True
    assert out["title"].startswith("session/")
    assert seen.get("status") == "draft"
    assert seen.get("skip_validation") is True
    assert "session-summary" in (seen.get("tags") or [])


def test_enabled_opt_in(monkeypatch):
    monkeypatch.delenv("AIPLAT_SESSION_WIKI", raising=False)
    assert session_wiki_enabled() is False
    monkeypatch.setenv("AIPLAT_SESSION_WIKI", "true")
    assert session_wiki_enabled() is True


@pytest.mark.asyncio
async def test_hook_disabled_skips(monkeypatch):
    monkeypatch.delenv("AIPLAT_SESSION_WIKI", raising=False)
    ctx = SimpleNamespace(state={"summary": "x" * 80}, session_id="s")
    out = await session_wiki_worker_hook(ctx)
    assert out["session_wiki"] == "disabled"
    assert out["continue"] is True


@pytest.mark.asyncio
async def test_hook_writes_when_enabled(monkeypatch):
    monkeypatch.setenv("AIPLAT_SESSION_WIKI", "1")
    called = {}

    def fake_write(title, summary, **kwargs):
        called["title"] = title
        called["summary"] = summary
        return {"ok": True, "title": "session/x"}

    monkeypatch.setattr(
        "core.harness.memory.session_wiki.write_session_wiki_page",
        fake_write,
    )
    ctx = SimpleNamespace(
        state={
            "final_answer": "B" * 50,
            "task": "land session wiki",
            "session_id": "sid-9",
            "agent_id": "coder",
        },
        session_id="sid-9",
        agent_id="coder",
    )
    out = await session_wiki_worker_hook(ctx)
    assert called["title"] == "land session wiki"
    assert out["session_wiki"]["ok"] is True
