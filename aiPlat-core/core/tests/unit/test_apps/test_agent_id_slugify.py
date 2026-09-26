"""Agent id slugify: ASCII only, keep human display_name separate."""

from __future__ import annotations

from core.management.agent_manager import AgentManager


def test_slugify_keeps_english_id():
    assert AgentManager._slugify_agent_id("ppt_maker") == "ppt_maker"
    assert AgentManager._slugify_agent_id("PPT-Maker") == "ppt_maker"


def test_slugify_strips_cjk_to_ppt_hint():
    assert AgentManager._slugify_agent_id(
        "PPT 制作数字员工", fallback_display="PPT 制作数字员工"
    ) == "ppt_maker"


def test_slugify_hash_fallback():
    aid = AgentManager._slugify_agent_id("完全中文名称无英文")
    assert aid.startswith("agent_")
    assert aid.isascii()
