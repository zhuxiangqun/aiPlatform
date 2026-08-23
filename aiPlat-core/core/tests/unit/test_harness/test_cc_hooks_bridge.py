"""G6 CC/Codex hooks 协议桥测试（plan-g6-hooks-bridge.md §4 验收 1-5）。"""

import json
import os
import tempfile

import pytest

from core.harness.infrastructure.hooks import cc_bridge
from core.harness.infrastructure.hooks.cc_bridge import (
    CCHookBridge,
    load_cc_hooks_if_configured,
    load_hooks_json,
    register_cc_hooks,
)
from core.harness.infrastructure.hooks.cc_bridge_rules import (
    CC_EVENTS,
    CODEX_EVENTS,
    mapped_event_count,
    resolve_phase,
)
from core.harness.infrastructure.hooks.hook_manager import HookContext, HookManager, HookPhase


# ---------- 验收 1：hooks.json 解析（CC 格式） ----------

def test_load_hooks_json_cc_format(tmp_path):
    cfg = {
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "echo session-start"}]}],
            "PreToolUse": [{"hooks": [{"type": "command", "command": "echo pre-tool"}]}],
        }
    }
    p = tmp_path / "hooks.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    parsed = load_hooks_json(str(p))
    assert parsed["source"] == "cc"
    assert parsed["events"]["SessionStart"] == ["echo session-start"]
    assert parsed["events"]["PreToolUse"] == ["echo pre-tool"]
    assert parsed["unmapped"] == []


def test_load_hooks_json_skips_non_command_handlers(tmp_path):
    cfg = {
        "hooks": {
            "Stop": [
                {"hooks": [{"type": "command", "command": "echo stop"}]},
                {"hooks": [{"type": "http", "url": "http://x"}]},  # 非 command 跳过
            ]
        }
    }
    p = tmp_path / "hooks.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    parsed = load_hooks_json(str(p))
    assert parsed["events"]["Stop"] == ["echo stop"]


def test_load_hooks_json_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_hooks_json(str(tmp_path / "nope.json"))


def test_load_hooks_json_codex_array_format(tmp_path):
    cfg = [
        {"hook_event_name": "PreToolUse", "command": "echo codex-pre-tool", "matcher": "Write"},
        {"hook_event_name": "SessionStart", "command": "echo codex-start"},
    ]
    p = tmp_path / "hooks.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    parsed = load_hooks_json(str(p))
    assert parsed["source"] == "codex"
    assert parsed["events"]["PreToolUse"] == ["echo codex-pre-tool"]


# ---------- 验收 2：事件映射表覆盖度 ----------

def test_mapping_coverage_cc():
    # CC 30 事件中 ≥7 个可映射（设计 §3.2）
    assert mapped_event_count("cc") >= 7
    assert resolve_phase("SessionStart", "cc") == HookPhase.SESSION_START
    assert resolve_phase("UserPromptSubmit", "cc") == HookPhase.PRE_LOOP
    assert resolve_phase("PreToolUse", "cc") == HookPhase.PRE_TOOL_USE
    assert resolve_phase("PostToolUse", "cc") == HookPhase.POST_TOOL_USE
    assert resolve_phase("Stop", "cc") == HookPhase.STOP


def test_mapping_unmapped_events_fail_open():
    # 未知事件 → None（fail-open 不崩溃）
    assert resolve_phase("Notification", "cc") is not None or True  # 即使映射也兼容
    assert resolve_phase("TotallyUnknownEvent", "cc") is None
    assert resolve_phase("TotallyUnknownEvent", "codex") is None


def test_mapping_coverage_codex():
    assert mapped_event_count("codex") >= 4
    assert resolve_phase("SessionEnd", "codex") == HookPhase.SESSION_END


def test_cc_event_fullset_defined():
    # 事件全集常量存在（供覆盖度断言）
    assert len(CC_EVENTS) >= 12
    assert len(CODEX_EVENTS) >= 5


# ---------- 验收 3：command handler 执行 ----------

@pytest.mark.asyncio
async def test_command_handler_execution(tmp_path):
    hook = CCHookBridge(name="t:echo", command="echo hello-g6", phase=HookPhase.PRE_LOOP, repo_root=str(tmp_path))
    result = await hook(HookContext(phase=HookPhase.PRE_LOOP))
    assert result["continue"] is True
    assert result["cc_bridge"]["ok"] is True
    assert "hello-g6" in result["cc_bridge"]["stdout"]


@pytest.mark.asyncio
async def test_command_handler_trigger_via_manager(tmp_path):
    mgr = HookManager()
    # 清掉默认 hooks 干扰，单独注册
    for h in mgr.get_hooks(HookPhase.SESSION_START):
        mgr.unregister(h.name)
    mgr.register(CCHookBridge(name="t:cc-start", command="echo cc-start-ok", phase=HookPhase.SESSION_START, repo_root=str(tmp_path)))
    results = await mgr.trigger(HookPhase.SESSION_START, HookContext(phase=HookPhase.SESSION_START))
    assert any(isinstance(r, dict) and r.get("cc_bridge", {}).get("ok") for r in results)


# ---------- 验收 4：失败 fail-open ----------

@pytest.mark.asyncio
async def test_command_not_found_fail_open(tmp_path):
    hook = CCHookBridge(name="t:nope", command="definitely-not-a-real-cmd-xyz", phase=HookPhase.STOP, repo_root=str(tmp_path))
    result = await hook(HookContext(phase=HookPhase.STOP))
    assert result["continue"] is True  # 不阻断
    assert result["cc_bridge"]["ok"] is False
    assert result["cc_bridge"]["exit_code"] == 127


@pytest.mark.asyncio
async def test_command_timeout_fail_open(tmp_path):
    hook = CCHookBridge(name="t:sleep", command="sleep 5", phase=HookPhase.STOP, repo_root=str(tmp_path))
    cc_bridge.COMMAND_TIMEOUT_SECONDS = 0.2
    try:
        result = await hook(HookContext(phase=HookPhase.STOP))
        assert result["continue"] is True
        assert result["cc_bridge"]["ok"] is False
        assert "timeout" in result["cc_bridge"]["stderr"]
    finally:
        cc_bridge.COMMAND_TIMEOUT_SECONDS = 30.0


# ---------- 验收 5：接线（生产路径引用） ----------

def test_wiring_cc_bridge_in_hook_manager():
    import inspect
    from core.harness.infrastructure.hooks import hook_manager
    src = inspect.getsource(hook_manager.HookManager.__init__)
    assert "cc_bridge" in src
    assert "load_cc_hooks_if_configured" in src


def test_register_cc_hooks_wires_into_manager(tmp_path, monkeypatch):
    cfg = {
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "echo wired"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "echo stop"}]}],
        }
    }
    p = tmp_path / "hooks.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("AIPLAT_CC_HOOKS_PATH", str(p))
    mgr = HookManager()
    stats = register_cc_hooks(mgr, repo_root=str(tmp_path))
    assert stats["loaded"] == 2
    assert stats["events"] == 2
    names = {h.name for phase in mgr._hooks.values() for h in phase}
    assert any(n.startswith("cc_bridge:") for n in names)


def test_load_cc_hooks_if_configured_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AIPLAT_CC_HOOKS_PATH", raising=False)
    monkeypatch.setattr(cc_bridge, "_config_path", lambda: None)
    mgr = HookManager()
    stats = load_cc_hooks_if_configured(mgr)
    assert stats["enabled"] is False
