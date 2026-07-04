"""
OnboardMixin — extracted from ExecutionStore deploy_mixin.py.

Entity-specific CRUD methods.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
import uuid
from ._base import _json_dumps, _json_loads


class OnboardMixin:
    """Extracted from ExecutionStore."""
    # ==================== Onboarding Evidence (Wizard) ====================

    async def create_onboarding_evidence(
        self,
        *,
        tenant_id: Optional[str],
        step_key: str,
        action: str,
        status: str,
        input: Optional[Dict[str, Any]] = None,
        output: Optional[Dict[str, Any]] = None,
        links: Optional[Dict[str, Any]] = None,
        approval_request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = float(time.time())
            rid = str(uuid.uuid4())
            rec = {
                "id": rid,
                "tenant_id": str(tenant_id or ""),
                "step_key": str(step_key),
                "action": str(action),
                "status": str(status),
                "input_json": _json_dumps(input or {}),
                "output_json": _json_dumps(output or {}),
                "links_json": _json_dumps(links or {}),
                "approval_request_id": str(approval_request_id) if approval_request_id else None,
                "created_at": now,
            }
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO onboarding_evidence(
                      id, tenant_id, step_key, action, status, input_json, output_json, links_json, approval_request_id, created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?);
                    """,
                    (
                        rec["id"],
                        rec["tenant_id"],
                        rec["step_key"],
                        rec["action"],
                        rec["status"],
                        rec["input_json"],
                        rec["output_json"],
                        rec["links_json"],
                        rec["approval_request_id"],
                        rec["created_at"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            **row,
            "input": _json_loads(row.get("input_json")) or {},
            "output": _json_loads(row.get("output_json")) or {},
            "links": _json_loads(row.get("links_json")) or {},
        }

    async def list_onboarding_evidence(
        self,
        *,
        tenant_id: Optional[str],
        step_key: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                where = "tenant_id=?"
                args: List[Any] = [str(tenant_id or "")]
                if step_key:
                    where += " AND step_key=?"
                    args.append(str(step_key))
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM onboarding_evidence WHERE {where}", tuple(args)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"""
                    SELECT * FROM onboarding_evidence
                    WHERE {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    tuple(args + [int(limit), int(offset)]),
                ).fetchall()
                items = []
                for r in rows:
                    d = dict(r)
                    d["input"] = _json_loads(d.get("input_json")) or {}
                    d["output"] = _json_loads(d.get("output_json")) or {}
                    d["links"] = _json_loads(d.get("links_json")) or {}
                    items.append(d)
                return {"items": items, "total": total, "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_onboarding_evidence(self, *, tenant_id: Optional[str], evidence_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM onboarding_evidence WHERE tenant_id=? AND id=?",
                    (str(tenant_id or ""), str(evidence_id)),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {
            **row,
            "input": _json_loads(row.get("input_json")) or {},
            "output": _json_loads(row.get("output_json")) or {},
            "links": _json_loads(row.get("links_json")) or {},
        }

    async def update_onboarding_evidence_links(self, *, tenant_id: Optional[str], evidence_id: str, links: Dict[str, Any]) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE onboarding_evidence SET links_json=? WHERE tenant_id=? AND id=?;",
                    (_json_dumps(links or {}), str(tenant_id or ""), str(evidence_id)),
                )
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    async def get_plugin(self, *, tenant_id: Optional[str], plugin_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM plugins WHERE tenant_id=? AND plugin_id=?",
                    (str(tenant_id or ""), str(plugin_id)),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {**row, "manifest": _json_loads(row.get("manifest_json")) or {}, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def list_plugins(self, *, tenant_id: Optional[str], limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute("SELECT COUNT(1) AS c FROM plugins WHERE tenant_id=?", (str(tenant_id or ""),)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    "SELECT * FROM plugins WHERE tenant_id=? ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    (str(tenant_id or ""), int(limit), int(offset)),
                ).fetchall()
                items = []
                for r in rows:
                    d = dict(r)
                    d["manifest"] = _json_loads(d.get("manifest_json")) or {}
                    d["metadata"] = _json_loads(d.get("metadata_json")) or {}
                    items.append(d)
                return {"items": items, "total": total, "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def set_plugin_enabled(self, *, tenant_id: Optional[str], plugin_id: str, enabled: bool) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            now = float(time.time())
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE plugins SET enabled=?, updated_at=? WHERE tenant_id=? AND plugin_id=?;",
                    (1 if bool(enabled) else 0, now, str(tenant_id or ""), str(plugin_id)),
                )
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    async def create_plugin_run(
        self,
        *,
        run_id: str,
        tenant_id: Optional[str],
        plugin_id: str,
        status: str,
        trace_id: Optional[str] = None,
        approval_request_id: Optional[str] = None,
        input: Optional[Dict[str, Any]] = None,
        output: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = float(time.time())
            rec = {
                "run_id": str(run_id),
                "tenant_id": str(tenant_id or ""),
                "plugin_id": str(plugin_id),
                "status": str(status),
                "trace_id": str(trace_id) if trace_id else None,
                "approval_request_id": str(approval_request_id) if approval_request_id else None,
                "input_json": _json_dumps(input or {}),
                "output_json": _json_dumps(output or {}),
                "error": str(error) if error else None,
                "created_at": now,
                "updated_at": now,
            }
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO plugin_runs(
                      run_id, tenant_id, plugin_id, status, trace_id, approval_request_id, input_json, output_json, error, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(run_id) DO UPDATE SET
                      status=excluded.status,
                      trace_id=excluded.trace_id,
                      approval_request_id=excluded.approval_request_id,
                      input_json=excluded.input_json,
                      output_json=excluded.output_json,
                      error=excluded.error,
                      updated_at=excluded.updated_at;
                    """,
                    (
                        rec["run_id"],
                        rec["tenant_id"],
                        rec["plugin_id"],
                        rec["status"],
                        rec["trace_id"],
                        rec["approval_request_id"],
                        rec["input_json"],
                        rec["output_json"],
                        rec["error"],
                        rec["created_at"],
                        rec["updated_at"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "input": _json_loads(row.get("input_json")) or {}, "output": _json_loads(row.get("output_json")) or {}}

