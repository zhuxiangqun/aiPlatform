"""
PackageMixin — extracted from ExecutionStore skill_pack_mixin.py.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
from ._base import _json_dumps, _json_loads


class PackageMixin:
    """Extracted from ExecutionStore."""
    async def install_skill_pack(self, *, pack_id: str, version: Optional[str], scope: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"spi-{uuid.uuid4().hex[:12]}",
                "pack_id": str(pack_id),
                "version": str(version) if version is not None else None,
                "scope": str(scope or "workspace"),
                "installed_at": now,
                "metadata_json": _json_dumps(metadata or {}),
            }
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                # ensure pack exists
                pack = conn.execute("SELECT 1 FROM skill_packs WHERE id = ?", (str(pack_id),)).fetchone()
                if not pack:
                    raise ValueError("Skill pack not found")
                # ensure version exists if provided
                if rec["version"]:
                    v = conn.execute(
                        "SELECT 1 FROM skill_pack_versions WHERE pack_id = ? AND version = ?;",
                        (str(pack_id), str(rec["version"])),
                    ).fetchone()
                    if not v:
                        raise ValueError("Skill pack version not found")
                conn.execute(
                    "INSERT INTO skill_pack_installs(id,pack_id,version,scope,installed_at,metadata_json) VALUES(?,?,?,?,?,?);",
                    (rec["id"], rec["pack_id"], rec["version"], rec["scope"], rec["installed_at"], rec["metadata_json"]),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "id": row["id"],
            "pack_id": row["pack_id"],
            "version": row.get("version"),
            "scope": row.get("scope"),
            "installed_at": row.get("installed_at"),
            "metadata": _json_loads(row.get("metadata_json")) or {},
        }

    async def list_skill_pack_installs(self, *, scope: Optional[str] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                where = ""
                args: List[Any] = []
                if scope:
                    where = "WHERE scope = ?"
                    args.append(str(scope))
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM skill_pack_installs {where};", args).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM skill_pack_installs {where} ORDER BY installed_at DESC LIMIT ? OFFSET ?;",
                    [*args, int(limit), int(offset)],
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
                    "version": r.get("version"),
                    "scope": r.get("scope"),
                    "installed_at": r.get("installed_at"),
                    "metadata": _json_loads(r.get("metadata_json")) or {},
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    # ---------------------------------------------------------------------
    # Roadmap-P0: packages registry (publish/install)
    # ---------------------------------------------------------------------

    async def publish_package_version(
        self,
        *,
        package_name: str,
        version: str,
        manifest: Dict[str, Any],
        artifact_path: Optional[str] = None,
        artifact_sha256: Optional[str] = None,
        approval_request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"pkgv-{uuid.uuid4().hex[:12]}",
                "package_name": str(package_name),
                "version": str(version),
                "manifest_json": _json_dumps(manifest or {}),
                "artifact_path": str(artifact_path) if artifact_path else None,
                "artifact_sha256": str(artifact_sha256) if artifact_sha256 else None,
                "approval_request_id": str(approval_request_id) if approval_request_id else None,
                "created_at": now,
            }
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
                    """
                    INSERT INTO package_versions(
                      id, package_name, version, manifest_json, artifact_path, artifact_sha256, approval_request_id, created_at
                    ) VALUES(?,?,?,?,?,?,?,?);
                    """,
                    (
                        rec["id"],
                        rec["package_name"],
                        rec["version"],
                        rec["manifest_json"],
                        rec["artifact_path"],
                        rec["artifact_sha256"],
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
            "id": row["id"],
            "package_name": row["package_name"],
            "version": row["version"],
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "artifact_path": row.get("artifact_path"),
            "artifact_sha256": row.get("artifact_sha256"),
            "approval_request_id": row.get("approval_request_id"),
            "created_at": row.get("created_at"),
        }

    async def list_package_versions(self, *, package_name: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute("SELECT COUNT(1) AS c FROM package_versions WHERE package_name = ?;", (str(package_name),)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    "SELECT * FROM package_versions WHERE package_name = ? ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    (str(package_name), int(limit), int(offset)),
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items: List[Dict[str, Any]] = []
        for r in res.get("items") or []:
            items.append(
                {
                    "id": r["id"],
                    "package_name": r["package_name"],
                    "version": r["version"],
                    "manifest": _json_loads(r.get("manifest_json")) or {},
                    "artifact_path": r.get("artifact_path"),
                    "artifact_sha256": r.get("artifact_sha256"),
                    "approval_request_id": r.get("approval_request_id"),
                    "created_at": r.get("created_at"),
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def get_package_version(self, *, package_name: str, version: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM package_versions WHERE package_name = ? AND version = ?;",
                    (str(package_name), str(version)),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {
            "id": row["id"],
            "package_name": row["package_name"],
            "version": row["version"],
            "manifest": _json_loads(row.get("manifest_json")) or {},
            "artifact_path": row.get("artifact_path"),
            "artifact_sha256": row.get("artifact_sha256"),
            "approval_request_id": row.get("approval_request_id"),
            "created_at": row.get("created_at"),
        }

    async def record_package_install(
        self,
        *,
        package_name: str,
        version: Optional[str],
        scope: str,
        metadata: Optional[Dict[str, Any]] = None,
        approval_request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"pkgi-{uuid.uuid4().hex[:12]}",
                "package_name": str(package_name),
                "version": str(version) if version is not None else None,
                "scope": str(scope or "workspace"),
                "installed_at": now,
                "metadata_json": _json_dumps(metadata or {}),
                "approval_request_id": str(approval_request_id) if approval_request_id else None,
            }
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                if rec["version"]:
                    v = conn.execute(
                        "SELECT 1 FROM package_versions WHERE package_name = ? AND version = ?;",
                        (str(package_name), str(rec["version"])),
                    ).fetchone()
                    if not v:
                        raise ValueError("Package version not found")
                conn.execute(
                    "INSERT INTO package_installs(id,package_name,version,scope,installed_at,metadata_json,approval_request_id) VALUES(?,?,?,?,?,?,?);",
                    (
                        rec["id"],
                        rec["package_name"],
                        rec["version"],
                        rec["scope"],
                        rec["installed_at"],
                        rec["metadata_json"],
                        rec["approval_request_id"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "id": row["id"],
            "package_name": row["package_name"],
            "version": row.get("version"),
            "scope": row.get("scope"),
            "installed_at": row.get("installed_at"),
            "metadata": _json_loads(row.get("metadata_json")) or {},
            "approval_request_id": row.get("approval_request_id"),
        }

    async def list_package_installs(self, *, scope: Optional[str] = None, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                where = ""
                args: List[Any] = []
                if scope:
                    where = "WHERE scope = ?"
                    args.append(str(scope))
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM package_installs {where};", args).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM package_installs {where} ORDER BY installed_at DESC LIMIT ? OFFSET ?;",
                    [*args, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items: List[Dict[str, Any]] = []
        for r in res.get("items") or []:
            items.append(
                {
                    "id": r["id"],
                    "package_name": r["package_name"],
                    "version": r.get("version"),
                    "scope": r.get("scope"),
                    "installed_at": r.get("installed_at"),
                    "metadata": _json_loads(r.get("metadata_json")) or {},
                    "approval_request_id": r.get("approval_request_id"),
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

