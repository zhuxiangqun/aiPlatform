"""IDE bypass capture → Team Brain (+ optional Session Wiki)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def ide_capture_env(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    shared.mkdir()
    learnings = shared / "learnings.json"
    learnings.write_text(json.dumps({"entries": []}), encoding="utf-8")
    wiki = tmp_path / "wiki" / "collections" / "default"
    (wiki / "topics").mkdir(parents=True)

    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))

    import core.harness.memory.shared_memory as sm
    import core.harness.memory.ide_capture as ic
    import core.harness.memory.session_wiki as sw

    monkeypatch.setattr(sm, "_LEARNINGS_PATH", str(learnings))
    monkeypatch.setattr(sm, "_SHARED_DIR", str(shared))

    return {
        "learnings": learnings,
        "wiki": wiki,
        "ic": ic,
        "sw": sw,
        "tmp": tmp_path,
    }


def test_ingest_success_publishes_team_brain(ide_capture_env):
    ic = ide_capture_env["ic"]
    out = ic.ingest_ide_capture(
        prompt="fix JWT expiry in auth middleware",
        result="check exp claim before refresh; add clock skew 30s",
        tools=["grep", "edit"],
        success=True,
        tags=["auth", "cursor"],
        source="cursor",
        session_id="sess-1",
    )
    assert out["ok"] is True
    assert out["action"] == "team_brain"
    key = out["learning"].get("key", "")
    assert key.startswith("team_solution:manual:")
    data = json.loads(ide_capture_env["learnings"].read_text(encoding="utf-8"))
    keys = [e.get("key") for e in data.get("entries", [])]
    assert key in keys


def test_ingest_failure_records_medium_learning(ide_capture_env):
    ic = ide_capture_env["ic"]
    out = ic.ingest_ide_capture(
        prompt="npm run build OOM",
        result="still OOMs after NODE_OPTIONS bump",
        success=False,
        source="claude_code",
    )
    assert out["ok"] is True
    assert out["action"] == "shared_learning_fail"
    assert "ide_fail" in out["learning"].get("key", "")


def test_ingest_empty_rejected(ide_capture_env):
    ic = ide_capture_env["ic"]
    out = ic.ingest_ide_capture(prompt="", result="")
    assert out["ok"] is False
    assert out["reason"] == "empty_payload"


def test_ingest_write_wiki_opt_in(ide_capture_env, monkeypatch):
    ic = ide_capture_env["ic"]
    written = {}

    def _fake_write_page(**kwargs):
        written.update(kwargs)
        return str(ide_capture_env["wiki"] / "topics" / "session.md")

    monkeypatch.setattr(
        "core.harness.knowledge.wiki_engine.write_page",
        _fake_write_page,
    )
    out = ic.ingest_ide_capture(
        prompt="migrate local postgres to docker",
        result="use host.docker.internal and recreate volume; tests green",
        success=True,
        write_wiki=True,
        source="cursor",
        session_id="s-wiki",
    )
    assert out["ok"] is True
    assert out.get("wiki", {}).get("ok") is True
    assert written.get("status") == "draft"
    assert "session/" in str(written.get("title") or "")


@pytest.mark.asyncio
async def test_session_wiki_worker_respects_env(ide_capture_env, monkeypatch):
    sw = ide_capture_env["sw"]
    monkeypatch.delenv("AIPLAT_SESSION_WIKI", raising=False)
    class Ctx:
        state = {
            "success": True,
            "final_answer": "x" * 50,
            "session_id": "ab",
            "task": "build fix",
            "agent_id": "programmer",
        }
        session_id = "ab"
        agent_id = "programmer"

    disabled = await sw.session_wiki_worker_hook(Ctx())
    assert disabled["session_wiki"] == "disabled"

    monkeypatch.setenv("AIPLAT_SESSION_WIKI", "true")
    written = {}

    def _fake_write_page(**kwargs):
        written.update(kwargs)
        return "/tmp/wiki-page.md"

    monkeypatch.setattr(
        "core.harness.knowledge.wiki_engine.write_page",
        _fake_write_page,
    )
    enabled = await sw.session_wiki_worker_hook(Ctx())
    assert enabled["session_wiki"]["ok"] is True
    assert written.get("category") == "topics"


def test_session_wiki_too_short(ide_capture_env):
    sw = ide_capture_env["sw"]
    out = sw.write_session_wiki_page(title="t", summary="short")
    assert out["ok"] is False
    assert out["reason"] == "summary_too_short"


def test_cli_normalize_hook_payload(monkeypatch):
    """scripts/ide_capture.py --from-hook normalizes Cursor shapes."""
    import importlib.util
    import io
    import sys

    here = Path(__file__).resolve()
    script = None
    for parent in here.parents:
        candidate = parent / "scripts" / "ide_capture.py"
        if candidate.is_file():
            script = candidate
            break
    assert script is not None, "scripts/ide_capture.py not found"
    spec = importlib.util.spec_from_file_location("ide_capture_cli", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "user_prompt": "fix lint",
                    "assistant_message": "fixed unused import",
                    "tool_names": ["grep"],
                    "status": "ok",
                    "conversation_id": "c1",
                }
            )
        ),
    )
    payload = mod._read_payload(from_hook=True)
    assert payload["prompt"] == "fix lint"
    assert payload["result"] == "fixed unused import"
    assert payload["tools"] == ["grep"]
    assert payload["success"] is True
    assert payload["session_id"] == "c1"
