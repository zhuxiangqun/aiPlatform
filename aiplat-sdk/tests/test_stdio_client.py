"""P1 SDK StdioKernelClient 测试。

协议层单测（内存传输 mock）+ 真实内核集成测试（可选）。
StdioKernelClient 支持注入 transport 对象（start/request 经 transport 收发 JSONL）。
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiplat.stdio as stdio_mod
from aiplat.stdio import StdioKernelClient, StdioKernelError


class MemoryTransport:
    """内存 JSON-RPC 传输（替代真实 subprocess stdio）。"""

    def __init__(self, responder):
        self.responder = responder
        self.sent = []
        self.started = False

    async def start(self):
        self.started = True

    async def request(self, method: str, params: dict) -> dict:
        self.sent.append(method)
        return await self.responder(method, params)

    async def close(self):
        self.started = False


def _make_client(responder) -> StdioKernelClient:
    client = StdioKernelClient(kernel_cmd=[sys.executable, "-m", "core.acp.stdio_server"])
    transport = MemoryTransport(responder)
    client._transport = transport
    return client


async def _ok_responder(method: str, params: dict) -> dict:
    if method == "initialize":
        return {"protocol_version": "0.1.0", "capabilities": {"thread": ["start", "approve"]}}
    if method == "thread/start":
        return {"thread_id": "th_fake", "state": {"phase": "running"}, "run_id": "run_fake"}
    if method == "thread/events":
        after = int(params.get("after_seq", 0))
        all_events = [{"seq": 1, "event_type": "stage_started"},
                      {"seq": 2, "event_type": "stage_completed"}]
        return {"events": [e for e in all_events if e["seq"] > after]}
    if method == "thread/approve":
        return {"thread_id": "th_fake", "state": {"phase": "running", "approved": 1}}
    if method == "shutdown":
        return {"status": "ok"}
    return {}


# ── 协议层 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_initialize_returns_capabilities():
    client = _make_client(_ok_responder)
    await client.start()
    caps = client._capabilities
    assert caps["protocol_version"] == "0.1.0"
    assert "approve" in caps["capabilities"]["thread"]


@pytest.mark.asyncio
async def test_thread_start_maps_params():
    captured = {}

    async def responder(method, params):
        captured.update(params)
        return await _ok_responder(method, params)

    client = _make_client(responder)
    await client.start()
    thread = await client.thread_start("p1", "build auth")
    assert thread["thread_id"] == "th_fake"
    assert captured["project_id"] == "p1"
    assert captured["requirement"] == "build auth"


@pytest.mark.asyncio
async def test_thread_approve_and_events():
    client = _make_client(_ok_responder)
    await client.start()
    events = await client.thread_events("th_fake")
    assert len(events["events"]) == 2
    approved = await client.thread_approve("th_fake", {"phase": "awaiting_hitl"}, feedback="ok")
    assert approved["state"]["approved"] == 1


@pytest.mark.asyncio
async def test_stream_events_yields_all():
    client = _make_client(_ok_responder)
    await client.start()
    collected = []
    async for ev in client.stream_events("th_fake", poll_interval=0.001):
        collected.append(ev)
    assert len(collected) == 2
    assert collected[0]["event_type"] == "stage_started"


@pytest.mark.asyncio
async def test_error_response_raises():
    async def responder(method, params):
        if method == "initialize":
            return {"protocol_version": "0.1.0", "capabilities": {}}
        raise StdioKernelError("thread/start failed (-32602): invalid params")

    client = _make_client(responder)
    await client.start()
    with pytest.raises(StdioKernelError) as exc:
        await client.thread_start("", "")
    assert "-32602" in str(exc.value)


@pytest.mark.asyncio
async def test_request_before_start_raises():
    client = StdioKernelClient(kernel_cmd=[sys.executable, "-m", "core.acp.stdio_server"])
    with pytest.raises(StdioKernelError):
        await client.thread_status("th_1")


@pytest.mark.asyncio
async def test_context_manager_close():
    client = _make_client(_ok_responder)
    await client.start()
    assert client._proc is not None
    await client.close()
    assert client._proc is None


# ── 真实内核集成（可选）───────────────────────────────────────

@pytest.mark.asyncio
async def test_real_kernel_initialize():
    """spawn 真实 stdio 内核（若 aiPlat-core 不可导入则跳过）。"""
    core_dir = Path(__file__).resolve().parents[1].parent / "aiPlat-core"
    client = StdioKernelClient(cwd=str(core_dir), request_timeout=10)
    try:
        caps = await client.start()
        assert caps["protocol_version"].startswith("0.1")
    except (FileNotFoundError, StdioKernelError) as e:
        pytest.skip(f"real kernel unavailable: {e}")
    finally:
        await client.close()
