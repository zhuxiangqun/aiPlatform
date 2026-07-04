"""
PromptMixin — extracted from ExecutionStore deploy_mixin.py.

Entity-specific CRUD methods.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
from ._base import _json_dumps, _json_loads


class PromptMixin:
    """Extracted from ExecutionStore."""
    # ==================== Prompt Templates (MVP) ====================

    async def upsert_prompt_template(
        self,
        *,
        template_id: str,
        name: str,
        template: str,
        metadata: Optional[Dict[str, Any]] = None,
        increment_version: bool = True,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _bump(v: str) -> str:
            try:
                parts = str(v or "1.0.0").split(".")
                parts[-1] = str(int(parts[-1]) + 1)
                return ".".join(parts)
            except Exception:
                return "1.0.1"

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            now = time.time()
            try:
                row = conn.execute("SELECT * FROM prompt_templates WHERE template_id=?;", (str(template_id),)).fetchone()
                if row:
                    cur_ver = str(row["version"])
                    new_ver = _bump(cur_ver) if increment_version else cur_ver
                    conn.execute(
                        "UPDATE prompt_templates SET name=?, template=?, version=?, metadata_json=?, updated_at=? WHERE template_id=?;",
                        (str(name), str(template), str(new_ver), json.dumps(metadata or {}), now, str(template_id)),
                    )
                else:
                    new_ver = "1.0.0"
                    conn.execute(
                        "INSERT INTO prompt_templates(template_id, name, template, version, metadata_json, created_at, updated_at) VALUES(?,?,?,?,?,?,?);",
                        (str(template_id), str(name), str(template), str(new_ver), json.dumps(metadata or {}), now, now),
                    )
                # record version snapshot (best-effort, idempotent on (template_id, version))
                try:
                    vid = f"ptv:{template_id}:{new_ver}"
                    conn.execute(
                        "INSERT OR IGNORE INTO prompt_template_versions(id, template_id, version, template, metadata_json, created_at) VALUES(?,?,?,?,?,?);",
                        (vid, str(template_id), str(new_ver), str(template), json.dumps(metadata or {}), now),
                    )
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                conn.commit()
                out = conn.execute("SELECT * FROM prompt_templates WHERE template_id=?;", (str(template_id),)).fetchone()
                return dict(out) if out else {"template_id": template_id, "name": name, "version": new_ver}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_prompt_template(self, *, template_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM prompt_templates WHERE template_id=?;", (str(template_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_prompt_template_version(self, *, template_id: str, version: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM prompt_template_versions WHERE template_id=? AND version=? LIMIT 1;",
                    (str(template_id), str(version)),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def update_prompt_template_metadata(self, *, template_id: str, patch: Dict[str, Any], merge: bool = True) -> Optional[Dict[str, Any]]:
        """
        Update prompt template metadata_json without changing template content or version.
        merge=True will shallow-merge patch into existing metadata.
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            now = time.time()
            try:
                row = conn.execute("SELECT * FROM prompt_templates WHERE template_id=?;", (str(template_id),)).fetchone()
                if not row:
                    return None
                cur_meta = _json_loads(row.get("metadata_json")) or {}
                next_meta = dict(cur_meta)
                if merge:
                    next_meta.update(patch or {})
                else:
                    next_meta = dict(patch or {})
                conn.execute(
                    "UPDATE prompt_templates SET metadata_json=?, updated_at=? WHERE template_id=?;",
                    (json.dumps(next_meta), now, str(template_id)),
                )
                conn.commit()
                out = conn.execute("SELECT * FROM prompt_templates WHERE template_id=?;", (str(template_id),)).fetchone()
                return dict(out) if out else None
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_prompt_templates(self, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                total = int(conn.execute("SELECT COUNT(1) AS c FROM prompt_templates;").fetchone()["c"])
                rows = conn.execute(
                    "SELECT * FROM prompt_templates ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    (int(limit), int(offset)),
                ).fetchall()
                return {"total": total, "items": [dict(r) for r in rows]}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_prompt_template_versions(self, *, template_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                total = int(
                    conn.execute(
                        "SELECT COUNT(1) AS c FROM prompt_template_versions WHERE template_id=?;",
                        (str(template_id),),
                    ).fetchone()["c"]
                )
                rows = conn.execute(
                    "SELECT * FROM prompt_template_versions WHERE template_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    (str(template_id), int(limit), int(offset)),
                ).fetchall()
                return {"total": total, "items": [dict(r) for r in rows]}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def rollback_prompt_template_version(self, *, template_id: str, version: str) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            now = time.time()
            try:
                vrow = conn.execute(
                    "SELECT * FROM prompt_template_versions WHERE template_id=? AND version=? LIMIT 1;",
                    (str(template_id), str(version)),
                ).fetchone()
                if not vrow:
                    raise KeyError("version_not_found")
                conn.execute(
                    "UPDATE prompt_templates SET template=?, version=?, metadata_json=?, updated_at=? WHERE template_id=?;",
                    (str(vrow["template"]), str(version), str(vrow["metadata_json"] or "{}"), now, str(template_id)),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM prompt_templates WHERE template_id=?;", (str(template_id),)).fetchone()
                return dict(row) if row else {"template_id": template_id, "version": version}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def delete_prompt_template(self, *, template_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM prompt_templates WHERE template_id=?;", (str(template_id),))
                conn.execute("DELETE FROM prompt_template_versions WHERE template_id=?;", (str(template_id),))
                conn.commit()
                return (cur.rowcount or 0) > 0
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ── Prompt App Template CRUD ────────────────────────────────────

    async def list_prompt_app_templates(self, *, limit: int = 100, offset: int = 0,
                                         category: str = "", status: str = "") -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path
        def _sync():
            conn = self._connect(); conn.row_factory = sqlite3.Row
            try:
                where = []
                params = []
                if category: where.append("category=?"); params.append(category)
                if status: where.append("status=?"); params.append(status)
                w = (" WHERE " + " AND ".join(where)) if where else ""
                total = conn.execute(f"SELECT COUNT(*) FROM prompt_app_templates{w};", params).fetchone()[0]
                rows = conn.execute(
                    f"SELECT * FROM prompt_app_templates{w} ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    params + [limit, offset]
                ).fetchall()
                items = [dict(r) if r else None for r in rows]
                return {"total": total, "items": items}
            finally:
                conn.close()
        return await anyio.to_thread.run_sync(_sync)

    async def get_prompt_app_template(self, *, template_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path
        def _sync():
            conn = self._connect(); conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM prompt_app_templates WHERE id=?;", (str(template_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
        return await anyio.to_thread.run_sync(_sync)

    async def upsert_prompt_app_template(self, *, template_id: str, name: str,
                                          category: str = "", tags: str = "[]",
                                          system_prompt: str = "", user_prompt: str = "",
                                          assistant_prompt: str = "", variables: str = "[]",
                                          examples: str = "", constraints: str = "", scenario_tags: str = "[]",
                                          status: str = "draft") -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path
        import time as _t, json as _j
        now = _t.time()
        def _sync():
            conn = self._connect(); conn.row_factory = sqlite3.Row
            try:
                existing = conn.execute("SELECT * FROM prompt_app_templates WHERE id=?;", (str(template_id),)).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE prompt_app_templates SET name=?, category=?, tags=?, system_prompt=?, user_prompt=?, assistant_prompt=?, variables=?, examples=?, constraints=?, scenario_tags=?, status=?, updated_at=? WHERE id=?;",
                        (name, category, tags, system_prompt, user_prompt, assistant_prompt, variables, examples, constraints, scenario_tags, status, now, str(template_id))
                    )
                else:
                    conn.execute(
                        "INSERT INTO prompt_app_templates(id,name,category,tags,system_prompt,user_prompt,assistant_prompt,variables,examples,constraints,scenario_tags,version,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);",
                        (str(template_id), name, category, tags, system_prompt, user_prompt, assistant_prompt, variables, examples, constraints, scenario_tags, '1.0.0', status, now, now)
                    )
                conn.commit()
                return dict(conn.execute("SELECT * FROM prompt_app_templates WHERE id=?;", (str(template_id),)).fetchone())
            finally:
                conn.close()
        return await anyio.to_thread.run_sync(_sync)

    async def delete_prompt_app_template(self, *, template_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path
        def _sync():
            conn = self._connect(); conn.row_factory = sqlite3.Row
            try:
                cur = conn.execute("DELETE FROM prompt_app_templates WHERE id=?;", (str(template_id),))
                conn.commit()
                return (cur.rowcount or 0) > 0
            finally:
                conn.close()
        return await anyio.to_thread.run_sync(_sync)

    async def list_prompt_app_categories(self) -> List[str]:
        await self.init()
        db_path = self._config.db_path
        def _sync():
            conn = self._connect(); conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute("SELECT name FROM prompt_app_categories ORDER BY display_order;").fetchall()
                return [r[0] for r in rows]
            finally:
                conn.close()
        return await anyio.to_thread.run_sync(_sync)

    async def upsert_prompt_app_category(self, *, name: str, display_order: int = 0, icon: str = "", parent: str = ""):
        await self.init()
        db_path = self._config.db_path
        import time as _t
        now = _t.time()
        def _sync():
            conn = self._connect(); conn.row_factory = sqlite3.Row
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO prompt_app_categories(name,display_order,icon,parent,created_at) VALUES(?,?,?,?,COALESCE((SELECT created_at FROM prompt_app_categories WHERE name=?),?));",
                    (name, display_order, icon, parent, name, now)
                )
                conn.commit()
            finally:
                conn.close()
        await anyio.to_thread.run_sync(_sync)

    async def delete_prompt_app_category(self, *, name: str) -> bool:
        await self.init()
        db_path = self._config.db_path
        def _sync():
            conn = self._connect(); conn.row_factory = sqlite3.Row
            try:
                conn.execute("DELETE FROM prompt_app_categories WHERE name=?;", (name,))
                conn.commit()
                return True
            finally:
                conn.close()
        return await anyio.to_thread.run_sync(_sync)

    # ── Prompt App Instance CRUD ────────────────────────────────────

    async def list_prompt_app_instances(self, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path
        def _sync():
            conn = self._connect(); conn.row_factory = sqlite3.Row
            try:
                total = conn.execute("SELECT COUNT(*) FROM prompt_app_instances;").fetchone()[0]
                rows = conn.execute(
                    "SELECT * FROM prompt_app_instances ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    [limit, offset]
                ).fetchall()
                items = [dict(r) for r in rows]
                return {"total": total, "items": items}
            finally:
                conn.close()
        return await anyio.to_thread.run_sync(_sync)

    async def get_prompt_app_instance(self, *, instance_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path
        def _sync():
            conn = self._connect(); conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM prompt_app_instances WHERE id=?;", (str(instance_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
        return await anyio.to_thread.run_sync(_sync)

    async def upsert_prompt_app_instance(self, *, instance_id: str, name: str, source_template_id: str,
                                          system_prompt: str = "", user_prompt: str = "",
                                          assistant_prompt: str = "", variables: str = "[]",
                                          status: str = "draft") -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path
        import time as _t
        now = _t.time()
        def _sync():
            conn = self._connect(); conn.row_factory = sqlite3.Row
            try:
                existing = conn.execute("SELECT * FROM prompt_app_instances WHERE id=?;", (str(instance_id),)).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE prompt_app_instances SET name=?, system_prompt=?, user_prompt=?, assistant_prompt=?, variables=?, status=?, updated_at=? WHERE id=?;",
                        (name, system_prompt, user_prompt, assistant_prompt, variables, status, now, str(instance_id))
                    )
                else:
                    conn.execute(
                        "INSERT INTO prompt_app_instances(id,name,source_template_id,system_prompt,user_prompt,assistant_prompt,variables,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?);",
                        (str(instance_id), name, source_template_id, system_prompt, user_prompt, assistant_prompt, variables, status, now, now)
                    )
                conn.commit()
                return dict(conn.execute("SELECT * FROM prompt_app_instances WHERE id=?;", (str(instance_id),)).fetchone())
            finally:
                conn.close()
        return await anyio.to_thread.run_sync(_sync)

    async def delete_prompt_app_instance(self, *, instance_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path
        def _sync():
            conn = self._connect(); conn.row_factory = sqlite3.Row
            try:
                cur = conn.execute("DELETE FROM prompt_app_instances WHERE id=?;", (str(instance_id),))
                conn.commit()
                return (cur.rowcount or 0) > 0
            finally:
                conn.close()
        return await anyio.to_thread.run_sync(_sync)

    def _job_row_to_obj(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row.get("id"),
            "name": row.get("name"),
            "enabled": bool(int(row.get("enabled") or 0)),
            "cron": row.get("cron"),
            "timezone": row.get("timezone"),
            "kind": row.get("kind"),
            "target_id": row.get("target_id"),
            "user_id": row.get("user_id"),
            "session_id": row.get("session_id"),
            "payload": _json_loads(row.get("payload_json")) or {},
            "options": _json_loads(row.get("options_json")) or {},
            "delivery": _json_loads(row.get("delivery_json")) or {},
            "last_run_at": row.get("last_run_at"),
            "next_run_at": row.get("next_run_at"),
            "lock_until": row.get("lock_until"),
            "lock_owner": row.get("lock_owner"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    def _job_run_row_to_obj(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row.get("id"),
            "job_id": row.get("job_id"),
            "scheduled_for": row.get("scheduled_for"),
            "started_at": row.get("started_at"),
            "finished_at": row.get("finished_at"),
            "status": row.get("status"),
            "trace_id": row.get("trace_id"),
            "run_id": row.get("run_id"),
            "error": row.get("error"),
            "result": _json_loads(row.get("result_json")) or {},
            "created_at": row.get("created_at"),
        }

