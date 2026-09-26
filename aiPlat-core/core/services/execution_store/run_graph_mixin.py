"""
RunGraph Mixin — authoritative execution-tree projection for ExecutionViewer.

Nodes are UPSERTed (open/close); unlike syscall_events append-only rows.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import anyio

from ._base import _json_dumps, _json_loads


class RunGraphMixin:
    """Persists run_graph_nodes + run_graph_meta."""

    async def upsert_run_graph_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a single graph node. Returns the stored row dict."""
        await self.init()
        run_id = str(node.get("run_id") or "").strip()
        node_id = str(node.get("node_id") or "").strip()
        if not run_id or not node_id:
            raise ValueError("run_id and node_id are required")

        now = float(node.get("updated_at") or time.time())
        parent_id = node.get("parent_id")
        kind = str(node.get("kind") or "default")
        name = str(node.get("name") or node_id)
        label = node.get("label")
        role = str(node.get("role") or "work")
        status = str(node.get("status") or "running")
        start_time = node.get("start_time")
        end_time = node.get("end_time")
        duration_ms = node.get("duration_ms")
        args_json = _json_dumps(node.get("args") if node.get("args") is not None else {})
        result_json = _json_dumps(node.get("result") if node.get("result") is not None else {})
        error = node.get("error")
        if error is not None and not isinstance(error, str):
            error = _json_dumps(error)
        sort_key = float(node.get("sort_key") if node.get("sort_key") is not None else (start_time or now))
        input_tokens = int(node.get("input_tokens") or 0)
        output_tokens = int(node.get("output_tokens") or 0)
        cost = float(node.get("cost") or 0.0)

        def _sync():
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO run_graph_nodes(
                      run_id, node_id, parent_id, kind, name, label, role, status,
                      start_time, end_time, duration_ms, args_json, result_json, error,
                      sort_key, input_tokens, output_tokens, cost, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, node_id) DO UPDATE SET
                      parent_id=COALESCE(excluded.parent_id, run_graph_nodes.parent_id),
                      kind=excluded.kind,
                      name=excluded.name,
                      label=COALESCE(excluded.label, run_graph_nodes.label),
                      role=excluded.role,
                      status=excluded.status,
                      start_time=COALESCE(excluded.start_time, run_graph_nodes.start_time),
                      end_time=COALESCE(excluded.end_time, run_graph_nodes.end_time),
                      duration_ms=COALESCE(excluded.duration_ms, run_graph_nodes.duration_ms),
                      args_json=CASE
                        WHEN excluded.args_json IS NOT NULL AND excluded.args_json NOT IN ('', '{}')
                        THEN excluded.args_json ELSE run_graph_nodes.args_json END,
                      result_json=CASE
                        WHEN excluded.result_json IS NOT NULL AND excluded.result_json NOT IN ('', '{}')
                        THEN excluded.result_json ELSE run_graph_nodes.result_json END,
                      error=COALESCE(excluded.error, run_graph_nodes.error),
                      sort_key=COALESCE(excluded.sort_key, run_graph_nodes.sort_key),
                      input_tokens=CASE
                        WHEN excluded.input_tokens > 0 THEN excluded.input_tokens
                        ELSE run_graph_nodes.input_tokens END,
                      output_tokens=CASE
                        WHEN excluded.output_tokens > 0 THEN excluded.output_tokens
                        ELSE run_graph_nodes.output_tokens END,
                      cost=CASE
                        WHEN excluded.cost > 0 THEN excluded.cost ELSE run_graph_nodes.cost END,
                      updated_at=excluded.updated_at;
                    """,
                    (
                        run_id, node_id, parent_id, kind, name, label, role, status,
                        start_time, end_time, duration_ms, args_json, result_json, error,
                        sort_key, input_tokens, output_tokens, cost, now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO run_graph_meta(run_id, status, updated_at)
                    VALUES (?, 'running', ?)
                    ON CONFLICT(run_id) DO UPDATE SET updated_at=excluded.updated_at;
                    """,
                    (run_id, now),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM run_graph_nodes WHERE run_id=? AND node_id=?",
                    (run_id, node_id),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        raw = await anyio.to_thread.run_sync(_sync)
        return self._row_to_graph_node(raw) if raw else {}

    async def get_run_graph_node(self, run_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        await self.init()

        def _sync():
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM run_graph_nodes WHERE run_id=? AND node_id=?",
                    (str(run_id), str(node_id)),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        raw = await anyio.to_thread.run_sync(_sync)
        return self._row_to_graph_node(raw) if raw else None

    async def list_run_graph_nodes(self, run_id: str) -> List[Dict[str, Any]]:
        await self.init()

        def _sync():
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM run_graph_nodes
                    WHERE run_id=?
                    ORDER BY COALESCE(sort_key, start_time, 0), node_id
                    """,
                    (str(run_id),),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

        rows = await anyio.to_thread.run_sync(_sync)
        return [self._row_to_graph_node(r) for r in rows]

    async def set_run_graph_status(self, run_id: str, status: str) -> None:
        await self.init()
        now = time.time()

        def _sync():
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO run_graph_meta(run_id, status, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                      status=excluded.status,
                      updated_at=excluded.updated_at;
                    """,
                    (str(run_id), str(status), now),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def get_run_graph_status(self, run_id: str) -> Optional[str]:
        await self.init()

        def _sync():
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT status FROM run_graph_meta WHERE run_id=?",
                    (str(run_id),),
                ).fetchone()
                return str(row["status"]) if row else None
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def close_running_run_graph_nodes(
        self,
        run_id: str,
        *,
        status: str = "ok",
        end_time: Optional[float] = None,
    ) -> List[str]:
        """Force-close all still-running nodes. Returns closed node_ids."""
        await self.init()
        end = float(end_time or time.time())
        st = "ok" if status in ("ok", "success", "completed", "done") else "error"

        def _sync():
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT node_id, start_time FROM run_graph_nodes WHERE run_id=? AND status=?",
                    (str(run_id), "running"),
                ).fetchall()
                closed: List[str] = []
                for r in rows:
                    nid = str(r["node_id"])
                    start = r["start_time"]
                    dur = (end - float(start)) * 1000.0 if start is not None else None
                    conn.execute(
                        """
                        UPDATE run_graph_nodes
                        SET status=?, end_time=?, duration_ms=COALESCE(?, duration_ms), updated_at=?
                        WHERE run_id=? AND node_id=?
                        """,
                        (st, end, dur, end, str(run_id), nid),
                    )
                    closed.append(nid)
                conn.commit()
                return closed
            finally:
                conn.close()

        try:
            return await anyio.to_thread.run_sync(_sync)
        except Exception:
            logging.getLogger(__name__).debug("close_running_run_graph_nodes failed", exc_info=True)
            return []

    @staticmethod
    def _row_to_graph_node(row: Dict[str, Any]) -> Dict[str, Any]:
        if not row:
            return {}
        return {
            "run_id": row.get("run_id"),
            "node_id": row.get("node_id"),
            "parent_id": row.get("parent_id"),
            "kind": row.get("kind"),
            "name": row.get("name"),
            "label": row.get("label"),
            "role": row.get("role") or "work",
            "status": row.get("status"),
            "start_time": row.get("start_time"),
            "end_time": row.get("end_time"),
            "duration_ms": row.get("duration_ms"),
            "args": _json_loads(row.get("args_json")) or {},
            "result": _json_loads(row.get("result_json")) or {},
            "error": row.get("error"),
            "sort_key": row.get("sort_key"),
            "input_tokens": int(row.get("input_tokens") or 0),
            "output_tokens": int(row.get("output_tokens") or 0),
            "cost": float(row.get("cost") or 0.0),
            "updated_at": row.get("updated_at"),
        }
