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
    """GET /fde/dashboard/evolution — 四卡片 + 时间线聚合"""
    pending_decisions: List[Dict[str, Any]] = []
    signal_alerts: List[Dict[str, Any]] = []
    trace_anomalies: List[Dict[str, Any]] = []
    training: Dict[str, Any] = {}
    timeline: List[Dict[str, Any]] = []
    last_updated: str = ""


class DeliveryPlanPipelineSnapshot(BaseModel):
    """FDE 八步 pipeline 布尔快照（交付计划进度联动）。"""
    customer: bool = False
    domain: bool = False
    diagnosis: bool = False
    pocProfile: bool = False
    deployVersion: bool = False
    canaryResult: bool = False
    adopted: bool = False


class DeliveryPlanGenerateRequest(BaseModel):
    """POST /delivery-plan/generate — 由需求文本生成实施计划。"""
    customer_namespace: str
    requirement_text: str
    title: str = ""
    pipeline_snapshot: Optional[DeliveryPlanPipelineSnapshot] = None


class DeliveryPlanRefreshRequest(BaseModel):
    """POST /delivery-plan/refresh — 按 pipeline 重算进度。"""
    customer_namespace: str
    pipeline_snapshot: Optional[DeliveryPlanPipelineSnapshot] = None


class DeliveryPlanStepPatchRequest(BaseModel):
    """PATCH /delivery-plan/steps/{step_id} — 人工勾选（仅 auto_check 为空）。"""
    customer_namespace: str
    manual_done: bool = True
    pipeline_snapshot: Optional[DeliveryPlanPipelineSnapshot] = None
