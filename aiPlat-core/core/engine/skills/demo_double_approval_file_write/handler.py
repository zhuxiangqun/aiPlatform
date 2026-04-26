from __future__ import annotations

from typing import Dict, Any

from core.apps.skills.base import BaseSkill
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult
from core.harness.syscalls import sys_tool_call
from core.apps.tools.base import FileOperationsTool


class DemoDoubleApprovalFileWriteSkill(BaseSkill):
    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        path = str(params.get("path") or "").strip()
        content = str(params.get("content") or "")
        if not path:
            return SkillResult(success=False, error="path_required")

        tool_args = {
            "operation": "write",
            "path": path,
            "content": content,
            # Always request tool-level approval (to validate approval layering strategies).
            "_approval_required": True,
        }
        tool = FileOperationsTool()
        res = await sys_tool_call(
            tool,
            tool_args,
            user_id=getattr(context, "user_id", "system") or "system",
            session_id=getattr(context, "session_id", "default") or "default",
            trace_context={},
        )
        if not getattr(res, "success", False):
            return SkillResult(success=False, error=str(getattr(res, "error", None) or "tool_failed"), metadata=getattr(res, "metadata", None))
        return SkillResult(success=True, output=getattr(res, "output", None) or {})


def build_skill(*_args, **_kwargs):
    return DemoDoubleApprovalFileWriteSkill(
        SkillConfig(
            name="demo_double_approval_file_write",
            description="同时触发 skill/tool 双层审批（示范）",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "bytes_written": {"type": "integer"},
                    "sha256": {"type": "string"},
                },
            },
            metadata={
                "category": "execution",
                "risk_level": "high",
                "requires_approval": True,
            },
        )
    )
