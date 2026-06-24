"""
Tenant Manager - 租户管理

Persistence: memory (fast read) + SQLite (durable, survives restart).
"""

import os
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel


class TenantStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"
    PENDING = "pending"


class TenantPlan(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


PLAN_DEFAULTS = {
    "free":       {"max_agents": 3, "max_skills": 10, "monthly_tokens": 100000},
    "pro":        {"max_agents": 10, "max_skills": 50, "monthly_tokens": 1000000},
    "enterprise": {"max_agents": 100, "max_skills": 500, "monthly_tokens": 10000000},
}


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
    plan: str = "free"
    status: TenantStatus = TenantStatus.ACTIVE
    quota: TenantQuota = TenantQuota()
    config: TenantConfig = TenantConfig()
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)


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
        self._default_tenant_id = os.getenv("AIPLAT_DEFAULT_TENANT", "default")
        self._db = None
        self._load_from_db()

    def _ensure_db(self):
        if self._db is None:
            from storage.platform_db import PlatformDB
            self._db = PlatformDB()

    def _load_from_db(self):
        try:
            self._ensure_db()
            for row in self._db.list_tenants():
                tenant = Tenant(
                    tenant_id=row["tenant_id"],
                    name=row["name"],
                    plan=row.get("plan", "free"),
                    status=TenantStatus(row.get("status", "active")),
                    quota=TenantQuota(),
                    config=TenantConfig(
                        allow_public_skill_deployment=bool(row.get("allow_public_skill_deployment", True)),
                        allow_external_tools=bool(row.get("allow_external_tools", False)),
                        enable_mcp=bool(row.get("enable_mcp", True)),
                        enable_approval_required=bool(row.get("enable_approval_required", False)),
                        retention_days=int(row.get("retention_days", 30)),
                    ),
                )
                self._tenants[tenant.tenant_id] = tenant
        except Exception:
            pass  # DB not available yet, start empty

    def _persist(self, tenant: Tenant):
        try:
            self._ensure_db()
            self._db.upsert_tenant({
                "tenant_id": tenant.tenant_id,
                "name": tenant.name,
                "plan": getattr(tenant, "plan", "free"),
                "status": tenant.status.value,
                "retention_days": tenant.config.retention_days,
                "allow_public_skill_deployment": tenant.config.allow_public_skill_deployment,
                "allow_external_tools": tenant.config.allow_external_tools,
                "enable_mcp": tenant.config.enable_mcp,
                "enable_approval_required": tenant.config.enable_approval_required,
            })
        except Exception:
            pass

    def create_tenant(self, tenant_id: str, name: str, **kwargs) -> Tenant:
        """创建租户"""
        quota = kwargs.get("quota")
        config = kwargs.get("config")

        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            plan=kwargs.get("plan", "free"),
            status=TenantStatus(kwargs.get("status", "active")),
            quota=quota or TenantQuota(),
            config=config or TenantConfig(),
        )
        self._tenants[tenant_id] = tenant
        self._persist(tenant)
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
        tenant.updated_at = datetime.now(timezone.utc)
        self._persist(tenant)
        return tenant

    def delete_tenant(self, tenant_id: str) -> bool:
        """删除租户"""
        if tenant_id in self._tenants:
            self._tenants[tenant_id].status = TenantStatus.DELETED
            self._persist(self._tenants[tenant_id])
            try:
                self._ensure_db()
                self._db.delete_tenant(tenant_id)
            except Exception:
                pass
            return True
        return False

    def suspend_tenant(self, tenant_id: str) -> bool:
        """停用租户"""
        tenant = self._tenants.get(tenant_id)
        if tenant:
            tenant.status = TenantStatus.SUSPENDED
            self._persist(tenant)
            return True
        return False

    def activate_tenant(self, tenant_id: str) -> bool:
        """激活租户"""
        tenant = self._tenants.get(tenant_id)
        if tenant:
            tenant.status = TenantStatus.ACTIVE
            self._persist(tenant)
            return True
        return False

    def set_verification_token(self, tenant_id: str, token: str) -> bool:
        """设置邮箱验证 token"""
        try:
            self._ensure_db()
            self._db.upsert_tenant({
                "tenant_id": tenant_id,
                "name": self._tenants.get(tenant_id, Tenant(tenant_id=tenant_id, name="")).name,
                "verification_token": token,
            })
            return True
        except Exception:
            return False

    def verify_token(self, tenant_id: str, token: str) -> bool:
        """验证邮箱验证 token"""
        try:
            self._ensure_db()
            row = self._db.get_tenant(tenant_id)
            return row and row.get("verification_token") == token
        except Exception:
            return False

    def find_by_email(self, email: str) -> Optional[Tenant]:
        """通过邮箱查找租户（用于重复注册检测）"""
        try:
            self._ensure_db()
            row = self._db.find_by_email(email)
            if row:
                return self._tenants.get(row["tenant_id"])
        except Exception:
            pass
        return None

    def get_plan_quota(self, tenant_id: str) -> dict:
        """获取 plan 级别默认配额"""
        tenant = self._tenants.get(tenant_id)
        plan = getattr(tenant, "plan", "free") if tenant else "free"
        return PLAN_DEFAULTS.get(plan, PLAN_DEFAULTS["free"])

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