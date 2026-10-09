"""IDE capture → Factory coding handoff (no auto-run)."""

from __future__ import annotations

from core.harness.memory.ide_governed_handoff import (
    classify_ide_coding_handoff,
    ide_coding_handoff_payload,
)


def test_chat_capture_no_handoff():
    assert classify_ide_coding_handoff("总结一下四层架构") is None


def test_coding_prompt_handoff_factory():
    info = classify_ide_coding_handoff("帮我写代码实现登录接口")
    assert info is not None
    assert info["route"] == "/app/factory"


def test_payload_has_hint():
    p = ide_coding_handoff_payload("delegate coding for auth fix")
    assert p is not None
    assert p["kind"] == "ide_governed_coding_handoff"
    assert "does not start" in p["hint"]
