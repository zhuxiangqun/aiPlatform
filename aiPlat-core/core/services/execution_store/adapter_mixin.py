"""
AdapterMixin — extracted from ExecutionStore adapter_mixin.py.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
import uuid
from ._base import _json_dumps, _json_loads


class AdapterMixin:
    """Extracted from ExecutionStore."""
    # Adapters Registry (persist LLM adapter configs)
    # ---------------------------------------------------------------------

    async def upsert_adapter(self, record: Dict[str, Any]) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = dict(record or {})
            adapter_id = str(rec.get("adapter_id") or rec.get("id") or "")
            if not adapter_id:
                adapter_id = f"adapter-{uuid.uuid4().hex[:8]}"
            rec["adapter_id"] = adapter_id
            rec.setdefault("status", "active")
            rec.setdefault("created_at", now)
            rec["updated_at"] = now

            # Encrypt api_key at rest when configured.
            api_key_plain = str(rec.get("api_key") or "")
            api_key_enc = None
            api_key_kid = None
            try:
                from core.harness.infrastructure.crypto.secretbox import encrypt_str, is_configured

                if api_key_plain and is_configured():
                    api_key_enc = encrypt_str(api_key_plain)
                    api_key_kid = "fernet:v1"
                    api_key_plain = ""  # avoid storing plaintext
            except Exception as e:
                # fail-open: keep legacy plaintext
                logging.debug(str(e), exc_info=True)

            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
                    """
                    INSERT INTO adapters(
                      adapter_id, name, provider, description, status,
                      api_key, api_base_url, organization_id,
                      api_key_enc, api_key_kid,
                      models_json, rate_limit_json, retry_config_json, metadata_json,
                      created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(adapter_id) DO UPDATE SET
                      name=excluded.name,
                      provider=excluded.provider,
                      description=excluded.description,
                      status=excluded.status,
                      api_key=excluded.api_key,
                      api_key_enc=excluded.api_key_enc,
                      api_key_kid=excluded.api_key_kid,
                      api_base_url=excluded.api_base_url,
                      organization_id=excluded.organization_id,
                      models_json=excluded.models_json,
                      rate_limit_json=excluded.rate_limit_json,
                      retry_config_json=excluded.retry_config_json,
                      metadata_json=excluded.metadata_json,
                      updated_at=excluded.updated_at;
                    """,
                    (
                        adapter_id,
                        str(rec.get("name") or ""),
                        str(rec.get("provider") or ""),
                        str(rec.get("description") or ""),
                        str(rec.get("status") or "active"),
                        str(api_key_plain or ""),
                        str(rec.get("api_base_url") or ""),
                        str(rec.get("organization_id") or "") or None,
                        api_key_enc,
                        api_key_kid,
                        _json_dumps(rec.get("models") or []),
                        _json_dumps(rec.get("rate_limit") or {}),
                        _json_dumps(rec.get("retry_config") or {}),
                        _json_dumps(rec.get("metadata") or {}),
                        float(rec.get("created_at") or now),
                        float(now),
                    ),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM adapters WHERE adapter_id=?;", (adapter_id,)).fetchone()
                return dict(row) if row else {}
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        api_key = row.get("api_key")
        try:
            from core.harness.infrastructure.crypto.secretbox import decrypt_str, is_configured

            if row.get("api_key_enc") and is_configured():
                api_key = decrypt_str(row.get("api_key_enc"))
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        return {
            "adapter_id": row.get("adapter_id"),
            "name": row.get("name"),
            "provider": row.get("provider"),
            "description": row.get("description"),
            "status": row.get("status"),
            "api_key": api_key,
            "api_base_url": row.get("api_base_url"),
            "organization_id": row.get("organization_id"),
            "models": _json_loads(row.get("models_json")) or [],
            "rate_limit": _json_loads(row.get("rate_limit_json")) or {},
            "retry_config": _json_loads(row.get("retry_config_json")) or {},
            "metadata": _json_loads(row.get("metadata_json")) or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def get_adapter(self, adapter_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM adapters WHERE adapter_id=?;", (str(adapter_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        api_key = row.get("api_key")
        try:
            from core.harness.infrastructure.crypto.secretbox import decrypt_str, is_configured

            if row.get("api_key_enc") and is_configured():
                api_key = decrypt_str(row.get("api_key_enc"))
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        return {
            "adapter_id": row.get("adapter_id"),
            "name": row.get("name"),
            "provider": row.get("provider"),
            "description": row.get("description"),
            "status": row.get("status"),
            "api_key": api_key,
            "api_base_url": row.get("api_base_url"),
            "organization_id": row.get("organization_id"),
            "models": _json_loads(row.get("models_json")) or [],
            "rate_limit": _json_loads(row.get("rate_limit_json")) or {},
            "retry_config": _json_loads(row.get("retry_config_json")) or {},
            "metadata": _json_loads(row.get("metadata_json")) or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def list_adapters(self, *, provider: Optional[str] = None, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: List[Any] = []
                if provider:
                    clauses.append("provider=?")
                    params.append(str(provider))
                if status:
                    clauses.append("status=?")
                    params.append(str(status))
                where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM adapters {where};", params).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM adapters {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    [*params, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append(
                {
                    "adapter_id": r.get("adapter_id"),
                    "name": r.get("name"),
                    "provider": r.get("provider"),
                    "description": r.get("description"),
                    "status": r.get("status"),
                    "api_base_url": r.get("api_base_url"),
                    "models": _json_loads(r.get("models_json")) or [],
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at"),
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def delete_adapter(self, adapter_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM adapters WHERE adapter_id=?;", (str(adapter_id),))
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_adapter_secrets_status(self) -> Dict[str, Any]:
        """
        Returns counts of encrypted/plaintext adapter secrets stored at rest.
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                total = int(conn.execute("SELECT COUNT(1) AS c FROM adapters;").fetchone()["c"])
                enc = int(conn.execute("SELECT COUNT(1) AS c FROM adapters WHERE api_key_enc IS NOT NULL AND api_key_enc != '';").fetchone()["c"])
                plain = int(conn.execute("SELECT COUNT(1) AS c FROM adapters WHERE api_key IS NOT NULL AND api_key != '';").fetchone()["c"])
                return {"total": total, "encrypted": enc, "plaintext": plain}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def migrate_adapter_secrets_to_encrypted(self) -> Dict[str, Any]:
        """
        Encrypt any legacy plaintext api_key into api_key_enc and clear api_key.
        Requires AIPLAT_SECRET_KEY configured; otherwise raises.
        """
        await self.init()
        db_path = self._config.db_path

        from core.harness.infrastructure.crypto.secretbox import encrypt_str, is_configured

        if not is_configured():
            raise RuntimeError("AIPLAT_SECRET_KEY is not set")

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            updated = 0
            skipped = 0
            try:
                rows = conn.execute(
                    "SELECT adapter_id, api_key, api_key_enc FROM adapters WHERE api_key IS NOT NULL AND api_key != '';"
                ).fetchall()
                for r in rows:
                    aid = r["adapter_id"]
                    api_key = r["api_key"] or ""
                    api_key_enc = r["api_key_enc"]
                    if api_key_enc:
                        skipped += 1
                        continue
                    enc = encrypt_str(str(api_key))
                    conn.execute(
                        "UPDATE adapters SET api_key_enc=?, api_key_kid=?, api_key='' WHERE adapter_id=?;",
                        (enc, "fernet:v1", str(aid)),
                    )
                    updated += 1
                conn.commit()
            finally:
                conn.close()
            return {"updated": updated, "skipped": skipped, "scanned": len(rows)}

        return await anyio.to_thread.run_sync(_sync)

    # ---------------------------------------------------------------------
    # Global settings
    # ---------------------------------------------------------------------

