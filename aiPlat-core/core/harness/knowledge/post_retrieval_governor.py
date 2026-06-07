"""
Post-Retrieval Governance Pipeline.

Sits between retrieval results and LLM prompt construction.
Applies deterministic rules — no LLM calls, no external APIs.

Pipeline stages:
  ① Time-weighted freshness scoring
  ② Source credibility weighting
  ③ Information density scoring
  ④ Conflict detection (A-Box contradicts)
  ⑤ Dedup merge (Cosine > threshold)
  ⑥ Dynamic cutoff (elbow method)
  ⑦ Governance hints generation

Callers:
  - sys_knowledge_retrieve() in retrieval.py
  - Any agent that needs governed context assembly
"""
from __future__ import annotations

import os
import re
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple


# ── Module-level governance hints cache (read by Prompt injection layer) ──

_last_governance_context: Optional[str] = None
_last_governance_ts: float = 0.0
_GOVERNANCE_CACHE_TTL: float = 300.0  # 5 minutes


def get_last_governance_context() -> Optional[str]:
    """Return the latest governance context for Prompt injection, if fresh."""
    if _last_governance_context and (_time.time() - _last_governance_ts) < _GOVERNANCE_CACHE_TTL:
        return _last_governance_context
    return None


# ── Default credibility weights ──

DEFAULT_CREDIBILITY = {
    "kb:official": 1.0,
    "kb:technical": 0.85,
    "kb:wiki": 0.80,
    "kb:upload": 0.70,
    "kb:vault": 0.60,
    "kb:community": 0.50,
    "default": 0.50,
}


# ── Configuration ──

@dataclass
class GovernorConfig:
    time_decay_days: int = 180       # pages older than this get penalized
    time_boost_days: int = 30        # pages within this get a boost
    min_density_score: float = 0.15  # minimum information density to keep
    dedup_threshold: float = 0.92    # Cosine above this → merge
    min_keep_chunks: int = 3         # minimum chunks to keep after cutoff
    credibility_weights: Dict[str, float] = field(default_factory=lambda: DEFAULT_CREDIBILITY.copy())


# ── Data structures ──

@dataclass
class GovernanceHints:
    has_conflicts: bool = False
    conflict_pairs: List[Tuple[str, str]] = field(default_factory=list)
    oldest_source_age: int = 0
    newest_source_age: int = 0
    governance_applied: List[str] = field(default_factory=list)
    citation_required: bool = True


@dataclass
class GovernanceStats:
    raw_count: int = 0
    governed_count: int = 0
    time_penalized: int = 0
    density_filtered: int = 0
    dedup_merged: int = 0
    conflict_marked: int = 0
    cutoff_score: float = 0.0
    avg_composite_score: float = 0.0


# ── Scoring functions ──

def _compute_freshness(last_updated: str, config: GovernorConfig) -> float:
    """Score recent content higher. Returns 0.0-1.0."""
    if not last_updated:
        return 0.5  # unknown age = neutral
    try:
        # Try ISO format
        if 'T' in last_updated:
            dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(last_updated[:19], "%Y-%m-%d %H:%M:%S")
        age_days = (_time.time() - dt.timestamp()) / 86400
    except (ValueError, OSError):
        return 0.5

    if age_days <= config.time_boost_days:
        return 1.0
    if age_days <= config.time_decay_days:
        return 1.0 - 0.5 * (age_days - config.time_boost_days) / (config.time_decay_days - config.time_boost_days)
    return 0.3  # very old, still retrievable but penalized


