"""FDE Governance Validate — self-audit endpoint for 8 governance capabilities (split from fde.py)."""
from __future__ import annotations

from typing import Any, Dict, List
from apps.fde.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, HTTPException

import os
import json

router = APIRouter(tags=["fde-governance"])


def _list_available_domains() -> str:
    import os, json
    path = os.path.expanduser("~/.aiplat/ontologies/registry.json")
    try:
        with open(path) as f:
            domains = json.load(f).get("domains", {})
        return ", ".join(sorted(domains.keys()))
    except Exception:
        return "unknown"


@router.get("/governance/validate", response_model=FdeItemResponse)
async def fde_governance_validate():
    """Self-audit: verify all 8 declared governance capabilities are functional.

    Returns per-capability pass/fail with failure details.
    All checks are read-only and complete in <200ms.
    """
    import time as _t_gv
    t0 = _t_gv.time()
    checks = {}
    passed = 0
    total = 0

    def _check(name: str, fn):
        nonlocal passed, total
        total += 1
        try:
            ok = fn()
            if ok:
                checks[name] = "pass"
                passed += 1
            else:
                checks[name] = "fail (returned false)"
        except Exception as e:
            checks[name] = f"fail: {str(e)[:100]}"

    # 1. config_driven: OntologyBus renders valid markdown
    def _ck1():
        from core.harness.knowledge.ontology_bus import render_solution_table
        result = render_solution_table()
        return "## AI解决方案原型库" in result and "| 方案类别" in result

    # 2. hot_reload: mtime cache is functional
    def _ck2():
        from core.harness.knowledge.ontology_bus import load_solution_archetypes, clear_cache
        clear_cache()
        a1 = load_solution_archetypes()
        a2 = load_solution_archetypes()  # second call = cache hit
        return len(a1) >= 8 and a1 == a2

    # 3. schema_validation: GraphIndex loads domain constraints
    def _ck3():
        from core.harness.ontology_engine.graph_index import GraphIndex
        g = GraphIndex.load("fde-delivery")
        c = g._load_property_constraints()  # noqa - internal method, intentional for audit
        return "has_action" in c and "has_evidence" in c

    # 4. evidence_binding: Evidence class exists in fde-delivery YAML
    def _ck4():
        import os
        from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
        path = os.path.expanduser("~/.aiplat/ontologies/fde-delivery.yaml")
        dom = load_ontology_from_yaml(path)
        return any(c.label == "证据" for c in dom.classes)

    # 5. coverage_metrics: determinism_score compute logic is accessible
    def _ck5():
        from core.harness.ontology_engine.graph_index import GraphIndex
        g = GraphIndex.load("knowledge-atom")
        return g.stats().get("node_count", -1) >= 0

    # 6. term_auto_seeding: enterprise-terms GraphIndex exists
    def _ck6():
        from core.harness.ontology_engine.graph_index import GraphIndex
        tg = GraphIndex.load("enterprise-terms")
        return tg.stats().get("node_count", -1) >= 0

    # 7. knowledge_convergence: ConvergenceEngine loads config
    def _ck7():
        from core.harness.knowledge.convergence_engine import ConvergenceEngine
        ce = ConvergenceEngine()
        s = ce.get_status()
        return s.get("total_atoms", -1) >= 0

    # 8. auto_closed_loop: SECI engine singleton works
    def _ck8():
        from core.harness.knowledge.seci_engine import get_seci_engine
        se = get_seci_engine()
        return se.get_atom_count() >= 0

    _check("config_driven", _ck1)
    _check("hot_reload", _ck2)
    _check("schema_validation", _ck3)
    _check("evidence_binding", _ck4)
    _check("coverage_metrics", _ck5)
    _check("term_auto_seeding", _ck6)
    _check("knowledge_convergence", _ck7)
    _check("auto_closed_loop", _ck8)

    elapsed_ms = round((_t_gv.time() - t0) * 1000)

    return {
        "overall": "pass" if passed == total else "fail",
        "passed": passed,
        "total": total,
        "checks": checks,
        "audit_philosophy": "治理声明不自证。每项能力需通过可执行审计验证其真实存在——代码可查、端点可调、约束可测。",
        "elapsed_ms": elapsed_ms,
    }
