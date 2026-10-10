"""Digital-human operational intent → governed handoff ACTION."""

from __future__ import annotations

from core.harness.digital_human.operational_handoff import (
    append_handoff_action,
    classify_operational_handoff,
)


def test_chat_question_no_handoff():
    assert classify_operational_handoff("四层架构各自干什么？") is None


def test_factory_build_handoff():
    info = classify_operational_handoff("帮忙启动流水线创建项目")
    assert info is not None
    assert info["route"] == "/app/factory"


def test_approve_handoff_governance():
    info = classify_operational_handoff("帮我审批一下待审批单")
    assert info is not None
    assert info["route"] == "/governance"


def test_append_idempotent_and_strips_navigate():
    q = "请帮我部署上线"
    out = append_handoff_action("结论：到工厂确认。\n[ACTION:navigate:/app/factory]", q)
    assert "[ACTION:handoff:/app/factory]" in out
    assert "[ACTION:navigate:" not in out
    out2 = append_handoff_action(out, q)
    assert out2.count("[ACTION:handoff:") == 1
