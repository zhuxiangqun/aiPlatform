"""
Toolset governance (Phase R2).

Goal:
- Provide a *runtime* allowlist of tools that the agent loop can use.
- Provide minimal per-tool argument restrictions (initially: file_operations).

This is inspired by Hermes' "toolsets" approach: tools are grouped into
capability packs, and the runtime enforces what is available rather than
trusting UI configuration alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass(frozen=True)
class ToolsetPolicy:
    name: str
    description: str
    # Explicit allowlist of tool names.
    allowed_tools: Set[str] = field(default_factory=set)
    # Allowed tool name prefixes (for dynamic tools like mcp.<server>.*).
    allowed_prefixes: Set[str] = field(default_factory=set)
    # Per-tool restrictions (best-effort; enforced in sys_tool_call).
    file_operations_allowed_ops: Optional[Set[str]] = None
    repo_allowed_ops: Optional[Set[str]] = None


# NOTE: These tool names must match ToolConfig.name in core/apps/tools/*
DEFAULT_TOOLSETS: Dict[str, ToolsetPolicy] = {
    # Minimal safe toolset: local read/list only + low-risk utilities.
    "safe_readonly": ToolsetPolicy(
        name="safe_readonly",
        description="只读安全工具集：允许读取/列出文件与低风险工具，禁止写入/删除与高风险网络/代码执行",
        allowed_tools={"calculator", "search", "file_operations", "webfetch", "repo"},
        file_operations_allowed_ops={"read", "list"},
        repo_allowed_ops={"status", "diff", "log", "ls_files", "show", "branch_list"},
    ),
    # Default workspace toolset: allow write but still blocks dangerous tools by default.
    "workspace_default": ToolsetPolicy(
        name="workspace_default",
        description="工作区默认工具集：允许文件读写（含 patch/删除），以及基础 webfetch/search；不含 http/browser/code/database",
        allowed_tools={"calculator", "search", "file_operations", "webfetch", "repo"},
        file_operations_allowed_ops={"read", "list", "write", "delete"},
        # repo tool is allowed for read-only developer introspection
        repo_allowed_ops={"status", "diff", "log", "ls_files", "show", "branch_list"},
    ),
    # Full toolset (explicit opt-in).
    "full": ToolsetPolicy(
        name="full",
        description="全量工具集（高风险）：包含 http/browser/code/database；仅在显式选择时启用",
        allowed_tools={
            "calculator",
            "search",
            "file_operations",
            "webfetch",
            "http",
            "browser",
            "code",
            "database",
            "repo",
        },
        file_operations_allowed_ops={"read", "list", "write", "delete"},
    ),
    # Capability packs (Roadmap-2) - more explicit UX-friendly names.
    "write_repo": ToolsetPolicy(
        name="write_repo",
        description="仓库写入工具集：允许 file_operations 写/删（适用于生成补丁、批量改动）",
        allowed_tools={"file_operations", "calculator", "repo"},
        file_operations_allowed_ops={"read", "list", "write", "delete"},
        repo_allowed_ops={
            "status",
            "diff",
            "log",
            "ls_files",
            "show",
            "branch_list",
            "branch_create",
            "checkout",
            "add",
            "unstage",
            "restore",
            "commit",
        },
    ),
    "web": ToolsetPolicy(
        name="web",
        description="网络信息工具集：允许 webfetch/search（不含 browser 自动化）",
        allowed_tools={"webfetch", "search", "calculator"},
    ),
    "browser": ToolsetPolicy(
        name="browser",
        description="浏览器自动化工具集（高风险）：允许 browser/http（如启用）",
        allowed_tools={"browser", "http", "webfetch", "search", "calculator"},
    ),
    "mcp_readonly": ToolsetPolicy(
        name="mcp_readonly",
        description="MCP 只读工具集：允许 mcp.* 动态工具（受 allowed_tools 及审批策略约束）",
        allowed_prefixes={"mcp."},
        allowed_tools={"calculator"},
    ),
}


def resolve_toolset(name: Optional[str]) -> ToolsetPolicy:
    """Resolve toolset by name. Falls back to workspace_default."""
    if not name:
        return DEFAULT_TOOLSETS["workspace_default"]
    return DEFAULT_TOOLSETS.get(str(name), DEFAULT_TOOLSETS["workspace_default"])


def should_apply_toolset(name: Optional[str]) -> bool:
    """
    Whether we should auto-inject tools based on a toolset.

    - If the caller explicitly provides toolset → apply.
    - Otherwise keep behavior opt-in via env in integration layer.
    """
    return bool(name)


def is_tool_allowed(policy: ToolsetPolicy, tool_name: str, tool_args: Optional[Dict[str, Any]] = None) -> tuple[bool, Optional[str]]:
    """Return (allowed, reason)."""
    if tool_name not in policy.allowed_tools:
        # allow prefixes (for dynamic tools)
        if not any(tool_name.startswith(pfx) for pfx in (policy.allowed_prefixes or set())):
            return False, f"Tool '{tool_name}' is not allowed in toolset '{policy.name}'"

    if tool_name == "file_operations" and policy.file_operations_allowed_ops is not None:
        op = None
        if isinstance(tool_args, dict):
            op = tool_args.get("operation") or tool_args.get("op")
        if op and str(op) not in policy.file_operations_allowed_ops:
            return (
                False,
                f"file_operations operation '{op}' is not allowed in toolset '{policy.name}'",
            )

    if tool_name == "repo" and policy.repo_allowed_ops is not None:
        op = None
        if isinstance(tool_args, dict):
            op = tool_args.get("operation") or tool_args.get("op")
        if op and str(op) not in policy.repo_allowed_ops:
            return (
                False,
                f"repo operation '{op}' is not allowed in toolset '{policy.name}'",
            )

    return True, None
