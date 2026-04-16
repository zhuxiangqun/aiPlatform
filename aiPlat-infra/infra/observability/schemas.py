from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class TracingConfig:
    enabled: bool = True
    service_name: str = "ai-platform-infra"
    exporter: str = "otlp"
    endpoint: str = "http://localhost:4317"
    sample_rate: float = 1.0
    include_attributes: List[str] = field(default_factory=list)


@dataclass
class MetricsConfig:
    enabled: bool = True
    exporter: str = "otlp"
    endpoint: str = "http://localhost:4317"
    interval: int = 60


@dataclass
class LoggingConfig:
    enabled: bool = True
    exporter: str = "otlp"
    level: str = "INFO"
    include_trace_context: bool = True


@dataclass
class ResourceConfig:
    service_name: str = "ai-platform-infra"
    service_version: str = "1.0.0"
    deployment_environment: str = "development"


@dataclass
class ObservabilityConfig:
    enabled: bool = True
    # Provider: "otel" uses opentelemetry-sdk; "simple" uses in-memory Simple* implementation
    provider: str = "otel"
    tracing: Optional[TracingConfig] = None
    metrics: Optional[MetricsConfig] = None
    logging: Optional[LoggingConfig] = None
    resource: Optional[ResourceConfig] = None
