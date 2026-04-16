import asyncio
import os

from core.harness.execution.loop import ReActLoop
from core.harness.interfaces.loop import LoopState, LoopConfig


class _ModelWrite:
    async def generate(self, messages):
        class _R:
            def __init__(self, c):
                self.content = c

        return _R('ACTION: write: {"path":"a.txt","content":"sk-abcdefghijklmnopqrstuvwxyz"}')


class _WriteTool:
    name = "write"

    async def execute(self, params):
        class _R:
            def __init__(self, out):
                self.output = out

        return _R("ok")


def test_security_scan_allowlist_blocks_and_writes_audit_events(monkeypatch):
    # Only scan 'write'
    monkeypatch.setenv("AIPLAT_SECURITY_SCAN_TOOL_ALLOWLIST", "write")
    monkeypatch.delenv("AIPLAT_SECURITY_SCAN_TOOL_DENYLIST", raising=False)

    loop = ReActLoop(model=_ModelWrite(), tools=[_WriteTool()])
    state = LoopState(context={"task": "t", "messages": [{"role": "user", "content": "t"}], "session_id": "s", "user_id": "u"})
    res = asyncio.run(loop.run(state, LoopConfig(max_steps=1)))

    # Tool call should be denied by pre_approval_check
    assert "Denied:" in (res.final_state.context.get("observation") or "")

    events = res.final_state.context.get("audit_events") or []
    assert any(e.get("event") == "security_scan" and e.get("tool_name") for e in events)


def test_security_scan_denylist_disables_scan(monkeypatch):
    # Disable scan for write
    monkeypatch.setenv("AIPLAT_SECURITY_SCAN_TOOL_DENYLIST", "write")
    monkeypatch.delenv("AIPLAT_SECURITY_SCAN_TOOL_ALLOWLIST", raising=False)
    monkeypatch.setenv("AIPLAT_SECURITY_SCAN_TOOLS", "write,edit")

    loop = ReActLoop(model=_ModelWrite(), tools=[_WriteTool()])
    state = LoopState(context={"task": "t", "messages": [{"role": "user", "content": "t"}], "session_id": "s", "user_id": "u"})
    res = asyncio.run(loop.run(state, LoopConfig(max_steps=1)))

    # Tool executes normally
    assert (res.final_state.context.get("observation") or "") == "ok"

