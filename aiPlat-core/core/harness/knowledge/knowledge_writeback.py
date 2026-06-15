"""
Knowledge WriteBack — external system integration for ontology actions.

When an OntologyAction completes, registered writeback adapters can forward
the result to external business systems (REST webhooks, SQL databases, files,
message queues). This closes the loop: knowledge changes in the ontology
surface as actionable events in operational systems.

Adapters:
  - WebhookWriteBackAdapter: POST to REST endpoint
  - SQLWriteBackAdapter: INSERT/UPDATE via infra DatabaseClient
  - FileWriteBackAdapter: append to JSON/CSV files

Storage: per-collection writeback configs
  ~/.aiplat/wiki/collections/{id}/writebacks.json

callers:
  - knowledge_action.execute_action (auto-trigger)
  - wiki.py /ontology/writebacks (management API)
  - core_facade (facade exposure)
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import time as _time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.harness.knowledge.knowledge_action import OntologyAction

logger = logging.getLogger(__name__)


class WriteBackTarget(str, Enum):
    REST_WEBHOOK = "rest_webhook"
    SQL_DATABASE = "sql_database"
    LOCAL_FILE = "local_file"
    MESSAGE_QUEUE = "message_queue"


@dataclass
class WriteBackConfig:
    target_type: WriteBackTarget
    target_endpoint: str = ""              # webhook URL, SQL conn string, file path
    trigger_actions: List[str] = field(default_factory=lambda: ["create", "update", "deprecate"])
    field_mapping: Dict[str, str] = field(default_factory=dict)
    auth: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    retry_policy: Dict[str, Any] = field(default_factory=lambda: {"max_retries": 3, "backoff": "exponential"})
    idempotency_key_field: str = "action_id"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_type": self.target_type.value,
            "target_endpoint": self.target_endpoint,
            "trigger_actions": self.trigger_actions,
            "field_mapping": self.field_mapping,
            "auth": {k: "***" if "key" in k.lower() or "token" in k.lower() else v
                      for k, v in self.auth.items()},
            "enabled": self.enabled,
            "retry_policy": self.retry_policy,
            "idempotency_key_field": self.idempotency_key_field,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WriteBackConfig":
        return cls(
            target_type=WriteBackTarget(data.get("target_type", "rest_webhook")),
            target_endpoint=data.get("target_endpoint", ""),
            trigger_actions=data.get("trigger_actions", ["create", "update"]),
            field_mapping=data.get("field_mapping", {}),
            auth=data.get("auth", {}),
            enabled=data.get("enabled", True),
            retry_policy=data.get("retry_policy", {"max_retries": 3, "backoff": "exponential"}),
            idempotency_key_field=data.get("idempotency_key_field", "action_id"),
        )


class IWriteBackAdapter(ABC):
    @abstractmethod
    async def write(self, action: Any, config: WriteBackConfig) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def health_check(self, config: WriteBackConfig) -> bool:
        ...


class WebhookWriteBackAdapter(IWriteBackAdapter):
    async def write(self, action: Any, config: WriteBackConfig) -> Dict[str, Any]:
        try:
            import httpx
            payload = self._build_payload(action, config)
            headers = {
                "Content-Type": "application/json",
                "X-Idempotency-Key": getattr(action, config.idempotency_key_field, str(_time.time())),
            }
            for k, v in (config.auth or {}).items():
                if v:
                    headers[k] = v

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(config.target_endpoint, json=payload, headers=headers)
                body = resp.text[:500]
                return {
                    "success": resp.is_success,
                    "external_id": str(resp.status_code),
                    "response": body,
                }
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}

    def _build_payload(self, action: Any, config: WriteBackConfig) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "action_id": getattr(action, "action_id", ""),
            "verb": getattr(action, "verb", "").value if hasattr(getattr(action, "verb", ""), "value") else str(getattr(action, "verb", "")),
            "entity_uri": getattr(action, "target_entity_uri", ""),
            "actor": getattr(action, "actor", ""),
            "timestamp": getattr(action, "completed_at", getattr(action, "created_at", "")),
        }
        action_payload = getattr(action, "payload", {})
        for onto_field, ext_field in config.field_mapping.items():
            value = action_payload.get(onto_field)
            if value is not None:
                payload[ext_field] = str(value)[:5000] if isinstance(value, (dict, list)) else value
        return payload

    async def health_check(self, config: WriteBackConfig) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.head(config.target_endpoint)
                return resp.is_success or resp.status_code == 405  # HEAD not allowed
        except Exception:
            return False


class SQLWriteBackAdapter(IWriteBackAdapter):
    async def write(self, action: Any, config: WriteBackConfig) -> Dict[str, Any]:
        try:
            import sqlite3
            db_path = config.target_endpoint
            if not _os.path.exists(db_path):
                return {"success": False, "error": f"Database not found: {db_path}"}

            payload = action.payload if hasattr(action, "payload") else {}
            table = config.field_mapping.get("_table", "ontology_actions")
            conn = sqlite3.connect(db_path)
            try:
                fields = ", ".join([k for k in payload.keys() if not k.startswith("_")][:10])
                placeholders = ", ".join(["?" for _ in range(min(10, len(payload)))])
                values = [str(payload.get(k, ""))[:1000] for k in list(payload.keys())[:10] if not k.startswith("_")]
                conn.execute(
                    f"INSERT OR REPLACE INTO {table} ({fields}) VALUES ({placeholders})",
                    values,
                )
                conn.commit()
                return {"success": True, "external_id": getattr(action, "action_id", "")}
            finally:
                conn.close()
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}

    async def health_check(self, config: WriteBackConfig) -> bool:
        try:
            import sqlite3
            conn = sqlite3.connect(config.target_endpoint)
            conn.execute("SELECT 1")
            conn.close()
            return True
        except Exception:
            return False


class FileWriteBackAdapter(IWriteBackAdapter):
    async def write(self, action: Any, config: WriteBackConfig) -> Dict[str, Any]:
        try:
            import aiofiles
            path = _os.path.expanduser(config.target_endpoint)
            _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
            record = {
                "action_id": getattr(action, "action_id", ""),
                "verb": str(getattr(action, "verb", "")),
                "entity_uri": getattr(action, "target_entity_uri", ""),
                "timestamp": getattr(action, "completed_at", getattr(action, "created_at", "")),
                "payload_keys": list(getattr(action, "payload", {}).keys())[:10],
            }
            async with aiofiles.open(path, "a") as f:
                await f.write(_json.dumps(record, ensure_ascii=False) + "\n")
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}

    async def health_check(self, config: WriteBackConfig) -> bool:
        path = _os.path.expanduser(config.target_endpoint)
        return _os.path.exists(_os.path.dirname(path) or ".")


_ADAPTER_REGISTRY: Dict[WriteBackTarget, IWriteBackAdapter] = {
    WriteBackTarget.REST_WEBHOOK: WebhookWriteBackAdapter(),
    WriteBackTarget.SQL_DATABASE: SQLWriteBackAdapter(),
    WriteBackTarget.LOCAL_FILE: FileWriteBackAdapter(),
}


def _writeback_config_path(collection_id: str = "default") -> str:
    home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    return _os.path.join(home, "wiki", "collections", collection_id, "writebacks.json")


def register_writeback(config: WriteBackConfig, *, collection_id: str = "default") -> WriteBackConfig:
    u"""Register a writeback configuration."""
    existing = load_writebacks(collection_id=collection_id)
    existing.append(config)
    _save_writebacks(existing, collection_id=collection_id)
    return config


def unregister_writeback(target_endpoint: str, *, collection_id: str = "default") -> bool:
    u"""Remove a writeback configuration by endpoint."""
    configs = load_writebacks(collection_id=collection_id)
    new_configs = [c for c in configs if c.target_endpoint != target_endpoint]
    if len(new_configs) == len(configs):
        return False
    _save_writebacks(new_configs, collection_id=collection_id)
    return True


def load_writebacks(*, collection_id: str = "default") -> List[WriteBackConfig]:
    u"""Load all registered writeback configurations."""
    path = _writeback_config_path(collection_id)
    if not _os.path.exists(path):
        return []
    try:
        data = _json.load(open(path, "r", encoding="utf-8"))
        return [WriteBackConfig.from_dict(c) for c in data.get("writebacks", [])]
    except Exception:
        logger.warning("Failed to load writebacks for %s", collection_id)
        return []


def _save_writebacks(configs: List[WriteBackConfig], *, collection_id: str = "default") -> None:
    path = _writeback_config_path(collection_id)
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump({
            "version": "v1.0",
            "updated_at": _time.time(),
            "writebacks": [c.to_dict() for c in configs],
        }, f, indent=2, ensure_ascii=False)


async def trigger_writebacks(action: Any, *, collection_id: str = "default") -> List[Dict[str, Any]]:
    u"""Trigger all registered writeback adapters for an ontology action.

    Called automatically from execute_action on success.

    Returns list of per-adapter results.
    """
    configs = load_writebacks(collection_id=collection_id)
    if not configs:
        return []

    verb = str(getattr(action, "verb", "")).lower()
    results: List[Dict[str, Any]] = []

    for config in configs:
        if not config.enabled:
            continue
        if verb not in [a.lower() for a in config.trigger_actions]:
            continue

        adapter = _ADAPTER_REGISTRY.get(config.target_type)
        if adapter is None:
            results.append({"target": config.target_endpoint, "success": False, "error": f"No adapter for {config.target_type}"})
            continue

        last_error = None
        for attempt in range(config.retry_policy.get("max_retries", 3) + 1):
            try:
                result = await adapter.write(action, config)
                if result.get("success"):
                    result["target"] = config.target_endpoint
                    result["attempts"] = attempt + 1
                    results.append(result)
                    break
                last_error = result.get("error")
            except Exception as e:
                last_error = str(e)[:200]

            if attempt < config.retry_policy.get("max_retries", 3):
                delay = 2 ** attempt if config.retry_policy.get("backoff") == "exponential" else 1
                import asyncio
                await asyncio.sleep(delay)
        else:
            results.append({
                "target": config.target_endpoint,
                "success": False,
                "error": last_error or "max retries exhausted",
                "attempts": config.retry_policy.get("max_retries", 3) + 1,
            })

    return results
