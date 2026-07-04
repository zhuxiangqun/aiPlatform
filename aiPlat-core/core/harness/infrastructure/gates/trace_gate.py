"""
TraceGate (Phase 3 - minimal).

This gate provides a best-effort tracing span wrapper using the existing
TraceService integration.

In later phases, TraceGate will:
- enforce run_id/trace_id propagation through PromptContext/ExecutionResult
- persist syscall-level audit records to ExecutionStore
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.harness.kernel.runtime import get_kernel_runtime


@dataclass
class TraceSpan:
    """A minimal span handle for best-effort end()."""

    trace_id: Optional[str]
    span_id: Optional[str]
    name: str


class TraceGate:
    def __init__(self) -> None:
        # ── Span completeness metrics ──
        self._spans_started: int = 0
        self._spans_ended: int = 0
        self._spans_success: int = 0
        self._spans_failed: int = 0
        self._open_spans: Dict[str, TraceSpan] = {}

    async def start(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> TraceSpan:
        runtime = get_kernel_runtime()
        trace_service = getattr(runtime, "trace_service", None) if runtime else None
        if not trace_service:
            return TraceSpan(trace_id=None, span_id=None, name=name)
        try:
            attrs = dict(attributes or {})
            # Allow passing a trace_id explicitly (preferred), otherwise use current active trace context.
            trace_id = attrs.pop("trace_id", None)
            if not trace_id:
                ctx = getattr(trace_service, "_context", None)
                trace_id = getattr(ctx, "trace_id", None) if ctx else None
            if not trace_id:
                # Fallback: start a new trace (best-effort)
                trace = await trace_service.start_trace(name="kernel", attributes={"source": "syscall"})
                trace_id = getattr(trace, "trace_id", None)
            span = await trace_service.start_span(trace_id=trace_id, name=name, attributes=attrs)
            result = TraceSpan(trace_id=trace_id, span_id=getattr(span, "span_id", None), name=name)
            self._spans_started += 1
            if result.span_id:
                self._open_spans[result.span_id] = result
            return result
        except Exception:
            return TraceSpan(trace_id=None, span_id=None, name=name)

    async def end(self, span: TraceSpan, success: bool = True) -> None:
        runtime = get_kernel_runtime()
        trace_service = getattr(runtime, "trace_service", None) if runtime else None
        if not trace_service or not span.span_id:
            return
        try:
            from core.services.trace_service import SpanStatus

        except Exception:
            return

    def get_stats(self) -> dict:
        return {
            "spans_started": self._spans_started,
            "spans_ended": self._spans_ended,
            "spans_success": self._spans_success,
            "spans_failed": self._spans_failed,
            "open_spans": len(self._open_spans),
            "orphan_spans": max(0, self._spans_started - self._spans_ended),
            "completeness_pct": round(
                self._spans_ended / max(self._spans_started, 1) * 100, 1
            ),
        }
