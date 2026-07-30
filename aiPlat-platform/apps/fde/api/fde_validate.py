"""FDE — E2E Validation + Industry Benchmark."""
from __future__ import annotations

import os
from typing import Any, Dict
from apps.fde.api.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["fde-validate"])


# ════════════════════════════════════════════════════════════
# I: FDE E2E Validation — quick component connectivity test
# ════════════════════════════════════════════════════════════

@router.get("/validate", response_model=FdeItemResponse)
async def fde_validate():
    """Quick E2E validation of FDE pipeline component connectivity.

    Returns per-component pass/fail status. All checks use try/catch
    so a single failure doesn't block the rest.
    """
    checks = {}
    passed = 0
    total = 0

    def _check(key: str, fn):
        nonlocal passed, total
        total += 1
        try:
            v = fn()
            checks[key] = "pass" if v else "fail"
            passed += int(bool(v))
        except Exception as e:
            checks[key] = f"fail: {str(e)[:80]}"

    # 1. Domain registry load
    def _ck_domains():
        import json
        with open(os.path.expanduser("~/.aiplat/ontologies/registry.json")) as f:
            r = json.load(f)
        return len(r.get("domains", {})) >= 2

    # 2. Domain router classify
    def _ck_router():
        from core.api.core_facade import DomainRouter
        r = DomainRouter()
        return bool(r.classify("政务招标围标串标检测"))

    # 3. GraphIndex load
    def _ck_graph():
        from core.api.core_facade import GraphIndex
        g = GraphIndex.load("ai-knowledge")
        return g.stats().get("node_count", 0) >= 0

    # 4. Delivery graph
    def _ck_delivery():
        from core.api.core_facade import GraphIndex
        GraphIndex.load("fde-delivery")
        return True

    # 5. Ontology YAML load
    def _ck_ontology():
        from core.api.core_facade import load_ontology_from_yaml
        path = os.path.expanduser("~/.aiplat/ontologies/ai-knowledge.yaml")
        dom = load_ontology_from_yaml(path)
        return len(dom.classes) > 0

    # 6. Solution YAML load
    def _ck_solution():
        from core.api.core_facade import load_ontology_from_yaml
        path = os.path.expanduser("~/.aiplat/ontologies/ai-solution.yaml")
        dom = load_ontology_from_yaml(path)
        return len(dom.classes) > 0

    # 7. Consistency gate import
    def _ck_consistency():
        from core.harness.knowledge.consistency_gate import check_cross_stage_consistency
        warnings = check_cross_stage_consistency("## 2. Data Maturity\nmaturity=1\n## 6. Config\nUse GPT-4 large model")
        return len(warnings) > 0  # Should detect contradiction

    # 8. Cross-domain analog
    def _ck_cross_domain():
        from core.harness.knowledge.ontology_query_mapper import discover_cross_domain_analogs
        result = discover_cross_domain_analogs("AI技术")
        return isinstance(result, dict)

    _check("domains", _ck_domains)
    _check("router", _ck_router)
    _check("graph_index", _ck_graph)
    _check("delivery_tracking", _ck_delivery)
    _check("ontology_yaml", _ck_ontology)
    _check("solution_yaml", _ck_solution)
    _check("consistency_gate", _ck_consistency)
    _check("cross_domain_analog", _ck_cross_domain)

    return {
        "passed": passed,
        "total": total,
        "status": "healthy" if passed == total else "degraded",
        "checks": checks,
    }


# ════════════════════════════════════════════════════════════
# K: FDE Industry Benchmark — aggregated stats across all sessions
# ════════════════════════════════════════════════════════════

@router.get("/benchmark", response_model=FdeItemResponse)
async def fde_benchmark():
    """Aggregated statistics across all FDE diagnosis sessions.

    Returns per-industry breakdown: session count, action count, delivery rate,
    most common recommendations, and readiness score distribution.
    """
    try:
        from core.api.core_facade import GraphIndex

        fd = GraphIndex.load("fde-delivery")
        industries: dict = {}
        total_sessions = 0
        total_actions = 0
        all_actions: list = []

        for nid, node in list(fd._nodes.items()):
            if getattr(node, "class_name", "") != "DiagnosisSession":
                continue
            total_sessions += 1
            name = node.entity_name

            # Infer industry from session metadata (stored in entity_name as "{industry}_{company}")
            parts = name.split("_", 1)
            ind = parts[0].lower() if parts else "unknown"
            if len(ind) < 2 or len(ind) > 20:
                ind = "unknown"

            if ind not in industries:
                industries[ind] = {"sessions": 0, "actions": 0, "delivered": 0, "top_actions": []}

            industries[ind]["sessions"] += 1
            neighbors = fd.get_neighbor_edges(nid, direction="outgoing")
            has_actions = False
            for neighbor_id, edge in neighbors:
                if edge.relation_name == "has_action":
                    has_actions = True
                    action_node = fd.get_node(neighbor_id)
                    if action_node:
                        aname = action_node.entity_name[:80]
                        industries[ind]["actions"] += 1
                        all_actions.append({"industry": ind, "action": aname})
            if has_actions:
                industries[ind]["delivered"] += 1

        # Compute per-industry delivery rate and top actions
        for ind, data in industries.items():
            data["delivery_rate"] = (
                round(data["delivered"] / data["sessions"] * 100)
                if data["sessions"] else 0
            )
            # Top actions for this industry
            ind_actions = [a["action"] for a in all_actions if a["industry"] == ind]
            from collections import Counter
            data["top_actions"] = [a[0] for a in Counter(ind_actions).most_common(5)]

        # Global top actions
        from collections import Counter as _Counter
        global_actions = [a["action"] for a in all_actions]
        top_global = [a[0] for a in _Counter(global_actions).most_common(10)]

        # Delivery rate trend (recent vs overall)
        overall_rate = round(
            sum(d["delivered"] for d in industries.values()) /
            max(total_sessions, 1) * 100
        )

        return {
            "total_sessions": total_sessions,
            "total_actions": sum(d["actions"] for d in industries.values()),
            "overall_delivery_rate": overall_rate,
            "industries": {
                ind: {
                    "sessions": d["sessions"],
                    "actions": d["actions"],
                    "delivery_rate": d["delivery_rate"],
                    "top_actions": d["top_actions"],
                }
                for ind, d in sorted(industries.items(),
                                    key=lambda x: x[1]["sessions"], reverse=True)
            },
            "top_recommendations": top_global,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Benchmark failed: {str(e)[:300]}")
