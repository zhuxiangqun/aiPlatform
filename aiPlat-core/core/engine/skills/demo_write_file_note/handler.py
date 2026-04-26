from __future__ import annotations

import hashlib
from typing import Any, Dict

from core.apps.skills.base import BaseSkill
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult
from core.harness.syscalls.tool import sys_tool_call
from core.apps.tools.base import FileOperationsTool


class DemoWriteFileNoteSkill(BaseSkill):
    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        path = str(params.get("path") or "").strip()
        content = str(params.get("content") or "")
        if not path:
            return SkillResult(success=False, error="path_required")

        # Skill 本身是 requires_approval=true；因此在 approval replay 时，不应再次强制工具审批，避免双重审批。
        require_tool_approval = not bool(params.get("_approval_request_id"))
        tool_args = {
            "operation": "write",
            "path": path,
            "content": content,
            "_approval_required": bool(require_tool_approval),
        }

        tool = FileOperationsTool()
        r = await sys_tool_call(
            tool,
            tool_args,
            user_id=str(context.user_id or "system"),
            session_id=str(context.session_id or "default"),
            trace_context={"_approval_required": True},
        )
        if not getattr(r, "success", False):
            # propagate approval_required/policy_denied
            return SkillResult(
                success=False,
                error=str(getattr(r, "error", None) or "tool_failed"),
                metadata=getattr(r, "metadata", {}) or {},
            )

        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return SkillResult(
            success=True,
            output={"path": path, "bytes_written": len(content.encode("utf-8")), "sha256": sha},
            metadata={"tool": "file_operations"},
        )


def build_skill(*args, **kwargs):
    cfg = SkillConfig(
        name="demo_write_file_note",
        description="将输入内容写入指定路径（示范技能，默认需审批）。",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
        output_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}, "bytes_written": {"type": "integer"}, "sha256": {"type": "string"}},
        },
        metadata={
            "category": "execution",
            "version": "0.1.0",
            "skill_kind": "executable",
            "permissions": ["tool:file_write"],
            "auto_trigger_allowed": False,
            "requires_approval": True,
        },
    )
    return DemoWriteFileNoteSkill(cfg)
