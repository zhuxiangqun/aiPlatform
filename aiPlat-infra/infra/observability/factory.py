from typing import Optional
from .schemas import ObservabilityConfig
from .base import Tracer, OTelMetrics, OTelLogger
from .tracing import SimpleTracer, SimpleOTelMetrics, SimpleOTelLogger


def create_observability(config: Optional[ObservabilityConfig] = None) -> dict:
    config = config or ObservabilityConfig()

    return {
        "tracer": SimpleTracer(config),
        "metrics": SimpleOTelMetrics(config),
        "logger": SimpleOTelLogger(config),
    }


def create_tracer(config: Optional[ObservabilityConfig] = None) -> Tracer:
    config = config or ObservabilityConfig()
    return SimpleTracer(config)


def create_otel_metrics(config: Optional[ObservabilityConfig] = None) -> OTelMetrics:
    config = config or ObservabilityConfig()
    return SimpleOTelMetrics(config)


def create_otel_logger(config: Optional[ObservabilityConfig] = None) -> OTelLogger:
    config = config or ObservabilityConfig()
    return SimpleOTelLogger(config)
