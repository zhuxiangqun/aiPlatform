"""
PlatformDB — unified SQLite persistence for platform data.

Replaces in-memory-only storage for tenants, API keys, quotas, and billing.
Uses read-through cache pattern: memory is primary, SQLite is persisted backing.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ensure_db_path() -> str:
    db_path = os.getenv(
        "AIPLAT_PLATFORM_DB_PATH",
        str(Path.home() / ".aiplat" / "platform.sqlite3"),
    )
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return db_path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    plan TEXT DEFAULT 'free',
    status TEXT DEFAULT 'active',
    gpu_quota INTEGER DEFAULT 0,
    storage_quota_mb INTEGER DEFAULT 0,
    retention_days INTEGER DEFAULT 30,
    allow_public_skill_deployment INTEGER DEFAULT 1,
    allow_external_tools INTEGER DEFAULT 0,
    enable_mcp INTEGER DEFAULT 1,
    enable_approval_required INTEGER DEFAULT 0,
    verification_token TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_hash TEXT PRIMARY KEY,
    key_prefix TEXT DEFAULT '',
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    app_id TEXT DEFAULT '',
    permissions TEXT DEFAULT '[]',
    expires_at TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS quotas (
    tenant_id TEXT PRIMARY KEY,
    max_agents INTEGER DEFAULT 10,
    max_skills INTEGER DEFAULT 50,
    max_api_keys INTEGER DEFAULT 10,
    max_concurrent_runs INTEGER DEFAULT 5,
    monthly_tokens INTEGER DEFAULT 1000000,
    used_agents INTEGER DEFAULT 0,
    used_skills INTEGER DEFAULT 0,
    used_api_keys INTEGER DEFAULT 0,
    used_concurrent_runs INTEGER DEFAULT 0,
    used_monthly_tokens INTEGER DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS billing_records (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    capability_type TEXT DEFAULT '',
    tokens_used INTEGER DEFAULT 0,
    cost_cents INTEGER DEFAULT 0,
    recorded_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id);
CREATE INDEX IF NOT EXISTS idx_billing_tenant_date ON billing_records(tenant_id, recorded_at);
"""


class PlatformDB:
    """Unified SQLite persistence for platform data."""

    _instance: Optional[PlatformDB] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._db_path = _ensure_db_path()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    # ── Tenant CRUD ──────────────────────────────────────

    def upsert_tenant(self, data: Dict[str, Any]) -> None:
        """Insert or update a tenant."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO tenants
               (tenant_id, name, plan, status, gpu_quota, storage_quota_mb,
                retention_days, allow_public_skill_deployment, allow_external_tools,
                enable_mcp, enable_approval_required, verification_token, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM tenants WHERE tenant_id=?), ?), ?)""",
            (data["tenant_id"], data.get("name", ""), data.get("plan", "free"),
             data.get("status", "active"), data.get("gpu_quota", 0),
             data.get("storage_quota_mb", 0), data.get("retention_days", 30),
             int(data.get("allow_public_skill_deployment", True)),
             int(data.get("allow_external_tools", False)),
             int(data.get("enable_mcp", True)),
             int(data.get("enable_approval_required", False)),
             data.get("verification_token"), data["tenant_id"], now, now),
        )
        self._conn.commit()

    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM tenants WHERE tenant_id=? AND status!='deleted'",
            (tenant_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM tenants WHERE name=? AND status!='deleted'",
            (email,)
        ).fetchone()
        return dict(row) if row else None

    def list_tenants(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM tenants WHERE status=?", (status,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM tenants").fetchall()
        return [dict(r) for r in rows]

    def delete_tenant(self, tenant_id: str) -> None:
        self._conn.execute(
            "UPDATE tenants SET status='deleted', updated_at=? WHERE tenant_id=?",
            (datetime.now(timezone.utc).isoformat(), tenant_id),
        )
        self._conn.commit()

    # ── API Key CRUD ────────────────────────────────────

    def upsert_api_key(self, data: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO api_keys
               (key_hash, key_prefix, user_id, tenant_id, app_id, permissions,
                expires_at, active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM api_keys WHERE key_hash=?), ?))""",
            (data["key_hash"], data.get("key_prefix", data["key_hash"][:8]),
             data.get("user_id", ""), data.get("tenant_id", ""),
             data.get("app_id", ""), json.dumps(data.get("permissions", [])),
             data.get("expires_at"), int(data.get("active", True)),
             data["key_hash"], now),
        )
        self._conn.commit()

    def get_api_key(self, key_hash: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM api_keys WHERE key_hash=? AND active=1", (key_hash,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            d["permissions"] = json.loads(d.get("permissions", "[]"))
        except Exception:
            d["permissions"] = []
        return d

    def list_api_keys(self, tenant_id: str) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT key_hash, key_prefix, user_id, tenant_id, app_id, active, expires_at, created_at, permissions FROM api_keys WHERE tenant_id=?",
            (tenant_id,)
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d.pop("key_hash", None)
            try:
                d["permissions"] = json.loads(d.get("permissions", "[]"))
            except Exception:
                d["permissions"] = []
            result.append(d)
        return result

    def revoke_api_key(self, key_hash: str) -> bool:
        self._conn.execute(
            "UPDATE api_keys SET active=0 WHERE key_hash=?", (key_hash,)
        )
        self._conn.commit()
        return self._conn.total_changes > 0

    # ── Quota CRUD ──────────────────────────────────────

    def upsert_quota(self, data: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO quotas
               (tenant_id, max_agents, max_skills, max_api_keys, max_concurrent_runs,
                monthly_tokens, used_agents, used_skills, used_api_keys,
                used_concurrent_runs, used_monthly_tokens, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (data["tenant_id"], data.get("max_agents", 10), data.get("max_skills", 50),
             data.get("max_api_keys", 10), data.get("max_concurrent_runs", 5),
             data.get("monthly_tokens", 1000000), data.get("used_agents", 0),
             data.get("used_skills", 0), data.get("used_api_keys", 0),
             data.get("used_concurrent_runs", 0), data.get("used_monthly_tokens", 0), now),
        )
        self._conn.commit()

    def get_quota(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM quotas WHERE tenant_id=?", (tenant_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── Billing CRUD ────────────────────────────────────

    def insert_billing_record(self, data: Dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO billing_records (id, tenant_id, capability_type, tokens_used, cost_cents, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
            (data["id"], data["tenant_id"], data.get("capability_type", ""),
             data.get("tokens_used", 0), data.get("cost_cents", 0),
             data.get("recorded_at", datetime.now(timezone.utc).isoformat())),
        )
        self._conn.commit()

    def get_monthly_breakdown(self, tenant_id: str, year: int, month: int) -> List[Dict[str, Any]]:
        month_str = f"{year}-{month:02d}"
        rows = self._conn.execute(
            """SELECT capability_type, SUM(tokens_used) as tokens, SUM(cost_cents) as cost
               FROM billing_records
               WHERE tenant_id=? AND substr(recorded_at, 1, 7)=?
               GROUP BY capability_type""",
            (tenant_id, month_str),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_total_monthly_tokens(self, year: int, month: int) -> int:
        month_str = f"{year}-{month:02d}"
        row = self._conn.execute(
            "SELECT COALESCE(SUM(tokens_used), 0) FROM billing_records WHERE substr(recorded_at, 1, 7)=?",
            (month_str,),
        ).fetchone()
        return row[0] if row else 0


def get_platform_db() -> PlatformDB:
    return PlatformDB()
