"""Response models for the FDE workbench endpoints (workbench.py)."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CapabilityItem(BaseModel):
    """工作台能力条目。"""

    id: str
    name: str
    desc: str = ""
    icon: str = ""


class TaskSubmitResponse(BaseModel):
    """任务提交响应。"""

    run_id: str
    status: str
    spec_id: str = ""


class TaskFeedbackResponse(BaseModel):
    """任务反馈响应。"""

    run_id: str
    rating: int
    recorded: bool = True


class TrainingStatusResponse(BaseModel):
    """LoRAAutoTrigger 训练流水线状态（端点返回 get_status() + 附加字段）"""

    enabled: bool = False
    approved_total: int = 0
    quality_count: int = 0
    threshold: int = 0
    quality_threshold: float = 0.0
    max_samples: int = 0
    progress_pct: float = 0.0
    ready_to_trigger: bool = False
    dataset_dir: str = ""
    latest_model: str = ""
    latest_model_completed_at: str = ""
    dataset_count: int = 0
    error: Optional[str] = None


class SkillInstallResponse(BaseModel):
    """Skill 安装响应。"""

    status: str
    skill: str
    source: str = ""


class SeedDemoResponse(BaseModel):
    """演示种子写入响应。"""

    seeded: int
    specs: List[str] = Field(default_factory=list)
    note: str = ""


class BatchResultItem(BaseModel):
    """批量操作单项结果。"""

    spec_id: str
    status: str
    error: Optional[str] = None


class BatchMarkStableResponse(BaseModel):
    """批量标记稳定响应。"""

    total: int
    stable: int
    results: List[BatchResultItem] = Field(default_factory=list)


# ── Request models ──────────────────────────────────────────────────

class TaskSubmitRequest(BaseModel):
    """任务提交请求。"""

    description: str
    capability: str = "general"
    spec_id: str = ""
    run_id: str = ""


class TaskFeedbackRequest(BaseModel):
    """任务反馈请求。"""

    rating: int = 0
    action: str = "useful"


class SpecCreateRequest(BaseModel):
    """创建 Spec 请求。"""

    spec_id: str
    content: dict = Field(default_factory=dict)
    created_by: str = "developer"


class SpecReviseRequest(BaseModel):
    """修订 Spec 请求。"""

    content: dict
    trigger: str = "manual"
    trigger_detail: str = ""
    created_by: str = "developer"
    affected_stages: Optional[List[int]] = None
    re_execute: bool = False


class SkillInstallRequest(BaseModel):
    """Skill 安装请求。"""

    url: str


class SpecPromotionRequest(BaseModel):
    """Spec 晋升请求。"""

    target_platform: str = "platform"
    reason: str = ""


class SpecApproveRequest(BaseModel):
    """Spec 审批通过请求。"""

    approver: str = "admin"
    note: str = ""


class SpecRejectRequest(BaseModel):
    """Spec 驳回请求。"""

    approver: str = "admin"
    reason: str = ""
