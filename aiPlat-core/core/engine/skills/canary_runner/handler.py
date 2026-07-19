u"""
Canary Runner Handler (v2.7) — scoring_engine-powered quality gates.

Replaces hardcoded thresholds with configurable scoring models
that adapt to domain maturity levels.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from core.harness.infrastructure.gateway.fde_notifier import _notify_safe

logger = logging.getLogger("canary_runner")


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    u"""Run canary quality gates with dynamic thresholds.

    Input: { domain_id, canary_data: { error_rate, latency_p95, golden_pass_rate } }
    """
    domain_id = params.get("domain_id", "")
    canary_data = params.get("canary_data", {})

    # ── Load or build canary_quality scoring model ──
    maturity_score = 50.0
    try:
        from core.harness.knowledge.domain_maturity import compute_domain_maturity
        maturity = compute_domain_maturity(domain_id)
        maturity_score = maturity.get("maturity_score", 50)
    except Exception:
        pass

    # Dynamic thresholds based on maturity: lower maturity → looser thresholds
    # 5 levels: seeding[0-20), growing[20-40), building[40-60), stable[60-80), production-ready[80-100]
    level_idx = min(4, max(0, int(maturity_score / 20)))
    thresholds = {
        "error_rate": [15.0, 10.0, 8.0, 5.0, 3.0][level_idx],
        "latency_p95": [10.0, 5.0, 3.0, 2.0, 1.0][level_idx],
        "golden_pass_rate": [60.0, 70.0, 80.0, 90.0, 95.0][level_idx],
    }

    # ── Evaluate using scoring_engine ──
    scores = {}
    details = []
    rules = [
        ("error_rate", "error_pct", ">", thresholds["error_rate"], 3,
         f"错误率 > {thresholds['error_rate']}%"),
        ("latency_p95", "latency_p95", ">", thresholds["latency_p95"], 2,
         f"P95延迟 > {thresholds['latency_p95']}s"),
        ("golden_pass", "golden_pass_rate", "<", thresholds["golden_pass_rate"], 2,
         f"Golden通过率 < {thresholds['golden_pass_rate']}%"),
    ]

    total_score = 0
    for rule_name, field, op, threshold, weight, desc in rules:
        value = float(canary_data.get(field, 0))
        violated = (op == ">" and value > threshold) or (op == "<" and value < threshold)
        score = weight if not violated else 0
        total_score += score
        scores[rule_name] = score
        details.append({
            "rule": rule_name, "field": field, "value": value,
            "threshold": threshold, "operator": op, "violated": violated,
            "weight": weight, "score": score,
        })

    max_score = sum(r[3] for r in rules)
    passed = total_score >= max_score * 0.6

    result = {
        "passed": passed,
        "total_score": total_score,
        "max_score": max_score,
        "pass_pct": round(total_score / max_score * 100, 1),
        "maturity_score": maturity_score,
        "thresholds_used": thresholds,
        "rule_scores": scores,
        "details": details,
        "recommendation": "proceed" if passed else "hold — quality gates not met",
    }

    logger.info("Canary check for %s: %s (%.1f/%.0f, maturity=%.0f)",
                 domain_id, "PASS" if passed else "FAIL",
                 total_score, max_score, maturity_score)

    _notify_safe("灰度质量门禁", domain_id, {"passed": result["passed"], "score": result["total_score"]})

    return result
