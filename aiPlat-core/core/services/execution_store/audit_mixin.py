"""
AuditMixin — extracted from ExecutionStore events_mixin.py.

Auto-generated via Mixin split. Contains entity-specific CRUD methods.

# DEPRECATED: concrete tenant DDL/CRUD migrate to platform layer (P0-A3)
P0-A3 (2026-08): tenant_policies CRUD moved to platform TenantStore
(aiPlat-platform/tenants/tenant_store.py). This mixin keeps audit_logs
(execution infrastructure).
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
from ._base import _json_dumps, _json_loads


class AuditMixin:
    """Extracted from ExecutionStore."""
    # ==================== Audit Logs (enterprise governance) ====================

    async def add_audit_log(
        self,
        *,
        action: str,
        status: Optional[str] = None,
        tenant_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        request_id: Optional[str] = None,
        change_id: Optional[str] = None,
        run_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
        created_at: Optional[float] = None,
    ) -> None:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> None:
            import hashlib as _hashlib
            conn = self._connect()
            # Manage the transaction explicitly so (read last hash → insert) is atomic
            # under concurrency: BEGIN IMMEDIATE takes a write lock up-front, serializing
            # writers and preventing chain forks.
            conn.isolation_level = None
            try:
                ts = float(created_at if created_at is not None else time.time())
                detail_str = _json_dumps(detail or {})
                conn.execute("BEGIN IMMEDIATE;")
                row = conn.execute(
                    "SELECT entry_hash FROM audit_logs WHERE tenant_id IS ? "
                    "ORDER BY id DESC LIMIT 1;",
                    (tenant_id,),
                ).fetchone()
                prev_hash = row[0] if (row and row[0]) else ""
                # Tamper-evidence: per-tenant hash chain over the immutable entry fields.
                canonical = "|".join(str(x) for x in (
                    tenant_id, actor_id, actor_role, str(action), resource_type, resource_id,
                    request_id, change_id, run_id, trace_id, status, detail_str, ts,
                ))
                entry_hash = _hashlib.sha256(
                    (prev_hash + "|" + canonical).encode("utf-8")
                ).hexdigest()
                conn.execute(
                    """
                    INSERT INTO audit_logs(
                      tenant_id, actor_id, actor_role, action, resource_type, resource_id,
                      request_id, change_id, run_id, trace_id, status, detail_json, created_at,
                      prev_hash, entry_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        tenant_id,
                        actor_id,
                        actor_role,
                        str(action),
                        resource_type,
                        resource_id,
                        request_id,
                        change_id,
                        run_id,
                        trace_id,
                        status,
                        detail_str,
                        ts,
                        (prev_hash or None),
                        entry_hash,
                    ),
                )
                conn.execute("COMMIT;")
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def verify_audit_chain(self, *, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Verify the tamper-evidence hash chain for a tenant's audit log.

        Recomputes each entry_hash from the stored immutable fields + the prior row's
        hash and compares to the stored hash. Any mismatch means a row was modified,
        deleted, or inserted out of band (tampering). Legacy rows with NULL entry_hash
        (written before the v51 migration) are counted as 'unverifiable' and skipped.

        Returns: {ok, total, verified, unverifiable, broken_at}
          - ok: True iff every hashed row verifies
          - broken_at: id of the first row whose recomputed hash mismatches (None if ok)
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            import hashlib as _hashlib
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT id, tenant_id, actor_id, actor_role, action, resource_type, "
                    "resource_id, request_id, change_id, run_id, trace_id, status, detail_json, "
                    "created_at, prev_hash, entry_hash FROM audit_logs "
                    "WHERE tenant_id IS ? ORDER BY id ASC;",
                    (tenant_id,),
                ).fetchall()
            finally:
                conn.close()

            prev = ""
            verified = 0
            unverifiable = 0
            for r in rows:
                (rid, t, aid, arole, action, rtype, rid_res, req, chg, run, trace,
                 status, detail_json, ts, prev_hash, entry_hash) = r
                if not entry_hash:
                    unverifiable += 1
                    prev = ""  # write path treated a NULL previous hash as ""
                    continue
                canonical = "|".join(str(x) for x in (
                    t, aid, arole, str(action), rtype, rid_res, req, chg, run, trace,
                    status, detail_json, float(ts),
                ))
                expected = _hashlib.sha256(
                    (prev + "|" + canonical).encode("utf-8")
                ).hexdigest()
                if expected != entry_hash:
                    return {"ok": False, "total": len(rows), "verified": verified,
                            "unverifiable": unverifiable, "broken_at": rid}
                verified += 1
                prev = entry_hash
            return {"ok": True, "total": len(rows), "verified": verified,
                    "unverifiable": unverifiable, "broken_at": None}

        return await anyio.to_thread.run_sync(_sync)

    async def list_audit_logs(
        self,
        *,
        tenant_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        request_id: Optional[str] = None,
        change_id: Optional[str] = None,
        run_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        status: Optional[str] = None,
        created_after: Optional[float] = None,
        created_before: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses = ["1=1"]
                params: list = []
                if tenant_id:
                    clauses.append("tenant_id=?")
                    params.append(str(tenant_id))
                if actor_id:
                    clauses.append("actor_id=?")
                    params.append(str(actor_id))
                if action:
                    clauses.append("action=?")
                    params.append(str(action))
                if resource_type:
                    clauses.append("resource_type=?")
                    params.append(str(resource_type))
                if resource_id:
                    clauses.append("resource_id=?")
                    params.append(str(resource_id))
                if request_id:
                    clauses.append("request_id=?")
                    params.append(str(request_id))
                if change_id:
                    clauses.append("change_id=?")
                    params.append(str(change_id))
                if run_id:
                    clauses.append("run_id=?")
                    params.append(str(run_id))
                if trace_id:
                    clauses.append("trace_id=?")
                    params.append(str(trace_id))
                if status:
                    clauses.append("status=?")
                    params.append(str(status))
                if created_after is not None:
                    clauses.append("created_at>=?")
                    params.append(float(created_after))
                if created_before is not None:
                    clauses.append("created_at<=?")
                    params.append(float(created_before))
                where = " AND ".join(clauses)
                total = conn.execute(f"SELECT COUNT(1) FROM audit_logs WHERE {where}", params).fetchone()[0]
                rows = conn.execute(
                    f"""
                    SELECT id, tenant_id, actor_id, actor_role, action, resource_type, resource_id,
                           request_id, change_id, run_id, trace_id, status, detail_json, created_at
                    FROM audit_logs
                    WHERE {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    [*params, int(limit), int(offset)],
                ).fetchall()
                items = []
                for r in rows:
                    items.append(
                        {
                            "id": r["id"],
                            "tenant_id": r["tenant_id"],
                            "actor_id": r["actor_id"],
                            "actor_role": r["actor_role"],
                            "action": r["action"],
                            "resource_type": r["resource_type"],
                            "resource_id": r["resource_id"],
                            "request_id": r["request_id"],
                            "change_id": r["change_id"],
                            "run_id": r["run_id"],
                            "trace_id": r["trace_id"],
                            "status": r["status"],
                            "detail": _json_loads(r["detail_json"]) or {},
                            "created_at": r["created_at"],
                        }
                    )
                return {"items": items, "total": int(total), "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)
