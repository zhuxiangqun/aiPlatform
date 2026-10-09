"""Team Brain — publish / recall / format (Hivemind-style thin aggregator)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def team_brain_env(tmp_path, monkeypatch):
    skills = tmp_path / "task_skills"
    skills.mkdir()
    exp = tmp_path / "experience_feedback.json"
    exp.write_text("[]", encoding="utf-8")
    shared = tmp_path / "shared"
    shared.mkdir()
    learnings = shared / "learnings.json"
    learnings.write_text(json.dumps({"entries": []}), encoding="utf-8")

    monkeypatch.setenv("AIPLAT_EXPERIENCE_FILE", str(exp))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))

    import core.harness.memory.team_brain as tb
    import core.harness.memory.shared_memory as sm

    monkeypatch.setattr(tb, "_task_skills_dir", lambda: skills)
    monkeypatch.setattr(tb, "_experience_path", lambda: exp)
    monkeypatch.setattr(sm, "_LEARNINGS_PATH", str(learnings))
    monkeypatch.setattr(sm, "_SHARED_DIR", str(shared))

    return {"skills": skills, "exp": exp, "learnings": learnings, "tb": tb, "sm": sm}


def test_publish_and_recall_manual(team_brain_env):
    tb = team_brain_env["tb"]
    rec = tb.publish_manual_solution(
        title="Docker build OOM",
        summary="Set NODE_OPTIONS=--max-old-space-size=4096 before npm run build",
        source_agent="senior_agent",
        keywords=["docker", "oom", "build"],
    )
    assert rec.get("key", "").startswith("team_solution:manual:")
    hits = tb.recall_team_solutions("docker oom build", limit=5)
    assert any("oom" in (h.summary + h.title).lower() for h in hits)
    msg = tb.format_recall_message(hits)
    assert msg is not None
    assert msg["meta"]["role"] == "team_brain_recall"
    assert "[Team Brain]" in msg["content"]


def test_hot_task_skill_listed(team_brain_env):
    tb = team_brain_env["tb"]
    skills: Path = team_brain_env["skills"]
    (skills / "migrate_pg.json").write_text(
        json.dumps(
            {
                "skill_id": "migrate_pg",
                "name": "Postgres migration",
                "pass_rate": 0.92,
                "pipeline_id": "pipe-1",
                "agent_sequence": ["backend_developer"],
                "keywords": ["postgres", "migration", "alembic"],
                "created_at": "2026-10-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (skills / "cold.json").write_text(
        json.dumps({"skill_id": "cold", "name": "cold", "pass_rate": 0.5, "keywords": ["x"]}),
        encoding="utf-8",
    )
    items = tb.list_team_solutions(limit=20)
    ids = {i.id for i in items if i.kind == "task_skill"}
    assert "migrate_pg" in ids
    assert "cold" not in ids
    hits = tb.recall_team_solutions("alembic postgres migration", limit=3)
    assert hits and hits[0].id == "migrate_pg"


def test_promoted_experience_recalled(team_brain_env):
    tb = team_brain_env["tb"]
    exp: Path = team_brain_env["exp"]
    exp.write_text(
        json.dumps(
            [
                {
                    "rule_id": "gotcha-ssl-verify",
                    "status": "promoted",
                    "content": "Disable SSL verify only in local docker-compose, never in prod",
                    "confidence": 0.95,
                    "promoted_at": "2026-10-02T00:00:00Z",
                },
                {
                    "rule_id": "pending-review",
                    "status": "promoted:review",
                    "content": "should not appear",
                    "confidence": 0.99,
                },
            ]
        ),
        encoding="utf-8",
    )
    hits = tb.recall_team_solutions("ssl docker-compose local", limit=5)
    ids = {h.id for h in hits}
    assert "gotcha-ssl-verify" in ids
    assert "pending-review" not in ids


def test_publish_task_skill_solution_requires_hot(team_brain_env):
    tb = team_brain_env["tb"]
    cold = tb.publish_task_skill_solution(
        {"skill_id": "x", "name": "x", "pass_rate": 0.5, "keywords": ["a"]},
        source_agent="t",
    )
    assert cold is None
    hot = tb.publish_task_skill_solution(
        {
            "skill_id": "hot1",
            "name": "Hot skill",
            "pass_rate": 0.9,
            "pipeline_id": "p",
            "keywords": ["redis", "cache"],
        },
        source_agent="pipeline",
    )
    assert hot is not None
    assert "team_solution:task_skill:hot1" in str(hot.get("key") or "")


def test_status_counts(team_brain_env):
    tb = team_brain_env["tb"]
    tb.publish_manual_solution("Tip", "Use make lint before commit", keywords=["lint"])
    st = tb.team_brain_status()
    assert st["total"] >= 1
    assert "by_kind" in st


@pytest.mark.asyncio
async def test_build_context_injects_team_brain_card(team_brain_env):
    """MemoryManager.build_context should inject [Team Brain] system card + inspect card."""
    tb = team_brain_env["tb"]
    tb.publish_manual_solution(
        title="Redis cache stampede",
        summary="Use singleflight + short TTL jitter for hot keys",
        keywords=["redis", "cache", "stampede"],
    )
    from core.harness.memory.manager import MemoryManager

    mm = MemoryManager(namespace="team-brain-test")
    result = await mm.build_context(
        "redis cache stampede fix",
        "you are a coding agent",
        session_id="team-brain-test",
    )
    messages = list(getattr(result, "messages", None) or result or [])
    team_msgs = [
        m
        for m in messages
        if isinstance(m, dict)
        and (m.get("meta") or {}).get("role") == "team_brain_recall"
    ]
    assert team_msgs, "expected team_brain_recall system message"
    assert "[Team Brain]" in str(team_msgs[0].get("content") or "")
    card = getattr(mm, "_last_team_brain_recall", None) or {}
    assert int(card.get("count") or 0) >= 1
