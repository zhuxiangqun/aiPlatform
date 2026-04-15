"""
Data Models for Management Module
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from datetime import datetime


@dataclass
class ResourceStats:
    """Resource statistics"""
    total: int
    used: int
    available: int
    utilization: float


@dataclass
class AllocatedResource:
    """Allocated resource"""
    allocation_id: str
    resource_type: str
    amount: int
    allocated_at: datetime
    expires_at: Optional[datetime]


@dataclass
class AlertRule:
    """Alert rule definition"""
    name: str
    metric: str
    threshold: float
    duration: int
    severity: str
    enabled: bool = True


@dataclass
class Alert:
    """Alert instance"""
    alert_id: str
    rule_name: str
    status: str
    message: str
    started_at: datetime
    resolved_at: Optional[datetime] = None


@dataclass
class CostBreakdown:
    """Cost breakdown"""
    date: str
    total: float
    by_model: Dict[str, float]
    by_user: Dict[str, float]


@dataclass
class BudgetStatus:
    """Budget status"""
    daily_used: float
    daily_limit: float
    daily_percentage: float
    monthly_used: float
    monthly_limit: float
    monthly_percentage: float
    alerts: List[str]


@dataclass
class SlowQuery:
    """Slow query information"""
    query_id: str
    sql: str
    duration_ms: int
    executed_at: datetime


@dataclass
class CacheStats:
    """Cache statistics"""
    hits: int
    misses: int
    keys: int
    used_memory: int
    hit_rate: float


@dataclass
class DBPoolStats:
    """Database connection pool statistics"""
    pool_size: int
    pool_min: int
    pool_max: int
    pool_available: int
    pool_in_use: int


# NodeManager schemas
@dataclass
class GPUStatus:
    """GPU status information"""
    gpu_id: str
    model: str
    utilization: float
    memory_used: int
    memory_total: int
    temperature: float
    power_usage: float
    status: str


@dataclass
class NodeInfo:
    """Node information"""
    name: str
    ip: str
    gpu_model: str
    gpu_count: int
    driver_version: str
    status: str
    gpus: List[GPUStatus]
    labels: Dict[str, str]
    conditions: List[Dict[str, Any]]
    created_at: datetime


@dataclass
class ServiceInfo:
    """Service information"""
    name: str
    namespace: str
    type: str
    image: str
    replicas: int
    ready_replicas: int
    gpu_count: int
    gpu_type: str
    status: str
    pods: List[Dict[str, Any]]
    config: Dict[str, Any]
    created_at: datetime


@dataclass
class ImageInfo:
    """Image information"""
    id: str
    name: str
    tag: str
    size: int
    type: str
    created_at: datetime
    vulnerability_scan: str


@dataclass
class QuotaInfo:
    """Resource quota information"""
    id: str
    name: str
    gpu_quota: int
    gpu_used: int
    team: str
    status: str
    created_at: datetime


@dataclass
class PolicyInfo:
    """Scheduling policy information"""
    id: str
    name: str
    type: str
    priority: int
    node_selector: Dict[str, str]
    status: str


@dataclass
class TaskInfo:
    """Task information"""
    id: str
    name: str
    gpu_count: int
    gpu_type: str
    queue: str
    priority: int
    status: str
    position: int
    estimated_wait_time: int
    submitter: str
    submitted_at: datetime


@dataclass
class AutoscalingPolicy:
    """Autoscaling policy information"""
    id: str
    service: str
    type: str
    min_replicas: int
    max_replicas: int
    current_replicas: int
    target_replicas: int
    metrics: List[Dict[str, Any]]
    status: str


# ModelManager schemas
from enum import Enum


class ModelType(Enum):
    """模型类型"""
    CHAT = "chat"
    EMBEDDING = "embedding"
    IMAGE = "image"
    AUDIO = "audio"


class ModelSource(Enum):
    """模型来源"""
    CONFIG = "config"
    LOCAL = "local"
    EXTERNAL = "external"


class ModelStatus(Enum):
    """模型状态"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
    NOT_CONFIGURED = "not_configured"


@dataclass
class ModelConfig:
    """模型配置参数"""
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: List[str] = None
    api_key_env: str = None
    base_url: str = None
    headers: Dict[str, str] = None
    
    def __post_init__(self):
        if self.stop is None:
            self.stop = []
        if self.headers is None:
            self.headers = {}


@dataclass
class ModelStats:
    """模型使用统计"""
    requests_total: int = 0
    requests_success: int = 0
    requests_failed: int = 0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_total: int = 0
    avg_latency_ms: float = 0.0
    last_request_at: datetime = None
    cost_total_usd: float = 0.0


@dataclass
class ModelInfo:
    """模型信息"""
    id: str
    name: str
    display_name: str = None
    type: ModelType = ModelType.CHAT
    provider: str = ""
    source: ModelSource = ModelSource.EXTERNAL
    enabled: bool = True
    status: ModelStatus = ModelStatus.NOT_CONFIGURED
    config: ModelConfig = None
    stats: ModelStats = None
    description: str = ""
    tags: List[str] = None
    capabilities: List[str] = None
    created_at: datetime = None
    updated_at: datetime = None
    
    def __post_init__(self):
        if self.config is None:
            self.config = ModelConfig()
        if self.stats is None:
            self.stats = ModelStats()
        if self.tags is None:
            self.tags = []
        if self.capabilities is None:
            self.capabilities = []
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.display_name is None:
            self.display_name = self.name