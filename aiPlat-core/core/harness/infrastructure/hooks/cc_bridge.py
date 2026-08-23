"""
CC/Codex hooks.json 协议桥。

让 aiPlat 直接消费 Claude Code / Codex 的 hooks.json 配置，把外部事件
映射到 aiPlat HookPhase 生命周期执行 command handler（企业远程策略场景：
复用 CC 生态 hooks 脚本零改写接入）。

设计依据：docs/research/plan-g6-hooks-bridge.md §3.3/§5
对齐 DSH hooks-claude-code / hooks-codex 的诚实披露：
- 仅 command handler（http/mcp_tool/prompt/agent handler 跳过记 WARNING）
- 子集映射（unmapped 事件 fail-open 不静默执行）
- 进程级单配置（无分层发现/热重载，v1 不做）
- 安全：command 以 repo 目录 cwd 执行，权限继承执行者身份
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cc_bridge_rules import resolve_phase
from .hook_manager import Hook, HookContext, HookManager, HookPhase

logger = logging.getLogger(__name__)

# hooks.json 结构：{"hooks": {"EventName": [{"hooks": [{"type": "command", "command": "..."}]}]}}
# 兼容 CC 单对象与 Codex 数组两种形态
DEFAULT_CONFIG_PATH = "~/.aiplat/hooks.json"
ENV_CONFIG_PATH = "AIPLAT_CC_HOOKS_PATH"
COMMAND_TIMEOUT_SECONDS = 30.0
_LOADED = False


def _config_path() -> Optional[Path]:
    env_path = os.getenv(ENV_CONFIG_PATH)
    if env_path:
        p = Path(env_path).expanduser()
        return p if p.exists() else None
    p = Path(DEFAULT_CONFIG_PATH).expanduser()
    return p if p.exists() else None


def load_hooks_json(path: Optional[str] = None) -> Dict[str, Any]:
    """解析 CC/Codex hooks.json，返回结构化事件映射。

    :param path: hooks.json 路径；None 时按 env/默认路径探测
    :return: {"events": {event: [command, ...]}, "source": "cc"/"codex", "unmapped": [...]}
    """
    cfg = None
    if path is not None:
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"hooks.json not found: {p}")
        cfg = json.loads(p.read_text(encoding="utf-8"))
    else:
        p = _config_path()
        if p is None:
            return {"events": {}, "source": "cc", "unmapped": [], "path": None}
        cfg = json.loads(p.read_text(encoding="utf-8"))

    source = "codex" if isinstance(cfg, list) else "cc"
    hooks_map: Dict[str, Any] = {}
    if source == "cc":
        hooks_map = cfg.get("hooks", {}) if isinstance(cfg, dict) else {}
    elif isinstance(cfg, list):
        # Codex 数组形态：[{"hook_event_name": "PreToolUse", "command": "...", "matcher": "..."}]
        for item in cfg:
            ev = item.get("hook_event_name")
            cmd = item.get("command")
            if ev and cmd:
                hooks_map.setdefault(ev, []).append({"type": "command", "command": cmd})

    events: Dict[str, List[str]] = {}
    unmapped: List[str] = []
    for event, handlers in hooks_map.items():
        commands = []
        if isinstance(handlers, list):
            for h in handlers:
                if isinstance(h, dict):
                    hooks = h.get("hooks", [h])
                    for sub in hooks:
                        if isinstance(sub, dict) and sub.get("type") == "command" and sub.get("command"):
                            commands.append(str(sub["command"]))
                        elif isinstance(sub, dict) and sub.get("type") != "command":
                            logger.warning("G6: handler type %s skipped (command-only)", sub.get("type"))
        if not commands:
            continue
        if resolve_phase(event, source) is None:
            unmapped.append(event)
            continue
        events[event] = commands

    return {"events": events, "source": source, "unmapped": unmapped, "path": str(p) if path is None or Path(path).expanduser().exists() else path}


def _run_command(command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
    """执行 command handler：shell=False 拆词、超时、stderr 捕获、fail-open。

    返回结构化结果（对齐 syscall 可观测：ok/error/耗时）。
    """
    import shlex

    argv = shlex.split(command)
    if not argv:
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": "empty command", "elapsed": 0.0}
    try:
        import time

        start = time.monotonic()
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        elapsed = time.monotonic() - start
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-2000:],
            "stderr": (proc.stderr or "")[-2000:],
            "elapsed": round(elapsed, 3),
        }
    except subprocess.TimeoutExpired as e:
        logger.warning("G6: command timed out after %ss: %s", COMMAND_TIMEOUT_SECONDS, command)
        return {"ok": False, "exit_code": -1, "stdout": "", "stderr": f"timeout after {COMMAND_TIMEOUT_SECONDS}s", "elapsed": COMMAND_TIMEOUT_SECONDS}
    except FileNotFoundError:
        logger.warning("G6: command not found (fail-open): %s", argv[0])
        return {"ok": False, "exit_code": 127, "stdout": "", "stderr": f"command not found: {argv[0]}", "elapsed": 0.0}
    except Exception as e:  # noqa: BLE001 — best-effort 审计，fail-open
        logger.warning("G6: command failed (fail-open): %s", e)
        return {"ok": False, "exit_code": -1, "stdout": "", "stderr": str(e)[:300], "elapsed": 0.0}


class CCHookBridge(Hook):
    """把 CC/Codex 外部事件包装成 aiPlat Hook（command handler 执行器）。"""

    def __init__(self, name: str, command: str, phase: HookPhase, repo_root: Optional[str] = None, priority: int = 0):
        super().__init__(name=name, callback=self._run, phase=phase, priority=priority)
        self.command = command
        self.repo_root = repo_root

    async def _run(self, context: HookContext) -> Dict[str, Any]:
        result = await asyncio.to_thread(_run_command, self.command, self.repo_root)
        if not result.get("ok"):
            logger.warning("G6: hook %s exited %s (fail-open): %s", self.name, result.get("exit_code"), result.get("stderr"))
        # CC 语义 {"continue": false} / updatedInput 记日志不生效（对齐 DSH 限制披露）
        return {"continue": True, "cc_bridge": result}


def register_cc_hooks(hook_manager: HookManager, repo_root: Optional[str] = None) -> Dict[str, Any]:
    """解析 hooks.json 并把 command handlers 注册进 HookManager。

    返回统计（loaded/events/unmapped/errors），供启动日志与测试断言。
    """
    try:
        parsed = load_hooks_json()
    except Exception as e:  # noqa: BLE001 — 配置损坏不阻断启动
        logger.warning("G6: hooks.json load failed (skip): %s", e)
        return {"enabled": True, "loaded": 0, "events": 0, "unmapped": [], "errors": [str(e)[:200]]}

    if not parsed.get("events"):
        return {"enabled": True, "loaded": 0, "events": 0, "unmapped": parsed.get("unmapped", []), "errors": []}

    source = parsed.get("source", "cc")
    loaded = 0
    for event, commands in parsed["events"].items():
        phase = resolve_phase(event, source)
        if phase is None:
            continue
        for i, cmd in enumerate(commands):
            hook = CCHookBridge(
                name=f"cc_bridge:{event}:{i}",
                command=cmd,
                phase=phase,
                repo_root=repo_root,
            )
            hook_manager.register(hook)
            loaded += 1
    logger.info("G6: registered %d cc/codex command hooks (source=%s, unmapped=%d)", loaded, source, len(parsed.get("unmapped", [])))
    return {"enabled": True, "loaded": loaded, "events": len(parsed["events"]), "unmapped": parsed.get("unmapped", []), "errors": []}


def load_cc_hooks_if_configured(hook_manager: HookManager) -> Dict[str, Any]:
    """HookManager 初始化入口：配置存在时才装载（默认关，env 可控）。

    生产 caller：hook_manager.HookManager.__init__（见 hook_manager.py）。
    """
    if _config_path() is None:
        return {"enabled": False, "loaded": 0, "events": 0, "unmapped": [], "errors": []}
    return register_cc_hooks(hook_manager)
