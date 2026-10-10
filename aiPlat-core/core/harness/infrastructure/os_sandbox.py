"""
OS 原生沙箱执行器（P1, 对标 Codex sandboxing crate）。

提供 bubblewrap (Linux) / seatbelt (macOS) 可选命令包装器——在现有 subprocess
调用链外加一层 OS 级隔离（只读系统路径 + 可写工作区 + 网络白名单）。

策略（harness 文章 · 生产收紧）：
  - 开发默认：未设 AIPLAT_SANDBOX → 不强制；无沙箱时 fail-open（原命令）
  - AIPLAT_PROFILE=production：自动启用平台可用沙箱；不可用时 fail-closed
  - 紧急逃生：AIPLAT_SANDBOX_FAIL_OPEN=true（仅运维）

用法：
    cmd = build_os_sandbox_cmd(["python3", "main.py"], workdir="/tmp/proj", network=False)
    # → ["bwrap", ...] 或 seatbelt；生产无沙箱 → SandboxRequiredError

设计依据：docs/research/Codex-Harness开源借鉴分析报告.md §2.4 (P1)
参考实现：codex-rs/bwrap/ + codex-rs/sandboxing/（Landlock/seccomp/Seatbelt）
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 环境开关：AIPLAT_SANDBOX=bwrap|seatbelt|auto|on|off
ENV_SANDBOX = "AIPLAT_SANDBOX"
ENV_PROFILE = "AIPLAT_PROFILE"
ENV_FAIL_CLOSED = "AIPLAT_SANDBOX_FAIL_CLOSED"
ENV_FAIL_OPEN = "AIPLAT_SANDBOX_FAIL_OPEN"

# 只读挂载的系统路径（bwrap --ro-bind：宿主机路径 → 容器内路径）
_DEFAULT_RO_PATHS: List[str] = [
    "/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc/ssl", "/etc/alternatives",
]
# 可写白名单（工作区 + 临时目录；其余默认只读/隔离）
_DEFAULT_TMP_WRITE: List[str] = ["/tmp", "/var/tmp"]

_OFF_VALUES = frozenset({"off", "0", "false", "no", "none", "disabled"})
_ON_VALUES = frozenset({"auto", "on", "1", "true", "yes", "y"})


class SandboxRequiredError(RuntimeError):
    """OS sandbox required (production / fail-closed) but not active."""


@dataclass
class SandboxMode:
    """当前可用的 OS 沙箱模式。"""
    kind: str          # "bwrap" | "seatbelt" | "none"
    available: bool    # 该模式的二进制是否存在
    enabled: bool      # 策略是否要求启用

    @property
    def active(self) -> bool:
        """是否实际启用（可用 + 策略启用）。"""
        return self.available and self.enabled


def is_production_profile() -> bool:
    return (os.environ.get(ENV_PROFILE) or "").strip().lower() == "production"


def sandbox_fail_closed() -> bool:
    """Production defaults fail-closed; explicit env overrides either way.

    FAIL_OPEN wins over FAIL_CLOSED (emergency escape hatch).
    """
    fo = (os.environ.get(ENV_FAIL_OPEN) or "").strip().lower()
    if fo in ("1", "true", "yes", "y", "on"):
        return False
    fc = (os.environ.get(ENV_FAIL_CLOSED) or "").strip().lower()
    if fc in ("1", "true", "yes", "y", "on"):
        return True
    if fc in ("0", "false", "no", "n", "off"):
        return False
    return is_production_profile()


def _platform_auto_kind(bwrap: bool, seatbelt: bool) -> tuple:
    """Prefer seatbelt on macOS, bwrap elsewhere; report preferred even if missing."""
    if sys.platform == "darwin":
        if seatbelt:
            return "seatbelt", True
        if bwrap:
            return "bwrap", True
        return "seatbelt", False
    if bwrap:
        return "bwrap", True
    if seatbelt:
        return "seatbelt", True
    return "bwrap", False


def detect_sandbox_mode() -> SandboxMode:
    """探测当前平台可用的 OS 沙箱 + 用户/生产策略开关。"""
    requested = (os.environ.get(ENV_SANDBOX, "") or "").strip().lower()
    bwrap = shutil.which("bwrap") is not None
    seatbelt = shutil.which("sandbox-exec") is not None
    auto_kind, auto_avail = _platform_auto_kind(bwrap, seatbelt)

    if requested in _OFF_VALUES:
        return SandboxMode(kind="none", available=False, enabled=False)

    if requested == "bwrap":
        return SandboxMode(kind="bwrap", available=bwrap, enabled=True)
    if requested == "seatbelt":
        return SandboxMode(kind="seatbelt", available=seatbelt, enabled=True)

    # auto / on / production default → enable preferred kind
    if requested in _ON_VALUES or (not requested and is_production_profile()):
        return SandboxMode(kind=auto_kind, available=auto_avail, enabled=True)

    # Dev default: report preferred kind for diagnostics, keep disabled
    if auto_avail:
        return SandboxMode(kind=auto_kind, available=True, enabled=False)
    return SandboxMode(kind="none", available=False, enabled=False)


def _bwrap_args(
    workdir: str,
    network: bool,
    ro_paths: Optional[List[str]] = None,
    write_paths: Optional[List[str]] = None,
) -> List[str]:
    """构造 bubblewrap 参数：只读系统 + 可写工作区/tmp + 可选网络。"""
    ro = list(ro_paths or _DEFAULT_RO_PATHS)
    write = list(write_paths or []) + list(_DEFAULT_TMP_WRITE)
    if workdir:
        write.append(workdir)

    args: List[str] = [
        "bwrap",
        "--die-with-parent",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--new-session",
    ]
    if not network:
        args += ["--unshare-net"]
    for p in sorted(set(ro)):
        if os.path.isdir(p):
            args += ["--ro-bind", p, p]
    for p in sorted(set(write)):
        if os.path.isdir(p):
            args += ["--bind", p, p]
    args += ["--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp"]
    return args


def _seatbelt_args(workdir: str, network: bool) -> List[str]:
    """构造 macOS seatbelt (sandbox-exec) 参数：读写限制 + 可选网络。"""
    sbpl = f"""
