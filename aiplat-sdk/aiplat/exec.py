"""aiplat exec — 单次非交互执行入口（Codex-Harness 借鉴 P2：codex exec 对齐）。

两种模式（CI 友好，JSON 输出）：
  1. 默认：`aiplat exec "requirement"` — 经 stdio JSON-RPC 内核跑 PipelineSession
     （thread/start → 轮询 status → 输出最终状态 JSON）
  2. --script：`aiplat exec --script "bash script.sh"` — 零 LLM 直接执行
     （对齐 P2-A7 cron script 模式：fail-closed 入口白名单 bash/sh/python3/python）

契约：CLI 是纯客户端（复用 aiplat.stdio.StdioKernelClient，不包含业务逻辑）；
--script 模式零 LLM 调用、白名单外入口拒绝（fail-closed）；输出统一 JSON
（status/exit_code/run_id/phase 等），方便 CI 消费。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from typing import Any, Dict, List, Optional

# 对齐 P2-A7 cron script 模式入口白名单（fail-closed：白名单外拒绝执行）
_ALLOWED_SCRIPT_ENTRIES = {"bash", "sh", "python3", "python"}


def exec_script(
    script: str,
    workdir: str = "",
    timeout_seconds: float = 60.0,
) -> Dict[str, Any]:
    """零 LLM script 执行（对齐 P2-A7）：subprocess 运行白名单内命令，JSON 结果。

    fail-closed：入口不在 {bash,sh,python3,python} 时拒绝执行（返回 exit_code=125，
    与 codex exec 拒绝语义一致，绝不静默 fallback）。
    """
    script = (script or "").strip()
    if not script:
        return {"status": "error", "error": "empty script", "exit_code": 125}
    first = script.split()[0] if script.split() else ""
    if first not in _ALLOWED_SCRIPT_ENTRIES:
        return {
            "status": "error",
            "error": f"entry '{first}' not in {sorted(_ALLOWED_SCRIPT_ENTRIES)} (fail-closed)",
            "exit_code": 125,
        }

    try:
        proc = subprocess.run(
            script,
            shell=True,
            cwd=workdir or None,
            capture_output=True,
            text=True,
            timeout=float(timeout_seconds),
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "exit_code": 124,
                "timeout_seconds": float(timeout_seconds)}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e)[:500], "exit_code": 125}

    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-8000:],
    }


async def exec_pipeline(
    requirement: str,
    project_id: str = "cli-default",
    poll_interval: float = 0.5,
    max_polls: int = 600,
    kernel_cmd: Optional[List[str]] = None,
    client: Any = None,
) -> Dict[str, Any]:
    """经 stdio JSON-RPC 内核跑一次流水线（thread/start → 轮询 status）。

    复用 aiplat.stdio.StdioKernelClient（纯客户端）；完成后返回最终状态 JSON。
    超时（max_polls）返回 status=timeout 并尝试 thread/cancel（best-effort）。
    ``client`` 可注入（测试用 fake transport，见 tests/test_exec_cli.py）。
    """
    from aiplat.stdio import StdioKernelClient

    owns_client = client is None
    if client is None:
        if kernel_cmd is None:
            kernel_cmd = [sys.executable, "-m", "core.acp.stdio_server"]
        client = StdioKernelClient(kernel_cmd=kernel_cmd)

    async def _run() -> Dict[str, Any]:
        await client.start()
        started = await client.thread_start(project_id, requirement)
        thread_id = str(started.get("thread_id") or "")
        if not thread_id:
            return {"status": "error", "error": "thread/start returned no thread_id",
                    "started": started}

        final = {"status": "unknown", "thread_id": thread_id, "run_id": started.get("run_id", "")}
        for _ in range(int(max_polls)):
            st = await client.thread_status(thread_id)
            phase = str(st.get("phase") or "")
            final = {"status": "running" if phase in ("executing", "running") else phase,
                     "thread_id": thread_id,
                     "run_id": st.get("run_id") or started.get("run_id", ""),
                     "phase": phase,
                     "state": st}
            if phase in ("done", "failed", "cancelled", "paused"):
                break
            await asyncio.sleep(poll_interval)
        else:
            # 轮询耗尽：best-effort cancel 后返回 timeout
            try:
                await client.thread_cancel(thread_id)
            except Exception:  # noqa: BLE001
                pass
            final["status"] = "timeout"
        return final

    try:
        return await _run()
    finally:
        if owns_client and hasattr(client, "close"):
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass


def _emit(result: Dict[str, Any], json_output: bool) -> int:
    if json_output:
        print(json.dumps(result, ensure_ascii=False, default=str))
    else:
        # 人类可读摘要（CI 推荐 --json）
        if result.get("status") == "ok":
            print(f"OK exit={result.get('exit_code', 0)}")
        elif result.get("status") == "failed":
            print(f"FAILED exit={result.get('exit_code')}")
            if result.get("stderr"):
                print(result["stderr"][-2000:])
        else:
            print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result.get("status") in ("ok", "done") else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aiplat exec",
        description="aiPlat 单次非交互执行入口（codex exec 对齐，CI 友好 JSON 输出）",
    )
    parser.add_argument("requirement", nargs="?", default="",
                        help="任务需求（默认流水线模式）；配合 --script 时忽略")
    parser.add_argument("--script", default="",
                        help="零 LLM script 执行（白名单 bash/sh/python3/python）")
    parser.add_argument("--project-id", default="cli-default", help="流水线 project_id")
    parser.add_argument("--workdir", default="", help="script 模式工作目录")
    parser.add_argument("--timeout", type=float, default=60.0, help="script 模式超时秒数")
    parser.add_argument("--json", action="store_true", help="JSON 输出（CI 推荐）")
    args = parser.parse_args(argv)

    if args.script:
        result = exec_script(args.script, workdir=args.workdir,
                             timeout_seconds=args.timeout)
    else:
        requirement = (args.requirement or "").strip()
        if not requirement:
            parser.error("requirement 或 --script 必须提供其一")
        try:
            result = asyncio.run(exec_pipeline(requirement, project_id=args.project_id))
        except Exception as e:  # noqa: BLE001
            result = {"status": "error", "error": str(e)[:500]}
    return _emit(result, json_output=args.json)


if __name__ == "__main__":
    sys.exit(main())
