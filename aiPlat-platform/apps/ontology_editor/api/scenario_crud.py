u"""Ontology Editor — Scenario Selection API (v2.7)."""
from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional

router = APIRouter(tags=["ontology-editor-scenarios"])


@router.get("/scenarios/compare", response_model=Dict[str, Any])
async def compare_domains():
    u"""Cross-domain maturity comparison."""
    try:
        from core.harness.knowledge.domain_maturity import compare_domains
        results = compare_domains()
        return {"domains": results, "total": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/recommend", response_model=Dict[str, Any])
async def recommend_scenarios(
    industry: str = Query(""),
    pain_points: str = Query(""),
    mode: str = Query("maturity"),
):
    u"""Recommend which domains to build first.

    mode=maturity: rank by computed maturity scores
    mode=scenario: rank by scenario fitness (5 criteria + quadrant)
    """
    try:
        if mode == "scenario":
            from core.harness.knowledge.scenario_selector import recommend_order
            results = recommend_order(industry=industry, pain_points=pain_points)
        else:
            from core.harness.knowledge.domain_maturity import compare_domains
            results = compare_domains()
            results = [{"domain_id": r["domain_id"], "maturity_score": r["maturity_score"],
                         "level": r["level"], "recommendation":
                         "build_first" if r["maturity_score"] >= 60 else "defer"}
                        for r in results]

        return {"recommendations": results, "total": len(results), "mode": mode}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/report", response_model=Dict[str, Any])
async def export_report(domain_ids: str = Query("")):
    u"""Export domain comparison report (markdown)."""
    try:
        from core.harness.knowledge.domain_maturity import export_comparison_report
        ids = [d.strip() for d in domain_ids.split(",") if d.strip()] if domain_ids else None
        report = export_comparison_report(ids, format="md")
        return {"format": "markdown", "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenarios/{domain_id}", response_model=Dict[str, Any])
async def upsert_scenario(domain_id: str, data: Dict[str, Any]):
    u"""Create or update a scenario definition for a domain (writes to registry.json)."""
    try:
        import json, os

        base = os.path.expanduser(os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))
        reg_path = os.path.join(base, "registry.json")

        with open(reg_path) as f:
            reg = json.load(f)

        dom = reg.get("domains", {}).get(domain_id)
        if not dom:
            raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")

        dom.setdefault("scenarios", [])
        scenario_name = data.get("name", "")
        existing = [s for s in dom["scenarios"] if s.get("name") == scenario_name]
        scenario_data = {
            "name": scenario_name,
            "pain": data.get("pain", ""),
            "impact": data.get("impact", "medium"),
            "urgency": data.get("urgency", "medium"),
            "process_closure": data.get("process_closure", "unknown"),
            "data_availability": data.get("data_availability", "unknown"),
            "value_verifiability": data.get("value_verifiability", "unknown"),
            "semantic_asset_reuse": data.get("semantic_asset_reuse", "medium"),
        }
        if existing:
            existing[0].update(scenario_data)
        else:
            dom["scenarios"].append(scenario_data)

        with open(reg_path, "w") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2)

        return {"domain_id": domain_id, "scenario": scenario_name, "status": "upserted"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenarios/refresh-maturity/{domain_id}", response_model=Dict[str, Any])
async def refresh_maturity(domain_id: str):
    u"""Refresh maturity scores for a domain."""
    try:
        from core.harness.knowledge.domain_router import DomainRouter
        router = DomainRouter()
        result = router.refresh_domain_maturity(domain_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
