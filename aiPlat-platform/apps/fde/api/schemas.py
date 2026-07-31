"""FDE response schemas — typed response_model classes for FDE API endpoints.

Replaces bare `response_model=StatusResponse` with structured Pydantic models,
improving OpenAPI documentation and type safety for API consumers.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class FdeStatusResponse(BaseModel):
    """通用状态响应 — 用于返回操作结果的端点（如 POST/PUT/DELETE）"""
    status: str = "ok"
    message: str = ""
    data: Optional[Dict[str, Any]] = None


class FdeListResponse(BaseModel):
    """通用列表响应 — 用于返回集合的端点（如 GET list endpoints）"""
    items: List[Dict[str, Any]] = []
    total: int = 0


class FdeItemResponse(BaseModel):
    """通用单项响应 — 用于返回单个实体的端点"""
    data: Dict[str, Any] = {}


class FdeHealthResponse(BaseModel):
    """GET /fde/health — 全组件健康检查聚合"""
    status: str = "healthy"
    components: Dict[str, Any] = {}
    warnings: List[str] = []
    uptime_ms: int = 0


class FdeFreezeResponse(BaseModel):
    """POST /fde/project/freeze — 项目中止冻结归档"""
    status: str = "frozen"
    archive_summary: Dict[str, Any] = {}
    message: str = ""


class FdeDashboardResponse(BaseModel):
    """GET /fde/dashboard — 四卡片 + 时间线聚合"""
    pending_decisions: List[Dict[str, Any]] = []
    signal_alerts: List[Dict[str, Any]] = []
    trace_anomalies: List[Dict[str, Any]] = []
    training: Dict[str, Any] = {}
    timeline: List[Dict[str, Any]] = []
    last_updated: str = ""
