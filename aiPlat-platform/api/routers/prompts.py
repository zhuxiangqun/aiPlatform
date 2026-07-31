"""
Platform Prompt API — external callers can run prompt app templates.
Exposes the core POST /api/core/prompts/app/run endpoint for external use.
"""
from __future__ import annotations
from typing import Dict, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from auth.deps import require_auth

router = APIRouter(prefix="/platform/prompts", tags=["prompts"])


@router.post("/run", response_model=StatusResponse)
async def run_template(request: dict, _auth: str = Depends(require_auth)):
    """Run a prompt template: render variables → LLM → return output.
    
    Body: { template_id, instance_id?, variables, model? }
    """
    try:
        template_id = request.get("template_id", "")
        instance_id = request.get("instance_id", "")
        variables = request.get("variables", {})
        from core.api.core_facade import best_model_for_purpose  # v2.5
        model = request.get("model") or best_model_for_purpose("chat")

        if not template_id and not instance_id:
            raise HTTPException(status_code=400, detail="template_id or instance_id required")

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "http://localhost:8002/api/core/prompts/app/run",
                json={
                    "template_id": template_id,
                    "instance_id": instance_id,
                    "variables": variables,
                    "model": model,
                },
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Core unavailable: {str(e)[:200]}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Run failed: {str(e)[:200]}")
