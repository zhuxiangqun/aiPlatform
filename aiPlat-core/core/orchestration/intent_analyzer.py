"""Intent Analyzer — user natural language → StructuredIntent.

Parses user description into domain, features, complexity, and constraints.
Uses lightweight heuristics + keyword matching (no LLM for this step).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List


_DOMAIN_KEYWORDS = {
    "SaaS": ["saas", "平台", "管理", "后台", "dashboard", "团队", "协作", "多用户", "权限"],
    "Web App": ["网站", "网页", "web", "前端", "页面", "展示", "博客", "blog"],
    "CLI Tool": ["命令行", "cli", "终端", "脚本", "自动化", "tool"],
    "API": ["api", "接口", "服务", "微服务", "后端"],
    "Mobile": ["app", "移动", "手机", "ios", "android", "小程序"],
    "Data": ["数据", "分析", "报表", "etl", "爬虫", "采集", "统计"],
}

_COMPLEXITY_HINTS = {
    "high": ["实时", "高并发", "分布式", "微服务", "多端", "同步", "复杂"],
    "medium": ["管理", "协作", "权限", "数据库", "搜索", "文件"],
    "low": ["简单", "展示", "静态", "博客", "单页", "工具"],
}


@dataclass
class StructuredIntent:
    """Structured analysis of user intent."""
    domain: str = "general"
    features: List[str] = field(default_factory=list)
    complexity: str = "medium"  # low | medium | high
    constraints: List[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "features": self.features,
            "complexity": self.complexity,
            "constraints": self.constraints,
        }


def analyze_intent(user_text: str) -> StructuredIntent:
    """Analyze user text into structured intent using fast keyword heuristics."""
    text_lower = user_text.lower()
    intent = StructuredIntent(raw_text=user_text)

    # Detect domain
    scores: Dict[str, int] = {}
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[domain] = score
    if scores:
        intent.domain = max(scores, key=scores.get)  # type: ignore[arg-type]

    # Detect complexity
    for level, hints in _COMPLEXITY_HINTS.items():
        if any(h in text_lower for h in hints):
            intent.complexity = level
            break

    # Extract features (sentences/phrases with common patterns)
    feature_patterns = [
        r"(?:需要|支持|实现|包含|提供|具备|能够)(.+?)(?:[，,。.]|$)",
        r"(?:功能|feature)[：:]\s*(.+)",
    ]
    for pat in feature_patterns:
        for m in re.finditer(pat, text_lower):
            feat = m.group(1).strip()
            if len(feat) > 2 and feat not in intent.features:
                intent.features.append(feat)
    if not intent.features:
        sentences = re.split(r"[，,。.]", user_text)
        intent.features = [s.strip() for s in sentences if len(s.strip()) > 5][:5]

    # Detect constraints
    for m in re.finditer(r"(?:必须|要求|约束|限制|只能|不能|禁止|不超过)(.+?)(?:[，,。.]|$)", text_lower):
        intent.constraints.append(m.group(0).strip())

    return intent
