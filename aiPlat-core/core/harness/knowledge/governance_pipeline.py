u"""
Governance Pipeline — 6-step governance cycle orchestrator (v2.8).

Orchestrates: scenario identification → semantic modeling → data mapping →
             quality validation → service publishing → feedback optimization.

Produces GovernanceCycleResult with health scores and actionable recommendations.
"""
from __future__ import annotations

import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("governance_pipeline")

HISTORY_DIR = _os.path.expanduser("~/.aiplat/governance_cycles")


@dataclass
class StepResult:
    step_index: int
    step_name: str
    status: str = "completed"          # completed | skipped | warning | failed
    metrics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class GovernanceCycleResult:
    cycle_id: str
    timestamp: str
    domain_id: str
    step_results: List[StepResult] = field(default_factory=list)
    overall_health: float = 0.0
    health_level: str = "unknown"
    recommendations: List[str] = field(default_factory=list)
    triggered_actions: List[str] = field(default_factory=list)


async def run_cycle(
    domain_id: str,
    *,
    steps: List[str] = None,
    auto_publish: bool = False,
) -> GovernanceCycleResult:
    u"""Run the 6-step governance cycle for a domain."""
    import time
    cycle_id = f"gov-cycle-{domain_id}-{int(time.time())}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result = GovernanceCycleResult(cycle_id=cycle_id, timestamp=now, domain_id=domain_id)

    all_steps = steps or ["scenario", "modeling", "mapping", "quality", "publishing", "feedback"]

    for idx, step_name in enumerate(all_steps):
        step = StepResult(step_index=idx + 1, step_name=step_name)
        t0 = time.time()

        try:
            if step_name == "scenario":
                _run_scenario_check(domain_id, step)
            elif step_name == "modeling":
                _run_modeling_check(domain_id, step)
            elif step_name == "mapping":
                _run_mapping_check(domain_id, step)
            elif step_name == "quality":
                _run_quality_check(domain_id, step)
            elif step_name == "publishing":
                _run_publishing_check(domain_id, step, auto_publish)
            elif step_name == "feedback":
                _run_feedback_check(domain_id, step)
        except Exception as e:
            step.status = "failed"
            step.warnings.append(str(e))
            logger.warning("Governance step %s failed for %s: %s", step_name, domain_id, e)

        step.duration_ms = (time.time() - t0) * 1000
        result.step_results.append(step)

    # Calculate overall health (weighted average)
    weights = {"scenario": 0.15, "modeling": 0.15, "mapping": 0.20, "quality": 0.20,
               "publishing": 0.15, "feedback": 0.15}
    total = 0.0
    for step in result.step_results:
        w = weights.get(step.step_name, 0.1)
        score = 100.0 if step.status == "completed" else 60.0 if step.status == "warning" else 30.0
        total += score * w
    result.overall_health = round(total, 1)

    if result.overall_health >= 80:
        result.health_level = "good"
    elif result.overall_health >= 60:
        result.health_level = "warning"
    else:
        result.health_level = "critical"

    # Generate recommendations
    for step in result.step_results:
        if step.status == "warning" or step.status == "failed":
            result.recommendations.append(f"[{step.step_name}] {'; '.join(step.warnings[:2])}")
        if step.status == "failed":
            result.triggered_actions.append(f"alert:{step.step_name}_failed")

    _save_cycle(result)
    logger.info("Governance cycle %s: health=%.1f (%s)", domain_id,
                 result.overall_health, result.health_level)
    return result


async def run_all_domains() -> List[GovernanceCycleResult]:
    u"""Run governance cycle for all registered domains."""
    from core.harness.knowledge.domain_router import DomainRouter
    router = DomainRouter()
    domains = router.list_domains()
    results = []
    for did in domains:
        result = await run_cycle(did)
        results.append(result)
    return results


def get_cycle_history(domain_id: str = "", limit: int = 10) -> List[Dict]:
    u"""Get historical governance cycle results."""
    import json, os
    if not os.path.exists(HISTORY_DIR):
        return []
    results = []
    for fname in sorted(os.listdir(HISTORY_DIR), reverse=True)[:limit]:
        if domain_id and domain_id not in fname:
            continue
        try:
            with open(os.path.join(HISTORY_DIR, fname)) as f:
                results.append(json.load(f))
        except Exception:
            pass
    return results[:limit]


