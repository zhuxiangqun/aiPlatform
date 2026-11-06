"""Product-plane /healthz — FE EvalCenter probes for b1l_execution_stubs when proxy mode."""
from __future__ import annotations

from typing import Any, Dict, Union

from fastapi import APIRouter, Depends, Request, Response
from auth.deps import require_auth
from apps.common_schemas import ItemResponse
from apps.eval.api.eval_upstream import proxy_eval_store, proxy_status

router = APIRouter(tags=["eval-product-health"])


@router.get("/healthz", response_model=ItemResponse)
async def product_healthz(
    request: Request,
    _auth: str = Depends(require_auth),
) -> Union[Dict[str, Any], Response]:
    """Mirror standalone `GET /api/platform/apps/eval/healthz` when proxied.

    Cohost (no AIPLAT_EVAL_SERVICE_URL): return a minimal cohost payload so the
    path is not 404 — FE treats missing product healthz as soft-fail already.
    """
    proxied = await proxy_eval_store(request, path="/healthz")
    if proxied is not None:
        return proxied
    st = proxy_status()
    return {
        "data": {
            "status": "ok",
            "mode": st.get("mode") or "cohost",
            "deploy_unit": "central",
            "b1l_execution_stubs": False,
            "process_split_authorized": False,
            "note": "cohost product healthz — standalone stubs only when AIPLAT_EVAL_SERVICE_URL set",
        }
    }
