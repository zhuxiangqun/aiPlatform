from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict
import time


class MetricSource(Enum):
    AGENT = "agent"
    LOOP = "loop"
    TOOL = "tool"
    SKILL = "skill"
    ADAPTER = "adapter"
    COORDINATOR = "coordinator"
    SYSTEM = "system"


class MetricCategory(Enum):
    PERFORMANCE = "performance"
    QUALITY = "quality"
    RELIABILITY = "reliability"
    RESOURCE = "resource"


@dataclass
class MetricData:
    name: str
    value: float
    source: MetricSource
    category: MetricCategory
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregatedMetric:
    name: str
    count: int
    sum: float
    min: float
    max: float
    avg: float
    p50: float
    p95: float
    p99: float


class MetricsAggregator:
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self._metrics: Dict[str, List[MetricData]] = defaultdict(list)

    def add(self, metric: MetricData):
        key = f"{metric.source.value}:{metric.name}"
        self._metrics[key].append(metric)
        if len(self._metrics[key]) > self.window_size:
            self._metrics[key] = self._metrics[key][-self.window_size:]

    def get_aggregated(self, name: str, source: MetricSource) -> Optional[AggregatedMetric]:
        key = f"{source.value}:{name}"
        metrics = self._metrics.get(key, [])
        if not metrics:
            return None
        values = [m.value for m in metrics]
        values.sort()
        n = len(values)
        return AggregatedMetric(
            name=name,
            count=n,
            sum=sum(values),
            min=min(values),
            max=max(values),
            avg=sum(values) / n,
            p50=values[int(n * 0.5)],
            p95=values[int(n * 0.95)],
            p99=values[int(n * 0.99)],
        )

    def get_recent(self, name: str, source: MetricSource, limit: int = 100) -> List[MetricData]:
        key = f"{source.value}:{name}"
        return self._metrics.get(key, [])[-limit:]


class MetricsCollector:
    _instance: Optional["MetricsCollector"] = None

    def __init__(self):
        self.aggregator = MetricsAggregator()
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._timers: Dict[str, List[float]] = defaultdict(list)

    @classmethod
    def get_instance(cls) -> "MetricsCollector":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def record(
        self,
        name: str,
        value: float,
        source: MetricSource,
        category: MetricCategory,
        labels: Optional[Dict[str, str]] = None,
        **metadata,
    ):
        metric = MetricData(
            name=name,
            value=value,
            source=source,
            category=category,
            labels=labels or {},
            metadata=metadata,
        )
        self.aggregator.add(metric)

    def increment(self, name: str, source: MetricSource, delta: float = 1.0, **labels):
        key = f"{source.value}:{name}"
        self._counters[key] += delta
        self.record(name, self._counters[key], source, MetricCategory.PERFORMANCE, labels)

    def gauge(self, name: str, source: MetricSource, value: float, **labels):
        key = f"{source.value}:{name}"
        self._gauges[key] = value
        self.record(name, value, source, MetricCategory.RESOURCE, labels)

    def timer(self, name: str, source: MetricSource, duration_ms: float, **labels):
        key = f"{source.value}:{name}"
        self._timers[key].append(duration_ms)
        if len(self._timers[key]) > 100:
            self._timers[key] = self._timers[key][-100:]
        self.record(name, duration_ms, source, MetricCategory.PERFORMANCE, labels)

    def timing_context(self, name: str, source: MetricSource):
        return TimerContext(self, name, source)

    def get_counter(self, name: str, source: MetricSource) -> float:
        key = f"{source.value}:{name}"
        return self._counters.get(key, 0.0)

    def get_gauge(self, name: str, source: MetricSource) -> Optional[float]:
        key = f"{source.value}:{name}"
        return self._gauges.get(key)

    def get_aggregated(self, name: str, source: MetricSource) -> Optional[AggregatedMetric]:
        return self.aggregator.get_aggregated(name, source)

    def get_all_counters(self) -> Dict[str, float]:
        return dict(self._counters)

    def get_all_gauges(self) -> Dict[str, float]:
        return dict(self._gauges)

    def get_metrics_by_source(self, source: MetricSource) -> Dict[str, AggregatedMetric]:
        result = {}
        for key in self._counters:
            if key.startswith(source.value + ":"):
                name = key.split(":", 1)[1]
                agg = self.aggregator.get_aggregated(name, source)
                if agg:
                    result[name] = agg
        return result

    def reset(self):
        self._counters.clear()
        self._gauges.clear()
        self._timers.clear()
        self.aggregator = MetricsAggregator()


class TimerContext:
    def __init__(self, collector: MetricsCollector, name: str, source: MetricSource):
        self.collector = collector
        self.name = name
        self.source = source
        self.start_time = time.time()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        self.collector.timer(self.name, self.source, duration_ms)


def create_metrics_collector() -> MetricsCollector:
    return MetricsCollector()


metrics_collector = MetricsCollector.get_instance()