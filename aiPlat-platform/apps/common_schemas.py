"""Common response schemas — shared typed response_model classes for all platform modules.

Replaces bare `response_model=dict` / `response_model=Dict[str, Any]` with structured
Pydantic models, improving OpenAPI documentation and type safety across the platform.

Why ``extra="allow"``: many thin routes return domain fields (``eval_protocol``,
``artifact_id``, ``report``, nested ``data.items``) alongside the common envelope.
Strict models silently stripped those keys and broke Eval Center / protocol wiring.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class StatusResponse(BaseModel):
    """通用状态响应 — POST/PUT/DELETE 操作返回。"""

    model_config = ConfigDict(extra="allow")

    status: str = "ok"
    message: str = ""
    detail: Optional[str] = None


class ListResponse(BaseModel):
    """通用列表响应 — GET 集合端点返回（顶层 items/total）。"""

    model_config = ConfigDict(extra="allow")

    items: List[Dict[str, Any]] = []
    total: int = 0


class ItemResponse(BaseModel):
    """通用单项响应 — GET 单实体端点返回（载荷在 data 内）。"""

    model_config = ConfigDict(extra="allow")

    data: Dict[str, Any] = {}
