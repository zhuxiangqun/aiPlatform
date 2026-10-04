"""Unique Agent eval writer: generate / inspect / skip / listed enqueue."""
from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from core.apps.eval import agent_eval as ev
from core.engine.skills.eval_code_generator.handler import _extract_target, execute as eval_skill_execute


def _write_agent(home: Path, agent_id: str, extra_fm: str = "") -> None:
    d = home / "agents" / agent_id
    d.mkdir(parents=True)
    (d / "AGENT.md").write_text(
        "---\n"
        f"name: {agent_id}\n"
        f"display_name: {agent_id}\n"
        "description: unit test agent\n"
        "agent_type: conversational\n"
        f"{extra_fm}"
        "---\n\n## SOP\nhello\n",
        encoding="utf-8",
    )


def _seed_traces(home: Path, agent_id: str, n: int = 2) -> None:
    db = home / "aiplat_executions.sqlite3"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            """
            CREATE TABLE agent_executions (
              id TEXT PRIMARY KEY,
              agent_id TEXT NOT NULL,
              status TEXT NOT NULL,
              output_json TEXT,
              start_time REAL,
              created_at REAL NOT NULL
            )
            """
        )
        for i in range(n):
            conn.execute(
                "INSERT INTO agent_executions VALUES (?,?,?,?,?,?)",
                (f"run-{i}", agent_id, "completed", '{"ok":true}', 1.0 + i, 1.0 + i),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def plat_home(tmp_path, monkeypatch):
    home = tmp_path / "aiplat"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    return home


def test_inspect_missing_agent(plat_home):
    snap = ev.inspect_agent_eval("no_such_agent")
    assert snap["found"] is False
    assert snap["action"] == "skip"


@pytest.mark.asyncio
async def test_skip_no_traces_and_skip_eval_engineer(plat_home):
    _write_agent(plat_home, "demo_agent")
    out = await ev.generate_agent_eval("demo_agent", use_llm=False)
    assert out["action"] == "skip"
    assert "No execution traces" in str(out.get("message") or "")
    last = plat_home / "eval" / "demo_agent" / "last_action.json"
    assert last.is_file()

    _write_agent(
        plat_home,
        "eval_engineer",
        extra_fm="required_skills:\n  - eval_code_generator\n",
    )
    _seed_traces(plat_home, "eval_engineer")
    self_out = await ev.generate_agent_eval("eval_engineer", use_llm=False, force=True)
    assert self_out["action"] == "skip"
    assert "评估生成器" in str(self_out.get("message") or "")


@pytest.mark.asyncio
async def test_generate_writes_files_and_second_call_skips(plat_home):
    _write_agent(plat_home, "qa_agent")
    _seed_traces(plat_home, "qa_agent")
    out = await ev.generate_agent_eval("qa_agent", use_llm=False, run_runner=True)
    assert out["action"] == "generated"
    assert out["wrote_scoring_dimensions"] is True
    metric = plat_home / "eval" / "qa_agent" / "eval_metric.py"
    runner = plat_home / "eval" / "qa_agent" / "eval_runner.py"
    assert metric.is_file()
    assert runner.is_file()
    md = (plat_home / "agents" / "qa_agent" / "AGENT.md").read_text(encoding="utf-8")
    assert "scoring_dimensions:" in md
    assert "task_completion" in md
    assert out.get("runner", {}).get("ok") is True

    again = await ev.generate_agent_eval("qa_agent", use_llm=False)
    assert again["action"] == "skip"
    assert "Already has" in str(again.get("message") or "")

    snap = ev.inspect_agent_eval("qa_agent")
    assert snap["complete"] is True
    assert snap["has_scoring"] is True
    assert snap["trace_count"] >= 1
    assert isinstance(snap.get("last_report"), dict)
    assert snap["last_report"].get("total_runs") == 2


def test_enqueue_listed_without_loop_does_not_raise(plat_home):
    ev.enqueue_listed_agent_eval("qa_agent")
    ev.enqueue_listed_agent_eval("")


def test_handler_extracts_target_agent_id():
    assert _extract_target({"target_agent_id": "qa_agent"}) == "qa_agent"
    assert _extract_target({"message": "target_agent_id: programmer_agent"}) == "programmer_agent"
    assert _extract_target({"message": {"target_agent_id": "pm_agent"}}) == "pm_agent"
    assert _extract_target({"message": "hello"}) == ""


@pytest.mark.asyncio
async def test_handler_missing_target():
    out = await eval_skill_execute({"message": "评估一下"})
    assert out["success"] is False
    assert out["error"] == "missing_target_agent_id"


@pytest.mark.asyncio
async def test_handler_execute_generates_via_unique_writer(plat_home):
    _write_agent(plat_home, "qa_agent")
    _seed_traces(plat_home, "qa_agent")
    out = await eval_skill_execute(
        {
            "target_agent_id": "qa_agent",
            "message": "评估 qa_agent",
            "use_llm": False,
        }
    )
    assert out.get("success") is True
    assert out.get("action") == "generated"
    assert (plat_home / "eval" / "qa_agent" / "eval_metric.py").is_file()


def test_entropy_inspect_is_thin_proxy():
    from core.api.routers import entropy as entropy_mod

    inspect_http = inspect.getsource(entropy_mod.inspect_eval_for_agent)
    assert "inspect_agent_eval" in inspect_http
    assert "yaml.safe_dump" not in inspect_http


def test_entropy_generate_is_thin_proxy():
    src = inspect.getsource(ev.generate_agent_eval)
    from core.api.routers import entropy as entropy_mod

    http = inspect.getsource(entropy_mod.generate_eval_for_agent)
    assert "generate_agent_eval" in http
    assert "yaml.safe_dump" not in http
    assert "scoring_dimensions" in src


def test_agent_manager_lists_enqueue_hook():
    from core.management import agent_manager as am

    src = inspect.getsource(am.AgentManager.update_agent)
    assert "enqueue_listed_agent_eval" in src
    assert '== "listed"' in src or "== 'listed'" in src
