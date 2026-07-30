"""
PurposeRegistry — 数据使用目的注册中心 (Palantir Security 3D — Purpose 维度)

定义每个 Purpose 对可用工具、数据操作和敏感数据访问的限制:

  每个 Purpose 包含:
    - tool_whitelist: 该目的下允许使用的工具集合
    - action_whitelist: 该目的下允许执行的 action 类型
    - max_marking_level: 允许访问的最高 Marking 级别
    - require_approval: 是否强制审批
    - description: 人类可读说明

默认: "general" purpose = 无限制 (向后兼容)
环境变量: AIPLAT_REQUIRE_PURPOSE=true → 强制每次操作声明 Purpose

调用者: PolicyGate.check_tool_3d() → 运行时三维权限计算
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Marking Level (from knowledge_markings) ──────────────────────────────

try:
    from core.harness.knowledge.knowledge_markings import MarkingLevel
    PUBLIC = MarkingLevel.PUBLIC
    INTERNAL = MarkingLevel.INTERNAL
    CONFIDENTIAL = MarkingLevel.CONFIDENTIAL
    RESTRICTED = MarkingLevel.RESTRICTED
except ImportError:
    class MarkingLevel:
        PUBLIC = 1
        INTERNAL = 2
        CONFIDENTIAL = 3
        RESTRICTED = 4


# ── Purpose Definitions ───────────────────────────────────────────────────

@dataclass
class Purpose:
    """单个目的定义."""
    purpose_id: str
    label: str
    description: str
    tool_whitelist: Set[str] = field(default_factory=set)       # 允许的工具名集合
    action_whitelist: Set[str] = field(default_factory=set)     # 允许的 action 类型
    max_marking_level: int = MarkingLevel.PUBLIC                 # 最高可访问 Marking
    require_approval: bool = False                               # 是否强制审批
    allowed_roles: Set[str] = field(default_factory=set)         # 允许的角色

    def to_dict(self) -> Dict[str, Any]:
        return {
            "purpose_id": self.purpose_id,
            "label": self.label,
            "description": self.description,
            "tool_whitelist": sorted(self.tool_whitelist),
            "action_whitelist": sorted(self.action_whitelist),
            "max_marking_level": self.max_marking_level,
            "require_approval": self.require_approval,
            "allowed_roles": sorted(self.allowed_roles),
        }


# ── Built-in Purposes ────────────────────────────────────────────────────

_BUILTIN_PURPOSES: Dict[str, Purpose] = {
    "general": Purpose(
        purpose_id="general",
        label="通用操作",
        description="无限制的通用操作 (默认)",
        tool_whitelist=set(),               # 空=全部允许
        action_whitelist=set(),
        max_marking_level=MarkingLevel.RESTRICTED,
        require_approval=False,
    ),
    "diagnosis": Purpose(
        purpose_id="diagnosis",
        label="诊断分析",
        description="运行诊断、查看系统状态、分析日志",
        tool_whitelist={
            "sys_code_intel_context", "sys_code_intel_blast",
            "sys_wiki_context", "sys_wiki_retrieve",
            "sys_knowledge_retrieve", "file_read",
            "sys_glob", "code_search",
        },
        action_whitelist={"read", "read_body", "cite"},
        max_marking_level=MarkingLevel.CONFIDENTIAL,
        require_approval=False,
    ),
    "deployment": Purpose(
        purpose_id="deployment",
        label="部署发布",
        description="打包、部署、灰度发布、配置更新",
        tool_whitelist={
            "file_write", "file_edit", "shell_exec",
            "sys_skill_call", "sys_tool_call",
            "code_execute",
        },
        action_whitelist={"update", "state_change"},
        max_marking_level=MarkingLevel.CONFIDENTIAL,
        require_approval=True,
        allowed_roles={"admin", "developer", "fde"},
    ),
    "knowledge_gen": Purpose(
        purpose_id="knowledge_gen",
        label="知识生产",
        description="文档上传、实体抽取、本体编辑、Wiki 写入",
        tool_whitelist={
            "file_write", "file_edit", "sys_knowledge_retrieve",
            "sys_wiki_context", "sys_wiki_retrieve",
        },
        action_whitelist={"read", "read_body", "update", "state_change"},
        max_marking_level=MarkingLevel.RESTRICTED,
        require_approval=False,
        allowed_roles={"admin", "developer"},
    ),
    "audit_review": Purpose(
        purpose_id="audit_review",
        label="审计审查",
        description="查看审计日志、合规检查、安全审查",
        tool_whitelist={
            "file_read", "sys_knowledge_retrieve",
            "sys_code_intel_context",
        },
        action_whitelist={"read", "read_body", "cite"},
        max_marking_level=MarkingLevel.RESTRICTED,
        require_approval=False,
        allowed_roles={"admin", "approver"},
    ),
    "training": Purpose(
        purpose_id="training",
        label="培训沙盒",
        description="在隔离沙盒中运行培训和实验",
        tool_whitelist={
            "file_read", "file_write", "sys_knowledge_retrieve",
            "sys_skill_call",
        },
        action_whitelist={"read", "read_body", "update"},
        max_marking_level=MarkingLevel.INTERNAL,
        require_approval=False,
        allowed_roles={"admin", "developer", "user", "fde"},
    ),
}


# ── PurposeRegistry ───────────────────────────────────────────────────────

class PurposeRegistry:
    """目的注册中心.

    使用方式:
        registry = PurposeRegistry.get()
        purpose = registry.get("diagnosis")
        allowed = registry.check_tool("diagnosis", "file_write")  # → False
    """

    _instance: Optional["PurposeRegistry"] = None

    def __init__(self):
        self._purposes: Dict[str, Purpose] = dict(_BUILTIN_PURPOSES)

    @classmethod
    def get(cls) -> "PurposeRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get(self, purpose_id: str) -> Optional[Purpose]:
        """获取 Purpose 定义. 默认返回 general."""
        return self._purposes.get(purpose_id) or self._purposes.get("general")

    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有已注册的 Purpose."""
        return [p.to_dict() for p in self._purposes.values()]

    def register(self, purpose: Purpose) -> None:
        """注册自定义 Purpose (运行时可扩展)."""
        self._purposes[purpose.purpose_id] = purpose
        logger.info("Registered purpose: %s", purpose.purpose_id)

    def check_tool(
        self,
        purpose_id: str,
        tool_name: str,
        *,
        role: str = "",
        marking_level: int = MarkingLevel.PUBLIC,
    ) -> Dict[str, Any]:
        """检查该 Purpose 下是否允许使用指定工具.

        Returns:
            {"allowed": bool, "reason": str, "require_approval": bool}
        """
        purpose = self.get(purpose_id)
        if purpose is None:
            return {"allowed": False, "reason": f"Unknown purpose: {purpose_id}", "require_approval": False}

        # Check role
        if purpose.allowed_roles and role and role not in purpose.allowed_roles:
            return {
                "allowed": False,
                "reason": f"Role '{role}' not allowed for purpose '{purpose_id}' (allowed: {sorted(purpose.allowed_roles)})",
                "require_approval": False,
            }

        # Check tool whitelist (empty = allow all)
        if purpose.tool_whitelist and tool_name not in purpose.tool_whitelist:
            return {
                "allowed": False,
                "reason": f"Tool '{tool_name}' not allowed for purpose '{purpose_id}'",
                "require_approval": False,
            }

        # Check marking level
        if marking_level > purpose.max_marking_level:
            return {
                "allowed": False,
                "reason": f"Marking level {marking_level} exceeds max allowed {purpose.max_marking_level} for purpose '{purpose_id}'",
                "require_approval": False,
            }

        return {
            "allowed": True,
            "reason": "allowed",
            "require_approval": purpose.require_approval,
        }

    def check_action(
        self,
        purpose_id: str,
        action: str,
    ) -> Dict[str, Any]:
        """检查该 Purpose 下是否允许执行指定 action."""
        purpose = self.get(purpose_id)
        if purpose is None:
            return {"allowed": False, "reason": f"Unknown purpose: {purpose_id}", "require_approval": False}

        if purpose.action_whitelist and action not in purpose.action_whitelist:
            return {
                "allowed": False,
                "reason": f"Action '{action}' not allowed for purpose '{purpose_id}'",
                "require_approval": False,
            }

        return {
            "allowed": True,
            "reason": "allowed",
            "require_approval": purpose.require_approval,
        }


# ── Convenience ───────────────────────────────────────────────────────────

def get_purpose_registry() -> PurposeRegistry:
    """全局单例获取."""
    return PurposeRegistry.get()
