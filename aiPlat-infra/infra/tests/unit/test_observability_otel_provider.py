from infra.observability import ObservabilityConfig, TracingConfig, MetricsConfig, LoggingConfig
from infra.observability.factory import create_tracer
from infra.observability.otel import get_in_memory_span_exporter


def test_otel_tracer_in_memory_exporter_collects_span():
    cfg = ObservabilityConfig(
        enabled=True,
        provider="otel",
        tracing=TracingConfig(enabled=True, exporter="in_memory", endpoint="http://localhost:4317"),
        metrics=MetricsConfig(enabled=False),
        logging=LoggingConfig(enabled=False),
    )

    tracer = create_tracer(cfg)
    with tracer.start_span("unit_test_span") as span:
        span.set_attribute("k", "v")
        span.add_event("evt", {"a": 1})
        span.set_status("ok", "done")

    exporter = get_in_memory_span_exporter()
    assert exporter is not None
    spans = exporter.get_finished_spans()
    assert any(s.name == "unit_test_span" for s in spans)

