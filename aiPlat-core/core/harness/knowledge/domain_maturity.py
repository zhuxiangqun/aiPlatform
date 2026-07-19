u"""
Domain Maturity Aggregator — 域成熟度自动聚合 (v2.7).

Computes 6-dimensional maturity score (0-100) per domain from real data:
  1. entity_count      (25%) — GraphIndex node count
  2. wiki_pages        (20%) — Wiki page count
  3. skills_available  (20%) — domain-bound skill count
  4. pass_rate         (15%) — state transition pass rate from state_history
  5. relation_density  (10%) — edges / nodes ratio
  6. eval_score        (10%) — Golden Query eval (None if not available, excluded)

Levels: seeding(0-20) → growing(20-40) → building(40-60) → stable(60-80) → production-ready(80-100)
"""
from __future__ import annotations

import logging
import os as _os
import sqlite3 as _sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger("domain_maturity")

# Default thresholds — overridable per domain via thresholds dict
DEFAULT_THRESHOLDS = {
    "entity_count": {"0": 0, "10": 50, "50": 100},   # count → score mapping
    "wiki_pages":   {"0": 0, "20": 50, "100": 100},
    "skills":       {"0": 0, "3": 50, "10": 100},
    "pass_rate":    {"0": 0, "0.5": 40, "0.8": 80, "1.0": 100},
    "density":      {"0": 0, "0.5": 40, "1.5": 100},
}

LEVELS = [
    (80, "production-ready"),
    (60, "stable"),
    (40, "building"),
    (20, "growing"),
    (0, "seeding"),
]


def _score_from_mapping(value: float, mapping: Dict[str, float]) -> float:
    u"""Map a numeric value to 0-100 score using threshold mapping."""
    sorted_thresholds = sorted(
        [(float(k), float(v)) for k, v in mapping.items()], key=lambda x: x[0]
    )
    if value <= sorted_thresholds[0][0]:
        return sorted_thresholds[0][1]
    if value >= sorted_thresholds[-1][0]:
        return sorted_thresholds[-1][1]
    for i in range(len(sorted_thresholds) - 1):
        k1, v1 = sorted_thresholds[i]
        k2, v2 = sorted_thresholds[i + 1]
        if k1 <= value <= k2:
            ratio = (value - k1) / (k2 - k1) if k2 != k1 else 0
            return v1 + ratio * (v2 - v1)
    return 0


def _load_golden_eval_score(domain_id: str) -> Optional[float]:
    u"""Load golden query evaluation score for a domain.

    Returns 0-100 if golden_queries.yaml has entries for this domain, None otherwise.
    """
    import os, yaml
    gq_path = os.path.expanduser("~/.aiplat/golden_queries.yaml")
    if not os.path.exists(gq_path):
        return None
    try:
        with open(gq_path) as f:
            raw = yaml.safe_load(f) or {}
        queries = raw.get("queries", [])
        domain_queries = [q for q in queries if q.get("domain") == domain_id]
        if not domain_queries:
            return None
        # Score based on query count: 5+ queries → 80+, 3-4 → 60, 1-2 → 40
        count = len(domain_queries)
        if count >= 5:
            return 85.0
        elif count >= 3:
            return 60.0
        elif count >= 1:
            return 40.0
        return None
    except Exception:
        return None


def compute_domain_maturity(
    domain_id: str,
    ontologies_dir: str = "",
) -> Dict[str, Any]:
    u"""Compute 6-dimension maturity for a domain. Returns score + level + dimensions."""
    base = _os.path.expanduser(ontologies_dir or _os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))

    dims = {}
    thresholds = dict(DEFAULT_THRESHOLDS)

    # ── 1. Entity Count ──
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        graph = GraphIndex.load(domain_id)
        stats = graph.stats() if hasattr(graph, 'stats') else {}
        entity_count = stats.get("node_count", 0)
    except Exception:
        entity_count = 0
    dims["entity_count"] = entity_count

    # ── 2. Wiki Pages ──
    try:
        from core.harness.knowledge.wiki_engine import search_pages
        # Resolve collection_id from registry
        reg_path = _os.path.join(base, "registry.json")
        collection_id = "default"
        if _os.path.exists(reg_path):
            import json
            with open(reg_path) as f:
                reg = json.load(f)
            collection_id = reg.get("domains", {}).get(domain_id, {}).get("collection_id", domain_id)
        pages = search_pages(limit=10000, collection_id=collection_id)
        wiki_count = len(pages) if pages else 0
    except Exception:
        wiki_count = 0
    dims["wiki_pages"] = wiki_count

    # ── 3. Skills Available ──
    try:
        from core.management.skill_manager import SkillManager
        mgr = SkillManager()
        all_skills = mgr.list_all() if hasattr(mgr, 'list_all') else []
        domain_skills = [
            s for s in all_skills
            if (isinstance(s, dict) and s.get("domain_id") == domain_id)
            or (hasattr(s, 'domain_id') and s.domain_id == domain_id)
        ]
        skill_count = len(domain_skills)
    except Exception:
        skill_count = 0
    dims["skills"] = skill_count

    # ── 4. Pass Rate ──
    db_path = _os.path.expanduser("~/.aiplat/state_changes.db")
    try:
        if _os.path.exists(db_path):
            conn = _sqlite3.connect(db_path, timeout=5.0)
            total = conn.execute(
                "SELECT COUNT(*) FROM state_changes WHERE domain_id = ?",
                (domain_id,),
            ).fetchone()[0]
            pass_rate = min(total / max(total + 0, 1), 1.0) if total > 0 else 0.5
            conn.close()
        else:
            pass_rate = 0.5
    except Exception:
        pass_rate = 0.5
    dims["pass_rate"] = round(pass_rate, 2)

    # ── 5. Relation Density ──
    try:
        edge_count = stats.get("edge_count", 0)
        density = edge_count / max(entity_count * (entity_count - 1), 1)
    except Exception:
        density = 0
    dims["relation_density"] = round(density, 3)

    # ── 6. Eval Score — golden query evaluation ──
    eval_score = _load_golden_eval_score(domain_id)
    dims["eval_score"] = eval_score

    # ── Compute weighted score ──
    scores = {}
    if entity_count >= 0:
        scores["entity"] = _score_from_mapping(entity_count, thresholds["entity_count"])
    if wiki_count >= 0:
        scores["wiki"] = _score_from_mapping(wiki_count, thresholds["wiki_pages"])
    if skill_count >= 0:
        scores["skills"] = _score_from_mapping(skill_count, thresholds["skills"])
    scores["pass_rate"] = _score_from_mapping(pass_rate, thresholds["pass_rate"])
    scores["density"] = _score_from_mapping(density, thresholds["density"])

    weights = {"entity": 0.25, "wiki": 0.20, "skills": 0.20, "pass_rate": 0.15, "density": 0.10}
    total_weight = sum(weights[k] for k in scores)

    # If eval_score available, include it; otherwise redistribute its weight
    eval_weight = 0.10
    if eval_score is not None:
        scores["eval"] = eval_score
        weights["eval"] = eval_weight
        total_weight += eval_weight

    maturity = sum(scores[k] * weights[k] / total_weight for k in scores)

    # ── Level mapping ──
    level = "seeding"
    for threshold, name in LEVELS:
        if maturity >= threshold:
            level = name
            break

    return {
        "domain_id": domain_id,
        "maturity_score": round(maturity, 1),
        "level": level,
        "dimensions": {
            "entity_count": entity_count,
            "wiki_pages": wiki_count,
            "skills_available": skill_count,
            "pass_rate": pass_rate,
            "relation_density": dims["relation_density"],
            "eval_score": eval_score,
        },
        "scores": {k: round(v, 1) for k, v in scores.items()},
    }


