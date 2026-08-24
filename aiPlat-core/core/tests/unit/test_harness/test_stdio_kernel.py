"""P0-a stdio JSON-RPC 持久内核测试（plan: Codex-Harness开源借鉴分析报告 §2.1）。

协议层单测（不依赖真实 PipelineEngine）：JSON-RPC 2.0 帧、方法分发、
错误信封、背压 -32001、Thread 生命周期映射。
"""

import json

import pytest

from core.acp.stdio_server import (
    ERR_SERVER_OVERLOADED,
    MAX_CONCURRENT,
    StdioKernel,
    handle_request,
)


class FakeSession:
    """替代 PipelineSession 的假会话（协议层测试用）。"""

    def __init__(self):
        self.started = False
        self.approved = 0
        self.rejected = 0
        self.rolled_back = 0

    async def start(self, project_id, requirement, prd_data=None):
        self.started = True
        return {"phase": "running", "run_id": "run_fake", "project_id": project_id,
                "requirement": requirement}

    async def approve(self, state, feedback=""):
        self.approved += 1
        return {**state, "phase": "running", "approved": self.approved}

    async def reject(self, state, feedback):
        self.rejected += 1
        return {**state, "phase": "running", "rejected": self.rejected}

    async def rollback(self, state, stage_id):
        self.rolled_back += 1
        return {**state, "phase": "rolled_back"}


@pytest.fixture
def kernel(monkeypatch):
    k = StdioKernel()

    def _create_session(thread_id):
        return FakeSession()

    monkeypatch.setattr(k, "_create_session", _create_session)
    return k


# ── JSON-RPC 帧与分发 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_initialize_returns_capabilities(kernel):
    resp = await handle_request(kernel, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp["result"]["protocol_version"] == "0.1.0"
    assert "start" in resp["result"]["capabilities"]["thread"]
    assert "approve" in resp["result"]["capabilities"]["thread"]
    assert "item.event" in resp["result"]["capabilities"]["events"]


@pytest.mark.asyncio
async def test_unknown_method_returns_error(kernel):
    resp = await handle_request(kernel, {"jsonrpc": "2.0", "id": 2, "method": "nope", "params": {}})
    assert resp["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_parse_error_envelope(kernel, capsys):
    # 直接模拟：handle_request 不负责 parse（parse 在主循环）——验证 -32700 由 _error 生成
    from core.acp.stdio_server import _error
    assert _error(None, -32700, "Parse error")["error"]["code"] == -32700


# ── Thread 生命周期 ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_thread_start_creates_session(kernel):
    resp = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 3, "method": "thread/start",
        "params": {"project_id": "p1", "requirement": "build auth"},
    })
    result = resp["result"]
    assert result["thread_id"].startswith("th_")
    assert result["state"]["phase"] == "running"
    assert result["state"]["project_id"] == "p1"
    assert "run_id" in result


@pytest.mark.asyncio
async def test_thread_start_requires_fields(kernel):
    resp = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 4, "method": "thread/start",
        "params": {"project_id": "p1"},
    })
    assert resp["error"]["code"] == -32602  # Invalid params


@pytest.mark.asyncio
async def test_thread_status_and_resume(kernel):
    start = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 5, "method": "thread/start",
        "params": {"project_id": "p1", "requirement": "req"},
    })
    tid = start["result"]["thread_id"]
    status = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 6, "method": "thread/status",
        "params": {"thread_id": tid},
    })
    assert status["result"]["phase"] == "running"
    resume = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 7, "method": "thread/resume",
        "params": {"thread_id": tid},
    })
    assert resume["result"]["thread_id"] == tid


@pytest.mark.asyncio
async def test_thread_approve_reject_flow(kernel):
    start = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 8, "method": "thread/start",
        "params": {"project_id": "p1", "requirement": "req"},
    })
    tid = start["result"]["thread_id"]
    approve = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 9, "method": "thread/approve",
        "params": {"thread_id": tid, "feedback": "looks good"},
    })
    assert approve["result"]["state"]["approved"] == 1
    reject = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 10, "method": "thread/reject",
        "params": {"thread_id": tid, "feedback": "redo"},
    })
    assert reject["result"]["state"]["rejected"] == 1


@pytest.mark.asyncio
async def test_thread_rollback(kernel):
    start = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 11, "method": "thread/start",
        "params": {"project_id": "p1", "requirement": "req"},
    })
    tid = start["result"]["thread_id"]
    rb = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 12, "method": "thread/rollback",
        "params": {"thread_id": tid, "stage_id": "s1"},
    })
    assert rb["result"]["state"]["phase"] == "rolled_back"


@pytest.mark.asyncio
async def test_unknown_thread_raises_invalid_params(kernel):
    resp = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 13, "method": "thread/status",
        "params": {"thread_id": "th_nope"},
    })
    assert resp["error"]["code"] == -32602


# ── 背压语义 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_backpressure_error_code_constant():
    assert ERR_SERVER_OVERLOADED == -32001
    assert MAX_CONCURRENT >= 1
    from core.acp.stdio_server import _error
    resp = _error(1, ERR_SERVER_OVERLOADED, "server overloaded, retry with backoff")
    assert resp["error"]["code"] == -32001


@pytest.mark.asyncio
async def test_internal_error_envelope(kernel, monkeypatch):
    async def boom(params):
        raise RuntimeError("boom")

    monkeypatch.setattr(kernel, "thread_status", boom)
    resp = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 14, "method": "thread/status",
        "params": {"thread_id": "th_1"},
    })
    assert resp["error"]["code"] == -32603
    assert "boom" in resp["error"]["message"]


# ── 事件流映射 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_thread_events_returns_list(kernel):
    resp = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 15, "method": "thread/start",
        "params": {"project_id": "p1", "requirement": "req"},
    })
    tid = resp["result"]["thread_id"]
    events = await handle_request(kernel, {
        "jsonrpc": "2.0", "id": 16, "method": "thread/events",
        "params": {"thread_id": tid},
    })
    assert isinstance(events["result"]["events"], list)


@pytest.mark.asyncio
async def test_shutdown(kernel):
    resp = await handle_request(kernel, {"jsonrpc": "2.0", "id": 17, "method": "shutdown", "params": {}})
    assert resp["result"]["status"] == "ok"
