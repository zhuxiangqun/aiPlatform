"""Ontology Editor — Scenario Selection API (v2.7)."""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request

# 为什么：走 apps.common_schemas，避免 `from api.*` 环依赖
from apps.common_schemas import StatusResponse
from auth.request_identity import resolve_request_tenant

router = APIRouter(tags=["ontology-editor-scenarios"])


@router.get("/scenarios/compare", response_model=StatusResponse)
async def compare_domains(request: Request):
    """Cross-domain maturity comparison.

    Args:
        request: FastAPI Request；身份租户（N09 K18）。
    """
    try:
        tenant_id = resolve_request_tenant(request)
        from core.api.core_facade import compare_domains

        results = compare_domains(tenant_id=tenant_id)
        return {"domains": results, "total": len(results), "tenant_id": tenant_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/recommend", response_model=StatusResponse)
async def recommend_scenarios(
    request: Request,
    industry: str = Query(""),
    pain_points: str = Query(""),
    mode: str = Query("maturity"),
):
    """Recommend which domains to build first.

    Args:
        request: FastAPI Request；身份租户（N09 K18）。
        industry: industry 参数。
        pain_points: pain_points 参数。
        mode: mode 参数。
    """
    try:
        tenant_id = resolve_request_tenant(request)
        if mode == "scenario":
            from core.api.core_facade import recommend_order

            results = recommend_order(industry=industry, pain_points=pain_points)
        else:
            from core.api.core_facade import compare_domains

            results = compare_domains(tenant_id=tenant_id)
            results = [
                {
                    "domain_id": r["domain_id"],
                    "maturity_score": r["maturity_score"],
                    "level": r["level"],
                    "recommendation": (
                        "build_first" if r["maturity_score"] >= 60 else "defer"
                    ),
                }
                for r in results
            ]

        return {
            "recommendations": results,
            "total": len(results),
            "mode": mode,
            "tenant_id": tenant_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/report", response_model=StatusResponse)
async def export_report(request: Request, domain_ids: str = Query("")):
    """Export domain comparison report (markdown).

    Args:
        request: FastAPI Request；身份租户（N09 K18）。
        domain_ids: domain_ids 参数。
    """
    try:
        tenant_id = resolve_request_tenant(request)
        from core.api.core_facade import export_comparison_report

        ids = [d.strip() for d in domain_ids.split(",") if d.strip()] if domain_ids else None
        report = export_comparison_report(ids, format="md")
        return {"format": "markdown", "report": report, "tenant_id": tenant_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenarios/{domain_id}", response_model=StatusResponse)
async def upsert_scenario(domain_id: str, data: Dict[str, Any], request: Request):
    """Create or update a scenario definition for a domain (writes to registry.json).

    Args:
        domain_id: domain 标识。
        data: data 参数。
        request: FastAPI Request；身份租户（N09 K18）。
    """
    try:
        import json
        import os

        tenant_id = resolve_request_tenant(request)
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

        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "scenario": scenario_name,
            "status": "upserted",
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenarios/refresh-maturity/{domain_id}", response_model=StatusResponse)
async def refresh_maturity(domain_id: str, request: Request):
    """Refresh maturity scores for a domain.

    Args:
        domain_id: domain 标识。
        request: FastAPI Request；身份租户（N09 K18）。
    """
    try:
        tenant_id = resolve_request_tenant(request)
        from core.api.core_facade import DomainRouter

        router_obj = DomainRouter()
        # 为什么：N09 K19 — 成熟度刷新须按身份租户加载 GraphIndex
        result = router_obj.refresh_domain_maturity(domain_id, tenant_id=tenant_id)
        if isinstance(result, dict):
            return {**result, "tenant_id": tenant_id}
        return {"domain_id": domain_id, "tenant_id": tenant_id, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
