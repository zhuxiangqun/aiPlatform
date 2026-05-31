"""
OpenTelemetry bridge — exports syscall events as OTEL spans.
Best-effort: silently degrades if opentelemetry not installed.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

_log = logging.getLogger("aiplat.otel_bridge")

_OTEL_AVAILABLE = False
_tracer: Optional[Any] = None


def _init_otel() -> None:
    """Lazy-init OpenTelemetry if available. No-op if not installed."""
    global _OTEL_AVAILABLE, _tracer
    if _OTEL_AVAILABLE:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource

        provider = TracerProvider(
            resource=Resource.create({SERVICE_NAME: "aiPlat-core"})
        )
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("aiplat.syscall")
        _OTEL_AVAILABLE = True
    except ImportError:
        _log.debug("opentelemetry not installed, OTEL export disabled")
    except Exception:
        _log.debug("OpenTelemetry init failed", exc_info=True)


def export_syscall_as_span(event: Dict[str, Any]) -> None:
    """Export a syscall event as an OpenTelemetry span. Best-effort."""
    _init_otel()
    if not _OTEL_AVAILABLE or _tracer is None:
        return

    try:
        from opentelemetry.trace import Status, StatusCode

        name = f"{event.get('kind', 'unknown')}.{event.get('name', 'unknown')}"
        start = event.get("start_time")
        end = event.get("end_time")
        status = event.get("status", "unknown")

        with _tracer.start_as_current_span(
            name,
            start_time=_to_ns(start),
            attributes={
                "syscall.kind": event.get("kind", ""),
                "syscall.name": event.get("name", ""),
                "syscall.status": status,
                "syscall.run_id": event.get("run_id", ""),
                "syscall.trace_id": event.get("trace_id", ""),
                "syscall.target_type": event.get("target_type", ""),
                "syscall.duration_ms": event.get("duration_ms", 0),
            },
        ) as span:
            if status == "error":
                span.set_status(Status(StatusCode.ERROR))
            elif status == "ok":
                span.set_status(Status(StatusCode.OK))
            if end:
                span.end(end_time=_to_ns(end))
    except Exception:
        _log.debug("OTEL span export failed", exc_info=True)


def _to_ns(ts: Optional[float]) -> Optional[int]:
    if ts is None:
        return None
    return int(ts * 1e9)
