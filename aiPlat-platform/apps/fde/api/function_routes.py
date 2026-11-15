"""FDE Function invoke — 薄路由，经 CoreFacade 调 FunctionRegistry。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-functions"])


class FunctionInvokeBody(BaseModel):
    """Function invoke 请求体。"""

    params: Dict[str, Any] = Field(default_factory=dict)


def _parse_scopes(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


@router.post("/functions/{function_id}/invoke")
async def invoke_function_route(
    request: Request,
    function_id: str,
    body: FunctionInvokeBody = Body(default_factory=FunctionInvokeBody),
    actor: str = Query("", description="caller actor"),
    x_aiplat_scopes: Optional[str] = Header(None, alias="X-AIPLAT-SCOPES"),
):
    """调用无副作用 Function（L1 permissions + side_effects 硬门）。

    Args:
        request: FastAPI Request。
        function_id: FunctionContract id（路径可含冒号，需 URL 编码）。
        body: 输入 params。
        actor: 操作者。
        x_aiplat_scopes: 权限 scopes。
    """
    from core.api.core_facade import invoke_function

    permissions = _parse_scopes(x_aiplat_scopes)
    if not permissions:
        permissions = _parse_scopes(request.headers.get("X-AIPLAT-SCOPES"))

    out = await invoke_function(
        function_id,
        body.params if body else {},
        permissions=permissions or None,
        actor=actor or "",
    )
    status = out.get("status")
    if status == "not_found":
        raise HTTPException(status_code=404, detail=out.get("reason") or "not_found")
    if status == "policy_denied":
        raise HTTPException(status_code=403, detail=out.get("reason") or "policy_denied")
    if status == "side_effects_forbidden":
        raise HTTPException(
            status_code=422, detail=out.get("reason") or "side_effects_forbidden"
        )
    if status in ("timeout", "error"):
        raise HTTPException(status_code=500, detail=out.get("reason") or status)
    return out
