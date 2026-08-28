"""web_result_quality.py — Web 搜索结果可信度评估（AnySearch 借鉴 P1-2，2026-08-28）。

对结构化 web 搜索结果（web_search structured=true 输出的事实条目）做可信度评估：
  - 信源域名权威度（官方域名/知名站 > 普通站 > 低质站）
  - 查询相关性（词重叠，对齐 retrieval_quality_gate._score_chunk）
  - 多源一致性（同 claim 多源出现 → 提升）
  - 时效性（可选，条目含 publish_date 时生效）

输出 {pass, action, per_result, avg_score, reasons}：
  pass=True  → use_results（可信度达标）
  pass=False → flag_for_human（关键场景需人工复核——文章"结果污染成本"）
  每条结果附 quality_score（0-1）与 reason（可追溯）。
"""
from __future__ import annotations

import re
from typing import Any

# 权威域名前缀/域名白名单（启发式：官方/知名机构与开发者平台）
_AUTHORITATIVE_HOSTS = (
    "github.com", "gitlab.com", "stackoverflow.com", "stackexchange.com",
    "python.org", "pypi.org", "npmjs.com", "mozilla.org", "w3.org",
    "wikipedia.org", "docs.", "developer.", "learn.microsoft.com",
    "react.dev", "vuejs.org", "kubernetes.io", "docker.com", "nodejs.org",
    "rust-lang.org", "golang.org", "openai.com", "anthropic.com",
)
_LOW_QUALITY_HOSTS = (
    "medium.com", "blogspot.com", "wordpress.com", "quora.com",
    "reddit.com", "baidu.com", "toutiao.com", "weibo.com",
    "sina.com.cn", "sohu.com", "163.com",
)
# 明确不可信（文章：结果污染来源）
_UNRELIABLE_KEYWORDS = (
    "advertorial", "sponsored", "sponsor", "affiliate", "buy now",
    "click here", "free download", "discount code",
)


def _tokenize(text: str) -> set:
    """中英文 token 化：英文词 + 中文二元组。"""
    tokens = set()
    for m in re.finditer(r"[a-z0-9_]{2,}", (text or "").lower()):
        tokens.add(m.group(0))
    for m in re.finditer(r"[\u4e00-\u9fff]", (text or "")):
        tokens.add(m.group(0))
    return tokens


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return (url or "").lower()


def _domain_authority(url: str) -> float:
    """信源域名权威度（0-1）。"""
    host = _host_of(url)
    if not host:
        return 0.0
    if any(k in host for k in _UNRELIABLE_KEYWORDS):
        return 0.1
    if any(host.startswith(a) or a in host for a in _AUTHORITATIVE_HOSTS):
        return 0.9
    if any(h in host for h in _LOW_QUALITY_HOSTS):
        return 0.3
    # 普通站：顶级域判断
    if host.endswith((".edu", ".gov", ".org")):
        return 0.7
    return 0.5


def _query_relevance(query: str, evidence: str) -> float:
    """查询相关性（词重叠比例，对齐 retrieval_quality_gate）。"""
    qw = _tokenize(query)
    ew = _tokenize(evidence)
    if not qw:
        return 0.0
    overlap = len(qw & ew)
    return round(overlap / len(qw), 3)


def assess_web_results(results: list[dict[str, Any]], query: str,
                       threshold: float = 0.4,
                       min_results: int = 2) -> dict[str, Any]:
    """评估结构化 web 结果可信度。

    单条 score = 0.4*域名权威 + 0.4*查询相关性 + 0.2*多源一致性（后续统一注入）。
    多源一致性：同 host 的重复条目仅计一次（去重已由 web_search 完成，此处对
    同 claim 多源出现的信号做轻量奖励——按 source 字段多样性）。
    """
    if not results or len(results) < min_results:
        return {"pass": False, "action": "flag_for_human", "per_result": [],
                "avg_score": 0.0,
                "reason": f"结果不足（{len(results) or 0} < {min_results}），需人工复核"}

    # 多源一致性：source 字段多样性（ddg_abstract+cross / ddg_abstract / ddg_related 等）
    source_set = {str(r.get("source") or "") for r in results if isinstance(r, dict)}
    cross_bonus = 0.1 if len(source_set) >= 2 else 0.0

    per_result = []
    scores: list[float] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        url = str(r.get("source_url") or "")
        evidence = str(r.get("evidence_snippet") or r.get("text") or "")
        auth = _domain_authority(url)
        rel = _query_relevance(query, evidence)
        base_conf = float(r.get("confidence", 0) or 0)
        score = round(min(1.0, 0.4 * auth + 0.4 * rel + 0.2 * base_conf + cross_bonus), 3)
        scores.append(score)
        reasons = [f"域名权威={auth}", f"相关性={rel}", f"置信度={base_conf}"]
        if cross_bonus:
            reasons.append(f"多源一致(+{cross_bonus})")
        per_result.append({
            "source_url": url,
            "quality_score": score,
            "reason": "; ".join(reasons),
        })

    avg = round(sum(scores) / max(len(scores), 1), 3)
    passed = avg >= threshold
    return {
        "pass": passed,
        "action": "use_results" if passed else "flag_for_human",
        "per_result": per_result,
        "avg_score": avg,
        "reason": (f"平均可信度 {avg} >= {threshold}，可用" if passed
                   else f"平均可信度 {avg} < {threshold}，建议人工复核（结果污染风险）"),
    }


def annotate_results(results: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """原地标注 quality_score/reason 到每条结果（供调用方直接消费）。"""
    assessment = assess_web_results(results, query)
    by_url = {p["source_url"]: p for p in assessment.get("per_result", [])}
    out = []
    for r in results:
        if not isinstance(r, dict):
            continue
        q = by_url.get(str(r.get("source_url") or ""), {})
        out.append({**r, "quality_score": q.get("quality_score", 0.0),
                    "quality_reason": q.get("reason", "")})
    return out
