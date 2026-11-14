"""TenantStoreProtocol — tenant quota / usage / policy store interface (P0-A3).

# NOTE: interface contract only — implementation should move to platform layer (P0-A3)
# DEPRECATED: concrete CRUD migrate to platform TenantStore (aiPlat-platform/tenants/tenant_store.py)

Defines the contract that the platform-layer TenantStore implements. Core
consumers (policy gate, llm accounting, policy engine) read/write tenant data
through this protocol + registry, so core never owns the tenant tables' DDL or
CRUD (architecture: tenant governance belongs to platform, §5.29 kernel
agnostic).

Injection: platform startup calls ``set_tenant_store(store)`` once. Until then
``get_tenant_store()`` returns None and consumers keep their existing
``if store and hasattr(store, ...)`` guards (zero breakage).

Method signatures mirror the former core ExecutionStore mixin methods exactly
(quota_mixin / audit_mixin) — call sites are unchanged, only the store source
changes.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class TenantStoreProtocol(Protocol):
    """Tenant quota / usage / policy CRUD contract (implemented by platform)."""

    # ── tenant_quotas ──
    async def get_tenant_quota(self, *, tenant_id: str) -> Optional[Dict[str, Any]]:
        """读取租户配额。

        Args:
            tenant_id: 租户 ID。
        """
        ...

    async def upsert_tenant_quota(
        self, *, tenant_id: str, quota: Dict[str, Any], version: Optional[int] = None
    ) -> Dict[str, Any]:
        """写入或更新租户配额。

        Args:
            tenant_id: 租户 ID。
            quota: 配额字段 dict。
            version: 可选乐观锁版本。
        """
        ...

    # ── tenant_usage ──
    async def add_tenant_usage(
        self,
        *,
        tenant_id: str,
        metric_key: str,
        amount: float,
        day: Optional[str] = None,
    ) -> Dict[str, Any]:
        """累加租户用量。

        Args:
            tenant_id: 租户 ID。
            metric_key: 用量指标键。
            amount: 增量。
            day: 可选日分区；None 表示当天。
        """
        ...

    async def get_tenant_usage(
        self, *, tenant_id: str, day: str, metric_key: str
    ) -> float:
        """读取单日单指标用量。

        Args:
            tenant_id: 租户 ID。
            day: 日分区。
            metric_key: 用量指标键。
        """
        ...

    async def list_tenant_usage(
        self,
        *,
        tenant_id: str,
        day_start: Optional[str] = None,
        day_end: Optional[str] = None,
        metric_key: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """分页列出租户用量。

        Args:
            tenant_id: 租户 ID。
            day_start: 起始日；None 不限。
            day_end: 结束日；None 不限。
            metric_key: 可选指标过滤。
            limit: 返回条数上限。
            offset: 分页偏移。
        """
        ...

    # ── tenant_policies ──
    async def get_tenant_policy(self, *, tenant_id: str) -> Optional[Dict[str, Any]]:
        """读取租户策略。

        Args:
            tenant_id: 租户 ID。
        """
        ...

    async def upsert_tenant_policy(
        self, *, tenant_id: str, policy: Dict[str, Any], version: Optional[int] = None
    ) -> Dict[str, Any]:
        """写入或更新租户策略。

        Args:
            tenant_id: 租户 ID。
            policy: 策略字段 dict。
            version: 可选乐观锁版本。
        """
        ...

    async def list_tenant_policies(
        self, *, limit: int = 100, offset: int = 0
    ) -> Dict[str, Any]:
        """分页列出租户策略。

        Args:
            limit: 返回条数上限。
            offset: 分页偏移。
        """
        ...


# ── registry ──
_tenant_store: Optional[TenantStoreProtocol] = None


def set_tenant_store(store: Optional[TenantStoreProtocol]) -> None:
    """注入平台 TenantStore（启动时调用一次，可幂等）。

    Args:
        store: 平台实现；None 表示卸载。
    """
    global _tenant_store
    _tenant_store = store


def get_tenant_store() -> Optional[TenantStoreProtocol]:
    """返回已注入的租户存储；未注入时为 None。"""
    return _tenant_store
