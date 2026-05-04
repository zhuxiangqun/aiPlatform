from __future__ import annotations

from typing import Any, Dict

from core.apps.skills.base import BaseSkill
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult


class DocQuerySkill(BaseSkill):
    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        tenant_id = (
            str(params.get("tenant_id") or "").strip()
            or str(getattr(context, "tenant_id", "") or "")
            or str((context.metadata or {}).get("tenant_id") or "")
            or "default"
        )
        collection_id = str(params.get("collection_id") or "").strip() or "default"
        doc_id = str(params.get("doc_id") or "").strip() or None
        question = str(params.get("question") or "").strip()
        top_k = int(params.get("top_k") or 8)
        retrieval_policy = params.get("retrieval_policy") or {}

        if not question:
            return SkillResult(success=False, error="question_required")

        try:
            from core.apps.document_intelligence.query import query_elements

            out = query_elements(
                tenant_id=tenant_id,
                collection_id=collection_id,
                doc_id=doc_id,
                question=question,
                top_k=top_k,
                retrieval_policy=retrieval_policy,
            )
            return SkillResult(success=True, output=out, metadata={"category": "document"})
        except Exception as e:
            return SkillResult(success=False, error=str(e))


def build_skill(*args, **kwargs):
    cfg = SkillConfig(
        name="doc_query",
        description="通用资料查询（MVP）：基于 kb_elements 内容检索，返回片段与引用。",
        input_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "collection_id": {"type": "string"},
                "doc_id": {"type": "string"},
                "question": {"type": "string"},
                "top_k": {"type": "integer"},
            },
            "required": ["question"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "items": {"type": "array", "items": {"type": "object"}},
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
    return DocQuerySkill(cfg)
