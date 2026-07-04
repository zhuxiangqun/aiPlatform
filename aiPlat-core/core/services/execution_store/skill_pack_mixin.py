class GatewayMixin:
    """Extracted from ExecutionStore."""
"""
Skill Pack management — extracted from ExecutionStore gateway_mixin.py.

Handles: update, delete, publish version, list versions, install, list installs.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
import uuid
from ._base import _json_dumps, _json_loads


class SkillPackMixin:
    """Skill Pack CRUD — extracted from ExecutionStore."""
    async def update_skill_pack(self, pack_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM skill_packs WHERE id = ?", (str(pack_id),)).fetchone()
                if not row:
                    return None
                cur = dict(row)
                now = time.time()
                name = str(patch.get("name") or cur.get("name") or "")
                desc = patch.get("description") if "description" in patch else cur.get("description")
                manifest = _json_dumps(patch.get("manifest") if "manifest" in patch else (_json_loads(cur.get("manifest_json")) or {}))
                conn.execute(
                    "UPDATE skill_packs SET name=?, description=?, manifest_json=?, updated_at=? WHERE id=?;",
                    (name, desc, manifest, float(now), str(pack_id)),
                )
                conn.commit()
                row2 = conn.execute("SELECT * FROM skill_packs WHERE id = ?", (str(pack_id),)).fetchone()
                return dict(row2) if row2 else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row.get("description"),
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def delete_skill_pack(self, pack_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM skill_packs WHERE id = ?;", (str(pack_id),))
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def publish_skill_pack_version(self, *, pack_id: str, version: str) -> Dict[str, Any]:
        """
        Publish an immutable version snapshot for a skill pack.
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                pack = conn.execute("SELECT * FROM skill_packs WHERE id = ?", (str(pack_id),)).fetchone()
                if not pack:
                    raise ValueError("Skill pack not found")
                rec = {
                    "id": f"spv-{uuid.uuid4().hex[:12]}",
                    "pack_id": str(pack_id),
                    "version": str(version),
                    "manifest_json": pack["manifest_json"],
                    "created_at": now,
                }
                conn.execute(
                    "INSERT INTO skill_pack_versions(id,pack_id,version,manifest_json,created_at) VALUES(?,?,?,?,?);",
                    (rec["id"], rec["pack_id"], rec["version"], rec["manifest_json"], rec["created_at"]),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "id": row["id"],
            "pack_id": row["pack_id"],
            "version": row["version"],
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "created_at": row.get("created_at"),
        }

    async def list_skill_pack_versions(self, *, pack_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute("SELECT COUNT(1) AS c FROM skill_pack_versions WHERE pack_id = ?;", (str(pack_id),)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    "SELECT * FROM skill_pack_versions WHERE pack_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    (str(pack_id), int(limit), int(offset)),
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append(
                {
                    "id": r["id"],
                    "pack_id": r["pack_id"],
                    "version": r["version"],
                    "manifest": _json_loads(r.get("manifest_json")) or {},
                    "created_at": r.get("created_at"),
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def get_skill_pack_version(self, *, pack_id: str, version: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM skill_pack_versions WHERE pack_id = ? AND version = ?;",
                    (str(pack_id), str(version)),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {
            "id": row["id"],
            "pack_id": row["pack_id"],
            "version": row["version"],
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "created_at": row.get("created_at"),
        }
    """Skill Pack CRUD only."""
    pass
    async def create_skill_pack(self, pack: Dict[str, Any]) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": pack.get("id") or f"sp-{uuid.uuid4().hex[:12]}",
                "name": str(pack.get("name") or ""),
                "description": pack.get("description"),
                "manifest_json": _json_dumps(pack.get("manifest") or {}),
                "created_at": now,
                "updated_at": now,
            }
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO skill_packs(id,name,description,manifest_json,created_at,updated_at) VALUES(?,?,?,?,?,?);",
                    (rec["id"], rec["name"], rec["description"], rec["manifest_json"], rec["created_at"], rec["updated_at"]),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row.get("description"),
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def get_skill_pack(self, pack_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM skill_packs WHERE id = ?", (str(pack_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row.get("description"),
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def list_skill_packs(self, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute("SELECT COUNT(1) AS c FROM skill_packs;").fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    "SELECT * FROM skill_packs ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    (int(limit), int(offset)),
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "description": r.get("description"),
                    "manifest": _json_loads(r.get("manifest_json")) or {},
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at"),
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}
