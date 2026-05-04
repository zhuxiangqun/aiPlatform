from __future__ import annotations

from typing import Any, Dict

from core.apps.skills.base import BaseSkill
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult


class KBQuerySkill(BaseSkill):
    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        tenant_id = str(params.get("tenant_id") or "").strip() or str(context.tenant_id or "default")
        collection_id = str(params.get("collection_id") or "").strip() or "default"
        question = str(params.get("question") or "").strip()
        year = params.get("year", None)
        year = int(year) if year is not None and str(year).strip() else None
        limit = int(params.get("limit") or 50)

        if not question:
            return SkillResult(success=False, error="question_required")

        try:
            from core.apps.multimodal_kb.service import query

            out = query(tenant_id=tenant_id, collection_id=collection_id, question=question, year=year, limit=limit)
            return SkillResult(success=True, output=out, metadata={"category": "knowledge"})
        except Exception as e:
            return SkillResult(success=False, error=str(e))


def build_skill(*args, **kwargs):
    cfg = SkillConfig(
        name="kb_query",
        description="多模态知识库查询（MVP）：支持“投资预算”类问答，返回结构化条目与 citations（bbox/页码）。",
        input_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "租户ID（多租户隔离）"},
                "collection_id": {"type": "string", "description": "知识库集合ID（默认 default）"},
                "question": {"type": "string", "description": "问题，例如：2026年投资预算是哪些？"},
                "year": {"type": "integer", "description": "可选：指定年度（默认从问题推断，缺省为 2026）"},
                "limit": {"type": "integer", "description": "返回条数上限（默认 50）"},
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
            },
        },
        metadata={
            "category": "knowledge",
            "version": "0.1.0",
            "skill_kind": "executable",
            "permissions": ["kb:read"],
            "auto_trigger_allowed": True,
            "requires_approval": False,
        },
    )
    return KBQuerySkill(cfg)

