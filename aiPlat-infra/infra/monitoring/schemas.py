from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class MetricConfig:
    enabled: bool = True
    prefix: str = "ai_platform_infra"
    labels: Dict[str, str] = field(default_factory=dict)
    export_interval: int = 60


@dataclass
class HealthCheckConfig:
    enabled: bool = True
    path: str = "/health"
    interval: int = 30


@dataclass
class HeartbeatConfig:
    enabled: bool = True
    interval: int = 10
    timeout: int = 30


@dataclass
class AlertRule:
    name: str = ""
    metric: str = ""
    condition: str = ""
    level: str = "warning"
    cooldown: int = 300


@dataclass
class MonitoringConfig:
    enabled: bool = True
    port: int = 9090
    metrics: Optional[MetricConfig] = None
    health_check: Optional[HealthCheckConfig] = None
    heartbeat: Optional[HeartbeatConfig] = None
    alerts: List[AlertRule] = field(default_factory=list)