(version 1)
(deny default)
(allow process-exec)
(allow file-read*)
(allow file-write* (subpath "{workdir}") (subpath "/tmp") (subpath "/var/tmp"))
(allow sysctl-read)
"""
    if network:
        sbpl += "(allow network*)\n"
    return ["sandbox-exec", "-p", sbpl]


def build_os_sandbox_cmd(
    cmd: List[str],
    *,
    workdir: str = "",
    network: bool = False,
    mode: Optional[SandboxMode] = None,
    fail_closed: Optional[bool] = None,
) -> List[str]:
    """把命令包装进 OS 沙箱。

    - mode.active → 包装后的 argv
    - 非 active + fail-open（开发默认）→ 原 cmd
    - 非 active + fail-closed（生产默认）→ raise SandboxRequiredError
    """
    mode = mode or detect_sandbox_mode()
    closed = sandbox_fail_closed() if fail_closed is None else bool(fail_closed)
    if mode.active:
        if mode.kind == "bwrap":
            return _bwrap_args(workdir, network) + list(cmd)
        if mode.kind == "seatbelt":
            return _seatbelt_args(workdir, network) + list(cmd)
        return list(cmd)
    if closed:
        raise SandboxRequiredError(
            "OS sandbox required but not active "
            f"(kind={mode.kind} available={mode.available} enabled={mode.enabled} "
            f"profile={os.environ.get(ENV_PROFILE) or '(unset)'}). "
            "Install bwrap/sandbox-exec and set AIPLAT_SANDBOX=auto|bwrap|seatbelt, "
            "or set AIPLAT_SANDBOX_FAIL_OPEN=true for emergency unsandboxed run."
        )
    return list(cmd)


def sandbox_env_ready() -> Dict[str, object]:
    """诊断信息：当前沙箱模式/可用性/激活状态 + 生产收紧策略。"""
    mode = detect_sandbox_mode()
    closed = sandbox_fail_closed()
    return {
        "mode": mode.kind,
        "available": mode.available,
        "enabled": mode.enabled,
        "active": mode.active,
        "env": ENV_SANDBOX,
        "profile": (os.environ.get(ENV_PROFILE) or "").strip().lower() or "(unset)",
        "fail_closed": closed,
        "production_tightened": bool(is_production_profile() and closed),
    }
