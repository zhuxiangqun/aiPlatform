"""
ReleaseMixin — extracted from ExecutionStore deploy_mixin.py.

Entity-specific CRUD methods.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
import uuid
from ._base import _json_dumps, _json_loads


class ReleaseMixin:
    """Extracted from ExecutionStore."""
    # ==================== Release Rollouts / Metrics (PR-10) ====================

    async def upsert_release_rollout(
        self,
        *,
        tenant_id: Optional[str],
        target_type: str,
        target_id: str,
        candidate_id: str,
        mode: str = "percentage",
        percentage: Optional[int] = None,
        include_actor_ids: Optional[List[str]] = None,
        exclude_actor_ids: Optional[List[str]] = None,
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = float(time.time())
            rec = {
                "tenant_id": str(tenant_id or ""),
                "target_type": str(target_type),
                "target_id": str(target_id),
                "candidate_id": str(candidate_id),
                "mode": str(mode or "percentage"),
                "percentage": int(percentage) if percentage is not None else None,
                "include_actor_ids_json": _json_dumps(include_actor_ids or []),
                "exclude_actor_ids_json": _json_dumps(exclude_actor_ids or []),
                "enabled": 1 if bool(enabled) else 0,
                "metadata_json": _json_dumps(metadata or {}),
                "created_at": now,
                "updated_at": now,
            }
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO release_rollouts(
                      tenant_id, target_type, target_id, candidate_id, mode, percentage,
                      include_actor_ids_json, exclude_actor_ids_json, enabled, metadata_json,
                      created_at, updated_at
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(tenant_id, target_type, target_id) DO UPDATE SET
                      candidate_id=excluded.candidate_id,
                      mode=excluded.mode,
                      percentage=excluded.percentage,
                      include_actor_ids_json=excluded.include_actor_ids_json,
                      exclude_actor_ids_json=excluded.exclude_actor_ids_json,
                      enabled=excluded.enabled,
                      metadata_json=excluded.metadata_json,
                      updated_at=excluded.updated_at;
                    """,
                    (
                        rec["tenant_id"],
                        rec["target_type"],
                        rec["target_id"],
                        rec["candidate_id"],
                        rec["mode"],
                        rec["percentage"],
                        rec["include_actor_ids_json"],
                        rec["exclude_actor_ids_json"],
                        rec["enabled"],
                        rec["metadata_json"],
                        rec["created_at"],
                        rec["updated_at"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            **row,
            "include_actor_ids": _json_loads(row.get("include_actor_ids_json")) or [],
            "exclude_actor_ids": _json_loads(row.get("exclude_actor_ids_json")) or [],
            "metadata": _json_loads(row.get("metadata_json")) or {},
        }

    async def get_release_rollout(self, *, tenant_id: Optional[str], target_type: str, target_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM release_rollouts WHERE tenant_id=? AND target_type=? AND target_id=?",
                    (str(tenant_id or ""), str(target_type), str(target_id)),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {
            **row,
            "include_actor_ids": _json_loads(row.get("include_actor_ids_json")) or [],
            "exclude_actor_ids": _json_loads(row.get("exclude_actor_ids_json")) or [],
            "metadata": _json_loads(row.get("metadata_json")) or {},
        }

    async def list_release_rollouts(
        self,
        *,
        tenant_id: Optional[str],
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses = ["tenant_id=?"]
                params: List[Any] = [str(tenant_id or "")]
                if target_type:
                    clauses.append("target_type=?")
                    params.append(str(target_type))
                if target_id:
                    clauses.append("target_id=?")
                    params.append(str(target_id))
                where = "WHERE " + " AND ".join(clauses)
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM release_rollouts {where};", tuple(params)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM release_rollouts {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    tuple(params + [int(limit), int(offset)]),
                ).fetchall()
                items = []
                for r in rows:
                    d = dict(r)
                    d["include_actor_ids"] = _json_loads(d.get("include_actor_ids_json")) or []
                    d["exclude_actor_ids"] = _json_loads(d.get("exclude_actor_ids_json")) or []
                    d["metadata"] = _json_loads(d.get("metadata_json")) or {}
                    items.append(d)
                return {"items": items, "total": total, "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def delete_release_rollout(self, *, tenant_id: Optional[str], target_type: str, target_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM release_rollouts WHERE tenant_id=? AND target_type=? AND target_id=?",
                    (str(tenant_id or ""), str(target_type), str(target_id)),
                )
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    async def add_release_metric_snapshot(
        self,
        *,
        tenant_id: Optional[str],
        candidate_id: str,
        metric_key: str,
        value: float,
        window_start: Optional[float] = None,
        window_end: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = float(time.time())
            sid = f"rms-{uuid.uuid4().hex[:12]}"
            rec = {
                "id": sid,
                "tenant_id": str(tenant_id or ""),
                "candidate_id": str(candidate_id),
                "metric_key": str(metric_key),
                "value": float(value),
                "window_start": float(window_start) if window_start is not None else None,
                "window_end": float(window_end) if window_end is not None else None,
                "metadata_json": _json_dumps(metadata or {}),
                "created_at": now,
            }
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO release_metrics_snapshots(
                      id, tenant_id, candidate_id, metric_key, value, window_start, window_end, metadata_json, created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?);
                    """,
                    (
                        rec["id"],
                        rec["tenant_id"],
                        rec["candidate_id"],
                        rec["metric_key"],
                        rec["value"],
                        rec["window_start"],
                        rec["window_end"],
                        rec["metadata_json"],
                        rec["created_at"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def list_release_metric_snapshots(
        self,
        *,
        tenant_id: Optional[str],
        candidate_id: str,
        metric_key: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses = ["tenant_id=?", "candidate_id=?"]
                params: List[Any] = [str(tenant_id or ""), str(candidate_id)]
                if metric_key:
                    clauses.append("metric_key=?")
                    params.append(str(metric_key))
                where = "WHERE " + " AND ".join(clauses)
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM release_metrics_snapshots {where};", tuple(params)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM release_metrics_snapshots {where} ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    tuple(params + [int(limit), int(offset)]),
                ).fetchall()
                items = []
                for r in rows:
                    d = dict(r)
                    d["metadata"] = _json_loads(d.get("metadata_json")) or {}
                    items.append(d)
                return {"items": items, "total": total, "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

