"""
Layer 1 (core) 指标采集器
"""

from typing import List
from .collector import MetricsCollector, Metric


class CoreMetricsCollector(MetricsCollector):
    """Layer 1 (core) 指标采集器"""
    
    def __init__(self, endpoint: str = None):
        super().__init__("core", endpoint)
        
    async def collect(self) -> List[Metric]:
        """采集 core 层指标"""
        return [
            # Agent 指标
            Metric(
                name="agents_active_count",
                value=10,
                labels={"type": "all"},
                unit="agents"
            ),
            Metric(
                name="agents_tasks_completed_total",
                value=500,
                labels={"type": "all"},
                unit="tasks"
            ),
            Metric(
                name="agents_tasks_failed_total",
                value=5,
                labels={"type": "all"},
                unit="tasks"
            ),
            
            # Skill 指标
            Metric(
                name="skills_registered_count",
                value=50,
                labels={"type": "all"},
                unit="skills"
            ),
            Metric(
                name="skills_executions_total",
                value=1000,
                labels={"type": "all"},
                unit="executions"
            ),
            Metric(
                name="skills_average_execution_time_seconds",
                value=2.5,
                labels={"type": "all"},
                unit="seconds"
            ),
            
            # Memory 指标
            Metric(
                name="memory_sessions_active_count",
                value=100,
                labels={"type": "all"},
                unit="sessions"
            ),
            Metric(
                name="memory_context_average_size_bytes",
                value=1000,
                labels={"type": "all"},
                unit="bytes"
            ),
            
            # Format Affinity 指标 (新增)
            Metric(
                name="format_affinity_match_rate",
                value=0.85,
                labels={"type": "all"},
                unit="ratio"
            ),
            Metric(
                name="format_affinity_structural_score",
                value=0.82,
                labels={"type": "all"},
                unit="score"
            ),
            Metric(
                name="format_affinity_style_score",
                value=0.78,
                labels={"type": "all"},
                unit="score"
            ),
            
            # Value Decay 指标 (新增)
            Metric(
                name="value_decay_format_affinity",
                value=0.05,
                labels={"type": "format"},
                unit="per_day"
            ),
            Metric(
                name="value_decay_capability_complement",
                value=0.02,
                labels={"type": "capability"},
                unit="per_day"
            ),
            Metric(
                name="value_decay_feedback_quality",
                value=0.005,
                labels={"type": "feedback"},
                unit="per_day"
            )
        ]
