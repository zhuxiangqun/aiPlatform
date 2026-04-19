"""
Billing Meter - 计费计量服务
"""

from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel


class Usage(BaseModel):
    """用量记录"""
    tenant_id: str
    capability_type: str
    capability_name: str
    requests: int = 1
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    timestamp: datetime = datetime.now()


class Bill(BaseModel):
    """账单"""
    bill_id: str
    tenant_id: str
    period_start: datetime
    period_end: datetime
    total_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    status: str = "pending"


class BillingService:
    """计费服务"""

    def __init__(self):
        self._pricing: Dict[str, float] = {
            "agent": 0.001,
            "skill": 0.0005,
            "tool": 0.0001,
            "workflow": 0.002,
            "memory": 0.0001,
            "mcp": 0.0002,
        }
        self._records: list[Usage] = []
        self._monthly_usage: Dict[str, Dict[str, int]] = {}
        self._monthly_cost: Dict[str, float] = {}

    def set_price(self, capability_type: str, price_per_request: float) -> None:
        """设置价格"""
        self._pricing[capability_type] = price_per_request

    def get_price(self, capability_type: str) -> float:
        """获取价格"""
        return self._pricing.get(capability_type, 0.001)

    def record_usage(
        self,
        tenant_id: str,
        capability_type: str,
        capability_name: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> Usage:
        """记录用量"""
        price = self.get_price(capability_type)
        cost = price * (1 + input_tokens / 1000 + output_tokens / 1000)

        usage = Usage(
            tenant_id=tenant_id,
            capability_type=capability_type,
            capability_name=capability_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
        )
        self._records.append(usage)

        if tenant_id not in self._monthly_usage:
            self._monthly_usage[tenant_id] = {"requests": 0, "tokens": 0}
            self._monthly_cost[tenant_id] = 0.0

        self._monthly_usage[tenant_id]["requests"] += 1
        self._monthly_usage[tenant_id]["tokens"] += input_tokens + output_tokens
        self._monthly_cost[tenant_id] += cost

        return usage

    def get_monthly_usage(self, tenant_id: str) -> Dict[str, int]:
        """获取月度用量"""
        return self._monthly_usage.get(tenant_id, {"requests": 0, "tokens": 0})

    def get_monthly_cost(self, tenant_id: str) -> float:
        """获取月度费用"""
        return self._monthly_cost.get(tenant_id, 0.0)

    def get_usage_by_type(self, tenant_id: str, capability_type: str) -> Dict[str, int]:
        """按类型获取用量"""
        filtered = [r for r in self._records if r.tenant_id == tenant_id and r.capability_type == capability_type]
        requests = len(filtered)
        tokens = sum(r.input_tokens + r.output_tokens for r in filtered)
        return {"requests": requests, "tokens": tokens}

    def generate_bill(self, tenant_id: str, period_start: datetime, period_end: datetime) -> Bill:
        """生成账单"""
        usage = self._monthly_usage.get(tenant_id, {"requests": 0, "tokens": 0})
        cost = self._monthly_cost.get(tenant_id, 0.0)

        return Bill(
            bill_id=f"bill_{tenant_id}_{period_start.strftime('%Y%m')}",
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            total_requests=usage["requests"],
            total_tokens=usage["tokens"],
            total_cost=cost,
        )


billing_service = BillingService()