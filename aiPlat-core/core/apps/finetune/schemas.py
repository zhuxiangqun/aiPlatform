"""
Fine-tuning schemas — 数据集、作业、Provider 数据模型。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Dataset ──────────────────────────────────────────────────────────────

class DatasetSourceType(str, Enum):
    UPLOAD = "upload"           # 用户上传 JSONL
    EXECUTION_LOG = "execution_log"  # 从执行日志筛选
    ARENA_RESULT = "arena_result"    # 从 Arena 对战结果导出


class DatasetFormat(str, Enum):
    JSONL = "jsonl"
    JSON = "json"


class DatasetStatus(str, Enum):
    READY = "ready"
    IMPORTING = "importing"
    VALIDATING = "validating"
    ERROR = "error"


# ── Dataset API models ──

class DatasetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    source_type: DatasetSourceType = DatasetSourceType.UPLOAD
    source_id: str = ""         # execution_id / arena_match_id
    source_filter: Optional[Dict[str, Any]] = None  # 筛选条件 JSON
    format: DatasetFormat = DatasetFormat.JSONL

class DatasetUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class DatasetImportRequest(BaseModel):
    content: str = Field(default="", description="JSONL raw content")
    file_name: str = ""

class DatasetResponse(BaseModel):
    id: str
    name: str
    description: str
    source_type: DatasetSourceType
    source_id: str
    source_filter: Optional[Dict[str, Any]] = None
    format: DatasetFormat
    sample_count: int = 0
    file_size_bytes: int = 0
    status: DatasetStatus = DatasetStatus.READY
    error: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

class DatasetListResponse(BaseModel):
    datasets: List[DatasetResponse]
    total: int

class DatasetPreviewResponse(BaseModel):
    dataset_id: str
    samples: List[Dict[str, Any]]   # 前 100 条样本
    total_count: int
    stats: Dict[str, Any] = Field(default_factory=dict)


# ── Job ──────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    QUEUED = "queued"
    VALIDATING = "validating"
    UPLOADING = "uploading"
    TRAINING = "training"
    VALIDATING_MODEL = "validating_model"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FineTuneProvider(str, Enum):
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    LOCAL = "local"


class FineTuneTemplate(str, Enum):
    GENERAL = "general"           # 通用增强
    CODE = "code"                 # 代码能力
    CUSTOMER_SERVICE = "customer_service"  # 客服场景
    CUSTOM = "custom"             # 自定义


TEMPLATE_HYPERPARAMS: Dict[str, Dict[str, Any]] = {
    "general": {"epochs": 3, "learning_rate_multiplier": 1.0, "batch_size": 4},
    "code": {"epochs": 4, "learning_rate_multiplier": 1.8, "batch_size": 2},
    "customer_service": {"epochs": 2, "learning_rate_multiplier": 0.6, "batch_size": 8},
    "custom": {},
}


class JobCreateRequest(BaseModel):
    base_model: str = Field(min_length=1, description="基模型名 (如 deepseek-chat)")
    dataset_id: str = Field(min_length=1)
    provider: FineTuneProvider = FineTuneProvider.DEEPSEEK
    template: FineTuneTemplate = FineTuneTemplate.GENERAL
    custom_name: str = ""           # 自定义微调后模型名
    hyperparams: Dict[str, Any] = Field(default_factory=dict)
    suffix: Optional[str] = None    # DeepSeek/OpenAI 风格的 suffix


class JobResponse(BaseModel):
    id: str
    base_model: str
    dataset_id: str
    dataset_name: str = ""
    provider: FineTuneProvider
    provider_job_id: str = ""
    result_model: str = ""         # 产出的模型名
    status: JobStatus
    template: FineTuneTemplate = FineTuneTemplate.GENERAL
    hyperparams: Dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    sample_count: int = 0
    created_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    estimated_duration_seconds: int = 0

class JobListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int


# ── Provider ─────────────────────────────────────────────────────────────

class ProviderInfo(BaseModel):
    name: FineTuneProvider
    display_name: str
    available: bool
    quota_total: int = 0
    quota_used: int = 0
    supported_base_models: List[str] = Field(default_factory=list)
    estimated_cost_per_job: str = ""

class ProviderListResponse(BaseModel):
    providers: List[ProviderInfo]

# ═══════════════════════════════════════════════════════════════
# Training job models (migrated from Dict[str,Any] 2026-07-13)
# ═══════════════════════════════════════════════════════════════

class TrainingJobResponse(BaseModel):
    job_id: str
    status: str = "running"
    iterations: int = 0
    episodes: int = 0
    avg_reward: float = 0.0
    avg_loss: float = 0.0
    error: Optional[str] = None

class TrainingJobListResponse(BaseModel):
    jobs: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    error: Optional[str] = None

class ModelListItem(BaseModel):
    name: str
    display_name: str = ""
    provider_name: str = ""
    purpose: str = ""
    capability_score: float = 0.0
    available: bool = True

class ModelListResponse(BaseModel):
    models: List[ModelListItem] = Field(default_factory=list)
    total: int = 0
    error: Optional[str] = None

# ═══════════════════════════════════════════════════════════════
# Union types for dynamic backend endpoints (2026-07-13)
# ═══════════════════════════════════════════════════════════════

from typing import Union as _Union

class JobStatusResponse(BaseModel):
    """Generic job status — backend-dependent fields."""
    job_id: str
    status: str = ""
    model_config = {"extra": "allow"}  # allow backend-specific extra fields

class JobStatusErrorResponse(BaseModel):
    job_id: str
    status: str = "error"
    error: str = ""

DistillJobResult = _Union[JobStatusResponse, JobStatusErrorResponse]
ScratchJobResult = _Union[JobStatusResponse, JobStatusErrorResponse]

class TrainingJobCreatedResponse(BaseModel):
    job_id: str
    status: str = "running"


# ── Request models ──────────────────────────────────────────────────

class TrainingStartRequest(BaseModel):
    base_model: str
    dataset_id: str = ""
    num_iterations: int = 1
    episodes_per_iter: int = 8


class DistillationStartRequest(BaseModel):
    teacher_model: str = ""
    student_model: str = ""
    dataset_id: str = ""
    temperature: float = 2.0
    alpha: float = 0.5
    mode: str = "lora"
    epochs: int = 3


class ScratchTrainingStartRequest(BaseModel):
    dataset_id: str
    model_architecture: str = "gpt2"
    output_model_name: str = ""
    epochs: int = 3
    batch_size: int = 4
    learning_rate: float = 5e-5
