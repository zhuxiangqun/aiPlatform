"""
Knowledge Growth Metrics — time-series tracking of ontology growth.

Tracks how the knowledge base evolves over time:
  - Page count growth (by category and lifecycle state)
  - Cross-link growth (new wiki relations established)
  - Contradiction resolution rate
  - Quality score trends
  - KB document → wiki page conversion rate

Snapshots are recorded on write and retrieved for trend analysis.
Purpose: demonstrate "knowledge compound interest" to users.

Storage: ~/.aiplat/wiki/collections/{id}/growth_snapshots.json (append-only)

callers:
  - write_page / delete_page (via wiki_engine hooks)
  - GET /ontology/growth-stats
  - core_facade
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AI = "http://aiplat.local/knowledge#"


@dataclass
class GrowthSnapshot:
    timestamp: str
    page_count: int = 0
    kb_document_count: int = 0
    cross_link_count: int = 0
    contradiction_count: int = 0
    atom_count: int = 0
    avg_quality_score: float = 0.0
    by_category: Dict[str, int] = field(default_factory=dict)
    by_state: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "page_count": self.page_count,
            "kb_document_count": self.kb_document_count,
            "cross_link_count": self.cross_link_count,
            "contradiction_count": self.contradiction_count,
            "atom_count": self.atom_count,
            "avg_quality_score": round(self.avg_quality_score, 1),
            "by_category": self.by_category,
            "by_state": self.by_state,
        }


def _snapshots_path(collection_id: str = "default") -> str:
    home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    return _os.path.join(home, "wiki", "collections", collection_id, "growth_snapshots.json")


def _load_snapshots(collection_id: str = "default") -> List[Dict[str, Any]]:
    path = _snapshots_path(collection_id)
    if not _os.path.exists(path):
        return []
    try:
        return _json.load(open(path, "r", encoding="utf-8"))
    except Exception:
        return []


def _save_snapshots(snapshots: List[Dict[str, Any]], collection_id: str = "default") -> None:
    path = _snapshots_path(collection_id)
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    if len(snapshots) > 200:  # keep last 200 snapshots
        snapshots = snapshots[-200:]
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(snapshots, f, indent=2, ensure_ascii=False)


def take_growth_snapshot(collection_id: str = "default") -> GrowthSnapshot:
    u"""Snapshot current ontology state. Call this from write_page / delete_page hooks."""
    try:
        from core.harness.knowledge.knowledge_ontology import get_ontology
        onto = get_ontology()
    except Exception:
        return GrowthSnapshot(timestamp=datetime.now(timezone.utc).isoformat())

    page_count = 0
    kb_count = 0
    cross_links = 0
    contradictions = 0
    atom_count = 0
    by_category: Dict[str, int] = {}
    by_state: Dict[str, int] = {}
    quality_scores: List[float] = []

    for t in onto.triples:
        obj = t.object

        if t.predicate == "rdf:type":
            if "WikiPage" in obj:
                page_count += 1
            elif "KBDocument" in obj:
                kb_count += 1
            elif "KnowledgeAtom" in obj:
                atom_count += 1

        elif t.predicate == f"{AI}cites":
            cross_links += 1

        elif t.predicate == f"{AI}contradicts":
            contradictions += 1

        elif t.predicate == f"{AI}category":
            cat = obj.strip('"')
            by_category[cat] = by_category.get(cat, 0) + 1

        elif t.predicate == f"{AI}lifecycleState":
            state = obj.strip('"')
            by_state[state] = by_state.get(state, 0) + 1

        elif t.predicate == f"{AI}qualityScore":
            try:
                quality_scores.append(float(obj.strip('"')))
            except (ValueError, TypeError) as e:
                logging.debug(str(e), exc_info=True)

    # Halve cross-links since each link is a pair
    cross_links = cross_links // 2
    contradictions = contradictions // 2
    avg_quality = round(sum(quality_scores) / max(1, len(quality_scores)), 1) if quality_scores else 0.0

    snap = GrowthSnapshot(
        timestamp=datetime.now(timezone.utc).isoformat(),
        page_count=page_count,
        kb_document_count=kb_count,
        cross_link_count=cross_links,
        contradiction_count=contradictions,
        atom_count=atom_count,
        avg_quality_score=avg_quality,
        by_category=by_category,
        by_state=by_state,
    )

    existing = _load_snapshots(collection_id)
    existing.append(snap.to_dict())
    _save_snapshots(existing, collection_id)
    return snap


def get_growth_stats(
    collection_id: str = "default",
    *,
    days: int = 30,
) -> Dict[str, Any]:
    u"""Get growth statistics for the last N days.

    Returns timeline of snapshots + computed deltas.
    """
    snapshots = _load_snapshots(collection_id)
    if not snapshots:
        return _empty_stats()

    cutoff = _time.time() - days * 86400
    recent = [s for s in snapshots if _parse_ts(s.get("timestamp", "")) >= cutoff]

    if len(recent) < 2:
        return _single_snapshot_stats(recent[0] if recent else snapshots[-1])

    first = recent[0]
    last = recent[-1]

    # Compute deltas
    deltas = {
        "pages": last.get("page_count", 0) - first.get("page_count", 0),
        "kb_documents": last.get("kb_document_count", 0) - first.get("kb_document_count", 0),
        "cross_links": last.get("cross_link_count", 0) - first.get("cross_link_count", 0),
        "contradictions": last.get("contradiction_count", 0) - first.get("contradiction_count", 0),
        "atoms": last.get("atom_count", 0) - first.get("atom_count", 0),
        "avg_quality_delta": round(last.get("avg_quality_score", 0) - first.get("avg_quality_score", 0), 1),
    }

    # Conversion rate: wiki pages / KB docs
    conversion_rate = round(
        last.get("page_count", 0) / max(1, last.get("kb_document_count", 0)) * 100, 1
    )

    # Deduplication
    dedup_rate = round(
        (last.get("cross_link_count", 0) - first.get("cross_link_count", 0))
        / max(1, deltas["pages"]) * 10, 1
    ) if deltas["pages"] > 0 else 0.0

    # Growth velocity (per day average)
    analysis_days = max(1, days)

    return {
        "period": f"{days}d",
        "start": first.get("timestamp", ""),
        "end": last.get("timestamp", ""),
        "snapshot_count": len(recent),
        "current": last,
        "deltas": deltas,
        "metrics": {
            "conversion_rate_pct": conversion_rate,
            "dedup_score": dedup_rate,
            "pages_per_day": round(deltas["pages"] / analysis_days, 1),
            "links_per_day": round(deltas["cross_links"] / analysis_days, 1),
            "contradiction_change": deltas["contradictions"],
            "quality_trend": "improving" if deltas["avg_quality_delta"] > 0 else (
                "declining" if deltas["avg_quality_delta"] < 0 else "stable"
            ),
        },
        "timeline": recent[::max(1, len(recent) // 30)],  # ~30 data points for chart
    }


def estimate_compound_value(collection_id: str = "default") -> Dict[str, Any]:
    u"""Estimate the compound value of the knowledge base.

    Each cross-link multiplies the value of the linked entities.
    High-quality, well-linked knowledge creates network effects.
    """
    stats = get_growth_stats(collection_id, days=90)
    current = stats.get("current", {})
    pages = current.get("page_count", 0)
    links = current.get("cross_link_count", 0)
    quality = current.get("avg_quality_score", 70)

    # Compound value = pages × (1 + links/pages) × quality_factor
    link_density = links / max(1, pages)
    quality_factor = quality / 100
    compound = round(pages * (1 + link_density) * max(0.1, quality_factor), 1)

    return {
        "pages": pages,
        "cross_links": links,
        "link_density": round(link_density, 3),
        "quality_score": quality,
        "compound_value": compound,
        "interpretation": (
            "High network density" if link_density > 1.5
            else "Growing network" if link_density > 0.5
            else "Knowledge is still forming — more cross-links will unlock compound value"
        ),
    }


def _parse_ts(ts: str) -> float:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def _empty_stats() -> Dict[str, Any]:
    return {
        "period": "n/a", "snapshot_count": 0,
        "current": {}, "deltas": {}, "metrics": {}, "timeline": [],
    }


def _single_snapshot_stats(snap: Dict) -> Dict[str, Any]:
    return {
        "period": "n/a", "snapshot_count": 1,
        "start": snap.get("timestamp", ""), "end": snap.get("timestamp", ""),
        "current": snap, "deltas": {},
        "metrics": {"conversion_rate_pct": 0, "pages_per_day": 0, "quality_trend": "n/a"},
        "timeline": [snap],
    }