def _compute_density(text: str) -> float:
    """Information density: structured content > narrative > noise.

    Rewards: tables (|), code blocks (```), lists (-/*), headings (#)
    Penalizes: excessive whitespace, very short content, HTML tags
    """
    if not text or len(text) < 50:
        return 0.1
    t = text[:5000]  # sample first 5k chars

    # Count structural elements
    tables = t.count("| --") + t.count("|---")
    code_blocks = t.count("```")
    headings = len(re.findall(r"^#{1,6}\s", t, re.MULTILINE))
    list_items = len(re.findall(r"^[\s]*[-*+]\s", t, re.MULTILINE))
    numbered_items = len(re.findall(r"^[\s]*\d+\.\s", t, re.MULTILINE))

    # Count noise indicators
    whitespace_ratio = t.count("\n\n") / max(len(t.split("\n")), 1)
    html_tags = len(re.findall(r"</?[a-z]+[^>]*>", t))

    # Composite score
    structure_score = min(1.0, (tables * 0.15 + code_blocks * 0.1 + headings * 0.05
                                 + list_items * 0.03 + numbered_items * 0.03))
    noise_penalty = min(0.3, whitespace_ratio * 0.2 + html_tags * 0.05)

    return max(0.1, min(1.0, 0.5 + structure_score - noise_penalty))


def _compute_credibility(source_type: str, source_uri: str = "",
                          config: GovernorConfig = None) -> float:
    """Source credibility based on type and URI patterns."""
    w = config.credibility_weights if config else DEFAULT_CREDIBILITY

    if source_type == "wiki":
        return w.get("kb:wiki", 0.8)
    if source_type == "kb":
        uri = source_uri.lower()
        if any(k in uri for k in ("official", "官方", "policy", "制度", "manual", "手册")):
            return w.get("kb:official", 1.0)
        if any(k in uri for k in ("tech", "技术", "api", "spec", "规范")):
            return w.get("kb:technical", 0.85)
        if any(k in uri for k in ("upload", "上传")):
            return w.get("kb:upload", 0.7)
        return w.get("kb:technical", 0.8)
    return w.get("default", 0.5)


# ── Deduplication ──

def _dedup_by_text_overlap(chunks: List[Dict], threshold: float = 0.92) -> Tuple[List[Dict], int]:
    """Simple text-overlap dedup: jaccard on word bigrams. O(n*m)."""
    if len(chunks) <= 1:
        return list(chunks), 0

    def _tokenize(s: str) -> Set[str]:
        words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', str(s)[:500])
        bigrams = set()
        for i in range(len(words) - 1):
            bigrams.add(f"{words[i]} {words[i+1]}")
        return bigrams

    merged = []
    used = set()
    for i, a in enumerate(chunks):
        if i in used:
            continue
        tokens_a = _tokenize(a.get("text", ""))
        best_j = -1
        best_sim = 0.0
        for j, b in enumerate(chunks):
            if j <= i or j in used:
                continue
            tokens_b = _tokenize(b.get("text", ""))
            if not tokens_a or not tokens_b:
                continue
            sim = len(tokens_a & tokens_b) / max(len(tokens_a | tokens_b), 1)
            if sim > best_sim:
                best_sim = sim
                best_j = j
        if best_sim >= threshold:
            used.add(best_j)
            # Merge: keep higher-scored, add dedup note
            a.setdefault("meta", {})["dedup_merged_from"] = chunks[best_j].get("title", "?")
        merged.append(a)

    return merged, len(used)


# ── Dynamic cutoff (elbow method) ──

def _dynamic_cutoff(scored: List[Tuple[Dict, float]], min_keep: int = 3) -> Tuple[List[Dict], float]:
    """Find the elbow in the composite score curve and cut there."""
    if len(scored) <= min_keep:
        return [c for c, _ in scored], 0.0

    scores = [s for _, s in scored]
    cut_idx = min_keep

    # Compute second derivative (difference of differences)
    if len(scores) >= 3:
        diffs = [scores[i] - scores[i + 1] for i in range(len(scores) - 1)]
        if len(diffs) >= 2:
            second_diffs = [diffs[i] - diffs[i + 1] for i in range(len(diffs) - 1)]
            # Find max second derivative (steepest drop)
            max_diff = max(second_diffs) if second_diffs else 0
            for i, sd in enumerate(second_diffs):
                if sd >= max_diff * 0.7:  # within 70% of max
                    cut_idx = max(min_keep, i + 2)
                    break

    return [c for c, _ in scored[:cut_idx]], scores[min(cut_idx - 1, len(scores) - 1)] if cut_idx < len(scores) else 0.0


