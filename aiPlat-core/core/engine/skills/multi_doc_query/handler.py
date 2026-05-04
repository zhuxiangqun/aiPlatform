from __future__ import annotations

from typing import Any, Dict, List

from core.apps.skills.base import BaseSkill
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult


class MultiDocQuerySkill(BaseSkill):
    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        tenant_id = (
            str(params.get("tenant_id") or "").strip()
            or str(getattr(context, "tenant_id", "") or "")
            or str((context.metadata or {}).get("tenant_id") or "")
            or "default"
        )
        collection_id = str(params.get("collection_id") or "").strip() or "default"
        question = str(params.get("question") or "").strip()
        doc_ids = [str(x).strip() for x in (params.get("doc_ids") or []) if str(x).strip()]
        top_k = int(params.get("top_k") or 8)
        retrieval_policy = params.get("retrieval_policy") or {}

        if not question:
            return SkillResult(success=False, error="question_required")
        if not doc_ids:
            return SkillResult(success=False, error="doc_ids_required")

        try:
            from core.apps.document_intelligence.query import query_elements

            out = query_elements(
                tenant_id=tenant_id,
                collection_id=collection_id,
                doc_id=None,
                doc_ids=doc_ids,
                question=question,
                top_k=top_k,
                retrieval_policy=retrieval_policy,
            )
            return SkillResult(success=True, output=out, metadata={"category": "document", "doc_count": len(doc_ids)})
        except Exception as e:
            return SkillResult(success=False, error=str(e))


def build_skill(*args, **kwargs):
    cfg = SkillConfig(
        name="multi_doc_query",
        description="多资料统一查询：在指定 doc_ids 范围内检索并返回片段与引用。",
        input_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "collection_id": {"type": "string"},
                "doc_ids": {"type": "array", "items": {"type": "string"}},
                "question": {"type": "string"},
                "top_k": {"type": "integer"},
            },
            "required": ["doc_ids", "question"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "items": {"type": "array", "items": {"type": "object"}},
                "citations": {"type": "array", "items": {"type": "object"}},
                "tenant_id": {"type": "string"},
                "collection_id": {"type": "string"},
                "doc_ids": {"type": "array", "items": {"type": "string"}},
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
    return MultiDocQuerySkill(cfg)
