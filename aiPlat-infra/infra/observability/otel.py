"""
OpenTelemetry SDK-backed implementations for infra.observability interfaces.

This module provides a "full" implementation (as opposed to the Simple* in-memory stubs):
- Tracing: opentelemetry-sdk tracer + span exporter (OTLP by default)
- Metrics: opentelemetry-sdk meter + OTLP metric exporter (OTLP by default)
- Logging: Python logging enriched with trace context (optional OTLP logs can be added later)

Design notes:
- Keep compatibility with existing code that expects tracer.start_span() to be usable as a context manager.
- Avoid hard dependency on any external backend by supporting exporter="in_memory" for tests.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional

from .base import Tracer, Span, SpanContext, OTelMetrics, OTelLogger, LogRecord
from .schemas import ObservabilityConfig, TracingConfig, MetricsConfig, LoggingConfig, ResourceConfig


_SDK_INITIALIZED = False
_IN_MEMORY_EXPORTER = None


def _ensure_sdk(config: ObservabilityConfig) -> None:
    global _SDK_INITIALIZED, _IN_MEMORY_EXPORTER
    if _SDK_INITIALIZED:
        return

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            SimpleSpanProcessor,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "opentelemetry-sdk is required for ObservabilityConfig(provider='otel'). "
            "Please add/install opentelemetry-sdk and exporters."
        ) from e

    tracing_cfg: TracingConfig = config.tracing or TracingConfig()
    metrics_cfg: MetricsConfig = config.metrics or MetricsConfig()
    res_cfg: ResourceConfig = config.resource or ResourceConfig()

    resource = Resource.create(
        {
            "service.name": res_cfg.service_name,
            "service.version": res_cfg.service_version,
            "deployment.environment": res_cfg.deployment_environment,
        }
    )

    # ---- Tracing provider ----
    tp = TracerProvider(resource=resource)
    exporter_name = (tracing_cfg.exporter or "otlp").lower()
    if exporter_name in ("in_memory", "memory"):
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        _IN_MEMORY_EXPORTER = InMemorySpanExporter()
        tp.add_span_processor(SimpleSpanProcessor(_IN_MEMORY_EXPORTER))
    else:
        # default: OTLP gRPC exporter
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Missing OTLP exporter. Install opentelemetry-exporter-otlp-proto-grpc."
            ) from e
        tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=tracing_cfg.endpoint)))

    trace.set_tracer_provider(tp)

    # ---- Metrics provider ----
    if metrics_cfg.enabled:
        exporter_name = (metrics_cfg.exporter or "otlp").lower()
        if exporter_name in ("otlp", "grpc"):
            try:
                from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            except Exception as e:  # pragma: no cover
                raise RuntimeError(
                    "Missing OTLP metric exporter. Install opentelemetry-exporter-otlp-proto-grpc."
                ) from e
            reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=metrics_cfg.endpoint),
                export_interval_millis=int(metrics_cfg.interval * 1000),
            )
            mp = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(mp)

    _SDK_INITIALIZED = True


def get_in_memory_span_exporter():
    """For tests: returns InMemorySpanExporter if configured, else None."""
    return _IN_MEMORY_EXPORTER


class OTelSpan(Span):
    def __init__(self, cm, otel_span):
        self._cm = cm
        self._span = otel_span

    # Context manager support (sync)
    def __enter__(self):
        # start_as_current_span returns a context manager; entering returns the span
        self._span = self._cm.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._cm.__exit__(exc_type, exc, tb)

    # Context manager support (async)
    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb):
        return self.__exit__(exc_type, exc, tb)

    def set_attribute(self, key: str, value: Any) -> None:
        try:
            self._span.set_attribute(key, value)
        except Exception:
            pass

    def add_event(self, name: str, attributes: Dict = None) -> None:
        try:
            self._span.add_event(name, attributes=attributes or {})
        except Exception:
            pass

    def set_status(self, code: str, message: str = "") -> None:
        try:
            from opentelemetry.trace.status import Status, StatusCode

            status_code = StatusCode.OK if str(code).lower() in ("ok", "success") else StatusCode.ERROR
            self._span.set_status(Status(status_code, message))
        except Exception:
            pass

    def end(self) -> None:
        try:
            self._span.end()
        except Exception:
            pass


class OTelTracer(Tracer):
    def __init__(self, config: ObservabilityConfig):
        self._config = config
        _ensure_sdk(config)

    def start_span(self, name: str, context: Optional[SpanContext] = None) -> Span:
        from opentelemetry import trace

        tracing_cfg = self._config.tracing or TracingConfig()
        tracer = trace.get_tracer(tracing_cfg.service_name)
        cm = tracer.start_as_current_span(name)
        # span returned by __enter__, but keep placeholder; OTelSpan handles it
        return OTelSpan(cm=cm, otel_span=None)

    def get_current_span(self) -> Optional[Span]:
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            # Wrap without a context manager
            return OTelSpan(cm=_NoopCM(), otel_span=span)
        except Exception:
            return None


class _NoopCM:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class OTelMetricsImpl(OTelMetrics):
    def __init__(self, config: ObservabilityConfig):
        self._config = config
        _ensure_sdk(config)
        from opentelemetry import metrics

        res_cfg = config.resource or ResourceConfig()
        self._meter = metrics.get_meter(res_cfg.service_name)

    def counter(self, name: str, **kwargs):
        c = self._meter.create_counter(name, unit=kwargs.get("unit"), description=kwargs.get("description"))

        class _C:
            def add(self, value: float, attributes: Dict = None) -> None:
                c.add(value, attributes=attributes or {})

        return _C()

    def up_down_counter(self, name: str, **kwargs):
        c = self._meter.create_up_down_counter(name, unit=kwargs.get("unit"), description=kwargs.get("description"))

        class _C:
            def add(self, value: float, attributes: Dict = None) -> None:
                c.add(value, attributes=attributes or {})

        return _C()

    def histogram(self, name: str, **kwargs):
        h = self._meter.create_histogram(name, unit=kwargs.get("unit"), description=kwargs.get("description"))

        class _H:
            def record(self, value: float, attributes: Dict = None) -> None:
                h.record(value, attributes=attributes or {})

        return _H()


class OTelLoggerImpl(OTelLogger):
    """
    Full OTel logs export is environment-dependent; as a pragmatic baseline we emit Python logs
    enriched with trace context (if enabled).
    """

    def __init__(self, config: ObservabilityConfig):
        self._config = config
        _ensure_sdk(config)
        import logging

        self._logger = logging.getLogger("infra.observability")
        lvl = (config.logging or LoggingConfig()).level
        self._logger.setLevel(getattr(logging, str(lvl).upper(), logging.INFO))

    def log(self, record: LogRecord) -> None:
        import logging

        msg = record.message
        attrs = record.attributes or {}
        if (self._config.logging or LoggingConfig()).include_trace_context:
            try:
                from opentelemetry import trace

                span = trace.get_current_span()
                ctx = span.get_span_context()
                attrs = dict(attrs)
                attrs["trace_id"] = format(ctx.trace_id, "032x") if ctx else ""
                attrs["span_id"] = format(ctx.span_id, "016x") if ctx else ""
            except Exception:
                pass

        sev = str(record.severity).upper()
        level = getattr(logging, sev, logging.INFO)
        self._logger.log(level, msg, extra={"attributes": attrs})

