"""local：模块接口。"""

from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import logging


class FeedbackLevel(Enum):
    """FeedbackLevel。"""
    TRACE = "trace"
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class FeedbackType(Enum):
    """FeedbackType。"""
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
    """FeedbackData。"""
    level: FeedbackLevel
    feedback_type: FeedbackType
    source: str
    content: Any
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)


FeedbackHandler = Callable[[FeedbackData], None]


class LocalFeedbackLoop:
    """LocalFeedbackLoop。"""
    def __init__(self, max_history: int = 100):
        """初始化。

        Args:
            max_history: max_history 参数。
        """
        self.max_history = max_history
        self._handlers: List[FeedbackHandler] = []
        self._history: List[FeedbackData] = []
        self._enabled = True

    def enable(self):
        """enable。
        """
        self._enabled = True

    def disable(self):
        """disable。
        """
        self._enabled = False

    def register_handler(self, handler: FeedbackHandler):
        """register_handler。

        Args:
            handler: handler 参数。
        """
        self._handlers.append(handler)

    def unregister_handler(self, handler: FeedbackHandler):
        """unregister_handler。

        Args:
            handler: handler 参数。
        """
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
        """emit。

        Args:
            level: level 参数。
            feedback_type: feedback_type 参数。
            source: source 参数。
            content: content 参数。
            metadata: metadata 参数。
            context: context 参数。
        """
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
            except Exception as e:
                logging.debug(str(e), exc_info=True)

    def success(self, source: str, content: Any, **context):
        """success。

        Args:
            source: source 参数。
            content: content 参数。
            context: context 参数。
        """
        self.emit(FeedbackLevel.INFO, FeedbackType.RESULT, source, content, **context)

    def error(self, source: str, content: Any, **context):
        """error。

        Args:
            source: source 参数。
            content: content 参数。
            context: context 参数。
        """
        self.emit(FeedbackLevel.ERROR, FeedbackType.ERROR, source, content, **context)

    def warning(self, source: str, content: Any, **context):
        """warning。

        Args:
            source: source 参数。
            content: content 参数。
            context: context 参数。
        """
        self.emit(FeedbackLevel.WARNING, FeedbackType.RESULT, source, content, **context)

    def debug(self, source: str, content: Any, **context):
        """debug。

        Args:
            source: source 参数。
            content: content 参数。
            context: context 参数。
        """
        self.emit(FeedbackLevel.DEBUG, FeedbackType.RESULT, source, content, **context)

    def get_history(
        self,
        level: Optional[FeedbackLevel] = None,
        feedback_type: Optional[FeedbackType] = None,
        source: Optional[str] = None,
        limit: int = 50,
    ) -> List[FeedbackData]:
        """获取 history。

        Args:
            level: level 参数。
            feedback_type: feedback_type 参数。
            source: source 参数。
            limit: 返回条数上限。
        """
        result = self._history
        if level:
            result = [f for f in result if f.level == level]
        if feedback_type:
            result = [f for f in result if f.feedback_type == feedback_type]
        if source:
            result = [f for f in result if f.source == source]
        return result[-limit:]

    def clear(self):
        """clear。
        """
        self._history.clear()

    def count(self) -> int:
        """count。
        """
        return len(self._history)


class FeedbackAggregator:
    """FeedbackAggregator。"""
    def __init__(self):
        """初始化。
        """
        self._by_type: Dict[FeedbackType, int] = {t: 0 for t in FeedbackType}
        self._by_level: Dict[FeedbackLevel, int] = {l: 0 for l in FeedbackLevel}
        self._by_source: Dict[str, int] = {}

    def record(self, feedback: FeedbackData):
        """record。

        Args:
            feedback: feedback 参数。
        """
        self._by_type[feedback.feedback_type] += 1
        self._by_level[feedback.level] += 1
        self._by_source[feedback.source] = self._by_source.get(feedback.source, 0) + 1

    def get_stats(self) -> Dict[str, Any]:
        """获取 stats。
        """
        return {
            "by_type": {t.value: c for t, c in self._by_type.items()},
            "by_level": {l.value: c for l, c in self._by_level.items()},
            "by_source": dict(self._by_source),
            "total": sum(self._by_type.values()),
        }


_local_feedback = LocalFeedbackLoop()


def get_local_feedback() -> LocalFeedbackLoop:
    """获取 local_feedback。
    """
    return _local_feedback


def create_local_feedback(max_history: int = 100) -> LocalFeedbackLoop:
    """创建 local_feedback。

    Args:
        max_history: max_history 参数。
    """
    return LocalFeedbackLoop(max_history)