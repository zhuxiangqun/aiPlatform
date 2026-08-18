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
    async def get_tenant_quota(self, *, tenant_id: str) -> Optional[Dict[str, Any]]: ...

    async def upsert_tenant_quota(
        self, *, tenant_id: str, quota: Dict[str, Any], version: Optional[int] = None
    ) -> Dict[str, Any]: ...

    # ── tenant_usage ──
    async def add_tenant_usage(
        self,
        *,
        tenant_id: str,
        metric_key: str,
        amount: float,
        day: Optional[str] = None,
    ) -> Dict[str, Any]: ...

    async def get_tenant_usage(
        self, *, tenant_id: str, day: str, metric_key: str
    ) -> float: ...

    async def list_tenant_usage(
        self,
        *,
        tenant_id: str,
        day_start: Optional[str] = None,
        day_end: Optional[str] = None,
        metric_key: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> Dict[str, Any]: ...

    # ── tenant_policies ──
    async def get_tenant_policy(self, *, tenant_id: str) -> Optional[Dict[str, Any]]: ...

    async def upsert_tenant_policy(
        self, *, tenant_id: str, policy: Dict[str, Any], version: Optional[int] = None
    ) -> Dict[str, Any]: ...

    async def list_tenant_policies(
        self, *, limit: int = 100, offset: int = 0
    ) -> Dict[str, Any]: ...


# ── registry ──
_tenant_store: Optional[TenantStoreProtocol] = None


def set_tenant_store(store: Optional[TenantStoreProtocol]) -> None:
    """Inject the platform TenantStore (idempotent; call once at startup)."""
    global _tenant_store
    _tenant_store = store


def get_tenant_store() -> Optional[TenantStoreProtocol]:
    """Return the injected tenant store, or None if not yet injected."""
    return _tenant_store
