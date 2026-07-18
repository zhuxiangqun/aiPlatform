"""Common response schemas — shared typed response_model classes for all platform modules.

Replaces bare `response_model=dict` / `response_model=Dict[str, Any]` with structured
Pydantic models, improving OpenAPI documentation and type safety across the platform.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class StatusResponse(BaseModel):
    """通用状态响应 — POST/PUT/DELETE 操作返回"""
    status: str = "ok"
    message: str = ""
    detail: Optional[str] = None


class ListResponse(BaseModel):
    """通用列表响应 — GET 集合端点返回"""
    items: List[Dict[str, Any]] = []
    total: int = 0


class ItemResponse(BaseModel):
    """通用单项响应 — GET 单实体端点返回"""
    data: Dict[str, Any] = {}
