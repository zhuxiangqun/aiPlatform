"""
告警通知器 — supports Email (SMTP) and Console (print) channels.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


class Notifier(ABC):
    """通知器基类"""

    @abstractmethod
    async def notify(self, alert: Dict[str, Any]) -> bool:
        """发送通知"""
        pass


class EmailNotifier(Notifier):
    """邮件通知器 — sends via SMTP with env var configuration.

    Env vars:
        AIPLAT_SMTP_HOST: SMTP server hostname (default: localhost)
        AIPLAT_SMTP_PORT: SMTP server port (default: 587)
        AIPLAT_SMTP_USER: SMTP username for auth (default: empty = no auth)
        AIPLAT_SMTP_PASSWORD: SMTP password for auth
        AIPLAT_SMTP_FROM: From address (default: aiplat@localhost)
    """

    def __init__(self, smtp_host: str = "", recipients: List[str] = None):
        self.smtp_host = smtp_host or os.getenv("AIPLAT_SMTP_HOST", "localhost")
        self.smtp_port = int(os.getenv("AIPLAT_SMTP_PORT", "587"))
        self.smtp_user = os.getenv("AIPLAT_SMTP_USER", "")
        self.smtp_password = os.getenv("AIPLAT_SMTP_PASSWORD", "")
        self.smtp_from = os.getenv("AIPLAT_SMTP_FROM", "aiplat@localhost")
        self.recipients = recipients or []

    async def notify(self, alert: Dict[str, Any]) -> bool:
        """发送邮件通知 — SMTP with TLS, falls back to console log."""
        subject = f"[{alert.get('severity', 'INFO').upper()}] Alert: {alert.get('rule', 'unknown')}"
        body = f"""
Alert: {alert.get('rule', 'unknown')}
Layer: {alert.get('layer', 'unknown')}
Metric: {alert.get('metric', 'unknown')}
Current Value: {alert.get('value', 'N/A')}
Threshold: {alert.get('threshold', 'N/A')}
Severity: {alert.get('severity', 'info')}
Time: {alert.get('timestamp', '')}
        """

        recipients = self.recipients
        if not recipients:
            recipients_str = alert.get("recipients", "")
            if isinstance(recipients_str, str) and recipients_str:
                recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]

        if not recipients:
            logger.warning("EmailNotifier: no recipients configured, skipping email for alert %s", alert.get('rule'))
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = self.smtp_from
            msg["To"] = ", ".join(recipients)
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            import asyncio
            def _send():
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                    server.starttls()
                    if self.smtp_user and self.smtp_password:
                        server.login(self.smtp_user, self.smtp_password)
                    server.sendmail(self.smtp_from, recipients, msg.as_string())

            await asyncio.to_thread(_send)
            logger.info("EmailNotifier: alert sent to %d recipients for rule %s", len(recipients), alert.get('rule'))
            return True
        except Exception as e:
            logger.warning("EmailNotifier: SMTP send failed for %s: %s. Falling back to console log.", alert.get('rule'), e)
            logger.warning("Alert (console fallback): [%s] %s — %s", alert.get('severity'), alert.get('rule'), alert.get('metric'))
            return False
