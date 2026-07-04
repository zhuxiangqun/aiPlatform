from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from core.harness.utils.model_injection import best_model_for_purpose


async def _llm_classify_intent(question: str) -> str:
    """Classify question intent via LLM (more accurate than regex for edge cases).
    Falls back to regex on error."""
    if len(question) < 5:
        return _detect_intent(question)
    try:
        from core.harness.syscalls.llm import sys_llm_generate
        prompt = (
            "将以下用户问题分类为以下意图之一：fact_lookup, summary, compare, "
            "evidence_trace, applicability_analysis, follow_up。"
            "只输出意图名称，不要输出其他内容。\n\n问题：" + question
        )
        resp = await sys_llm_generate(
            None, [{"role": "user", "content": prompt}],
            model_name=best_model_for_purpose("chat"), temperature=0.0, max_tokens=20,
        )
        result = (getattr(resp, "content", "") or str(resp)).strip().lower()
        valid = {"fact_lookup", "summary", "compare", "evidence_trace", "applicability_analysis", "follow_up"}
        return result if result in valid else _detect_intent(question)
    except Exception:
        return _detect_intent(question)


def _detect_intent(question: str) -> str:
    q = str(question or "").strip()
    if re.search(r"刚才|上面|前面|第二点|第三点|展开|继续说|重新回答|只看|基于刚才", q):
        return "follow_up"
    if re.search(r"借鉴意义|适合我吗|适用于|适合我们|对我的系统|对我们系统|有什么启发", q):
        return "applicability_analysis"
    if re.search(r"比较|差异|区别|共同点|异同|分别|优劣", q):
        return "compare"
    if re.search(r"依据|证据|哪一页|哪段|哪里提到|引用|出处", q):
        return "evidence_trace"
    if re.search(r"总结|概括|核心内容|关键信息|主要讲了什么|梳理|说了什么", q):
        return "summary"
    return "fact_lookup"


def _detect_entity_sensitive(question: str) -> bool:
    q = str(question or "").strip()
    return bool(re.search(r"谁|叫什么|名字|姓名|哪一年|什么时候|哪个公司|哪个学校|金额|多少|数字|地址|电话|邮箱", q))


def _detect_follow_up(question: str, recent_turn_summaries: Optional[List[str]] = None) -> bool:
    q = str(question or "").strip()
    if re.search(r"刚才|上面|前面|第二点|第三点|展开|继续说|重新回答|只看|上一条|前一条", q):
        return True
    return bool((recent_turn_summaries or []) and re.search(r"这个|这个结论|这一点|这部分|这个视频|这个资料", q))


def _detect_dominant_doc_kind(doc_kinds: Optional[List[str]]) -> str:
    kinds = [str(x).strip().lower() for x in (doc_kinds or []) if str(x).strip()]
    if not kinds:
        return ""
    if len(set(kinds)) == 1:
        return kinds[0]
    if "video" in kinds:
        return "mixed_video"
    return "mixed"


def _detect_evidence_granularity(intent: str, question: str, entity_sensitive: bool) -> str:
    if intent in ("summary",):
        return "coarse"
    if intent in ("compare", "applicability_analysis", "follow_up"):
        return "mixed"
    if intent in ("evidence_trace",):
        return "fine"
    if entity_sensitive:
        return "fine"
    q = str(question or "").strip()
    if len(q) <= 18:
        return "fine"
    return "mixed"


def _detect_answer_shape(intent: str, granularity: str) -> str:
    if intent == "summary":
        return "grounded_summary"
    if intent == "compare":
        return "comparative_analysis"
    if intent == "evidence_trace":
        return "evidence_first"
    if intent == "applicability_analysis":
        return "conditional_analysis"
    if granularity == "fine":
        return "short_grounded"
    return "grounded_summary"


async def analyze_question(
    *,
    question: str,
    scope: Optional[Dict[str, Any]] = None,
    recent_turn_summaries: Optional[List[str]] = None,
    doc_kinds: Optional[List[str]] = None,
) -> Dict[str, Any]:
    intent = await _llm_classify_intent(question)  # LLM first, regex fallback
    follow_up = _detect_follow_up(question, recent_turn_summaries)
    entity_sensitive = _detect_entity_sensitive(question)
    granularity = _detect_evidence_granularity(intent, question, entity_sensitive)
    answer_shape = _detect_answer_shape(intent, granularity)
    doc_ids = [str(x).strip() for x in ((scope or {}).get("doc_ids") or []) if str(x).strip()]
    dominant_doc_kind = _detect_dominant_doc_kind(doc_kinds)
    matched_rules: List[str] = [intent, f"granularity:{granularity}", f"answer:{answer_shape}"]
    if entity_sensitive:
        matched_rules.append("entity_sensitive")
    if follow_up:
        matched_rules.append("follow_up")
    if dominant_doc_kind:
        matched_rules.append(f"doc_kind:{dominant_doc_kind}")
    return {
        "intent": intent,
        "evidence_granularity": granularity,
        "answer_shape": answer_shape,
        "follow_up": follow_up,
        "entity_sensitive": entity_sensitive,
        "multi_doc": len(doc_ids) > 1,
        "dominant_doc_kind": dominant_doc_kind,
        "confidence": 0.75,
        "signals": {
            "matched_rules": matched_rules,
            "question_length": len(str(question or "").strip()),
            "doc_count": len(doc_ids),
        },
    }
