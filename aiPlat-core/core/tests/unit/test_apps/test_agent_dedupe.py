"""Agent display_name + content fingerprint reuse / dedupe."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from core.management.agent_manager import AgentInfo, AgentManager


def test_content_fingerprint_order_independent():
    a = AgentManager._content_fingerprint(["b", "a"], ["t2", "t1"], "react")
    b = AgentManager._content_fingerprint(["a", "b"], ["t1", "t2"], "react")
    c = AgentManager._content_fingerprint(["a", "b"], ["t1", "t2"], "rag")
    assert a == b
    assert a != c


def test_find_equivalent_by_display_name_and_fp():
    mgr = AgentManager.__new__(AgentManager)
    mgr._agents = {}
    now = datetime.now(timezone.utc)
    a1 = AgentInfo(
        id="agent_old",
        name="画面分析 Agent",
        type="react",
        status="ready",
        runtime_state="stopped",
        config={},
        skills=["vision_skill"],
        tools=["http"],
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
        metadata={"display_name": "画面分析 Agent"},
    )
    a2 = AgentInfo(
        id="agent_new",
        name="画面分析 Agent",
        type="react",
        status="ready",
        runtime_state="stopped",
        config={},
        skills=["other"],
        tools=[],
        created_at=now,
        updated_at=now,
        metadata={"display_name": "画面分析 Agent"},
    )
    mgr._agents = {a1.id: a1, a2.id: a2}

    hit = mgr.find_equivalent("画面分析 Agent", ["vision_skill"], ["http"], "react")
    assert hit is not None and hit.id == "agent_old"
    miss = mgr.find_equivalent("画面分析 Agent", ["vision_skill"], ["http"], "rag")
    assert miss is None


def test_dedupe_keeps_newest():
    mgr = AgentManager.__new__(AgentManager)
    mgr._agents = {}
    mgr._stats = {}
    mgr._skill_bindings = {}
    mgr._tool_bindings = {}
    mgr._execution_history = {}
    mgr._versions = {}
    mgr._scope = "workspace"
    mgr._reserved_ids = set()

    now = datetime.now(timezone.utc)
    older = AgentInfo(
        id="agent_a",
        name="字幕提取 Agent",
        type="react",
        status="ready",
        runtime_state="stopped",
        config={},
        skills=["s1"],
        tools=[],
        created_at=now - timedelta(hours=2),
        updated_at=now - timedelta(hours=2),
        metadata={"display_name": "字幕提取 Agent"},
    )
    newer = AgentInfo(
        id="agent_b",
        name="字幕提取 Agent",
        type="react",
        status="ready",
        runtime_state="stopped",
        config={},
        skills=["s1"],
        tools=[],
        created_at=now,
        updated_at=now,
        metadata={"display_name": "字幕提取 Agent"},
    )
    mgr._agents = {older.id: older, newer.id: newer}
    for aid in list(mgr._agents):
        mgr._stats[aid] = type("S", (), {})()
        mgr._skill_bindings[aid] = []
        mgr._tool_bindings[aid] = []
        mgr._execution_history[aid] = []

    # Avoid filesystem side effects in delete_agent
    mgr._resolve_agents_base_path = lambda: __import__("pathlib").Path("/tmp/aiplat-test-agents-none")  # type: ignore

    result = asyncio.get_event_loop().run_until_complete(mgr.dedupe_agents())
    assert result["removed_count"] == 1
    assert result["removed"] == ["agent_a"]
    assert "agent_b" in mgr._agents
    assert "agent_a" not in mgr._agents
