"""Trivial query handlers — instant answers for time, math, and simple facts.

Extracted from MaterialsChatAgent's bypass logic. Any agent can use these
to skip heavy retrieval for queries that don't need knowledge base access.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


WEEKDAY_NAMES = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def handle_time_query(query: str) -> Optional[str]:
    """Try to answer a time/date query. Returns answer string or None."""
    now = datetime.now()
    if "几点" in query or "时间" in query:
        return f"现在是 {now.strftime('%Y年%m月%d日 %H:%M')} {WEEKDAY_NAMES[now.weekday()]}"
    if "今天" in query and "日期" in query:
        return f"今天是 {now.strftime('%Y年%m月%d日')} {WEEKDAY_NAMES[now.weekday()]}"
    return None


def handle_math_expression(query: str) -> Optional[str]:
    """Try to evaluate a simple math expression. Returns result or None."""
    import re
    # Match simple arithmetic: digits, spaces, + - * / ( )
    expr = query.strip()
    if re.match(r"^[\d\s+\-*/().%]+$", expr) and len(expr) < 200:
        try:
            result = eval(expr, {"__builtins__": {}}, {})
            return f"{expr} = {result}"
        except Exception:
            return None
    return None
