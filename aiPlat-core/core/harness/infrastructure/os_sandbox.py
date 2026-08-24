"""
OS 原生沙箱执行器（P1, 对标 Codex sandboxing crate）。

提供 bubblewrap (Linux) / seatbelt (macOS) 可选命令包装器——在现有 subprocess
调用链外加一层 OS 级隔离（只读系统路径 + 可写工作区 + 网络白名单），
保留无 bwrap/seatbelt 环境下的 fail-open fallback（直接执行）。

用法：
    cmd = build_os_sandbox_cmd(["python3", "main.py"], workdir="/tmp/proj", network=False)
    # → ["bwrap", "--ro-bind", "/usr", "/usr", ..., "python3", "main.py"] 或原命令（fallback）

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

# 环境开关：AIPLAT_SANDBOX=bwrap → 强制 bubblewrap；=seatbelt → macOS；空/off → 不启用
ENV_SANDBOX = "AIPLAT_SANDBOX"
# 只读挂载的系统路径（bwrap --ro-bind：宿主机路径 → 容器内路径）
_DEFAULT_RO_PATHS: List[str] = [
    "/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc/ssl", "/etc/alternatives",
]
# 可写白名单（工作区 + 临时目录；其余默认只读/隔离）
_DEFAULT_TMP_WRITE: List[str] = ["/tmp", "/var/tmp"]


@dataclass
class SandboxMode:
    """当前可用的 OS 沙箱模式。"""
    kind: str          # "bwrap" | "seatbelt" | "none"
    available: bool    # 该模式的二进制是否存在
    enabled: bool      # 用户是否启用（AIPLAT_SANDBOX 匹配）

    @property
    def active(self) -> bool:
        """是否实际启用（可用 + 用户启用）。"""
        return self.available and self.enabled


def detect_sandbox_mode() -> SandboxMode:
    """探测当前平台可用的 OS 沙箱（bwrap/seatbelt）+ 用户开关。"""
    requested = (os.environ.get(ENV_SANDBOX, "") or "").strip().lower()
    want = requested in {"bwrap", "seatbelt"} and requested
    bwrap = shutil.which("bwrap") is not None
    seatbelt = shutil.which("sandbox-exec") is not None

    if want == "bwrap" or (not want and bwrap):
        kind, available = "bwrap", bwrap
    elif want == "seatbelt" or (not want and seatbelt):
        kind, available = "seatbelt", seatbelt
    else:
        kind, available = "none", False
    enabled = bool(want) or requested in {"bwrap", "seatbelt", "auto"}
    return SandboxMode(kind=kind, available=available, enabled=enabled)


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
    # 只读挂载系统路径（防止篡改系统文件）
    for p in sorted(set(ro)):
        if os.path.isdir(p):
            args += ["--ro-bind", p, p]
    # 可写工作区 + tmp
    for p in sorted(set(write)):
        if os.path.isdir(p):
            args += ["--bind", p, p]
    # 基本设备（/dev 空 + 无网络设备）
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
) -> List[str]:
    """把命令包装进 OS 沙箱；无可用沙箱时返回原命令（fail-open fallback）。

    :param cmd: 原始命令（argv 列表）
    :param workdir: 可写工作区路径（沙箱内可写）
    :param network: 是否允许网络（默认隔离）
    :param mode: 沙箱模式（默认探测）
    :return: 包装后的命令；若 mode.active=False 返回原 cmd
    """
    mode = mode or detect_sandbox_mode()
    if not mode.active:
        return list(cmd)
    if mode.kind == "bwrap":
        return _bwrap_args(workdir, network) + list(cmd)
    if mode.kind == "seatbelt":
        return _seatbelt_args(workdir, network) + list(cmd)
    return list(cmd)


def sandbox_env_ready() -> Dict[str, object]:
    """诊断信息：当前沙箱模式/可用性/激活状态。"""
    mode = detect_sandbox_mode()
    return {
        "mode": mode.kind,
        "available": mode.available,
        "enabled": mode.enabled,
        "active": mode.active,
        "env": ENV_SANDBOX,
    }
