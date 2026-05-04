from __future__ import annotations

from typing import Any, Dict, List

from core.apps.skills.base import BaseSkill
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult


class AnswerRewriteSkill(BaseSkill):
    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        collection_id = str(params.get("collection_id") or "").strip() or "default"
        question = str(params.get("question") or "").strip()
        current_answer = str(params.get("current_answer") or "").strip()
        items = list(params.get("items") or [])

        if not question:
            return SkillResult(success=False, error="question_required")

        try:
            from core.apps.document_intelligence.llm import chat_complete, llm_enabled
        except Exception as e:
            return SkillResult(success=False, error=f"llm_import_failed:{e}")

        if not llm_enabled():
            return SkillResult(success=False, error="llm_not_enabled")

        evidence_blocks: List[str] = []
        for idx, it in enumerate(items[:6], start=1):
            if not isinstance(it, dict):
                continue
            snippet = str(it.get("snippet") or "").strip()
            if not snippet:
                continue
            evidence_blocks.append(
                f"[依据{idx}] doc={str(it.get('doc_id') or '-')}, page={str(it.get('page_idx') or '-')}, score={str(it.get('score') or '-')}\n{snippet[:1200]}"
            )

        system_prompt = (
            "你是一个企业知识库问答助手。"
            "请把现有检索结果重写成自然、正式、简洁的中文答案。"
            "要求：1) 只依据提供内容，不编造；2) 优先总结业务事实、目标、数字、风险；"
            "3) 输出 2-4 段自然语言，不要使用“根据片段”“命中条目”等调试措辞；"
            "4) 若信息不足，要明确说明不确定。"
        )
        user_prompt = (
            f"问题：{question}\n\n"
            f"当前回答：{current_answer}\n\n"
            f"检索依据：\n{chr(10).join(evidence_blocks) if evidence_blocks else '(none)'}\n\n"
            "请直接输出重写后的正式答案。"
        )
        rewritten = chat_complete(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.2, max_tokens=700)
        if not rewritten:
            return SkillResult(success=False, error="llm_rewrite_failed")

        return SkillResult(
            success=True,
            output={
                "collection_id": collection_id,
                "question": question,
                "rewritten_answer": str(rewritten).strip(),
                "mode": "llm_rewrite",
            },
            metadata={"category": "document"},
        )


def build_skill(*args, **kwargs):
    cfg = SkillConfig(
        name="answer_rewrite",
        description="基于当前问题、原回答和命中片段，使用 LLM 重写为正式自然语言答案。",
        input_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "collection_id": {"type": "string"},
                "question": {"type": "string"},
                "current_answer": {"type": "string"},
                "items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["question"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "collection_id": {"type": "string"},
                "question": {"type": "string"},
                "rewritten_answer": {"type": "string"},
                "mode": {"type": "string"},
            },
        },
        metadata={
            "category": "document",
            "version": "0.1.0",
            "skill_kind": "executable",
            "permissions": ["doc:read"],
            "auto_trigger_allowed": False,
            "requires_approval": False,
        },
    )
    return AnswerRewriteSkill(cfg)
