"""Howl intervention counters for Governance KPIs."""

from __future__ import annotations

from core.harness.intervention.howl import (
    Howl,
    StallReason,
    _reset_howl_stats_for_tests,
    get_howl_stats,
)


def test_howl_records_semantic_stall():
    _reset_howl_stats_for_tests()
    howl = Howl()
    actions = [{"tool": "sys_file_write", "status": "ok"}] * 3
    r = howl.check(last_actions=actions)
    assert r.triggered is True
    assert r.stall_reason == StallReason.SEMANTIC_STALL
    stats = get_howl_stats()
    assert stats["total_interventions"] == 1
    assert stats["by_reason"].get("semantic_stall") == 1


def test_howl_no_trigger_no_count():
    _reset_howl_stats_for_tests()
    howl = Howl()
    r = howl.check(last_actions=[{"tool": "a"}, {"tool": "b"}])
    assert r.triggered is False
    assert get_howl_stats()["total_interventions"] == 0
