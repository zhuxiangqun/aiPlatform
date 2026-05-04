from __future__ import annotations

from typing import Any, Dict

from core.apps.skills.base import BaseSkill
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult


class DocSummarizeSkill(BaseSkill):
    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        tenant_id = str(params.get("tenant_id") or "").strip() or str(context.tenant_id or "default")
        collection_id = str(params.get("collection_id") or "").strip() or "default"
        doc_id = str(params.get("doc_id") or "").strip()
        profile = str(params.get("profile") or "key_points").strip()
        max_points = int(params.get("max_points") or 10)

        if not doc_id:
            return SkillResult(success=False, error="doc_id_required")

        try:
            from core.apps.document_intelligence.summarize import summarize_document

            out = summarize_document(
                tenant_id=tenant_id,
                collection_id=collection_id,
                doc_id=doc_id,
                profile=profile,
                max_points=max_points,
            )
            return SkillResult(success=True, output=out, metadata={"category": "document"})
        except Exception as e:
            return SkillResult(success=False, error=str(e))


def build_skill(*args, **kwargs):
    cfg = SkillConfig(
        name="doc_summarize",
        description="通用资料总结（MVP）：基于 kb_elements 生成核心要点与引用。",
        input_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "collection_id": {"type": "string"},
                "doc_id": {"type": "string"},
                "profile": {"type": "string"},
                "max_points": {"type": "integer"},
            },
            "required": ["doc_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "points": {"type": "array", "items": {"type": "object"}},
                "citations": {"type": "array", "items": {"type": "object"}},
                "tenant_id": {"type": "string"},
                "collection_id": {"type": "string"},
                "doc_id": {"type": "string"},
            },
        },
        metadata={
            "category": "document",
            "version": "0.1.0",
            "skill_kind": "executable",
            "permissions": ["doc:read"],
            "auto_trigger_allowed": True,
            "requires_approval": False,
        },
    )
    return DocSummarizeSkill(cfg)

