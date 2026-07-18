"""
EmailNotifier — lightweight email notification service for FDE delivery alerts.

Uses Python stdlib smtplib for zero-dependency SMTP delivery.
Configuration via environment variables:
  - AIPLAT_SMTP_HOST (default: localhost)
  - AIPLAT_SMTP_PORT (default: 587)
  - AIPLAT_SMTP_USER (default: empty → no auth)
  - AIPLAT_SMTP_PASS (default: empty)
  - AIPLAT_SMTP_FROM (default: fde@aiplat.local)
  - AIPLAT_SMTP_TLS  (default: true)

Usage:
    notifier = EmailNotifier()
    notifier.send(
        to="dm@customer.com",
        subject="[FDE] 质量评分低于阈值",
        body="当前 Golden Query 通过率 72%，低于 80% 阈值。请检查。"
    )
"""
import logging
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

_log = logging.getLogger("aiplat.notifier")


class EmailNotifier:
    """FDE 邮件通知器 — 交付告警/验收签收/中止通知等场景。"""

    def __init__(self):
        self.host = os.getenv("AIPLAT_SMTP_HOST", "localhost")
        self.port = int(os.getenv("AIPLAT_SMTP_PORT", "587"))
        self.user = os.getenv("AIPLAT_SMTP_USER", "")
        self.password = os.getenv("AIPLAT_SMTP_PASS", "")
        self.from_addr = os.getenv("AIPLAT_SMTP_FROM", "fde@aiplat.local")
        self.use_tls = os.getenv("AIPLAT_SMTP_TLS", "true").lower() in ("1", "true", "yes")

    def send(self, to: str, subject: str, body: str, html: Optional[str] = None) -> bool:
        """Send an email. Returns True on success, False on failure.

        Falls back to console log when SMTP host is localhost (dev mode).
        """
        if self.host == "localhost":
            _log.info(
                "[EmailNotifier] 开发模式 — 邮件未发送（SMTP_HOST=localhost）\n"
                "  To: %s\n  Subject: %s\n  Body: %.200s", to, subject, body
            )
            return True

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.from_addr
            msg["To"] = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))
            if html:
                msg.attach(MIMEText(html, "html", "utf-8"))

            context = ssl.create_default_context() if self.use_tls else None

            if self.use_tls:
                server = smtplib.SMTP(self.host, self.port, timeout=10)
                server.starttls(context=context)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=10)

            if self.user:
                server.login(self.user, self.password)

            server.sendmail(self.from_addr, [to], msg.as_string())
            server.quit()
            _log.info("[EmailNotifier] 邮件已发送 → %s: %s", to, subject)
            return True

        except Exception as e:
            _log.warning("[EmailNotifier] 发送失败 → %s: %s", to, str(e)[:200])
            return False


# Singleton
_notifier: Optional[EmailNotifier] = None


def get_email_notifier() -> EmailNotifier:
    global _notifier
    if _notifier is None:
        _notifier = EmailNotifier()
    return _notifier
