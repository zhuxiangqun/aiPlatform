from __future__ import annotations

import re
from typing import List, Optional

from .types import ExtractedNumber, OCRToken


_NUM_RE = re.compile(r"(?<!\w)(-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?)(?!\w)")


def _to_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", ""))
    except Exception:
        return None


def extract_numbers(tokens: List[OCRToken], *, window: int = 6) -> List[ExtractedNumber]:
    """
    从 OCR tokens 中抽取数字，并保留一个简易上下文（前后 window 个 token）。
    这是 PoC：先把“数值 + bbox 引用”链路跑通。
    """
    out: List[ExtractedNumber] = []
    texts = [t.text for t in tokens]
    for i, t in enumerate(tokens):
        m = _NUM_RE.search(t.text)
        if not m:
            continue
        raw = m.group(1)
        v = _to_float(raw)
        lo = max(0, i - window)
        hi = min(len(tokens), i + window + 1)
        ctx = " ".join(texts[lo:hi])
        out.append(ExtractedNumber(value_raw=raw, value=v, token=t, context=ctx))
    return out


def pick_value_by_year(numbers: List[ExtractedNumber], year: str) -> Optional[ExtractedNumber]:
    """
    极简“读图”策略：
    - 如果上下文里出现 year，则优先选它附近的数字
    - 否则返回 None
    """
    y = str(year or "").strip()
    if not y:
        return None
    hits = [n for n in numbers if y in (n.context or "")]
    if not hits:
        return None
    # 优先：value 最大的（更像销售额/收入），这只是 PoC 的启发式
    hits2 = sorted(hits, key=lambda x: (x.value is not None, x.value or 0.0), reverse=True)
    return hits2[0]


def pick_values_by_keywords(numbers: List[ExtractedNumber], keywords: List[str], *, limit: int = 10) -> List[ExtractedNumber]:
    """
    从 numbers 中筛选上下文包含任一关键词的项，返回若干候选（按 value 大小排序）。
    用于 PoC：回答“投资预算有哪些”这类问题。
    """
    ks = [str(k or "").strip() for k in (keywords or []) if str(k or "").strip()]
    if not ks:
        return []
    hits = []
    for n in numbers:
        ctx = str(n.context or "")
        if any(k in ctx for k in ks):
            hits.append(n)
    hits.sort(key=lambda x: (x.value is not None, x.value or 0.0), reverse=True)
    return hits[: max(0, int(limit))]
