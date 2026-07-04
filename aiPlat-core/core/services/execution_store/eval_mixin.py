"""
EvalMixin — extracted from ExecutionStore deploy_mixin.py.

Entity-specific CRUD methods.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
import uuid
from ._base import _json_dumps, _json_loads


class EvalMixin:
    """Extracted from ExecutionStore."""
    # ==================== Skill Evals (Trigger/Quality) ====================

    async def upsert_skill_eval_suite(
        self,
        *,
        suite_id: str,
        tenant_id: Optional[str],
        scope: str,
        target_skill_id: str,
        name: str,
        description: Optional[str],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect(); conn.row_factory = sqlite3.Row
            conn.row_factory = sqlite3.Row
            now = float(time.time())
            try:
                row = conn.execute("SELECT suite_id FROM skill_eval_suites WHERE suite_id=?;", (str(suite_id),)).fetchone()
                if row:
                    conn.execute(
                        "UPDATE skill_eval_suites SET tenant_id=?, scope=?, target_skill_id=?, name=?, description=?, config_json=?, updated_at=? WHERE suite_id=?;",
                        (
                            str(tenant_id) if tenant_id else None,
                            str(scope),
                            str(target_skill_id),
                            str(name),
                            str(description or ""),
                            _json_dumps(config or {}),
                            now,
                            str(suite_id),
                        ),
                    )
                else:
                    conn.execute(
                        "INSERT INTO skill_eval_suites(suite_id, tenant_id, scope, target_skill_id, name, description, config_json, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?);",
                        (
                            str(suite_id),
                            str(tenant_id) if tenant_id else None,
                            str(scope),
                            str(target_skill_id),
                            str(name),
                            str(description or ""),
                            _json_dumps(config or {}),
                            now,
                            now,
                        ),
                    )
                conn.commit()
                out = conn.execute("SELECT * FROM skill_eval_suites WHERE suite_id=?;", (str(suite_id),)).fetchone()
                return dict(out) if out else {"suite_id": suite_id}
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "config": _json_loads(row.get("config_json")) or {}}

    async def get_skill_eval_suite(self, *, suite_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect(); conn.row_factory = sqlite3.Row
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM skill_eval_suites WHERE suite_id=?;", (str(suite_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {**row, "config": _json_loads(row.get("config_json")) or {}}

    async def list_skill_eval_suites(self, *, tenant_id: Optional[str] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect(); conn.row_factory = sqlite3.Row
            conn.row_factory = sqlite3.Row
            try:
                where = ""
                params: list = []
                if tenant_id:
                    where = "WHERE tenant_id=?"
                    params.append(str(tenant_id))
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM skill_eval_suites {where};", tuple(params)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM skill_eval_suites {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    tuple(params + [int(limit), int(offset)]),
                ).fetchall()
                items = [dict(r) for r in rows]
                return {"items": items, "total": total, "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        out_items = []
        for it in res.get("items") or []:
            out_items.append({**it, "config": _json_loads(it.get("config_json")) or {}})
        return {**res, "items": out_items}

    async def delete_skill_eval_suite(self, *, suite_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect(); conn.row_factory = sqlite3.Row
            try:
                cur = conn.execute("DELETE FROM skill_eval_suites WHERE suite_id=?;", (str(suite_id),))
                conn.commit()
                return (cur.rowcount or 0) > 0
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def upsert_skill_eval_run(
        self,
        *,
        run_id: str,
        suite_id: str,
        tenant_id: Optional[str],
        mode: Optional[str],
        status: str,
        metrics: Optional[Dict[str, Any]],
        error: Optional[str],
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect(); conn.row_factory = sqlite3.Row
            conn.row_factory = sqlite3.Row
            now = float(time.time())
            try:
                row = conn.execute("SELECT run_id FROM skill_eval_runs WHERE run_id=?;", (str(run_id),)).fetchone()
                if row:
                    conn.execute(
                        "UPDATE skill_eval_runs SET suite_id=?, tenant_id=?, mode=?, status=?, metrics_json=?, error=?, updated_at=? WHERE run_id=?;",
                        (
                            str(suite_id),
                            str(tenant_id) if tenant_id else None,
                            str(mode or ""),
                            str(status),
                            _json_dumps(metrics) if metrics is not None else None,
                            str(error) if error else None,
                            now,
                            str(run_id),
                        ),
                    )
                else:
                    conn.execute(
                        "INSERT INTO skill_eval_runs(run_id, suite_id, tenant_id, mode, status, metrics_json, error, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?);",
                        (
                            str(run_id),
                            str(suite_id),
                            str(tenant_id) if tenant_id else None,
                            str(mode or ""),
                            str(status),
                            _json_dumps(metrics) if metrics is not None else None,
                            str(error) if error else None,
                            now,
                            now,
                        ),
                    )
                conn.commit()
                out = conn.execute("SELECT * FROM skill_eval_runs WHERE run_id=?;", (str(run_id),)).fetchone()
                return dict(out) if out else {"run_id": run_id}
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "metrics": _json_loads(row.get("metrics_json")) if isinstance(row.get("metrics_json"), str) else None}

    async def get_skill_eval_run(self, *, run_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect(); conn.row_factory = sqlite3.Row
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM skill_eval_runs WHERE run_id=?;", (str(run_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {**row, "metrics": _json_loads(row.get("metrics_json")) if isinstance(row.get("metrics_json"), str) else None}

    async def add_skill_eval_result(
        self,
        *,
        run_id: str,
        query_index: int,
        query_text: str,
        expected: str,
        selected_kind: str,
        selected_skill_id: str,
        selected_score: float,
        candidates: List[Dict[str, Any]],
        ok: bool,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect(); conn.row_factory = sqlite3.Row
            conn.row_factory = sqlite3.Row
            now = float(time.time())
            try:
                _id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO skill_eval_results(
                      id, run_id, query_index, query_text, expected, selected_kind, selected_skill_id, selected_score, candidates_json, ok, created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?);
                    """,
                    (
                        _id,
                        str(run_id),
                        int(query_index),
                        str(query_text),
                        str(expected),
                        str(selected_kind),
                        str(selected_skill_id),
                        float(selected_score),
                        _json_dumps(candidates or []),
                        1 if ok else 0,
                        now,
                    ),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM skill_eval_results WHERE id=?;", (_id,)).fetchone()
                return dict(row) if row else {"id": _id}
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "candidates": _json_loads(row.get("candidates_json")) if isinstance(row.get("candidates_json"), str) else []}

    async def list_skill_eval_results(self, *, run_id: str, limit: int = 200, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect(); conn.row_factory = sqlite3.Row
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute("SELECT COUNT(1) AS c FROM skill_eval_results WHERE run_id=?;", (str(run_id),)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    "SELECT * FROM skill_eval_results WHERE run_id=? ORDER BY query_index ASC LIMIT ? OFFSET ?;",
                    (str(run_id), int(limit), int(offset)),
                ).fetchall()
                items = [dict(r) for r in rows]
                return {"items": items, "total": total, "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        out_items = []
        for it in res.get("items") or []:
            out_items.append({**it, "candidates": _json_loads(it.get("candidates_json")) if isinstance(it.get("candidates_json"), str) else []})
        return {**res, "items": out_items}


