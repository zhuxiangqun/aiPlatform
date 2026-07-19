u"""
Domain Assessor Handler (v2.7) — data-driven domain recommendation.

Replaces LLM-inferred domain matching with computed scenario_selector
+ domain_maturity data. Produces structured, auditable output.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("domain_assessor")


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    u"""Main handler: classify domain match + compute maturity.

    Input: { customer_profile: { industry, pain_points, tech_stack, deploy },
             available_domains: [...] }
    Output: { primary_domain, confidence, match_reasons, alternatives,
              gap_analysis, maturity_details }
    """
    profile = params.get("customer_profile", {})
    industry = profile.get("industry", "")
    pain_points = profile.get("pain_points", "")
    available = params.get("available_domains", [])

    # ── Step 1: DomainRouter classify ──
    try:
        from core.harness.knowledge.domain_router import DomainRouter
        router = DomainRouter()
        classified = router.classify(f"{industry} {pain_points}")
        domain_id = classified.get("domain_id", "") if classified else ""
    except Exception as e:
        logger.warning("DomainRouter.classify failed: %s", e)
        domain_id = ""

    # ── Step 2: Scenario Selector — rank all domains ──
    recommendations = []
    try:
        from core.harness.knowledge.scenario_selector import recommend_order
        recommendations = recommend_order(
            industry=industry,
            pain_points=pain_points,
            limit=5,
        )
    except Exception as e:
        logger.warning("scenario_selector.recommend_order failed: %s", e)

    if not recommendations and domain_id:
        recommendations = [{"domain_id": domain_id, "priority_score": 50.0,
                            "priority": "P0", "recommendation": "build_first"}]

    # ── Step 3: Domain Maturity — computed detail ──
    primary = recommendations[0] if recommendations else {"domain_id": domain_id or "default"}
    primary_domain = primary.get("domain_id", "default")
    maturity_details = {}
    try:
        from core.harness.knowledge.domain_maturity import compute_domain_maturity, compute_gap_cost
        maturity_details = compute_domain_maturity(primary_domain)
        gap_cost = compute_gap_cost(primary_domain)
        maturity_details["gap_cost_hours"] = gap_cost.get("total_hours", 0)
    except Exception as e:
        logger.warning("domain_maturity.compute failed: %s", e)

    # ── Step 4: Assemble structured output ──
    result = {
        "primary_domain": primary_domain,
        "primary_maturity_score": round(maturity_details.get("maturity_score", 0), 1),
        "primary_maturity_level": maturity_details.get("level", "unknown"),
        "confidence": round(primary.get("priority_score", 50) / 100, 2),
        "match_reasons": [
            f"行业匹配: {industry}" if industry else "通用匹配",
            f"数据驱动推荐 (评分: {primary.get('priority_score', 0)})",
        ],
        "alternatives": [
            {
                "domain_id": r["domain_id"],
                "score": r["priority_score"],
                "priority": r.get("priority", "P1"),
                "reason": r.get("value_formula", ""),
            }
            for r in recommendations[1:4] if r.get("domain_id") != primary_domain
        ],
        "non_recommended": [
            r["domain_id"] for r in recommendations
            if r.get("recommendation") == "defer"
        ],
        "gap_analysis": {
            "entity_count": maturity_details.get("dimensions", {}).get("entity_count", 0),
            "wiki_pages": maturity_details.get("dimensions", {}).get("wiki_pages", 0),
            "skills_available": maturity_details.get("dimensions", {}).get("skills_available", 0),
            "gap_cost_hours": maturity_details.get("gap_cost_hours", 0),
        },
        "maturity_details": maturity_details,
    }

    logger.info("Domain assessment for '%s': %s (%.1f, %s)",
                 industry or "unknown", primary_domain,
                 result["primary_maturity_score"], result["primary_maturity_level"])

    return result
