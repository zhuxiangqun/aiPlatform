from typing import Dict, Any, Optional, Callable, List, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import asyncio
import logging


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

        now = datetime.now(timezone.utc)
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
        self._persist_alert(alert)

        for handler in self._handlers:
            try:
                await handler(alert)
            except Exception as e:
                logging.debug(str(e), exc_info=True)

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
        alert.acknowledged_at = datetime.now(timezone.utc)
        self._persist_alert(alert)
        return True

    def resolve(self, alert_id: str) -> bool:
        alert = self._active_alerts.get(alert_id)
        if not alert:
            return False
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(timezone.utc)
        self._persist_alert(alert)
        return True

    def suppress(self, rule_name: str, suppress: bool = True):
        self._suppressed[rule_name] = suppress

    def clear_resolved(self, older_than_seconds: int = 3600):
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
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

    # ── SQLite persistence (2026-07-18) ──
    _db_path: Optional[str] = None

    def _init_db(self) -> None:
        import sqlite3, os
        if self._db_path is not None:
            return
        db_dir = os.path.expanduser("~/.aiplat")
        os.makedirs(db_dir, exist_ok=True)
        self._db_path = os.path.join(db_dir, "alerts.db")
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY, rule_name TEXT, severity TEXT,
                    message TEXT, source TEXT, status TEXT,
                    timestamp TEXT, acknowledged_at TEXT, resolved_at TEXT,
                    fire_count INTEGER DEFAULT 1, metadata_json TEXT DEFAULT '{}'
                )
            """)
        self._load_alerts()
        _log.info(f"AlertEngine: SQLite persistence initialized ({self._db_path})")

    def _persist_alert(self, alert: AlertInstance) -> None:
        if self._db_path is None:
            self._init_db()
        import sqlite3, json
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (alert.id, alert.rule.name, alert.severity.value, alert.message,
                 alert.source, alert.status.value, alert.timestamp.isoformat(),
                 alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                 alert.resolved_at.isoformat() if alert.resolved_at else None,
                 alert.fire_count, json.dumps(alert.metadata, default=str))
            )

    def _load_alerts(self) -> None:
        import sqlite3, json
        if self._db_path is None:
            return
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute("SELECT * FROM alerts WHERE status != 'resolved'").fetchall()
        for row in rows:
            rule = self._rules.get(row[1]) or AlertRule(name=row[1], condition="", severity=AlertSeverity.WARNING)
            alert = AlertInstance(
                id=row[0], rule=rule, severity=AlertSeverity(row[2]),
                message=row[3], source=row[4], timestamp=datetime.fromisoformat(row[6]),
                status=AlertStatus(row[5]),
                acknowledged_at=datetime.fromisoformat(row[7]) if row[7] else None,
                resolved_at=datetime.fromisoformat(row[8]) if row[8] else None,
                fire_count=row[9], metadata=json.loads(row[10]) if row[10] else {}
            )
            self._active_alerts[alert.id] = alert
        if self._active_alerts:
            _log.info(f"AlertEngine: restored {len(self._active_alerts)} active alerts from SQLite")

    def _install_email_notifier(self) -> None:
        try:
            from core.harness.infrastructure.email_notifier import get_email_notifier
            notifier = get_email_notifier()
            async def _email_handler(alert: AlertInstance):
                subject = f"[{alert.severity.value.upper()}] {alert.rule.name}"
                body = f"Alert: {alert.message}\nSource: {alert.source}\nTime: {alert.timestamp}"
                notifier.send(to="admin@aiplat.local", subject=subject, body=body)
            self.register_handler(_email_handler)
            _log.info("AlertEngine: EmailNotifier registered as notification channel")
        except Exception as e:
            _log.warning(f"AlertEngine: EmailNotifier reg skipped ({e})")


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
    mgr = AlertManager()
    mgr._init_db()
    mgr._install_email_notifier()
    return mgr


alert_manager = AlertManager.get_instance()