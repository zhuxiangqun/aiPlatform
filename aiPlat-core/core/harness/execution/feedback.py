"""
Execution Feedback Module

Provides feedback mechanisms for execution loops.
"""

from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio


class FeedbackType(Enum):
    """Feedback types"""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    RETRY = "retry"
    TIMEOUT = "timeout"
    QUALITY = "quality"
    PERFORMANCE = "performance"


class FeedbackSeverity(Enum):
    """Feedback severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class FeedbackEntry:
    """Feedback entry"""
    type: FeedbackType
    severity: FeedbackSeverity
    source: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "source": self.source,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
            "suggestions": self.suggestions,
            "metadata": self.metadata,
        }


@dataclass
class FeedbackSummary:
    """Summary of feedback entries"""
    total: int
    by_type: Dict[str, int]
    by_severity: Dict[str, int]
    by_source: Dict[str, int]
    success_rate: float
    error_rate: float
    warning_rate: float


class FeedbackCollector:
    """Collects and manages feedback entries"""
    
    def __init__(self, max_entries: int = 1000):
        self._max_entries = max_entries
        self._entries: List[FeedbackEntry] = []
        self._handlers: List[Callable[[FeedbackEntry], None]] = []
    
    def register_handler(self, handler: Callable[[FeedbackEntry], None]):
        self._handlers.append(handler)
    
    def add(
        self,
        type: FeedbackType,
        severity: FeedbackSeverity,
        source: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        suggestions: Optional[List[str]] = None,
        **metadata,
    ) -> FeedbackEntry:
        entry = FeedbackEntry(
            type=type,
            severity=severity,
            source=source,
            message=message,
            context=context or {},
            suggestions=suggestions or [],
            metadata=metadata,
        )
        
        self._entries.append(entry)
        
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]
        
        for handler in self._handlers:
            try:
                handler(entry)
            except Exception:
                pass
        
        return entry
    
    def success(
        self,
        source: str,
        message: str = "Operation completed successfully",
        **metadata,
    ) -> FeedbackEntry:
        return self.add(
            FeedbackType.SUCCESS,
            FeedbackSeverity.LOW,
            source,
            message,
            metadata=metadata,
        )
    
    def error(
        self,
        source: str,
        message: str,
        suggestions: Optional[List[str]] = None,
        **metadata,
    ) -> FeedbackEntry:
        return self.add(
            FeedbackType.ERROR,
            FeedbackSeverity.HIGH,
            source,
            message,
            suggestions=suggestions,
            metadata=metadata,
        )
    
    def warning(
        self,
        source: str,
        message: str,
        suggestions: Optional[List[str]] = None,
        **metadata,
    ) -> FeedbackEntry:
        return self.add(
            FeedbackType.WARNING,
            FeedbackSeverity.MEDIUM,
            source,
            message,
            suggestions=suggestions,
            metadata=metadata,
        )
    
    def retry(
        self,
        source: str,
        message: str,
        attempt: int,
        max_attempts: int,
        **metadata,
    ) -> FeedbackEntry:
        return self.add(
            FeedbackType.RETRY,
            FeedbackSeverity.MEDIUM,
            source,
            message,
            metadata={"attempt": attempt, "max_attempts": max_attempts, **metadata},
        )
    
    def timeout(
        self,
        source: str,
        message: str,
        duration_ms: float,
        **metadata,
    ) -> FeedbackEntry:
        return self.add(
            FeedbackType.TIMEOUT,
            FeedbackSeverity.HIGH,
            source,
            message,
            metadata={"duration_ms": duration_ms, **metadata},
        )
    
    def quality(
        self,
        source: str,
        message: str,
        score: float,
        threshold: float,
        **metadata,
    ) -> FeedbackEntry:
        severity = FeedbackSeverity.LOW if score >= threshold else FeedbackSeverity.MEDIUM
        return self.add(
            FeedbackType.QUALITY,
            severity,
            source,
            message,
            metadata={"score": score, "threshold": threshold, **metadata},
        )
    
    def performance(
        self,
        source: str,
        message: str,
        duration_ms: float,
        threshold_ms: float,
        **metadata,
    ) -> FeedbackEntry:
        severity = FeedbackSeverity.LOW if duration_ms <= threshold_ms else FeedbackSeverity.MEDIUM
        return self.add(
            FeedbackType.PERFORMANCE,
            severity,
            source,
            message,
            metadata={"duration_ms": duration_ms, "threshold_ms": threshold_ms, **metadata},
        )
    
    def get_entries(
        self,
        type: Optional[FeedbackType] = None,
        severity: Optional[FeedbackSeverity] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[FeedbackEntry]:
        entries = self._entries
        
        if type:
            entries = [e for e in entries if e.type == type]
        if severity:
            entries = [e for e in entries if e.severity == severity]
        if source:
            entries = [e for e in entries if e.source == source]
        
        return entries[-limit:]
    
    def get_summary(self) -> FeedbackSummary:
        total = len(self._entries)
        if total == 0:
            return FeedbackSummary(
                total=0,
                by_type={},
                by_severity={},
                by_source={},
                success_rate=0.0,
                error_rate=0.0,
                warning_rate=0.0,
            )
        
        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        by_source: Dict[str, int] = {}
        
        for entry in self._entries:
            by_type[entry.type.value] = by_type.get(entry.type.value, 0) + 1
            by_severity[entry.severity.value] = by_severity.get(entry.severity.value, 0) + 1
            by_source[entry.source] = by_source.get(entry.source, 0) + 1
        
        success_count = by_type.get(FeedbackType.SUCCESS.value, 0)
        error_count = by_type.get(FeedbackType.ERROR.value, 0)
        warning_count = by_type.get(FeedbackType.WARNING.value, 0)
        
        return FeedbackSummary(
            total=total,
            by_type=by_type,
            by_severity=by_severity,
            by_source=by_source,
            success_rate=success_count / total,
            error_rate=error_count / total,
            warning_rate=warning_count / total,
        )
    
    def clear(self):
        self._entries.clear()


class ExecutionFeedback:
    """High-level execution feedback manager"""
    
    _instance: Optional["ExecutionFeedback"] = None
    
    def __init__(self, max_entries: int = 1000):
        self._collector = FeedbackCollector(max_entries)
        self._enabled = True
    
    @classmethod
    def get_instance(cls) -> "ExecutionFeedback":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def enable(self):
        self._enabled = True
    
    def disable(self):
        self._enabled = False
    
    @property
    def collector(self) -> FeedbackCollector:
        return self._collector
    
    def on_step_start(self, step_name: str, context: Optional[Dict[str, Any]] = None):
        if not self._enabled:
            return
        self._collector.add(
            FeedbackType.SUCCESS,
            FeedbackSeverity.LOW,
            f"step:{step_name}",
            f"Step {step_name} started",
            context=context,
        )
    
    def on_step_end(self, step_name: str, result: Any):
        if not self._enabled:
            return
        self._collector.success(
            f"step:{step_name}",
            f"Step {step_name} completed",
            result_type=type(result).__name__,
        )
    
    def on_step_error(
        self,
        step_name: str,
        error: Exception,
        suggestions: Optional[List[str]] = None,
    ):
        if not self._enabled:
            return
        self._collector.error(
            f"step:{step_name}",
            f"Step {step_name} failed: {str(error)}",
            suggestions=suggestions,
            error_type=type(error).__name__,
        )
    
    def on_loop_start(self, loop_name: str, max_iterations: int):
        if not self._enabled:
            return
        self._collector.add(
            FeedbackType.SUCCESS,
            FeedbackSeverity.LOW,
            f"loop:{loop_name}",
            f"Loop {loop_name} started",
            metadata={"max_iterations": max_iterations},
        )
    
    def on_loop_iteration(self, loop_name: str, iteration: int):
        if not self._enabled:
            return
        self._collector.add(
            FeedbackType.SUCCESS,
            FeedbackSeverity.LOW,
            f"loop:{loop_name}",
            f"Loop {loop_name} iteration {iteration}",
            metadata={"iteration": iteration},
        )
    
    def on_loop_end(self, loop_name: str, iterations: int, success: bool):
        if not self._enabled:
            return
        severity = FeedbackSeverity.LOW if success else FeedbackSeverity.MEDIUM
        self._collector.add(
            FeedbackType.SUCCESS if success else FeedbackType.WARNING,
            severity,
            f"loop:{loop_name}",
            f"Loop {loop_name} ended after {iterations} iterations",
            metadata={"iterations": iterations, "success": success},
        )
    
    def on_tool_call(self, tool_name: str, args: Dict[str, Any]):
        if not self._enabled:
            return
        self._collector.add(
            FeedbackType.SUCCESS,
            FeedbackSeverity.LOW,
            f"tool:{tool_name}",
            f"Tool {tool_name} called",
            context=args,
        )
    
    def on_tool_result(self, tool_name: str, result: Any, duration_ms: float):
        if not self._enabled:
            return
        self._collector.performance(
            f"tool:{tool_name}",
            f"Tool {tool_name} returned",
            duration_ms=duration_ms,
            threshold_ms=1000,
            result_type=type(result).__name__,
        )
    
    def on_tool_error(self, tool_name: str, error: Exception):
        if not self._enabled:
            return
        self._collector.error(
            f"tool:{tool_name}",
            f"Tool {tool_name} failed: {str(error)}",
            error_type=type(error).__name__,
        )
    
    def get_summary(self) -> FeedbackSummary:
        return self._collector.get_summary()
    
    def get_entries(self, **kwargs) -> List[FeedbackEntry]:
        return self._collector.get_entries(**kwargs)
    
    def clear(self):
        self._collector.clear()


def create_feedback(max_entries: int = 1000) -> ExecutionFeedback:
    return ExecutionFeedback(max_entries)


execution_feedback = ExecutionFeedback.get_instance()


__all__ = [
    "FeedbackType",
    "FeedbackSeverity",
    "FeedbackEntry",
    "FeedbackSummary",
    "FeedbackCollector",
    "ExecutionFeedback",
    "create_feedback",
    "execution_feedback",
]