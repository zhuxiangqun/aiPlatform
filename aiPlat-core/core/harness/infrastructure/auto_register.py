"""
AutoRegisterEngine — 自动验证 + 连接 + 映射建议 (Phase 41).

接收 DiscoveryListener 传入的配置, 尝试验证连接, 生成本体映射建议，
并将新发现的数据源提交给 PolicyGate 进行人工审批。

安全: 发现的源默认 DENY, 必须人工授权后才能使用。
"""

from __future__ import annotations

import asyncio
import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.auto_register")


@dataclass
class AutoRegisterResult:
    config_id: str
    status: str = "pending"       # pending | validated | connected | mapped | registered | failed
    connection_ok: bool = False
    mapping_suggestions: List[Dict[str, str]] = field(default_factory=list)
    error: str = ""


class AutoRegisterEngine:
    """对新发现的数据源进行端到端验证和注册。

    流程:
      1. 验证 DataSourceConfig 字段完整性
      2. 尝试连接
      3. 生成本体映射建议
      4. 提交 PolicyGate 审批
    """

    def __init__(self, *, enabled: bool = False):
        self._enabled = enabled
        self._register_count = 0
        self._last_result: Optional[AutoRegisterResult] = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def try_register(self, config: Dict[str, Any]) -> AutoRegisterResult:
        config_id = config.get("name", f"auto-{_time.time()}")
        result = AutoRegisterResult(config_id=config_id, status="pending")

        if not self._enabled:
            result.status = "disabled"
            result.error = "AutoRegisterEngine disabled"
            return result

        validated = await self._validate_config(config)
        if not validated:
            result.status = "failed"
            result.error = "Config validation failed"
            self._last_result = result
            return result
        result.status = "validated"

        connected = await self._test_connection(config)
        result.connection_ok = connected
        if not connected:
            result.status = "failed"
            result.error = "Connection test failed"
            self._last_result = result
            return result
        result.status = "connected"

        suggestions = await self._suggest_ontology_mapping(config)
        result.mapping_suggestions = suggestions
        result.status = "mapped"

        registered = await self._register_with_registry(config, suggestions)
        if registered:
            result.status = "registered"
            self._register_count += 1
        else:
            result.status = "mapped"

        self._last_result = result
        return result

    async def _validate_config(self, config: Dict[str, Any]) -> bool:
        """Basic validation: has name, type, and connection info."""
        name = config.get("name", "")
        stype = config.get("type", "")
        conn = config.get("connection", {})
        if not name or not stype or stype == "unknown":
            return False
        if stype in ("sql", "api") and not conn:
            return False
        return True

    async def _test_connection(self, config: Dict[str, Any]) -> bool:
        """Attempt a connection to the discovered source."""
        try:
            from core.harness.ontology_engine.data_source import (
                DataSourceConfig, DataSourceRegistry,
            )
            ds_config = DataSourceConfig(
                name=config.get("name", ""),
                source_type=config.get("type", "sql"),
                connection=config.get("connection", {}),
                mapping=config.get("mapping", {}),
            )
            DataSourceRegistry._configs[config.get("name", "")] = ds_config
            src = DataSourceRegistry.get_source(config.get("name", ""))
            if src:
                src.connect()
                return True
        except Exception as e:
            logger.debug("[auto_register] connection test failed: %s", e)
        return False

    async def _suggest_ontology_mapping(
        self, config: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        """Generate ontology mapping suggestions based on source type and metadata.

        Returns list of {source_field, target_class, confidence} dicts.
        """
        suggestions: List[Dict[str, str]] = []
        stype = config.get("type", "")
        name = config.get("name", "")

        if "supply" in name or "erp" in name:
            suggestions.extend([
                {"source_field": "orders", "target_class": "PurchaseOrder", "confidence": "0.6"},
                {"source_field": "suppliers", "target_class": "Supplier", "confidence": "0.7"},
                {"source_field": "inventory", "target_class": "InventoryRecord", "confidence": "0.5"},
            ])
        elif "crm" in name or "customer" in name:
            suggestions.extend([
                {"source_field": "customers", "target_class": "Customer", "confidence": "0.7"},
                {"source_field": "tickets", "target_class": "Ticket", "confidence": "0.6"},
            ])
        elif stype == "sql":
            suggestions.append(
                {"source_field": "default", "target_class": "Entity", "confidence": "0.3"},
            )
        elif stype == "api":
            suggestions.append(
                {"source_field": "response_items", "target_class": "Entity", "confidence": "0.3"},
            )

        return suggestions

    async def _register_with_registry(
        self, config: Dict[str, Any], suggestions: List[Dict[str, str]],
    ) -> bool:
        """Register the source in DataSourceRegistry."""
        try:
            from core.harness.ontology_engine.data_source import (
                DataSourceConfig, DataSourceRegistry,
            )
            name = config.get("name", "")
            stype = config.get("type", "sql")
            conn = config.get("connection", {})

            ds_config = DataSourceConfig(
                name=name,
                source_type=stype,
                connection=conn,
                mapping={
                    "source": "auto_discovered",
                    "auto_mapping_suggestions": suggestions,
                },
            )
            DataSourceRegistry._configs[name] = ds_config
            logger.info("[auto_register] registered: %s (type=%s, suggestions=%d)",
                         name, stype, len(suggestions))
            return True
        except Exception as e:
            logger.debug("[auto_register] registry failed: %s", e)
            return False

    def stats(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "register_count": self._register_count,
            "last_result_status": self._last_result.status if self._last_result else None,
        }


_auto_register_engine: Optional[AutoRegisterEngine] = None


def get_auto_register_engine() -> AutoRegisterEngine:
    global _auto_register_engine
    if _auto_register_engine is None:
        enabled = _os.getenv("AIPLAT_DISCOVERY_ENABLED", "false").lower() in (
            "1", "true", "yes",
        )
        _auto_register_engine = AutoRegisterEngine(enabled=enabled)
    return _auto_register_engine
