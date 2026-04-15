"""
System Reminders

Event-driven reminders to prevent instruction decay.
"""

from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class ReminderType(Enum):
    """Types of system reminders"""
    UNFINISHED_TODO = "unfinished_todo"
    EXPLORATION_SPIRAL = "exploration_spiral"
    TOOL_FAILURE = "tool_failure"
    CONTEXT_OVERLOAD = "context_overload"
    LONG_TASK = "long_task"


@dataclass
class ReminderRule:
    """A reminder rule configuration"""
    rule_id: str
    trigger_type: ReminderType
    condition: Callable[[Dict], bool]
    message_template: str
    priority: int = 0
    enabled: bool = True


class SystemReminders:
    """System reminders to prevent instruction decay"""
    
    def __init__(self):
        self._rules = []
        self._execution_state: Dict[str, Any] = {}
        self._register_default_rules()
    
    def _register_default_rules(self):
        """Register built-in reminder rules"""
        
        # Rule 1: Unfinished todos when calling task_complete
        self.add_rule(ReminderRule(
            rule_id="unfinished_todo",
            trigger_type=ReminderType.UNFINISHED_TODO,
            condition=self._check_unfinished_todos,
            message_template="提醒: 还有 {count} 个任务未完成: {items}",
            priority=1
        ))
        
        # Rule 2: Exploration spiral detection
        self.add_rule(ReminderRule(
            rule_id="exploration_spiral",
            trigger_type=ReminderType.EXPLORATION_SPIRAL,
            condition=self._check_exploration_spiral,
            message_template="注意: 已连续探索 {count} 个文件，该开始行动了",
            priority=2
        ))
        
        # Rule 3: Tool failure
        self.add_rule(ReminderRule(
            rule_id="tool_failure",
            trigger_type=ReminderType.TOOL_FAILURE,
            condition=self._check_tool_failure,
            message_template="工具调用失败: {error}。请检查参数或尝试其他工具。",
            priority=1
        ))
        
        # Rule 4: Context overload
        self.add_rule(ReminderRule(
            rule_id="context_overload",
            trigger_type=ReminderType.CONTEXT_OVERLOAD,
            condition=self._check_context_overload,
            message_template="警告: 上下文即将耗尽({usage:.0%})，建议总结当前进度。",
            priority=3
        ))
    
    def add_rule(self, rule: ReminderRule):
        """Add a reminder rule"""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)
    
    async def check_and_inject(
        self,
        state: Dict[str, Any]
    ) -> Optional[str]:
        """Check rules and return reminder message if triggered"""
        for rule in self._rules:
            if not rule.enabled:
                continue
            
            try:
                if rule.condition(state):
                    message = self._format_message(rule.message_template, state)
                    return message
            except Exception:
                continue
        
        return None
    
    def update_state(self, key: str, value: Any):
        """Update execution state for condition checking"""
        self._execution_state[key] = value
    
    def _check_unfinished_todos(self, state: Dict) -> bool:
        """Check for unfinished todos"""
        return (
            state.get("calling_tool") == "task_complete" and
            state.get("pending_todos", 0) > 0
        )
    
    def _check_exploration_spiral(self, state: Dict) -> bool:
        """Check for exploration spiral (too many reads without actions)"""
        consecutive_reads = state.get("consecutive_reads", 0)
        return consecutive_reads >= 5
    
    def _check_tool_failure(self, state: Dict) -> bool:
        """Check for tool failure"""
        return state.get("tool_failed", False)
    
    def _check_context_overload(self, state: Dict) -> bool:
        """Check for context overload"""
        usage = state.get("token_usage_ratio", 0)
        return usage >= 0.90
    
    def _format_message(self, template: str, state: Dict) -> str:
        """Format message template with state values"""
        try:
            return template.format(
                count=state.get("count", 0),
                items=state.get("items", ""),
                error=state.get("error", "unknown"),
                usage=state.get("token_usage_ratio", 0)
            )
        except (KeyError, ValueError):
            return template
    
    def enable_rule(self, rule_id: str):
        """Enable a rule"""
        for rule in self._rules:
            if rule.rule_id == rule_id:
                rule.enabled = True
    
    def disable_rule(self, rule_id: str):
        """Disable a rule"""
        for rule in self._rules:
            if rule.rule_id == rule_id:
                rule.enabled = False


# Global instance
_reminders: Optional[SystemReminders] = None


def get_system_reminders() -> SystemReminders:
    """Get global system reminders"""
    global _reminders
    if _reminders is None:
        _reminders = SystemReminders()
    return _reminders


__all__ = ["SystemReminders", "ReminderRule", "ReminderType", "get_system_reminders"]