# ── Main Governor ──

class PostRetrievalGovernor:
    """Deterministic post-retrieval governance pipeline.

    All stages are rule-based — no LLM calls, no external APIs.
    """

    def __init__(self, config: GovernorConfig = None):
        self.config = config or GovernorConfig()

    def govern(
        self,
        results: List[Dict[str, Any]],
        query: str = "",
        collection_id: str = "default",
    ) -> Tuple[List[Dict[str, Any]], GovernanceHints, GovernanceStats]:
        """Execute the full governance pipeline.

        Args:
            results: Raw retrieval results [{text, title, score, source_type, ...}]
            query: Original query (for context in hints)
            collection_id: Wiki collection ID

        Returns:
            (governed_chunks, hints, stats)
        """
        stats = GovernanceStats(raw_count=len(results))
        hints = GovernanceHints()

        if not results:
            return [], hints, stats

        # ── ① Freshness scoring ──
        hints.governance_applied.append("freshness_scoring")
        for r in results:
            last_up = r.get("last_updated") or r.get("meta", {}).get("last_updated", "")
            r["_freshness"] = _compute_freshness(last_up, self.config)
            if r["_freshness"] < 0.4:
                stats.time_penalized += 1

        # ── ② Credibility scoring ──
        hints.governance_applied.append("credibility_scoring")
        for r in results:
            st = r.get("source_type", "kb")
            su = r.get("source_uri") or r.get("source", "")
            if isinstance(su, list):
                su = su[0] if su else ""
            r["_credibility"] = _compute_credibility(st, str(su), self.config)

        # ── ③ Density scoring ──
        hints.governance_applied.append("density_scoring")
        for r in results:
            text = r.get("text", "") or r.get("summary", "") or r.get("body", "")
            r["_density"] = _compute_density(str(text))
            if r["_density"] < self.config.min_density_score:
                stats.density_filtered += 1

        # ── ④ Composite scoring ──
        for r in results:
            raw_score = r.get("score", 0.5)
            r["_composite"] = (
                raw_score * 0.55
                + r.get("_freshness", 0.5) * 0.15
                + r.get("_credibility", 0.5) * 0.15
                + r.get("_density", 0.3) * 0.15
            )

        # ── ⑤ Conflict detection ──
        hints.governance_applied.append("conflict_detection")
        try:
            from core.harness.knowledge.knowledge_abox_builder import build_abox
            titles = {r.get("title", "") for r in results if r.get("title")}
            if titles:
                onto = build_abox(collection_id=collection_id)
                for t in onto.triples:
                    if "contradicts" in str(t.predicate):
                        s = str(t.subject).split("#")[-1] if "#" in str(t.subject) else str(t.subject)
                        o = str(t.object).split("#")[-1] if "#" in str(t.object) else str(t.object)
                        if s in titles and o in titles:
                            hints.has_conflicts = True
                            pair = tuple(sorted([s, o]))
                            if pair not in hints.conflict_pairs:
                                hints.conflict_pairs.append(pair)
                            stats.conflict_marked += 1
        except Exception:
            pass

        # Mark conflicting chunks
        conflict_titles = set()
        for a, b in hints.conflict_pairs:
            conflict_titles.add(a)
            conflict_titles.add(b)
        for r in results:
            r["_has_contradiction"] = r.get("title", "") in conflict_titles

        # ── ⑥ Date range ──
        ages = []
        for r in results:
            lu = r.get("last_updated") or r.get("meta", {}).get("last_updated", "")
            if lu:
                try:
                    if 'T' in lu:
                        dt = datetime.fromisoformat(lu.replace('Z', '+00:00'))
                    else:
                        dt = datetime.strptime(lu[:19], "%Y-%m-%d %H:%M:%S")
                    ages.append((_time.time() - dt.timestamp()) / 86400)
                except (ValueError, OSError):
                    pass
        if ages:
            hints.oldest_source_age = int(max(ages))
            hints.newest_source_age = int(min(ages))

        # ── ⑦ Dedup merge ──
        hints.governance_applied.append("dedup_merge")
        deduped, merged_count = _dedup_by_text_overlap(results, self.config.dedup_threshold)
        stats.dedup_merged = merged_count

        # ── ⑧ Sort by composite score ──
        scored = sorted(
            [(r, r.get("_composite", r.get("score", 0.5))) for r in deduped],
            key=lambda x: -x[1],
        )

        #     ── ⑨ Dynamic cutoff ──
        hints.governance_applied.append("dynamic_cutoff")
        governed, cutoff = _dynamic_cutoff(scored, self.config.min_keep_chunks)
        stats.cutoff_score = cutoff
        stats.governed_count = len(governed)

        # Compute average composite
        if governed:
            stats.avg_composite_score = round(
                sum(c.get("_composite", 0) for c in governed) / len(governed), 3)

        # ── Record stats for observability ──
        self._record_stats(stats)

        # ── Update governance context cache for Prompt injection ──
        self._update_context_cache(hints, stats)

        return governed, hints, stats

    def _update_context_cache(self, hints: GovernanceHints, stats: GovernanceStats) -> None:
        """Build a governance context string for Prompt injection and cache it globally."""
        global _last_governance_context, _last_governance_ts

        lines = ["[系统] 召回后治理报告："]

        # Conflict context
        if hints.has_conflicts and hints.conflict_pairs:
            lines.append(f"⚠️ 检索发现 {len(hints.conflict_pairs)} 对矛盾信息：")
            for a, b in hints.conflict_pairs[:3]:
                lines.append(f"   · '{a}' 与 '{b}' 存在矛盾声明")
            lines.append("   处理方式：同时呈现双方立场，不要猜测哪个正确。")

        # Timeliness context
        if hints.oldest_source_age > 180:
            lines.append(f"⏰ 部分来源超过 {hints.oldest_source_age} 天未更新，时效性存疑。")
            lines.append("   请优先采纳更新近的信息，并在回答中标注信息的时间。")
        elif hints.newest_source_age > 30:
            lines.append(f"ℹ️ 最新来源距今 {hints.newest_source_age} 天。")

        # Governance summary
        lines.append(
            f"治理统计: 原始 {stats.raw_count} chunks → 治理后 {stats.governed_count} chunks "
            f"(时效降权 {stats.time_penalized}, 密度过滤 {stats.density_filtered}, "
            f"去重 {stats.dedup_merged}, 动态截断阈值 {stats.cutoff_score:.2f})")

        # Citation reminder
        lines.append("引用格式: [来源: wiki/页面标题] 或 [来源: 文档名]")

        _last_governance_context = "\n".join(lines)
        _last_governance_ts = _time.time()

    def _record_stats(self, stats: GovernanceStats) -> None:
        """Append governance snapshot to history file for metrics dashboard."""
        try:
            import json as _sj
            hist_path = os.path.join(
                os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat")),
                "wiki", "governance_history.json")
            history = []
            if os.path.exists(hist_path):
                history = _sj.loads(open(hist_path).read())
            history.append({
                "ts": _time.time(),
                "raw": stats.raw_count,
                "governed": stats.governed_count,
                "time_pen": stats.time_penalized,
                "density": stats.density_filtered,
                "dedup": stats.dedup_merged,
                "conflict": stats.conflict_marked,
                "avg_comp": stats.avg_composite_score,
                "cutoff": stats.cutoff_score,
            })
            os.makedirs(os.path.dirname(hist_path), exist_ok=True)
            open(hist_path, "w").write(_sj.dumps(history[-100:]))
        except Exception:
            pass
