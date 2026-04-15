from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio


class FeedbackLevel(Enum):
    TRACE = "trace"
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class FeedbackType(Enum):
    RESULT = "result"
    ERROR = "error"
    TIMEOUT = "timeout"
    RETRY = "retry"
    FALLBACK = "fallback"
    TOOL_OUTPUT = "tool_output"
    LLM_RESPONSE = "llm_response"
    STATE_CHANGE = "state_change"


@dataclass
class FeedbackData:
    level: FeedbackLevel
    feedback_type: FeedbackType
    source: str
    content: Any
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)


FeedbackHandler = Callable[[FeedbackData], None]


class LocalFeedbackLoop:
    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self._handlers: List[FeedbackHandler] = []
        self._history: List[FeedbackData] = []
        self._enabled = True

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def register_handler(self, handler: FeedbackHandler):
        self._handlers.append(handler)

    def unregister_handler(self, handler: FeedbackHandler):
        if handler in self._handlers:
            self._handlers.remove(handler)

    def emit(
        self,
        level: FeedbackLevel,
        feedback_type: FeedbackType,
        source: str,
        content: Any,
        metadata: Optional[Dict[str, Any]] = None,
        **context,
    ):
        if not self._enabled:
            return

        feedback = FeedbackData(
            level=level,
            feedback_type=feedback_type,
            source=source,
            content=content,
            metadata=metadata or {},
            context=context,
        )

        self._history.append(feedback)
        if len(self._history) > self.max_history:
            self._history.pop(0)

        for handler in self._handlers:
            try:
                handler(feedback)
            except Exception:
                pass

    def success(self, source: str, content: Any, **context):
        self.emit(FeedbackLevel.INFO, FeedbackType.RESULT, source, content, **context)

    def error(self, source: str, content: Any, **context):
        self.emit(FeedbackLevel.ERROR, FeedbackType.ERROR, source, content, **context)

    def warning(self, source: str, content: Any, **context):
        self.emit(FeedbackLevel.WARNING, FeedbackType.RESULT, source, content, **context)

    def debug(self, source: str, content: Any, **context):
        self.emit(FeedbackLevel.DEBUG, FeedbackType.RESULT, source, content, **context)

    def get_history(
        self,
        level: Optional[FeedbackLevel] = None,
        feedback_type: Optional[FeedbackType] = None,
        source: Optional[str] = None,
        limit: int = 50,
    ) -> List[FeedbackData]:
        result = self._history
        if level:
            result = [f for f in result if f.level == level]
        if feedback_type:
            result = [f for f in result if f.feedback_type == feedback_type]
        if source:
            result = [f for f in result if f.source == source]
        return result[-limit:]

    def clear(self):
        self._history.clear()

    def count(self) -> int:
        return len(self._history)


class FeedbackAggregator:
    def __init__(self):
        self._by_type: Dict[FeedbackType, int] = {t: 0 for t in FeedbackType}
        self._by_level: Dict[FeedbackLevel, int] = {l: 0 for l in FeedbackLevel}
        self._by_source: Dict[str, int] = {}

    def record(self, feedback: FeedbackData):
        self._by_type[feedback.feedback_type] += 1
        self._by_level[feedback.level] += 1
        self._by_source[feedback.source] = self._by_source.get(feedback.source, 0) + 1

    def get_stats(self) -> Dict[str, Any]:
        return {
            "by_type": {t.value: c for t, c in self._by_type.items()},
            "by_level": {l.value: c for l, c in self._by_level.items()},
            "by_source": dict(self._by_source),
            "total": sum(self._by_type.values()),
        }


_local_feedback = LocalFeedbackLoop()


def get_local_feedback() -> LocalFeedbackLoop:
    return _local_feedback


def create_local_feedback(max_history: int = 100) -> LocalFeedbackLoop:
    return LocalFeedbackLoop(max_history)