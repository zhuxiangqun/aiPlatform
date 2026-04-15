from typing import Dict, Any, Optional, Callable, List, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import asyncio


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


@dataclass
class AlertRule:
    name: str
    condition: str
    severity: AlertSeverity
    enabled: bool = True
    cooldown_seconds: int = 60
    description: str = ""


@dataclass
class AlertInstance:
    id: str
    rule: AlertRule
    severity: AlertSeverity
    message: str
    source: str
    timestamp: datetime = field(default_factory=datetime.now)
    status: AlertStatus = AlertStatus.ACTIVE
    metadata: Dict[str, Any] = field(default_factory=dict)
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    fire_count: int = 0


AlertHandlerType = Callable[[AlertInstance], Awaitable[None]]


class AlertManager:
    _instance: Optional["AlertManager"] = None

    def __init__(self):
        self._rules: Dict[str, AlertRule] = {}
        self._active_alerts: Dict[str, AlertInstance] = {}
        self._handlers: List[AlertHandlerType] = []
        self._last_fire_time: Dict[str, datetime] = {}
        self._suppressed: Dict[str, bool] = {}

    @classmethod
    def get_instance(cls) -> "AlertManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_rule(self, rule: AlertRule):
        self._rules[rule.name] = rule

    def add_rule(
        self,
        name: str,
        condition: str,
        severity: AlertSeverity,
        cooldown_seconds: int = 60,
        description: str = "",
        enabled: bool = True,
    ) -> AlertRule:
        rule = AlertRule(
            name=name,
            condition=condition,
            severity=severity,
            cooldown_seconds=cooldown_seconds,
            description=description,
            enabled=enabled,
        )
        self.register_rule(rule)
        return rule

    def register_handler(self, handler: AlertHandlerType):
        self._handlers.append(handler)

    async def fire(
        self,
        rule_name: str,
        message: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AlertInstance]:
        rule = self._rules.get(rule_name)
        if not rule or not rule.enabled:
            return None

        if rule.name in self._suppressed and self._suppressed[rule.name]:
            return None

        now = datetime.now()
        last_fire = self._last_fire_time.get(rule.name)
        if last_fire and (now - last_fire).total_seconds() < rule.cooldown_seconds:
            return None

        self._last_fire_time[rule.name] = now

        alert = AlertInstance(
            id=f"alert_{rule_name}_{now.timestamp()}",
            rule=rule,
            severity=rule.severity,
            message=message,
            source=source,
            metadata=metadata or {},
        )
        alert.fire_count = 1

        self._active_alerts[alert.id] = alert

        for handler in self._handlers:
            try:
                await handler(alert)
            except Exception:
                pass

        return alert

    def get_active_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        source: Optional[str] = None,
    ) -> List[AlertInstance]:
        alerts = list(self._active_alerts.values())
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if source:
            alerts = [a for a in alerts if a.source == source]
        return [a for a in alerts if a.status == AlertStatus.ACTIVE]

    def acknowledge(self, alert_id: str) -> bool:
        alert = self._active_alerts.get(alert_id)
        if not alert:
            return False
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now()
        return True

    def resolve(self, alert_id: str) -> bool:
        alert = self._active_alerts.get(alert_id)
        if not alert:
            return False
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now()
        return True

    def suppress(self, rule_name: str, suppress: bool = True):
        self._suppressed[rule_name] = suppress

    def clear_resolved(self, older_than_seconds: int = 3600):
        cutoff = datetime.now() - timedelta(seconds=older_than_seconds)
        to_remove = []
        for alert in self._active_alerts.values():
            if alert.status == AlertStatus.RESOLVED and alert.resolved_at:
                if alert.resolved_at < cutoff:
                    to_remove.append(alert.id)
        for alert_id in to_remove:
            del self._active_alerts[alert_id]

    def get_alert_stats(self) -> Dict[str, Any]:
        by_severity = {s: 0 for s in AlertSeverity}
        by_status = {s: 0 for s in AlertStatus}
        for alert in self._active_alerts.values():
            by_severity[alert.severity] += 1
            by_status[alert.status] += 1
        return {
            "total": len(self._active_alerts),
            "by_severity": {s.value: c for s, c in by_severity.items()},
            "by_status": {s.value: c for s, c in by_status.items()},
        }


class AlertNotification:
    def __init__(self, alert: AlertInstance):
        self.alert = alert
        self._notification_sent = False

    def format_message(self) -> str:
        severity_emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.ERROR: "❌",
            AlertSeverity.CRITICAL: "🔴",
        }
        emoji = severity_emoji.get(self.alert.severity, "❓")
        return f"{emoji} [{self.alert.severity.value.upper()}] {self.alert.message}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.alert.id,
            "rule": self.alert.rule.name,
            "severity": self.alert.severity.value,
            "message": self.alert.message,
            "source": self.alert.source,
            "timestamp": self.alert.timestamp.isoformat(),
            "status": self.alert.status.value,
            "metadata": self.alert.metadata,
        }


def create_alert_manager() -> AlertManager:
    return AlertManager()


alert_manager = AlertManager.get_instance()