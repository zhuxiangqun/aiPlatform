"""Chinese-language parsing data (regex patterns, stopwords, keywords).

Centralizes Chinese-language-specific constants that the engine needs to parse
Chinese user input. These are LANGUAGE DATA, not business concepts — they are
kept out of the kernel-agnostic execution layer (see CLAUDE.md §5.29) so that
``core/harness/execution/`` stays CJK-free (§78b).

Do NOT translate these — they match Chinese user input.
"""
from __future__ import annotations

from typing import Dict, List, Set

# ── Fact extraction from free-form user messages (loop/_facade.py) ──
FACT_BUDGET_RE = r"预算[是为:：]\s*(\d+)\s*万?"
FACT_NAME_RE = r"(?:我|本人)[叫是称呼为]\s*([\u4e00-\u9fa5a-zA-Z]{2,10})"
FACT_GOAL_RE = r"(?:目标|想|要)[是]?\s*(.{5,50})"

# ── Trigger keywords for proactive goal detection (loop/base.py) ──
TRIGGER_KEYWORDS: List[str] = ["帮我", "优化", "做一个", "能不能", "怎么样", "如何", "帮我写", "帮我设计", "帮我实现"]
PROACTIVE_GOAL_NEGATIVE_ANSWER = "不需要"

# ── Task-continuity stopwords + verdict template (loop/target_continuity.py) ──
TASK_CONTINUITY_STOPWORDS: Set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "and", "but", "or", "nor", "not", "so",
    "yet", "both", "either", "neither", "each", "every", "all", "any",
    "few", "more", "most", "other", "some", "such", "no", "only", "own",
    "same", "than", "too", "very", "just", "because", "about", "over",
    "this", "that", "these", "those", "it", "its", "he", "she", "they",
    "we", "you", "me", "him", "her", "us", "them", "my", "your", "his",
}
TASK_CONTINUITY_VERDICT_TMPL = "LLM裁决: {verdict} (重叠={score:.3f})"

# ── Task-type classification (pattern_cache.py) ──
PATTERN_QUERY_CLEAN_RE = r"[?？,，。！!的了吗呢吧是有什么如何怎么哪个哪些]"
TASK_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "code_gen": ["code", "代码", "写", "implement", "函数", "class"],
    "data_analysis": ["data", "数据", "统计", "分析", "chart", "图表"],
    "summarize": ["summar", "总结", "摘要", "概括"],
    "retrieval_qa": ["search", "搜索", "find", "查找", "retriev"],
}

# ── Roundtable agreement prefixes (roundtable.py) ──
ROUNDTABLE_AGREEMENT_PREFIXES = ("同意", "赞同", "Agre", "I ag")
