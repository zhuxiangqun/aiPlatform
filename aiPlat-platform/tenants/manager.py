"""
Tenant Manager - 租户管理
"""

from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel


class TenantStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class TenantQuota(BaseModel):
    max_agents: int = 10
    max_skills: int = 50
    max_api_keys: int = 10
    max_concurrent_runs: int = 5
    monthly_tokens: int = 1_000_000


class TenantConfig(BaseModel):
    allow_public_skill_deployment: bool = True
    allow_external_tools: bool = False
    enable_mcp: bool = True
    enable_approval_required: bool = False
    retention_days: int = 30


class Tenant(BaseModel):
    tenant_id: str
    name: str
    status: TenantStatus = TenantStatus.ACTIVE
    quota: TenantQuota = TenantQuota()
    config: TenantConfig = TenantConfig()
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()


class TenantStats(BaseModel):
    agent_count: int = 0
    skill_count: int = 0
    api_key_count: int = 0
    active_runs: int = 0
    monthly_token_usage: int = 0


class TenantManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._tenants: Dict[str, Tenant] = {}
        self._default_tenant_id = "default"

    def create_tenant(self, tenant_id: str, name: str, **kwargs) -> Tenant:
        """创建租户"""
        quota = kwargs.get("quota")
        config = kwargs.get("config")

        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            quota=quota or TenantQuota(),
            config=config or TenantConfig(),
        )
        self._tenants[tenant_id] = tenant
        return tenant

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """获取租户"""
        return self._tenants.get(tenant_id)

    def update_tenant(self, tenant_id: str, **kwargs) -> Optional[Tenant]:
        """更新租户"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None

        for key, value in kwargs.items():
            if hasattr(tenant, key):
                setattr(tenant, key, value)
        tenant.updated_at = datetime.now()
        return tenant

    def delete_tenant(self, tenant_id: str) -> bool:
        """删除租户"""
        if tenant_id in self._tenants:
            self._tenants[tenant_id].status = TenantStatus.DELETED
            return True
        return False

    def suspend_tenant(self, tenant_id: str) -> bool:
        """停用租户"""
        tenant = self._tenants.get(tenant_id)
        if tenant:
            tenant.status = TenantStatus.SUSPENDED
            return True
        return False

    def activate_tenant(self, tenant_id: str) -> bool:
        """激活租户"""
        tenant = self._tenants.get(tenant_id)
        if tenant:
            tenant.status = TenantStatus.ACTIVE
            return True
        return False

    def list_tenants(self, status: Optional[TenantStatus] = None) -> list[Tenant]:
        """列出租户"""
        tenants = list(self._tenants.values())
        if status:
            tenants = [t for t in tenants if t.status == status]
        return tenants

    def check_quota(self, tenant_id: str, resource: str, value: int = 1) -> bool:
        """检查配额"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return True

        quota = tenant.quota
        if resource == "agents":
            return quota.max_agents >= value
        elif resource == "skills":
            return quota.max_skills >= value
        elif resource == "api_keys":
            return quota.max_api_keys >= value
        elif resource == "concurrent_runs":
            return quota.max_concurrent_runs >= value
        return True

    def get_default_tenant_id(self) -> str:
        """获取默认租户ID"""
        return self._default_tenant_id


tenant_manager = TenantManager()