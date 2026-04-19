from __future__ import annotations

from typing import Any, Dict, Optional

from core.apps.plugins.manifest import PluginManifest


class PluginManager:
    """
    PR-11: PluginManager (MVP)

    目前只做：
    - install/upsert/list/enable
    - run：生成 run_id + 审计 + 通过 policy/approval gate（执行逻辑后续接 Orchestrator/Workflow）
    """

    def __init__(self, execution_store: Any):
        self._store = execution_store

    async def upsert_plugin(
        self,
        *,
        tenant_id: Optional[str],
        manifest: Dict[str, Any],
        enabled: bool = False,
    ) -> Dict[str, Any]:
        if not self._store:
            raise RuntimeError("ExecutionStore not initialized")
        m = PluginManifest.from_dict(manifest)
        return await self._store.upsert_plugin(
            tenant_id=str(tenant_id) if tenant_id else None,
            plugin_id=m.plugin_id,
            name=m.name,
            version=m.version,
            enabled=bool(enabled),
            manifest=m.to_dict(),
            metadata=m.metadata or {},
        )

    async def list_plugins(self, *, tenant_id: Optional[str], limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        if not self._store:
            raise RuntimeError("ExecutionStore not initialized")
        return await self._store.list_plugins(tenant_id=str(tenant_id) if tenant_id else None, limit=limit, offset=offset)

    async def get_plugin(self, *, tenant_id: Optional[str], plugin_id: str) -> Optional[Dict[str, Any]]:
        if not self._store:
            raise RuntimeError("ExecutionStore not initialized")
        return await self._store.get_plugin(tenant_id=str(tenant_id) if tenant_id else None, plugin_id=str(plugin_id))

    async def set_enabled(self, *, tenant_id: Optional[str], plugin_id: str, enabled: bool) -> bool:
        if not self._store:
            raise RuntimeError("ExecutionStore not initialized")
        return await self._store.set_plugin_enabled(tenant_id=str(tenant_id) if tenant_id else None, plugin_id=str(plugin_id), enabled=bool(enabled))

    async def list_versions(self, *, tenant_id: Optional[str], plugin_id: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        if not self._store:
            raise RuntimeError("ExecutionStore not initialized")
        return await self._store.list_plugin_versions(tenant_id=str(tenant_id) if tenant_id else None, plugin_id=str(plugin_id), limit=limit, offset=offset)

    async def rollback(self, *, tenant_id: Optional[str], plugin_id: str, version: str) -> Dict[str, Any]:
        if not self._store:
            raise RuntimeError("ExecutionStore not initialized")
        cur = await self._store.get_plugin(tenant_id=str(tenant_id) if tenant_id else None, plugin_id=str(plugin_id))
        if not cur:
            raise RuntimeError("plugin_not_found")
        pv = await self._store.get_plugin_version(tenant_id=str(tenant_id) if tenant_id else None, plugin_id=str(plugin_id), version=str(version))
        if not pv:
            raise RuntimeError("version_not_found")
        enabled = bool(int(cur.get("enabled") or 0) == 1)
        # upsert using stored manifest + keep enabled flag
        return await self.upsert_plugin(tenant_id=str(tenant_id) if tenant_id else None, manifest=pv.get("manifest") or {}, enabled=enabled)
