"""Capability Boundary diagnostic — domain maturity, skill availability, gaps.

GET /api/core/diagnostics/capability-boundary
GET /api/core/diagnostics/capability-boundary?domain=supply-chain
"""

from __future__ import annotations

import json, logging, os, time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
import yaml as _yaml

from core.api.deps import actor_from_http
from core.api.routers.system import ItemResponse
from core.schemas_common import Dict

router = APIRouter(tags=["diagnostics-capability"])


def _load_registry() -> dict:
    path = os.path.expanduser("~/.aiplat/ontologies/registry.json")
    if not os.path.isfile(path):
        return {"domains": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_golden_queries() -> dict:
    path = os.path.expanduser("~/.aiplat/wiki/golden_queries.yaml")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return _yaml.safe_load(f) or {}


def _load_gaps(domain_id: str) -> List[dict]:
    path = os.path.expanduser(f"~/.aiplat/ontologies/{domain_id}_gaps.yaml")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = _yaml.safe_load(f) or {}
        return list(data.get("gaps", []))
    except Exception:
        return []


def _calculate_maturity(metrics: dict) -> str:
    e = metrics.get("wiki_entities", 0)
    s = metrics.get("skills_available", 0)
    q = metrics.get("golden_query_pass_rate", 0.0)
    a = metrics.get("adopted_count", 0)
    if q >= 0.95 and a > 0 and s >= 2 and e >= 15:
        return "production-ready"
    if q >= 0.85 and s >= 2 and e >= 15:
        return "stable"
    if e >= 15 and s >= 1:
        return "building"
    if e >= 5:
        return "growing"
    return "seeding"


def _build_recommend(domain_id: str, metrics: dict, skills: list, gaps: list) -> List[str]:
    recs = []
    e = metrics.get("wiki_entities", 0)
    s = metrics.get("skills_available", 0)
    q = metrics.get("golden_queries", 0)
    qr = metrics.get("golden_query_pass_rate", 0.0)
    p = metrics.get("domain_prompt_ready", False)
    seed = metrics.get("seed_data_ready", False)

    if e < 15:
        recs.append(f"种子数据不足（当前{e}实体，需≥15），运行 `python scripts/ingest_seed.py --domain {domain_id}`")
    if s == 0:
        recs.append(f"该域尚无可用的领域Skill，建议创建SKILL.md并设置 domain_id: {domain_id}")
    if q == 0:
        recs.append(f"无Golden Query，在golden_queries.yaml中添加domain_queries.{domain_id}条目")
    if q > 0 and qr < 0.8:
        recs.append(f"Golden Query通过率偏低（{qr:.0%}），建议增加种子数据和实体关系")
    if not p:
        recs.append(f"域提示词缺失，在~/.aiplat/ontologies/{domain_id}.yaml中添加llm_prompt字段")
    if not seed:
        recs.append(f"种子数据文件不存在，运行 `python scripts/seed_wiki.py --domain {domain_id}`")
    if e >= 15 and s >= 1:
        recs.append(f"运行 `python scripts/ingest_seed.py --domain {domain_id}` 完成数据注入和GraphIndex构建")
    return recs


async def _get_wiki_entity_count(domain_id: str) -> int:
    try:
        from core.harness.knowledge.wiki_engine import list_all_pages
        pages = list_all_pages(collection_id=domain_id)
        return len(pages) if pages else 0
    except Exception:
        return 0


async def _get_graph_stats_sync(domain_id: str) -> dict:
    try:
        from core.api.core_facade import GraphIndex  # P0-A2: 经 CoreFacade
        g = GraphIndex.load(domain_id)
        edge_count = sum(len(n.out_edges) for n in g._nodes.values())
        return {
            "edge_count": edge_count,
            "node_count": len(g._nodes),
        }
    except Exception:
        return {"edge_count": 0, "node_count": 0}


def _get_domain_prompt_ready(domain_id: str) -> bool:
    try:
        from core.api.core_facade import _sync_resolve  # P0-A2: 经 CoreFacade
        _sync_resolve(f"domain-prompt-{domain_id}")
        return True
    except Exception:
        return False


def _get_seed_data_ready(domain_id: str) -> bool:
    return os.path.isfile(os.path.expanduser(f"~/.aiplat/seed_data/{domain_id}.json"))


async def build_capability_boundary(domain_filter: Optional[str] = None) -> dict:
    registry = _load_registry()
    domains_config = registry.get("domains", {})
    golden = _load_golden_queries()
    domain_queries = golden.get("domain_queries", {})

    target_domains = {}
    if domain_filter:
        for did in domain_filter.split(","):
            did = did.strip()
            if did in domains_config:
                target_domains[did] = domains_config[did]
    else:
        target_domains = domains_config

    try:
        from core.apps.skills.registry import get_skill_registry
        skill_registry = get_skill_registry()
    except Exception:
        skill_registry = None

    domain_results = {}
    for domain_id, cfg in target_domains.items():
        # Metrics
        wiki_entities = await _get_wiki_entity_count(domain_id)
        graph_stats = await _get_graph_stats_sync(domain_id)
        wiki_relations = graph_stats.get("edge_count", 0)
        domain_prompt_ready = _get_domain_prompt_ready(domain_id)
        seed_data_ready = _get_seed_data_ready(domain_id)

        # Combine Wiki + GraphIndex entities for maturity calculation
        total_entities = wiki_entities + graph_stats.get("node_count", 0)

        # Golden queries
        gq_list = domain_queries.get(domain_id, [])
        golden_queries_count = len(gq_list) if isinstance(gq_list, list) else 0
        golden_query_pass_rate = 0.0  # Requires server to run GoldenQueryRunner

        # Skills
        domain_skills = []
        if skill_registry:
            domain_skills = skill_registry.get_domain_skills(domain_id)

        skills_available = len(domain_skills)
        skills_enabled = len([s for s in domain_skills if s.get("total_executions", 0) >= 0])
        adopted_count = skill_registry.get_domain_adopted_count(domain_id) if skill_registry else 0

        metrics = {
            "wiki_entities": total_entities,
            "wiki_relations": wiki_relations,
            "skills_available": skills_available,
            "skills_enabled": skills_enabled,
            "golden_queries": golden_queries_count,
            "golden_query_pass_rate": golden_query_pass_rate,
            "adopted_count": adopted_count,
            "last_ingest_at": None,
            "domain_prompt_ready": domain_prompt_ready,
            "seed_data_ready": seed_data_ready,
            "graph_traversal_depth": 2 if wiki_entities > 0 else 0,
            "cross_domain_links": 0,
        }

        maturity = _calculate_maturity(metrics)
        gaps = _load_gaps(domain_id)
        recommend = _build_recommend(domain_id, metrics, domain_skills, gaps)

        domain_results[domain_id] = {
            "name": cfg.get("name", domain_id),
            "maturity": maturity,
            "metrics": metrics,
            "skills": domain_skills,
            "known_gaps": gaps,
            "recommend_next": recommend,
        }

    # Summary counts
    maturity_counts = {"seeding": 0, "growing": 0, "building": 0, "stable": 0, "production-ready": 0}
    for d in domain_results.values():
        maturity_counts[d["maturity"]] = maturity_counts.get(d["maturity"], 0) + 1

    total_skills = 0
    total_domain_skills = 0
    if skill_registry:
        all_skills = skill_registry.list_all() if hasattr(skill_registry, 'list_all') else []
        total_skills = len(all_skills)
        total_domain_skills = sum(1 for s in all_skills
                                  if str(getattr(getattr(s, '_config', None), 'metadata', {}).get("domain_id", "")).strip())

    return {
        "version": "1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_maturity": "seeding" if maturity_counts["production-ready"] == 0 and maturity_counts["stable"] == 0 else "building",
        "summary": {
            "total_domains": len(domain_results),
            "seeding_domains": maturity_counts["seeding"],
            "building_domains": maturity_counts["building"],
            "stable_domains": maturity_counts["stable"],
            "production_ready_domains": maturity_counts["production-ready"],
            "domains_with_no_data": sum(1 for d in domain_results.values() if d["metrics"]["wiki_entities"] == 0),
            "total_unwired_skills": total_skills - total_domain_skills,
            "total_domain_skills": total_domain_skills,
        },
        "domains": domain_results,
    }


@router.get("/diagnostics/capability-boundary")
async def get_capability_boundary(
    domain: Optional[str] = Query(None),
    request: Any = None,
):
    """Return per-domain capability maturity, gaps, and recommendations."""
    try:
        data = await build_capability_boundary(domain)
        return data
    except Exception as e:
        logging.getLogger("aiplat.diagnostics.capability").error(str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/diagnostics/rag-quality", response_model=ItemResponse)
async def get_rag_quality(
    hours: Optional[int] = Query(24, ge=1, le=168),
    domain: Optional[str] = Query("default"),
):
    """Return RAG quality dashboard: faithfulness, hallucination risk, user signals, retrieval quality."""
    try:
        from core.harness.evaluation.rag_diagnostics_collector import RAGDiagnosticsCollector
        collector = RAGDiagnosticsCollector()
        dash = await collector.collect_quality_dashboard(
            domain_id=domain or "default",
            lookback_hours=hours or 24,
        )
        overall = collector.compute_overall_score(dash)
        status = collector._classify_status(dash)
        anomalies = collector._detect_anomalies(dash)

        result = dash.to_dict() if hasattr(dash, 'to_dict') else {
            "period": f"{hours}h",
            "hallucination": getattr(dash, 'hallucination', {}),
            "signals": getattr(dash, 'signals', {}),
            "retrieval": getattr(dash, 'retrieval', {}),
        }
        metrics = {
            "faithfulness_score": result.get("hallucination", {}).get("avg_faithfulness", 0) if isinstance(result.get("hallucination"), dict) else 0,
            "answer_relevancy_score": result.get("hallucination", {}).get("avg_relevancy_proxy", 0) if isinstance(result.get("hallucination"), dict) else 0,
            "retrieval_precision": result.get("retrieval", {}).get("gate_pass_rate", 0) if isinstance(result.get("retrieval"), dict) else 0,
            "total_sessions": result.get("hallucination", {}).get("total_checks", 0) if isinstance(result.get("hallucination"), dict) else 0,
            "retry_rate": result.get("signals", {}).get("abandon_rate", 0) if isinstance(result.get("signals"), dict) else 0,
        }
        return {
            "overall_score": overall,
            "status": status,
            "period": f"{hours}h",
            "metrics": metrics,
            "anomalies": anomalies,
            "detail": result,
        }
    except Exception as e:
        logging.getLogger("aiplat.diagnostics.rag").error(str(e), exc_info=True)
        return {
            "overall_score": 0,
            "status": "unavailable",
            "period": f"{hours}h",
            "metrics": {"faithfulness_score": 0, "answer_relevancy_score": 0, "retrieval_precision": 0, "total_sessions": 0, "retry_rate": 0},
            "anomalies": [],
            "detail": {"error": str(e)[:200]},
        }