def _save_cycle(result: GovernanceCycleResult):
    import json, os
    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = os.path.join(HISTORY_DIR, f"{result.cycle_id}.json")
    data = {
        "cycle_id": result.cycle_id, "timestamp": result.timestamp,
        "domain_id": result.domain_id, "overall_health": result.overall_health,
        "health_level": result.health_level, "recommendations": result.recommendations,
        "step_results": [{k: getattr(s, k) for k in ("step_index", "step_name", "status", "metrics", "warnings", "duration_ms")}
                          for s in result.step_results],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _run_scenario_check(domain_id: str, step: StepResult):
    try:
        from core.harness.knowledge.domain_maturity import compute_domain_maturity
        maturity = compute_domain_maturity(domain_id)
        step.metrics = {"maturity_score": maturity["maturity_score"],
                         "level": maturity["level"]}
        if maturity["maturity_score"] < 40:
            step.status = "warning"
            step.warnings.append("Domain maturity is low (<40), consider seeding data")
    except Exception as e:
        step.status = "warning"
        step.warnings.append(f"Maturity compute failed: {e}")


def _run_modeling_check(domain_id: str, step: StepResult):
    try:
        import yaml, os
        base = os.path.expanduser(os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))
        yp = os.path.join(base, f"{domain_id}.yaml")
        if not os.path.exists(yp):
            step.status = "failed"
            step.warnings.append("Domain YAML file not found")
            return
        with open(yp) as f:
            raw = yaml.safe_load(f) or {}
        classes = raw.get("classes", {})
        props = raw.get("object_properties", [])
        rules = raw.get("inference_rules", [])
        step.metrics = {"class_count": len(classes), "property_count": len(props),
                         "rule_count": len(rules)}
        if not classes:
            step.status = "warning"
            step.warnings.append("No classes defined")
    except Exception as e:
        step.status = "warning"
        step.warnings.append(f"Modeling check failed: {e}")


def _run_mapping_check(domain_id: str, step: StepResult):
    try:
        import json, os
        base = os.path.expanduser("~/.aiplat/datasources")
        sources = 0
        mapped = 0
        if os.path.isdir(base):
            for fname in os.listdir(base):
                if fname.endswith(".yaml"):
                    sources += 1
                    import yaml
                    with open(os.path.join(base, fname)) as f:
                        ds = yaml.safe_load(f) or {}
                    mappings = ds.get("mapping", {}).get("field_mapping", [])
                    if mappings:
                        mapped += 1
        coverage = round(mapped / max(sources, 1) * 100, 1)
        step.metrics = {"sources": sources, "mapped_sources": mapped,
                         "coverage_pct": coverage}
        if coverage < 50:
            step.status = "warning"
            step.warnings.append(f"Mapping coverage low: {coverage}%")
    except Exception as e:
        step.status = "warning"
        step.warnings.append(f"Mapping check failed: {e}")


def _run_quality_check(domain_id: str, step: StepResult):
    try:
        from core.harness.knowledge.domain_maturity import compute_domain_maturity
        maturity = compute_domain_maturity(domain_id)
        dims = maturity.get("dimensions", {})
        step.metrics = {"eval_score": dims.get("eval_score"),
                         "pass_rate": dims.get("pass_rate", 0)}
        if dims.get("eval_score") is None:
            step.status = "warning"
            step.warnings.append("Golden query eval not configured (eval_score=None)")
    except Exception as e:
        step.status = "warning"
        step.warnings.append(f"Quality check failed: {e}")


def _run_publishing_check(domain_id: str, step: StepResult, auto_publish: bool):
    try:
        from core.harness.knowledge.domain_maturity import compute_domain_maturity
        maturity = compute_domain_maturity(domain_id)
        step.metrics = {"last_published": "auto" if auto_publish else "manual",
                         "maturity_score": maturity["maturity_score"]}
    except Exception as e:
        step.status = "warning"
        step.warnings.append(f"Publishing check failed: {e}")


def _run_feedback_check(domain_id: str, step: StepResult):
    try:
        import sqlite3, os, time
        db = os.path.expanduser("~/.aiplat/state_changes.db")
        feedback_count = 0
        if os.path.exists(db):
            conn = sqlite3.connect(db, timeout=5.0)
            row = conn.execute(
                "SELECT COUNT(*) FROM feedback WHERE domain_id = ? AND timestamp > ?",
                (domain_id, time.time() - 86400 * 30),
            ).fetchone()
            if row:
                feedback_count = row[0]
            conn.close()
        step.metrics = {"feedback_count_30d": feedback_count}
    except Exception:
        step.metrics = {"feedback_count_30d": 0}