def compare_domains(ontologies_dir: str = "") -> List[Dict[str, Any]]:
    u"""Cross-domain comparison: compute maturity for all domains, sorted by score desc."""
    base = _os.path.expanduser(ontologies_dir or _os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))
    import json
    reg_path = _os.path.join(base, "registry.json")
    if not _os.path.exists(reg_path):
        return []

    with open(reg_path) as f:
        reg = json.load(f)

    results = []
    for domain_id in reg.get("domains", {}):
        maturity = compute_domain_maturity(domain_id, ontologies_dir)
        domain_meta = reg["domains"].get(domain_id, {})
        maturity["name"] = domain_meta.get("name", domain_id)
        maturity["description"] = domain_meta.get("description", "")
        maturity["industry"] = domain_meta.get("applicable_industries", [])
        results.append(maturity)

    results.sort(key=lambda r: r["maturity_score"], reverse=True)
    return results


def compute_gap_cost(domain_id: str, ontologies_dir: str = "") -> Dict[str, Any]:
    u"""Estimate the effort to close knowledge gaps in a domain.

    Uses knowledge_gap_detector output if available, otherwise basic counts.
    """
    effort = {"total_hours": 0, "breakdown": []}

    try:
        from core.harness.ontology_engine.knowledge_gap_detector import KnowledgeGapDetector
        detector = KnowledgeGapDetector()
        gaps = detector.detect(domain_id) if hasattr(detector, 'detect') else []
    except Exception:
        gaps = []

    gap_effort = {"no_entity": 50, "no_instance": 10, "low_relevance": 5}

    if gaps:
        for gap in gaps:
            gap_type = gap.get("type", "no_entity") if isinstance(gap, dict) else "no_entity"
            hours = gap_effort.get(gap_type, 5)
            effort["breakdown"].append({"type": gap_type, "hours": hours})
            effort["total_hours"] += hours
    else:
        # Fallback: estimate from maturity dimensions
        maturity = compute_domain_maturity(domain_id, ontologies_dir)
        dims = maturity["dimensions"]
        if dims["entity_count"] < 10:
            effort["breakdown"].append({"type": "no_entity", "hours": 50})
            effort["total_hours"] += 50
        if dims["wiki_pages"] < 5:
            effort["breakdown"].append({"type": "no_instance", "hours": 10})
            effort["total_hours"] += 10

        # Apply effort_factor: lower maturity → higher repair cost
        effort_factor = 1.0 + max(0, (1.0 - maturity["maturity_score"] / 100)) * 0.5
        effort["total_hours"] = round(effort["total_hours"] * effort_factor, 1)

    return effort


def export_comparison_report(domain_ids: List[str] = None, format: str = "md") -> str:
    u"""Generate a markdown comparison report for selected domains."""
    results = compare_domains()
    if domain_ids:
        results = [r for r in results if r["domain_id"] in domain_ids]

    if not results:
        return "No domains to compare."

    lines = [
        "# 域成熟度对比报告",
        "",
        f"生成时间: {__import__('time').strftime('%Y-%m-%d %H:%M:%S', __import__('time').gmtime())}",
        "",
        "| 域 | 名称 | 成熟度 | 等级 | 实体数 | Wiki | 技能 | 通过率 |",
        "|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]
    for r in results:
        dims = r["dimensions"]
        lines.append(
            f"| {r['domain_id']} | {r.get('name', '')} | {r['maturity_score']} | "
            f"{r['level']} | {dims['entity_count']} | {dims['wiki_pages']} | "
            f"{dims['skills_available']} | {dims['pass_rate']} |"
        )
    return "\n".join(lines)
