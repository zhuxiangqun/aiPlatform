from typing import Optional
from .schemas import ObservabilityConfig
from .base import Tracer, OTelMetrics, OTelLogger
from .tracing import SimpleTracer, SimpleOTelMetrics, SimpleOTelLogger
from .otel import OTelTracer, OTelMetricsImpl, OTelLoggerImpl


def create_observability(config: Optional[ObservabilityConfig] = None) -> dict:
    config = config or ObservabilityConfig()

    provider = (config.provider or "otel").lower()
    if not config.enabled:
        provider = "simple"

    if provider == "simple":
        return {"tracer": SimpleTracer(config), "metrics": SimpleOTelMetrics(config), "logger": SimpleOTelLogger(config)}
    return {"tracer": OTelTracer(config), "metrics": OTelMetricsImpl(config), "logger": OTelLoggerImpl(config)}


def create_tracer(config: Optional[ObservabilityConfig] = None) -> Tracer:
    config = config or ObservabilityConfig()
    provider = (config.provider or "otel").lower()
    if not config.enabled or provider == "simple":
        return SimpleTracer(config)
    return OTelTracer(config)


def create_otel_metrics(config: Optional[ObservabilityConfig] = None) -> OTelMetrics:
    config = config or ObservabilityConfig()
    provider = (config.provider or "otel").lower()
    if not config.enabled or provider == "simple":
        return SimpleOTelMetrics(config)
    return OTelMetricsImpl(config)


def create_otel_logger(config: Optional[ObservabilityConfig] = None) -> OTelLogger:
    config = config or ObservabilityConfig()
    provider = (config.provider or "otel").lower()
    if not config.enabled or provider == "simple":
        return SimpleOTelLogger(config)
    return OTelLoggerImpl(config)
