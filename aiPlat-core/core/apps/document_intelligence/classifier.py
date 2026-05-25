"""
Document auto-classifier — categorizes ingested documents by content type.

This is an Internal Policy module per boundary-standard.md §决策树.
It decides what category a document belongs to (budget/tech/meeting/general),
which informs retrieval strategy and answer strategy.

Returns content_category + tags based on element text/table analysis.

Callers:
  - platform/kb/service.py (ingest pipeline)
  - platform/api/rest/routes.py (categories API)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


BUDGET_KEYWORDS = {"投资", "预算", "万元", "亿元", "经费", "拨款", "资金", "支出", "收入", "成本", "费用", "补贴", "专项资金", "政府采购"}

TECH_KEYWORDS = {
    "api", "sdk", "rest", "graphql", "http", "https", "json", "xml", "oauth",
    "jwt", "sql", "nosql", "redis", "kafka", "docker", "kubernetes", "k8s",
    "ci/cd", "git", "github", "gitlab", "jenkins", "terraform", "ansible",
    "微服务", "架构", "高可用", "容灾", "性能", "并发", "事务", "索引",
    "def ", "class ", "function ", "import ", "const ", "let ", "var ",
    "npm", "pip", "maven", "gradle", "webpack", "vite", "eslint", "prettier",
    "react", "vue", "angular", "django", "flask", "spring", "fastapi",
    "deployment", "rollback", "migration", "schema", "endpoint",
}

MEETING_KEYWORDS = {"会议", "参会", "纪要", "议题", "决议", "讨论", "汇报", "周报",
                     "月报", "日报", "进度", "下一步", "行动项", "待办", "TODO"}

DATE_PATTERNS = [
    r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?",
    r"\d{4}\.\d{1,2}\.\d{1,2}",
    r"(?:周[一二三四五六日]|星期[一二三四五六日])",
]


def _score_keywords(texts: List[str], keyword_set: set) -> int:
    score = 0
    for text in texts:
        lower = text.lower()
        for kw in keyword_set:
            if kw.lower() in lower:
                score += 1
    return score


def _has_date_pattern(text: str) -> bool:
    for pat in DATE_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def _extract_tags(texts: List[str], limit: int = 8) -> List[str]:
    all_text = " ".join(texts)
    wlen = re.findall(r"[\u4e00-\u9fa5]{2,6}", all_text)
    freq: Dict[str, int] = {}
    for w in wlen:
        freq[w] = freq.get(w, 0) + 1
    sorted_words = sorted(freq.items(), key=lambda x: -x[1])
    tags = [w for w, c in sorted_words if c >= 2 and w not in {"一个", "可以", "这个", "我们", "他们", "进行", "通过", "使用", "其中", "以及", "对于", "根据", "关于", "没有", "一些", "所有", "需要", "已经", "可能", "主要", "包括", "结果", "情况", "问题", "过程", "一种", "这样", "因此", "如果", "但是", "而且", "由于", "因为", "所以", "目前", "目前", "相关", "不同", "以下", "以上", "如下", "其他", "部分", "一般"}]
    return tags[:limit]


def classify_document(elements: List[Dict[str, Any]], kind: str) -> Dict[str, Any]:
    texts: List[str] = []
    table_texts: List[str] = []
    has_date = False

    for el in elements:
        t = str(el.get("text") or "")
        if t:
            texts.append(t)
            if not has_date:
                has_date = _has_date_pattern(t)
        cells = el.get("cells")
        if isinstance(cells, list):
            for row in cells:
                if isinstance(row, list):
                    table_texts.extend(str(c) for c in row if c)

    all_texts = texts + table_texts
    if not all_texts:
        return {"content_category": "general", "kind_category": kind_category(kind), "tags": []}

    budget_score = _score_keywords(all_texts, BUDGET_KEYWORDS)
    tech_score = _score_keywords(all_texts, TECH_KEYWORDS)
    meeting_score = _score_keywords(all_texts, MEETING_KEYWORDS)
    if has_date:
        meeting_score += 2

    if budget_score >= 3:
        category = "budget_investment"
    elif tech_score >= 4:
        category = "technical_doc"
    elif meeting_score >= 3:
        category = "meeting_notes"
    else:
        category = "general"

    tags = _extract_tags(all_texts)

    return {
        "content_category": category,
        "kind_category": kind_category(kind),
        "tags": tags,
        "scores": {"budget": budget_score, "tech": tech_score, "meeting": meeting_score},
    }


def kind_category(kind: str) -> str:
    mapping = {
        "pdf": "pdf", "video": "video",
        "word": "word", "docx": "word", "doc": "word",
        "ppt": "ppt", "pptx": "ppt",
        "md": "markdown", "markdown": "markdown",
    }
    return mapping.get(str(kind or "").lower().strip(), "pdf")


CATEGORY_LABELS: Dict[str, str] = {
    "pdf": "PDF 文档",
    "word": "Word 文档",
    "ppt": "PPT 演示",
    "markdown": "Markdown",
    "video": "视频",
    "budget_investment": "预算投资",
    "technical_doc": "技术文档",
    "meeting_notes": "会议纪要",
    "general": "通用文档",
}


__all__ = ["classify_document", "kind_category", "CATEGORY_LABELS"]
