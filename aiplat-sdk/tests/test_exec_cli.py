"""aiplat exec CLI 测试（Codex-Harness 借鉴 P2：codex exec 对齐）。

覆盖：
- --script 模式：白名单内命令执行/JSON 输出/白名单外 fail-closed/超时
- 流水线模式：exec_pipeline 经 stdio client 轮询到 done（fake transport）
- main() 参数校验（requirement 与 --script 至少其一）
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiplat.exec import exec_script, exec_pipeline, main  # noqa: E402


# ── --script 模式（零 LLM，fail-closed） ─────────────────────────


def test_exec_script_ok():
    r = exec_script("python3 -c 'print(42)'")
    assert r["status"] == "ok"
    assert r["exit_code"] == 0
    assert "42" in r["stdout"]


def test_exec_script_fail_closed_non_whitelist():
    """入口不在 {bash,sh,python3,python} → 拒绝（绝不静默 fallback）。"""
    r = exec_script("curl http://example.com")
    assert r["status"] == "error"
    assert r["exit_code"] == 125
    assert "fail-closed" in r["error"]


def test_exec_script_empty():
    r = exec_script("")
    assert r["status"] == "error"
    assert r["exit_code"] == 125


def test_exec_script_failed_exit():
    r = exec_script("python3 -c 'import sys; sys.exit(3)'")
    assert r["status"] == "failed"
    assert r["exit_code"] == 3


def test_exec_script_timeout():
    r = exec_script("python3 -c 'import time; time.sleep(5)'", timeout_seconds=0.2)
    assert r["status"] == "timeout"
    assert r["exit_code"] == 124


# ── 流水线模式（经 stdio client 轮询） ─────────────────────────


class FakeTransport:
    """模拟 stdio 内核：thread/start → status(running→done)。"""

    def __init__(self):
        self.started = False
        self.status_calls = 0

    async def start(self):
        self.started = True

    async def request(self, method: str, params: dict) -> dict:
        if method == "initialize":
            return {"protocol_version": "0.1.0", "capabilities": {"thread": ["start"]}}
        if method == "thread/start":
            return {"thread_id": "th_cli", "run_id": "run_cli", "state": {"phase": "executing"}}
        if method == "thread/status":
            self.status_calls += 1
            phase = "done" if self.status_calls >= 2 else "executing"
            return {"thread_id": "th_cli", "run_id": "run_cli", "phase": phase}
        if method == "thread/cancel":
            return {"status": "cancelled"}
        raise AssertionError(f"unexpected method: {method}")

    async def close(self):
        self.started = False


async def _run_pipeline_with_fake():
    from aiplat.stdio import StdioKernelClient

    client = StdioKernelClient(kernel_cmd=[sys.executable, "-m", "core.acp.stdio_server"])
    client._transport = FakeTransport()
    return await exec_pipeline("build auth", project_id="cli-test",
                               poll_interval=0.01, max_polls=10, client=client)


def test_exec_pipeline_reaches_done():
    result = asyncio.run(_run_pipeline_with_fake())
    assert result["status"] == "done"
    assert result["thread_id"] == "th_cli"
    assert result["run_id"] == "run_cli"


def test_main_requires_input(capsys):
    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2  # argparse error


def test_main_script_json(capsys):
    code = main(["--script", "python3 -c 'print(7)'", "--json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["status"] == "ok"
    assert data["exit_code"] == 0
