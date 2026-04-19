"""
Quota Manager - 配额管理
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class Quota(BaseModel):
    """配额"""
    tenant_id: str
    max_agents: int = 10
    max_skills: int = 50
    max_api_keys: int = 10
    max_concurrent_runs: int = 5
    monthly_tokens: int = 1_000_000
    updated_at: datetime = datetime.now()


class QuotaUsage(BaseModel):
    """配额使用"""
    tenant_id: str
    agents: int = 0
    skills: int = 0
    api_keys: int = 0
    concurrent_runs: int = 0
    monthly_tokens: int = 0


class QuotaExceededError(Exception):
    """配额超限异常"""
    pass


class QuotaManager:
    """配额管理服务"""

    def __init__(self):
        self._quotas: dict[str, Quota] = {}
        self._usage: dict[str, QuotaUsage] = {}

    def set_quota(
        self,
        tenant_id: str,
        max_agents: int = 10,
        max_skills: int = 50,
        max_api_keys: int = 10,
        max_concurrent_runs: int = 5,
        monthly_tokens: int = 1_000_000,
    ) -> None:
        """设置配额"""
        self._quotas[tenant_id] = Quota(
            tenant_id=tenant_id,
            max_agents=max_agents,
            max_skills=max_skills,
            max_api_keys=max_api_keys,
            max_concurrent_runs=max_concurrent_runs,
            monthly_tokens=monthly_tokens,
        )

    def get_quota(self, tenant_id: str) -> Optional[Quota]:
        """获取配额"""
        return self._quotas.get(tenant_id)

    def check(self, tenant_id: str, resource: str, value: int = 1) -> bool:
        """检查配额"""
        quota = self._quotas.get(tenant_id)
        if not quota:
            return True

        usage = self._usage.get(tenant_id, QuotaUsage(tenant_id=tenant_id))

        if resource == "agents":
            return usage.agents + value <= quota.max_agents
        elif resource == "skills":
            return usage.skills + value <= quota.max_skills
        elif resource == "api_keys":
            return usage.api_keys + value <= quota.max_api_keys
        elif resource == "concurrent_runs":
            return usage.concurrent_runs + value <= quota.max_concurrent_runs
        elif resource == "monthly_tokens":
            return usage.monthly_tokens + value <= quota.monthly_tokens
        return True

    def consume(self, tenant_id: str, resource: str, value: int = 1) -> bool:
        """消费配额"""
        if not self.check(tenant_id, resource, value):
            return False

        if tenant_id not in self._usage:
            self._usage[tenant_id] = QuotaUsage(tenant_id=tenant_id)

        usage = self._usage[tenant_id]
        if resource == "agents":
            usage.agents += value
        elif resource == "skills":
            usage.skills += value
        elif resource == "api_keys":
            usage.api_keys += value
        elif resource == "concurrent_runs":
            usage.concurrent_runs += value
        elif resource == "monthly_tokens":
            usage.monthly_tokens += value

        return True

    def release(self, tenant_id: str, resource: str, value: int = 1) -> None:
        """释放配额"""
        if tenant_id not in self._usage:
            return

        usage = self._usage[tenant_id]
        if resource == "agents":
            usage.agents = max(0, usage.agents - value)
        elif resource == "skills":
            usage.skills = max(0, usage.skills - value)
        elif resource == "api_keys":
            usage.api_keys = max(0, usage.api_keys - value)
        elif resource == "concurrent_runs":
            usage.concurrent_runs = max(0, usage.concurrent_runs - value)
        elif resource == "monthly_tokens":
            usage.monthly_tokens = max(0, usage.monthly_tokens - value)

    def get_usage(self, tenant_id: str) -> Optional[QuotaUsage]:
        """获取配额使用"""
        return self._usage.get(tenant_id)

    def reset_usage(self, tenant_id: str) -> None:
        """重置配额使用"""
        if tenant_id in self._usage:
            self._usage[tenant_id] = QuotaUsage(tenant_id=tenant_id)


quota_manager = QuotaManager()