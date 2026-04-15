"""
告警通知器
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List


class Notifier(ABC):
    """通知器基类"""
    
    @abstractmethod
    async def notify(self, alert: Dict[str, Any]) -> bool:
        """发送通知"""
        pass


class EmailNotifier(Notifier):
    """邮件通知器"""
    
    def __init__(self, smtp_host: str, recipients: List[str]):
        self.smtp_host = smtp_host
        self.recipients = recipients
        
    async def notify(self, alert: Dict[str, Any]) -> bool:
        """发送邮件通知"""
        subject = f"[{alert['severity'].upper()}] Alert: {alert['rule']}"
        body = f"""
Alert: {alert['rule']}
Layer: {alert['layer']}
Metric: {alert['metric']}
Current Value: {alert['value']}
Threshold: {alert['threshold']}
Severity: {alert['severity']}
Time: {alert['timestamp']}
        """
        
        # TODO: 实现邮件发送
        print(f"Sending email: {subject}")
        return True
