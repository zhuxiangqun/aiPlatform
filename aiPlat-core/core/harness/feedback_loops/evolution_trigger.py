from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio


class EvolutionTriggerType(Enum):
    ERROR_THRESHOLD = "error_threshold"
    LATENCY_THRESHOLD = "latency_threshold"
    QUALITY_SCORE = "quality_score"
    RETRY_COUNT = "retry_count"
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class EvolutionAction(Enum):
    RESTART = "restart"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    FALLBACK = "fallback"
    ADAPT_PROMPT = "adapt_prompt"
    SWITCH_MODEL = "switch_model"
    NOTIFY = "notify"


@dataclass
class EvolutionTrigger:
    trigger_type: EvolutionTriggerType
    condition: str
    threshold: float
    action: EvolutionAction
    enabled: bool = True
    cooldown_seconds: int = 60
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvolutionEvent:
    id: str
    trigger: EvolutionTrigger
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    action_taken: Optional[EvolutionAction] = None
    success: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


EvolutionHandler = Callable[[EvolutionEvent], asyncio.Future[None]]


class EvolutionTriggerManager:
    def __init__(self):
        self._triggers: Dict[str, EvolutionTrigger] = {}
        self._handlers: List[EvolutionHandler] = []
        self._event_history: List[EvolutionEvent] = []
        self._last_trigger_time: Dict[str, datetime] = {}
        self._enabled = True

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def register_trigger(
        self,
        name: str,
        trigger_type: EvolutionTriggerType,
        condition: str,
        threshold: float,
        action: EvolutionAction,
        cooldown_seconds: int = 60,
        enabled: bool = True,
        **metadata,
    ) -> EvolutionTrigger:
        trigger = EvolutionTrigger(
            trigger_type=trigger_type,
            condition=condition,
            threshold=threshold,
            action=action,
            cooldown_seconds=cooldown_seconds,
            enabled=enabled,
            metadata=metadata,
        )
        self._triggers[name] = trigger
        return trigger

    def add_trigger(
        self,
        name: str,
        trigger_type: EvolutionTriggerType,
        threshold: float,
        action: EvolutionAction,
        **kwargs,
    ) -> EvolutionTrigger:
        return self.register_trigger(
            name, trigger_type, "", threshold, action, **kwargs
        )

    def remove_trigger(self, name: str) -> bool:
        if name in self._triggers:
            del self._triggers[name]
            return True
        return False

    def register_handler(self, handler: EvolutionHandler):
        self._handlers.append(handler)

    async def evaluate_and_trigger(
        self,
        trigger_name: str,
        context: Dict[str, Any],
    ) -> Optional[EvolutionEvent]:
        if not self._enabled:
            return None

        trigger = self._triggers.get(trigger_name)
        if not trigger or not trigger.enabled:
            return None

        now = datetime.now()
        last_time = self._last_trigger_time.get(trigger_name)
        if last_time and (now - last_time).total_seconds() < trigger.cooldown_seconds:
            return None

        should_trigger = self._evaluate_condition(trigger, context)
        if not should_trigger:
            return None

        self._last_trigger_time[trigger_name] = now

        event = EvolutionEvent(
            id=f"evo_{trigger_name}_{now.timestamp()}",
            trigger=trigger,
            context=context,
            action_taken=trigger.action,
        )

        event.success = await self._execute_action(trigger.action, context)
        self._event_history.append(event)

        for handler in self._handlers:
            try:
                await handler(event)
            except Exception:
                pass

        return event

    def _evaluate_condition(self, trigger: EvolutionTrigger, context: Dict[str, Any]) -> bool:
        value = context.get(trigger.condition)
        if value is None:
            return False

        if trigger.trigger_type == EvolutionTriggerType.ERROR_THRESHOLD:
            return value >= trigger.threshold
        elif trigger.trigger_type == EvolutionTriggerType.LATENCY_THRESHOLD:
            return value >= trigger.threshold
        elif trigger.trigger_type == EvolutionTriggerType.QUALITY_SCORE:
            return value <= trigger.threshold
        elif trigger.trigger_type == EvolutionTriggerType.RETRY_COUNT:
            return value >= trigger.threshold

        return False

    async def _execute_action(self, action: EvolutionAction, context: Dict[str, Any]) -> bool:
        return True

    def get_triggers(self) -> Dict[str, EvolutionTrigger]:
        return dict(self._triggers)

    def get_event_history(
        self,
        trigger_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[EvolutionEvent]:
        events = self._event_history
        if trigger_name:
            events = [e for e in events if e.trigger.trigger_type.value == trigger_name]
        return events[-limit:]

    def get_trigger_stats(self) -> Dict[str, Any]:
        total = len(self._event_history)
        success = sum(1 for e in self._event_history if e.success)
        by_action: Dict[str, int] = {}
        for event in self._event_history:
            action = event.action_taken.value if event.action_taken else "none"
            by_action[action] = by_action.get(action, 0) + 1

        return {
            "total_events": total,
            "successful": success,
            "failed": total - success,
            "by_action": by_action,
            "active_triggers": sum(1 for t in self._triggers.values() if t.enabled),
        }

    def clear_history(self):
        self._event_history.clear()


class EvolutionEngine:
    def __init__(self):
        self.manager = EvolutionTriggerManager()
        self._trigger_hooks: Dict[EvolutionAction, Callable] = {}

    def register_hook(self, action: EvolutionAction, hook: Callable):
        self._trigger_hooks[action] = hook

    async def on_error_threshold(
        self,
        error_rate: float,
        threshold: float = 0.1,
        **context,
    ):
        return await self.manager.evaluate_and_trigger(
            "error_threshold", {"error_rate": error_rate, **context}
        )

    async def on_latency_threshold(
        self,
        latency_ms: float,
        threshold: float = 5000,
        **context,
    ):
        return await self.manager.evaluate_and_trigger(
            "latency_threshold", {"latency_ms": latency_ms, **context}
        )

    async def on_quality_score(
        self,
        score: float,
        threshold: float = 0.5,
        **context,
    ):
        return await self.manager.evaluate_and_trigger(
            "quality_score", {"quality_score": score, **context}
        )

    async def on_retry_count(
        self,
        retry_count: int,
        threshold: int = 3,
        **context,
    ):
        return await self.manager.evaluate_and_trigger(
            "retry_count", {"retry_count": retry_count, **context}
        )

    def setup_default_triggers(self):
        self.manager.add_trigger(
            "high_error_rate",
            EvolutionTriggerType.ERROR_THRESHOLD,
            0.1,
            EvolutionAction.FALLBACK,
            cooldown_seconds=120,
        )
        self.manager.add_trigger(
            "high_latency",
            EvolutionTriggerType.LATENCY_THRESHOLD,
            5000,
            EvolutionAction.SCALE_UP,
            cooldown_seconds=60,
        )
        self.manager.add_trigger(
            "low_quality",
            EvolutionTriggerType.QUALITY_SCORE,
            0.5,
            EvolutionAction.ADAPT_PROMPT,
            cooldown_seconds=300,
        )
        self.manager.add_trigger(
            "high_retries",
            EvolutionTriggerType.RETRY_COUNT,
            3,
            EvolutionAction.SWITCH_MODEL,
            cooldown_seconds=180,
        )


def create_evolution_engine() -> EvolutionEngine:
    engine = EvolutionEngine()
    engine.setup_default_triggers()
    return engine


_evolution_engine = EvolutionEngine()


def get_evolution_engine() -> EvolutionEngine:
    return _evolution_engine