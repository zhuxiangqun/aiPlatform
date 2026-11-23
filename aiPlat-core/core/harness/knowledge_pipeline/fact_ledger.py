"""v4.3.1 Phase 1 事实账本：Source Registry + Fact/Claim（SQLite）。

职责：
  - 登记不可变 Raw 快照（sha256 + snapshot 文件）
  - 写入 Fact/Claim；``review_status=published`` 时必须有非空 evidence
  - 查询在 SQL 层按 tenant_id 过滤（召回前，非召回后）

非目标：
  - 完整 ObjectSet/SDK、Wiki 只读化、Scenario Package（后续 Phase）
  - 替代现有 DataSourceRegistry 外部连接器（本模块是附录 A/D 契约层）
  - 宣称附录 N 全量认证（写入硬门加深仍为 partial）
  - 回滚 UI / 全量 Package+Action 总线合并（N24 含抬号+归档+restore+audit+审批式 restore+ActionExecution 桥接）
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.harness.knowledge.domain_router import DomainRouter
logger = logging.getLogger(__name__)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PUBLISHED = "published"
_ALLOWED_NEW_REVIEW = frozenset({"draft", "reviewed", "rejected"})


def default_fact_ledger_db_path() -> str:
    """解析 Fact Ledger SQLite 路径（尊重 AIPLAT_HOME / pytest）。

    Returns:
        数据库文件路径。
    """
    env = os.environ.get("AIPLAT_FACT_LEDGER_DB_PATH")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "fact_ledger.sqlite3")
    return "./data/fact_ledger.sqlite3"


def default_raw_snapshot_dir() -> Path:
    """Raw 快照根目录（按 tenant 分子目录）。

    Returns:
        快照根路径。
    """
    env = os.environ.get("AIPLAT_RAW_SNAPSHOT_DIR")
    if env:
        return Path(env).expanduser()
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return Path(home) / "raw"
    return Path("~/.aiplat/raw").expanduser()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FactLedgerError(ValueError):
    """Fact Ledger 契约或权限错误。"""


class FactLedger:
    """附录 A/D 最小实现：Source + Fact/Claim + 租户前置查询。"""

    def __init__(
        self,
        db_path: Optional[str] = None,
        raw_dir: Optional[Path] = None,
        action_execution_db_path: Optional[str] = None,
    ) -> None:
        """初始化账本。

        Args:
            db_path: SQLite 路径；默认 ``default_fact_ledger_db_path()``。
            raw_dir: Raw 快照根目录；默认 ``default_raw_snapshot_dir()``。
            action_execution_db_path: 可选 ActionExecution 库（revision 桥接）；
                空则用 ActionExecution 默认路径。
        """
        self.db_path = db_path or default_fact_ledger_db_path()
        self.raw_dir = Path(raw_dir) if raw_dir else default_raw_snapshot_dir()
        self.action_execution_db_path = action_execution_db_path

    async def initialize(self) -> None:
        """创建表结构（幂等）。"""
        import aiosqlite

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    collection_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    snapshot_uri TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    license TEXT,
                    acl_json TEXT NOT NULL,
                    connector TEXT NOT NULL,
                    status TEXT NOT NULL,
                    immutable INTEGER NOT NULL DEFAULT 1,
                    domain_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sources_tenant ON sources(tenant_id)"
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    fact_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    collection_id TEXT NOT NULL,
                    domain_id TEXT,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    source_policy TEXT NOT NULL,
                    extractor_version TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    recorded_at TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    inferred INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_facts_tenant ON facts(tenant_id)"
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS claims (
                    claim_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    collection_id TEXT NOT NULL,
                    domain_id TEXT,
                    text TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    source_policy TEXT NOT NULL,
                    extractor_version TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    recorded_at TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    conflict_key TEXT NOT NULL DEFAULT ''
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_claims_tenant ON claims(tenant_id)"
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_claims_conflict_key
                ON claims(tenant_id, collection_id, conflict_key)
                """
            )
            # 为什么：存量库缺 conflict_key 时补列，避免破坏已有 claims 行
            try:
                await db.execute(
                    "ALTER TABLE claims ADD COLUMN conflict_key TEXT NOT NULL DEFAULT ''"
                )
            except Exception as exc:  # noqa: schema-idempotent
                logger.debug("claims.conflict_key column ready: %s", exc)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS claim_conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    collection_id TEXT NOT NULL,
                    conflict_key TEXT NOT NULL,
                    claim_ids_json TEXT NOT NULL,
                    texts_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_claim_conflicts_open
                ON claim_conflicts(tenant_id, collection_id, conflict_key, status)
                """
            )
            # 为什么：N24 禁止无记录覆盖 — 变更前快照进 append-only 修订表
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS fact_revisions (
                    revision_row_id TEXT PRIMARY KEY,
                    fact_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    UNIQUE(fact_id, revision)
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_fact_revisions_fact
                ON fact_revisions(tenant_id, fact_id, revision)
                """
            )
            # 为什么：N24 Claim 与 Fact 对称 — 变更前快照进 append-only 修订表
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS claim_revisions (
                    revision_row_id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    UNIQUE(claim_id, revision)
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_claim_revisions_claim
                ON claim_revisions(tenant_id, claim_id, revision)
                """
            )
            # 为什么：N24 Source 与 Fact/Claim 对称 — 内容抬号前归档元数据；旧快照文件永不删
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS source_revisions (
                    revision_row_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    UNIQUE(source_id, revision)
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_source_revisions_source
                ON source_revisions(tenant_id, source_id, revision)
                """
            )
            # 为什么：N24 — Fact/Claim/Source 修订事件统一落入 append-only audit（非 Package/Action 总线）
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS revision_audit (
                    audit_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    to_revision INTEGER,
                    actor TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_revision_audit_entity
                ON revision_audit(tenant_id, entity_type, entity_id, recorded_at)
                """
            )
            # 为什么：N24 审批式 restore — 请求与批准分离；非管理端 UI / 非 Action 总线
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS revision_restore_requests (
                    request_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    target_revision INTEGER NOT NULL,
                    requester TEXT NOT NULL,
                    request_reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    approver TEXT,
                    decision_reason TEXT,
                    restore_receipt_json TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_revision_restore_req
                ON revision_restore_requests(tenant_id, entity_type, entity_id, status)
                """
            )
            # 为什么：N24 — revision_audit 决策事件桥接到 ActionExecution（非全量总线合并）
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS revision_action_bridge (
                    bridge_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    audit_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    UNIQUE(tenant_id, audit_id)
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_revision_action_bridge_entity
                ON revision_action_bridge(tenant_id, entity_type, entity_id)
                """
            )
            await db.commit()

    async def register_source(
        self,
        *,
        tenant_id: str,
        collection_id: str,
        kind: str,
        uri: str,
        content: bytes,
        connector: str,
        acl: Optional[List[str]] = None,
        domain_id: str = "",
        license: str = "company-internal",
        source_id: Optional[str] = None,
        revision: int = 1,
        revision_actor: str = "",
        revision_reason: str = "",
    ) -> Dict[str, Any]:
        """登记不可变 Raw：写快照文件 + Source 行。

        Args:
            tenant_id: 租户 ID（召回前过滤键）。
            collection_id: 集合 ID。
            kind: 来源类型（file/web/api/…）。
            uri: 逻辑来源 URI（非活指针）。
            content: 快照字节；hash 与不可变文件由此产生。
            connector: 连接器名。
            acl: ACL 主体列表。
            domain_id: 业务域 ID（由调用方传入；harness 不默认业务域名）。
            license: 许可标记。
            source_id: 可选显式 ID。
            revision: 修订号。
            revision_actor: 内容抬号归档 actor（可选）。
            revision_reason: 内容抬号归档理由（可选）。

        Returns:
            附录 A 形状的 source 记录。

        Raises:
            FactLedgerError: 参数非法 / 同号内容覆盖 / 快照冲突。
        """
        import aiosqlite

        if not tenant_id or not collection_id or not uri:
            raise FactLedgerError("tenant_id, collection_id, uri are required")
        if not content:
            raise FactLedgerError("content bytes required for immutable raw")

        sid = source_id or f"src-{uuid.uuid4().hex[:12]}"
        digest = _sha256_bytes(content)
        if not _SHA256_RE.match(digest):
            raise FactLedgerError("sha256 computation failed")

        existing: Optional[Dict[str, Any]] = None
        if source_id:
            existing = await self.get_source(sid, tenant_id=tenant_id)

        tenant_dir = self.raw_dir / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)

        if existing is not None:
            # 为什么：同内容幂等返回，避免无意义抬号
            if str(existing.get("sha256") or "") == digest:
                return existing
            # 为什么：N01 禁 silent 覆写；N24 仅允许 revision 抬号后新快照文件
            if int(revision) <= int(existing.get("revision") or 1):
                raise FactLedgerError(
                    "snapshot already exists: content change requires revision bump "
                    f"(existing={existing.get('revision')}, got={revision})"
                )
            await self._archive_source_revision(
                existing,
                actor=(revision_actor or "register_source").strip()
                or "register_source",
                reason=(revision_reason or "supersede").strip() or "supersede",
            )
            snap_path = tenant_dir / f"{sid}.r{int(revision)}.bin"
            if snap_path.exists():
                raise FactLedgerError(f"snapshot already exists: {snap_path}")
            snap_path.write_bytes(content)
            try:
                snap_path.chmod(0o444)
            except OSError as e:
                logger.debug("chmod snapshot skipped: %s", e)
            fetched_at = _utc_now()
            acl_list = list(acl or existing.get("acl") or [f"tenant:{tenant_id}"])
            record = {
                "source_id": sid,
                "tenant_id": tenant_id,
                "collection_id": collection_id,
                "kind": kind,
                "uri": uri,
                "snapshot_uri": str(snap_path),
                "sha256": digest,
                "fetched_at": fetched_at,
                "revision": int(revision),
                "license": license,
                "acl": acl_list,
                "connector": connector,
                "status": "active",
                "immutable": True,
                "domain_id": domain_id,
            }
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("PRAGMA busy_timeout=5000")
                await db.execute(
                    """
                    UPDATE sources SET
                        collection_id=?, kind=?, uri=?, snapshot_uri=?,
                        sha256=?, fetched_at=?, revision=?, license=?,
                        acl_json=?, connector=?, status=?, immutable=?,
                        domain_id=?
                    WHERE source_id=? AND tenant_id=?
                    """,
                    (
                        collection_id,
                        kind,
                        uri,
                        record["snapshot_uri"],
                        digest,
                        fetched_at,
                        int(revision),
                        license,
                        json.dumps(acl_list, ensure_ascii=False),
                        connector,
                        "active",
                        1,
                        domain_id,
                        sid,
                        tenant_id,
                    ),
                )
                await db.commit()
            return record

        snap_path = tenant_dir / f"{sid}.bin"
        if snap_path.exists():
            raise FactLedgerError(f"snapshot already exists: {snap_path}")
        snap_path.write_bytes(content)
        # 不可变：写后去掉写权限（尽力；Windows 可能无效）
        try:
            snap_path.chmod(0o444)
        except OSError as e:
            logger.debug("chmod snapshot skipped: %s", e)

        fetched_at = _utc_now()
        acl_list = list(acl or [f"tenant:{tenant_id}"])
        record = {
            "source_id": sid,
            "tenant_id": tenant_id,
            "collection_id": collection_id,
            "kind": kind,
            "uri": uri,
            "snapshot_uri": str(snap_path),
            "sha256": digest,
            "fetched_at": fetched_at,
            "revision": int(revision),
            "license": license,
            "acl": acl_list,
            "connector": connector,
            "status": "active",
            "immutable": True,
            "domain_id": domain_id,
        }

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                INSERT INTO sources (
                    source_id, tenant_id, collection_id, kind, uri, snapshot_uri,
                    sha256, fetched_at, revision, license, acl_json, connector,
                    status, immutable, domain_id, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sid,
                    tenant_id,
                    collection_id,
                    kind,
                    uri,
                    record["snapshot_uri"],
                    digest,
                    fetched_at,
                    int(revision),
                    license,
                    json.dumps(acl_list, ensure_ascii=False),
                    connector,
                    "active",
                    1,
                    domain_id,
                    fetched_at,
                ),
            )
            await db.commit()
        return record

    async def get_source(
        self,
        source_id: str,
        *,
        tenant_id: str,
        verify_integrity: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """按租户读取 source（跨租户返回 None）。

        Args:
            source_id: 来源 ID。
            tenant_id: 调用方租户；必须匹配行上 tenant_id。
            verify_integrity: True 时复算快照 sha256，不一致则抛错。

        Returns:
            source 字典或 None。

        Raises:
            FactLedgerError: verify_integrity 且快照缺失/被篡改。
        """
        import aiosqlite

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM sources WHERE source_id=? AND tenant_id=?",
                (source_id, tenant_id),
            )
            row = await cur.fetchone()
        if not row:
            return None
        record = self._row_source(row)
        if verify_integrity:
            await self.verify_raw_integrity(source_id, tenant_id=tenant_id)
            record["integrity_ok"] = True
        return record

    _SOURCE_CONTENT_KEYS = (
        "collection_id",
        "kind",
        "uri",
        "snapshot_uri",
        "sha256",
        "license",
        "acl",
        "connector",
        "status",
        "domain_id",
    )

    async def _archive_source_revision(
        self,
        source: Dict[str, Any],
        *,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """将即将被抬号覆盖的 Source 元数据写入 source_revisions。

        Args:
            source: 当前头版本快照（含 snapshot_uri；旧文件保留）。
            actor: 操作者。
            reason: 归档理由。

        Returns:
            修订行摘要。
        """
        import aiosqlite

        row_id = f"srev-{uuid.uuid4().hex[:12]}"
        recorded_at = _utc_now()
        entry = {
            "revision_row_id": row_id,
            "source_id": source["source_id"],
            "tenant_id": source["tenant_id"],
            "revision": int(source.get("revision") or 1),
            "snapshot": dict(source),
            "actor": actor,
            "reason": reason,
            "recorded_at": recorded_at,
            "is_head": False,
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                INSERT INTO source_revisions (
                    revision_row_id, source_id, tenant_id, revision,
                    snapshot_json, actor, reason, recorded_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    row_id,
                    source["source_id"],
                    source["tenant_id"],
                    int(source.get("revision") or 1),
                    json.dumps(source, ensure_ascii=False),
                    actor,
                    reason,
                    recorded_at,
                ),
            )
            await db.commit()
        # 为什么：归档必须可审计；与 Package/Action 总线解耦，仅账本内事件
        await self._emit_revision_audit(
            tenant_id=str(source["tenant_id"]),
            entity_type="source",
            entity_id=str(source["source_id"]),
            event_type="archive",
            revision=int(source.get("revision") or 1),
            actor=actor,
            reason=reason,
            detail={"revision_row_id": row_id},
        )
        return entry

    async def list_source_revisions(
        self,
        source_id: str,
        *,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """列出 Source 修订历史（归档 + 当前头）。

        Args:
            source_id: Source ID。
            tenant_id: 调用方租户。

        Returns:
            按 revision 升序的条目（含 snapshot）。
        """
        import aiosqlite

        if not tenant_id:
            raise FactLedgerError("tenant_id required")
        out: List[Dict[str, Any]] = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                """
                SELECT * FROM source_revisions
                WHERE source_id=? AND tenant_id=?
                ORDER BY revision ASC
                """,
                (source_id, tenant_id),
            )
            rows = await cur.fetchall()
        for row in rows:
            out.append(
                {
                    "revision_row_id": row["revision_row_id"],
                    "source_id": row["source_id"],
                    "tenant_id": row["tenant_id"],
                    "revision": int(row["revision"]),
                    "snapshot": json.loads(row["snapshot_json"] or "{}"),
                    "actor": row["actor"],
                    "reason": row["reason"],
                    "recorded_at": row["recorded_at"],
                    "is_head": False,
                }
            )
        head = await self.get_source(source_id, tenant_id=tenant_id)
        if head is not None:
            out.append(
                {
                    "revision_row_id": "",
                    "source_id": source_id,
                    "tenant_id": tenant_id,
                    "revision": int(head.get("revision") or 1),
                    "snapshot": head,
                    "actor": "head",
                    "reason": "current",
                    "recorded_at": head.get("fetched_at") or "",
                    "is_head": True,
                }
            )
        return out

    async def get_source_at_revision(
        self,
        source_id: str,
        *,
        tenant_id: str,
        revision: int,
    ) -> Optional[Dict[str, Any]]:
        """按 revision 读取 Source 元数据快照（头或归档）。

        Args:
            source_id: Source ID。
            tenant_id: 调用方租户。
            revision: 目标修订号。

        Returns:
            快照 dict；不存在则 None。
        """
        import aiosqlite

        head = await self.get_source(source_id, tenant_id=tenant_id)
        if head is not None and int(head.get("revision") or 1) == int(revision):
            return head
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                """
                SELECT snapshot_json FROM source_revisions
                WHERE source_id=? AND tenant_id=? AND revision=?
                """,
                (source_id, tenant_id, int(revision)),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return json.loads(row["snapshot_json"] or "{}")

    async def diff_source_revisions(
        self,
        source_id: str,
        *,
        tenant_id: str,
        from_revision: int,
        to_revision: int,
    ) -> Dict[str, Any]:
        """比较两个 Source revision 的元数据字段差。

        Args:
            source_id: Source ID。
            tenant_id: 调用方租户。
            from_revision: 旧修订。
            to_revision: 新修订。

        Returns:
            diff 回执。

        Raises:
            FactLedgerError: 任一 revision 缺失。
        """
        left = await self.get_source_at_revision(
            source_id, tenant_id=tenant_id, revision=int(from_revision)
        )
        right = await self.get_source_at_revision(
            source_id, tenant_id=tenant_id, revision=int(to_revision)
        )
        if left is None or right is None:
            raise FactLedgerError(
                f"source revision not found: from={from_revision} to={to_revision}"
            )
        changed: Dict[str, Any] = {}
        for key in self._SOURCE_CONTENT_KEYS:
            lv = left.get(key)
            rv = right.get(key)
            if key == "acl":
                same = json.dumps(lv or [], ensure_ascii=False, sort_keys=True) == json.dumps(
                    rv or [], ensure_ascii=False, sort_keys=True
                )
            else:
                same = ("" if lv is None else lv) == ("" if rv is None else rv)
            if not same:
                changed[key] = {"from": lv, "to": rv}
        return {
            "source_id": source_id,
            "tenant_id": tenant_id,
            "from_revision": int(from_revision),
            "to_revision": int(to_revision),
            "changed": changed,
            "unchanged": [k for k in self._SOURCE_CONTENT_KEYS if k not in changed],
        }

    async def verify_raw_integrity(
        self, source_id: str, *, tenant_id: str
    ) -> Dict[str, Any]:
        """读时校验：快照文件 sha256 必须与 Source 行一致。

        Args:
            source_id: 来源 ID。
            tenant_id: 调用方租户（召回前过滤）。

        Returns:
            校验回执：source_id / sha256 / snapshot_uri / ok=True。

        Raises:
            FactLedgerError: 跨租户/不存在、快照缺失、hash 不一致。
        """
        src = await self.get_source(source_id, tenant_id=tenant_id)
        if src is None:
            raise FactLedgerError(
                f"source not found for tenant: {source_id!r}"
            )
        snap = Path(src["snapshot_uri"])
        if not snap.is_file():
            raise FactLedgerError(
                f"raw snapshot missing: {snap} (source_id={source_id})"
            )
        actual = _sha256_bytes(snap.read_bytes())
        expected = str(src.get("sha256") or "")
        if not _SHA256_RE.match(expected):
            raise FactLedgerError(
                f"stored sha256 invalid for source_id={source_id}"
            )
        if actual != expected:
            # 篡改/覆盖拒绝：登记时的 digest 是权威，读路径不得 silent 放行
            raise FactLedgerError(
                f"raw integrity failed: sha256 mismatch for source_id={source_id}"
            )
        return {
            "ok": True,
            "source_id": source_id,
            "tenant_id": tenant_id,
            "sha256": expected,
            "snapshot_uri": str(snap),
            "immutable": bool(src.get("immutable")),
        }

    async def read_raw_bytes(
        self, source_id: str, *, tenant_id: str, verify: bool = True
    ) -> bytes:
        """读取不可变 Raw 快照字节；默认先验完整性。

        Args:
            source_id: 来源 ID。
            tenant_id: 调用方租户。
            verify: True（默认）时先 ``verify_raw_integrity``。

        Returns:
            快照文件字节。

        Raises:
            FactLedgerError: 不存在、校验失败、或快照不可读。
        """
        if verify:
            await self.verify_raw_integrity(source_id, tenant_id=tenant_id)
        src = await self.get_source(source_id, tenant_id=tenant_id)
        if src is None:
            raise FactLedgerError(
                f"source not found for tenant: {source_id!r}"
            )
        snap = Path(src["snapshot_uri"])
        if not snap.is_file():
            raise FactLedgerError(f"raw snapshot missing: {snap}")
        return snap.read_bytes()

    @staticmethod
    def _row_source(row: Any) -> Dict[str, Any]:
        return {
            "source_id": row["source_id"],
            "tenant_id": row["tenant_id"],
            "collection_id": row["collection_id"],
            "kind": row["kind"],
            "uri": row["uri"],
            "snapshot_uri": row["snapshot_uri"],
            "sha256": row["sha256"],
            "fetched_at": row["fetched_at"],
            "revision": row["revision"],
            "license": row["license"],
            "acl": json.loads(row["acl_json"] or "[]"),
            "connector": row["connector"],
            "status": row["status"],
            "immutable": bool(row["immutable"]),
            "domain_id": row["domain_id"],
        }

    def _validate_evidence(
        self, evidence: List[Dict[str, Any]], *, review_status: str
    ) -> None:
        if review_status == _PUBLISHED and not evidence:
            raise FactLedgerError("published requires non-empty evidence")
        for ev in evidence:
            if not ev.get("source_id"):
                raise FactLedgerError("evidence.source_id required")

    async def put_fact(
        self,
        *,
        tenant_id: str,
        collection_id: str,
        subject: str,
        predicate: str,
        object: str,
        evidence: List[Dict[str, Any]],
        source_policy: str,
        extractor_version: str,
        review_status: str,
        confidence: float,
        domain_id: str = "",
        fact_id: Optional[str] = None,
        status: str = "active",
        inferred: bool = False,
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
        revision: int = 1,
        enforce_write_gates: bool = True,
        allow_bootstrap_published: bool = False,
        source_policy_db_path: Optional[str] = None,
        revision_actor: str = "",
        revision_reason: str = "",
    ) -> Dict[str, Any]:
        """写入 Fact；默认强制来源策略 / 冲突门 / 状态边。

        Args:
            tenant_id: 租户。
            collection_id: 集合。
            subject: 主语实体。
            predicate: 谓词。
            object: 宾语（字符串化）。
            evidence: 证据列表（含 source_id）。
            source_policy: 来源策略 ID。
            extractor_version: 抽取器版本。
            review_status: draft/reviewed/published/…。
            confidence: 0–1。
            domain_id: 业务域 ID（调用方传入）。
            fact_id: 可选显式 ID。
            status: 生命周期状态。
            inferred: 是否推断。
            valid_from / valid_to: 有效期。
            revision: 修订号。
            enforce_write_gates: 为 True 时强制策略登记、冲突门、状态边（默认）。
            allow_bootstrap_published: 测试种子专用；跳过写入硬门（Facade 不暴露）。
            source_policy_db_path: 来源策略库路径（冲突/策略查询）。
            revision_actor: 修订归档 actor（可选；默认 put_fact）。
            revision_reason: 修订归档理由（可选；默认 supersede）。

        Returns:
            Fact 记录。

        Raises:
            FactLedgerError: 契约违反、无记录覆盖、或 evidence 指向未知 source。
        """
        import aiosqlite

        self._validate_evidence(evidence, review_status=review_status)
        for ev in evidence:
            src = await self.get_source(str(ev["source_id"]), tenant_id=tenant_id)
            if src is None:
                raise FactLedgerError(
                    f"evidence source not found in tenant: {ev['source_id']}"
                )

        fid = fact_id or f"fact-{uuid.uuid4().hex[:12]}"
        existing: Optional[Dict[str, Any]] = None
        if fact_id:
            existing = await self.get_fact(fid, tenant_id=tenant_id)

        # 为什么：transition / 已校验路径可关硬门；测试种子用 bootstrap 跳过
        apply_gates = bool(enforce_write_gates) and not bool(allow_bootstrap_published)
        if apply_gates:
            await self._enforce_put_fact_write_gates(
                tenant_id=tenant_id,
                subject=subject,
                predicate=predicate,
                source_policy=source_policy,
                review_status=review_status,
                status=status,
                existing=existing,
                source_policy_db_path=source_policy_db_path,
            )

        recorded_at = _utc_now()
        vf = valid_from or recorded_at
        record = {
            "fact_id": fid,
            "tenant_id": tenant_id,
            "collection_id": collection_id,
            "domain_id": domain_id,
            "subject": subject,
            "predicate": predicate,
            "object": object,
            "evidence": evidence,
            "source_policy": source_policy,
            "extractor_version": extractor_version,
            "review_status": review_status,
            "confidence": float(confidence),
            "valid_from": vf,
            "valid_to": valid_to,
            "recorded_at": recorded_at,
            "revision": int(revision),
            "status": status,
            "inferred": bool(inferred),
        }
        if existing is not None:
            # 为什么：内容不变视为幂等，避免无意义 revision 膨胀
            if self._fact_content_equal(existing, record):
                return existing
            # 为什么：N24 — 内容变更必须抬 revision，旧快照进 fact_revisions
            if int(revision) <= int(existing.get("revision") or 1):
                raise FactLedgerError(
                    "fact content change requires revision bump "
                    f"(existing={existing.get('revision')}, got={revision})"
                )
            await self._archive_fact_revision(
                existing,
                actor=(revision_actor or "put_fact").strip() or "put_fact",
                reason=(revision_reason or "supersede").strip() or "supersede",
            )
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                INSERT OR REPLACE INTO facts (
                    fact_id, tenant_id, collection_id, domain_id, subject, predicate,
                    object, evidence_json, source_policy, extractor_version,
                    review_status, confidence, valid_from, valid_to, recorded_at,
                    revision, status, inferred
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    fid,
                    tenant_id,
                    collection_id,
                    domain_id,
                    subject,
                    predicate,
                    object,
                    json.dumps(evidence, ensure_ascii=False),
                    source_policy,
                    extractor_version,
                    review_status,
                    float(confidence),
                    vf,
                    valid_to,
                    recorded_at,
                    int(revision),
                    status,
                    1 if inferred else 0,
                ),
            )
            await db.commit()
        # 为什么：N19 — put_fact 热路径 best-effort 落统一审计快照（失败不阻断写入）
        try:
            from core.harness.knowledge_pipeline.fact_query_audit import (
                maybe_record_put_fact_hotpath,
            )

            maybe_record_put_fact_hotpath(
                tenant_id=tenant_id,
                before=existing,
                after=record,
            )
        except Exception:
            logger.warning(
                "fact_query_audit put_fact hotpath failed for %s",
                fid,
                exc_info=True,
            )
        # 为什么：N20 — put_fact 热路径挂约束栈观测信封（不回滚写入）
        try:
            from core.harness.knowledge_pipeline.constraint_layers import (
                maybe_attach_put_fact_constraint_hotpath,
            )

            record = maybe_attach_put_fact_constraint_hotpath(record)
        except Exception:
            logger.warning(
                "constraint_layers put_fact hotpath failed for %s",
                fid,
                exc_info=True,
            )
        return record

    async def _enforce_put_fact_write_gates(
        self,
        *,
        tenant_id: str,
        subject: str,
        predicate: str,
        source_policy: str,
        review_status: str,
        status: str,
        existing: Optional[Dict[str, Any]],
        source_policy_db_path: Optional[str] = None,
    ) -> None:
        """N04/N12 写入硬门：策略已登记、冲突已裁决、状态边合法。

        Args:
            tenant_id: 租户。
            subject / predicate: Fact 键。
            source_policy: 策略 ID。
            review_status / status: 目标审核态与生命周期。
            existing: 已有 Fact；None 表示新建。
            source_policy_db_path: 策略库路径。
        """
        from core.harness.knowledge_pipeline.source_policy import (
            SourcePolicyError,
            assert_publish_allowed,
            get_source_policy,
        )

        pol_id = (source_policy or "").strip()
        if not pol_id:
            raise FactLedgerError("source_policy required")
        if get_source_policy(pol_id, tenant_id=tenant_id, db_path=source_policy_db_path) is None:
            raise FactLedgerError(f"unknown source_policy: {pol_id}")

        rs = (review_status or "").strip()
        st = (status or "").strip() or "active"

        if existing is None:
            if rs == _PUBLISHED:
                raise FactLedgerError(
                    "new fact cannot be published; use draft/reviewed then transition"
                )
            if rs not in _ALLOWED_NEW_REVIEW:
                raise FactLedgerError(
                    f"new fact review_status must be draft/reviewed/rejected, got {rs!r}"
                )
            if st != "active":
                raise FactLedgerError(
                    "new fact lifecycle status must be active"
                )
        else:
            old_rs = str(existing.get("review_status") or "")
            old_st = str(existing.get("status") or "")
            # 为什么禁止在 put_fact 改状态：边校验与 actor/reason 审计只走 transition API
            if rs != old_rs or st != old_st:
                raise FactLedgerError(
                    "review_status/status changes require transition API "
                    f"(got review {old_rs!r}→{rs!r}, lifecycle {old_st!r}→{st!r})"
                )

        if rs == _PUBLISHED:
            try:
                assert_publish_allowed(
                    tenant_id=tenant_id,
                    source_policy=pol_id,
                    subject=subject,
                    predicate=predicate,
                    db_path=source_policy_db_path,
                )
            except SourcePolicyError as exc:
                raise FactLedgerError(str(exc)) from exc

    async def put_claim(
        self,
        *,
        tenant_id: str,
        collection_id: str,
        text: str,
        evidence: List[Dict[str, Any]],
        source_policy: str,
        extractor_version: str,
        review_status: str,
        confidence: float,
        domain_id: str = "",
        claim_id: Optional[str] = None,
        status: str = "accepted",
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
        revision: int = 1,
        conflict_key: str = "",
        enforce_write_gates: bool = False,
        source_policy_db_path: Optional[str] = None,
        revision_actor: str = "",
        revision_reason: str = "",
    ) -> Dict[str, Any]:
        """写入 Claim；published 必须有 evidence；同 conflict_key 不同主张记冲突。

        Args:
            tenant_id: 租户。
            collection_id: 集合。
            text: 主张文本。
            evidence: 证据列表。
            source_policy: 来源策略。
            extractor_version: 抽取器版本。
            review_status: 审核状态。
            confidence: 置信度。
            domain_id: 业务域 ID（调用方传入）。
            claim_id: 可选 ID。
            status: Claim 状态。
            valid_from / valid_to: 有效期。
            revision: 修订号。
            conflict_key: 冲突键；空则不自动扫冲突。
            enforce_write_gates: True 时要求 source_policy 已登记。
            source_policy_db_path: 策略库路径。
            revision_actor: 修订归档 actor（可选；默认 put_claim）。
            revision_reason: 修订归档理由（可选；默认 supersede）。

        Returns:
            Claim 记录（可能含 ``conflict_id`` 若触发冲突记录）。

        Raises:
            FactLedgerError: 无证据 published / 未知 source / 策略未登记 / 无记录覆盖。
        """
        import aiosqlite

        self._validate_evidence(evidence, review_status=review_status)
        for ev in evidence:
            src = await self.get_source(str(ev["source_id"]), tenant_id=tenant_id)
            if src is None:
                raise FactLedgerError(
                    f"evidence source not found in tenant: {ev['source_id']}"
                )

        if enforce_write_gates:
            from core.harness.knowledge_pipeline.source_policy import get_source_policy

            pol_id = (source_policy or "").strip()
            if not pol_id:
                raise FactLedgerError("source_policy required")
            if (
                get_source_policy(
                    pol_id, tenant_id=tenant_id, db_path=source_policy_db_path
                )
                is None
            ):
                raise FactLedgerError(f"unknown source_policy: {pol_id}")

        cid = claim_id or f"cl-{uuid.uuid4().hex[:12]}"
        existing: Optional[Dict[str, Any]] = None
        if claim_id:
            existing = await self.get_claim(cid, tenant_id=tenant_id)
        ckey = (conflict_key or "").strip()
        recorded_at = _utc_now()
        vf = valid_from or recorded_at
        record = {
            "claim_id": cid,
            "tenant_id": tenant_id,
            "collection_id": collection_id,
            "domain_id": domain_id,
            "text": text,
            "evidence": evidence,
            "source_policy": source_policy,
            "extractor_version": extractor_version,
            "review_status": review_status,
            "confidence": float(confidence),
            "valid_from": vf,
            "valid_to": valid_to,
            "recorded_at": recorded_at,
            "revision": int(revision),
            "status": status,
            "conflict_key": ckey,
        }
        if existing is not None:
            # 为什么：内容不变视为幂等，避免无意义 revision 膨胀
            if self._claim_content_equal(existing, record):
                return existing
            # 为什么：N24 — Claim 内容变更必须抬 revision，旧快照进 claim_revisions
            if int(revision) <= int(existing.get("revision") or 1):
                raise FactLedgerError(
                    "claim content change requires revision bump "
                    f"(existing={existing.get('revision')}, got={revision})"
                )
            await self._archive_claim_revision(
                existing,
                actor=(revision_actor or "put_claim").strip() or "put_claim",
                reason=(revision_reason or "supersede").strip() or "supersede",
            )
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                INSERT OR REPLACE INTO claims (
                    claim_id, tenant_id, collection_id, domain_id, text,
                    evidence_json, source_policy, extractor_version, review_status,
                    confidence, valid_from, valid_to, recorded_at, revision, status,
                    conflict_key
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    cid,
                    tenant_id,
                    collection_id,
                    domain_id,
                    text,
                    json.dumps(evidence, ensure_ascii=False),
                    source_policy,
                    extractor_version,
                    review_status,
                    float(confidence),
                    vf,
                    valid_to,
                    recorded_at,
                    int(revision),
                    status,
                    ckey,
                ),
            )
            await db.commit()

        # 为什么：冲突只记录不裁决；同键不同主张 → open conflict
        if ckey:
            peers = await self.list_claims_by_conflict_key(
                tenant_id=tenant_id,
                collection_id=collection_id,
                conflict_key=ckey,
            )
            others = [
                p
                for p in peers
                if p.get("claim_id") != cid and str(p.get("text") or "") != str(text)
            ]
            if others:
                conf = await self.record_claim_conflict(
                    tenant_id=tenant_id,
                    collection_id=collection_id,
                    conflict_key=ckey,
                    claim_ids=[cid] + [str(p["claim_id"]) for p in others],
                    texts=[str(text)] + [str(p.get("text") or "") for p in others],
                )
                record["conflict_id"] = conf["conflict_id"]
        return record

    def _row_to_claim(self, row: Any) -> Dict[str, Any]:
        """将 claims 表行转为 Claim dict。

        Args:
            row: aiosqlite.Row 或兼容映射。
        """
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        return {
            "claim_id": row["claim_id"],
            "tenant_id": row["tenant_id"],
            "collection_id": row["collection_id"],
            "domain_id": row["domain_id"],
            "text": row["text"],
            "evidence": json.loads(row["evidence_json"] or "[]"),
            "source_policy": row["source_policy"],
            "extractor_version": row["extractor_version"],
            "review_status": row["review_status"],
            "confidence": row["confidence"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "recorded_at": row["recorded_at"],
            "revision": row["revision"],
            "status": row["status"],
            "conflict_key": row["conflict_key"] if "conflict_key" in keys else "",
        }

    async def get_claim(
        self,
        claim_id: str,
        *,
        tenant_id: str,
    ) -> Optional[Dict[str, Any]]:
        """按租户读取 Claim。

        Args:
            claim_id: Claim ID。
            tenant_id: 调用方租户。
        """
        import aiosqlite

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                "SELECT * FROM claims WHERE claim_id=? AND tenant_id=?",
                (claim_id, tenant_id),
            )
            row = await cur.fetchone()
        return self._row_to_claim(row) if row else None

    _CLAIM_CONTENT_KEYS = (
        "text",
        "evidence",
        "source_policy",
        "extractor_version",
        "review_status",
        "confidence",
        "valid_from",
        "valid_to",
        "status",
        "conflict_key",
    )

    def _claim_content_equal(
        self, left: Dict[str, Any], right: Dict[str, Any]
    ) -> bool:
        """比较 Claim 业务内容（忽略 revision / recorded_at / id）。

        Args:
            left: 已有 Claim。
            right: 待写入 Claim。

        Returns:
            True 表示内容等价（可幂等返回）。
        """
        for key in self._CLAIM_CONTENT_KEYS:
            lv = left.get(key)
            rv = right.get(key)
            if key == "evidence":
                lv = json.dumps(lv or [], ensure_ascii=False, sort_keys=True)
                rv = json.dumps(rv or [], ensure_ascii=False, sort_keys=True)
            elif key == "confidence":
                lv = float(lv or 0.0)
                rv = float(rv or 0.0)
            else:
                lv = "" if lv is None else lv
                rv = "" if rv is None else rv
            if lv != rv:
                return False
        return True

    async def _archive_claim_revision(
        self,
        claim: Dict[str, Any],
        *,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """将即将被覆盖的 Claim 快照写入 claim_revisions。

        Args:
            claim: 当前头版本快照。
            actor: 操作者。
            reason: 归档理由。

        Returns:
            修订行摘要。
        """
        import aiosqlite

        row_id = f"crev-{uuid.uuid4().hex[:12]}"
        recorded_at = _utc_now()
        snap = {k: v for k, v in claim.items() if k != "conflict_id"}
        entry = {
            "revision_row_id": row_id,
            "claim_id": claim["claim_id"],
            "tenant_id": claim["tenant_id"],
            "revision": int(claim.get("revision") or 1),
            "snapshot": snap,
            "actor": actor,
            "reason": reason,
            "recorded_at": recorded_at,
            "is_head": False,
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                INSERT INTO claim_revisions (
                    revision_row_id, claim_id, tenant_id, revision,
                    snapshot_json, actor, reason, recorded_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    row_id,
                    claim["claim_id"],
                    claim["tenant_id"],
                    int(claim.get("revision") or 1),
                    json.dumps(snap, ensure_ascii=False),
                    actor,
                    reason,
                    recorded_at,
                ),
            )
            await db.commit()
        await self._emit_revision_audit(
            tenant_id=str(claim["tenant_id"]),
            entity_type="claim",
            entity_id=str(claim["claim_id"]),
            event_type="archive",
            revision=int(claim.get("revision") or 1),
            actor=actor,
            reason=reason,
            detail={"revision_row_id": row_id},
        )
        return entry

    async def list_claim_revisions(
        self,
        claim_id: str,
        *,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """列出 Claim 修订历史（归档 + 当前头）。

        Args:
            claim_id: Claim ID。
            tenant_id: 调用方租户。

        Returns:
            按 revision 升序的条目（含 snapshot）。
        """
        import aiosqlite

        if not tenant_id:
            raise FactLedgerError("tenant_id required")
        out: List[Dict[str, Any]] = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                """
                SELECT * FROM claim_revisions
                WHERE claim_id=? AND tenant_id=?
                ORDER BY revision ASC
                """,
                (claim_id, tenant_id),
            )
            rows = await cur.fetchall()
        for row in rows:
            out.append(
                {
                    "revision_row_id": row["revision_row_id"],
                    "claim_id": row["claim_id"],
                    "tenant_id": row["tenant_id"],
                    "revision": int(row["revision"]),
                    "snapshot": json.loads(row["snapshot_json"] or "{}"),
                    "actor": row["actor"],
                    "reason": row["reason"],
                    "recorded_at": row["recorded_at"],
                    "is_head": False,
                }
            )
        head = await self.get_claim(claim_id, tenant_id=tenant_id)
        if head is not None:
            out.append(
                {
                    "revision_row_id": "",
                    "claim_id": claim_id,
                    "tenant_id": tenant_id,
                    "revision": int(head.get("revision") or 1),
                    "snapshot": head,
                    "actor": "head",
                    "reason": "current",
                    "recorded_at": head.get("recorded_at") or "",
                    "is_head": True,
                }
            )
        return out

    async def get_claim_at_revision(
        self,
        claim_id: str,
        *,
        tenant_id: str,
        revision: int,
    ) -> Optional[Dict[str, Any]]:
        """按 revision 读取 Claim 快照（头或归档）。

        Args:
            claim_id: Claim ID。
            tenant_id: 调用方租户。
            revision: 目标修订号。

        Returns:
            快照 dict；不存在则 None。
        """
        import aiosqlite

        head = await self.get_claim(claim_id, tenant_id=tenant_id)
        if head is not None and int(head.get("revision") or 1) == int(revision):
            return head
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                """
                SELECT snapshot_json FROM claim_revisions
                WHERE claim_id=? AND tenant_id=? AND revision=?
                """,
                (claim_id, tenant_id, int(revision)),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return json.loads(row["snapshot_json"] or "{}")

    async def diff_claim_revisions(
        self,
        claim_id: str,
        *,
        tenant_id: str,
        from_revision: int,
        to_revision: int,
    ) -> Dict[str, Any]:
        """比较两个 Claim revision 的内容字段差。

        Args:
            claim_id: Claim ID。
            tenant_id: 调用方租户。
            from_revision: 旧修订。
            to_revision: 新修订。

        Returns:
            diff 回执（changed 字段映射）。

        Raises:
            FactLedgerError: 任一 revision 缺失。
        """
        left = await self.get_claim_at_revision(
            claim_id, tenant_id=tenant_id, revision=int(from_revision)
        )
        right = await self.get_claim_at_revision(
            claim_id, tenant_id=tenant_id, revision=int(to_revision)
        )
        if left is None or right is None:
            raise FactLedgerError(
                f"claim revision not found: from={from_revision} to={to_revision}"
            )
        changed: Dict[str, Any] = {}
        for key in self._CLAIM_CONTENT_KEYS:
            lv = left.get(key)
            rv = right.get(key)
            if key == "evidence":
                same = json.dumps(lv or [], ensure_ascii=False, sort_keys=True) == json.dumps(
                    rv or [], ensure_ascii=False, sort_keys=True
                )
            elif key == "confidence":
                same = float(lv or 0.0) == float(rv or 0.0)
            else:
                same = ("" if lv is None else lv) == ("" if rv is None else rv)
            if not same:
                changed[key] = {"from": lv, "to": rv}
        return {
            "claim_id": claim_id,
            "tenant_id": tenant_id,
            "from_revision": int(from_revision),
            "to_revision": int(to_revision),
            "changed": changed,
            "unchanged": [k for k in self._CLAIM_CONTENT_KEYS if k not in changed],
        }

    async def list_claims_by_conflict_key(
        self,
        *,
        tenant_id: str,
        collection_id: str,
        conflict_key: str,
    ) -> List[Dict[str, Any]]:
        """列出同租户/集合/冲突键下的 Claim。

        Args:
            tenant_id: 租户。
            collection_id: 集合。
            conflict_key: 冲突键（空则返回空列表）。
        """
        import aiosqlite

        ckey = (conflict_key or "").strip()
        if not ckey:
            return []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                """
                SELECT * FROM claims
                WHERE tenant_id=? AND collection_id=? AND conflict_key=?
                ORDER BY recorded_at ASC
                """,
                (tenant_id, collection_id, ckey),
            )
            rows = await cur.fetchall()
        return [self._row_to_claim(r) for r in rows]

    async def record_claim_conflict(
        self,
        *,
        tenant_id: str,
        collection_id: str,
        conflict_key: str,
        claim_ids: List[str],
        texts: List[str],
        conflict_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """显式记录 Claim 冲突（open）；不自动裁决。

        Args:
            tenant_id: 租户。
            collection_id: 集合。
            conflict_key: 冲突键。
            claim_ids: 涉事 Claim。
            texts: 冲突主张文本。
            conflict_id: 可选显式 ID。

        Returns:
            冲突记录。

        Raises:
            FactLedgerError: 参数不足或主张不足两条。
        """
        import aiosqlite

        tid = (tenant_id or "").strip()
        cid = (collection_id or "").strip()
        ckey = (conflict_key or "").strip()
        if not tid or not cid or not ckey:
            raise FactLedgerError(
                "tenant_id, collection_id, conflict_key required for claim conflict"
            )
        if len(set(texts)) < 2 or len(claim_ids) < 2:
            raise FactLedgerError("claim conflict requires >=2 distinct texts/claim_ids")
        conf_id = conflict_id or f"cc-{uuid.uuid4().hex[:12]}"
        created_at = _utc_now()
        record = {
            "conflict_id": conf_id,
            "tenant_id": tid,
            "collection_id": cid,
            "conflict_key": ckey,
            "claim_ids": list(claim_ids),
            "texts": list(texts),
            "status": "open",
            "created_at": created_at,
            "resolved_at": None,
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                INSERT OR REPLACE INTO claim_conflicts (
                    conflict_id, tenant_id, collection_id, conflict_key,
                    claim_ids_json, texts_json, status, created_at, resolved_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    conf_id,
                    tid,
                    cid,
                    ckey,
                    json.dumps(record["claim_ids"], ensure_ascii=False),
                    json.dumps(record["texts"], ensure_ascii=False),
                    "open",
                    created_at,
                    None,
                ),
            )
            await db.commit()
        return record

    async def list_claim_conflicts(
        self,
        *,
        tenant_id: str,
        collection_id: Optional[str] = None,
        conflict_key: Optional[str] = None,
        status: str = "open",
    ) -> List[Dict[str, Any]]:
        """列出 Claim 冲突。

        Args:
            tenant_id: 租户。
            collection_id: 可选集合过滤。
            conflict_key: 可选冲突键过滤。
            status: 状态过滤；空串表示不过滤。
        """
        import aiosqlite

        clauses = ["tenant_id=?"]
        args: List[Any] = [tenant_id]
        if collection_id:
            clauses.append("collection_id=?")
            args.append(collection_id)
        if conflict_key:
            clauses.append("conflict_key=?")
            args.append(conflict_key)
        if status:
            clauses.append("status=?")
            args.append(status)
        sql = (
            "SELECT * FROM claim_conflicts WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC"
        )
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(sql, args)
            rows = await cur.fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "conflict_id": row["conflict_id"],
                    "tenant_id": row["tenant_id"],
                    "collection_id": row["collection_id"],
                    "conflict_key": row["conflict_key"],
                    "claim_ids": json.loads(row["claim_ids_json"] or "[]"),
                    "texts": json.loads(row["texts_json"] or "[]"),
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "resolved_at": row["resolved_at"],
                }
            )
        return out

    _FACT_CONTENT_KEYS = (
        "subject",
        "predicate",
        "object",
        "evidence",
        "source_policy",
        "extractor_version",
        "review_status",
        "confidence",
        "valid_from",
        "valid_to",
        "status",
        "inferred",
    )

    def _fact_content_equal(
        self, left: Dict[str, Any], right: Dict[str, Any]
    ) -> bool:
        """比较 Fact 业务内容（忽略 revision / recorded_at / id）。

        Args:
            left: 已有 Fact。
            right: 待写入 Fact。

        Returns:
            True 表示内容等价（可幂等返回）。
        """
        for key in self._FACT_CONTENT_KEYS:
            lv = left.get(key)
            rv = right.get(key)
            if key == "evidence":
                lv = json.dumps(lv or [], ensure_ascii=False, sort_keys=True)
                rv = json.dumps(rv or [], ensure_ascii=False, sort_keys=True)
            elif key == "confidence":
                lv = float(lv or 0.0)
                rv = float(rv or 0.0)
            elif key == "inferred":
                lv = bool(lv)
                rv = bool(rv)
            else:
                lv = "" if lv is None else lv
                rv = "" if rv is None else rv
            if lv != rv:
                return False
        return True

    async def _archive_fact_revision(
        self,
        fact: Dict[str, Any],
        *,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """将即将被覆盖的 Fact 快照写入 fact_revisions。

        Args:
            fact: 当前头版本快照。
            actor: 操作者。
            reason: 归档理由。

        Returns:
            修订行摘要。
        """
        import aiosqlite

        row_id = f"frev-{uuid.uuid4().hex[:12]}"
        recorded_at = _utc_now()
        entry = {
            "revision_row_id": row_id,
            "fact_id": fact["fact_id"],
            "tenant_id": fact["tenant_id"],
            "revision": int(fact.get("revision") or 1),
            "snapshot": dict(fact),
            "actor": actor,
            "reason": reason,
            "recorded_at": recorded_at,
            "is_head": False,
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                INSERT INTO fact_revisions (
                    revision_row_id, fact_id, tenant_id, revision,
                    snapshot_json, actor, reason, recorded_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    row_id,
                    fact["fact_id"],
                    fact["tenant_id"],
                    int(fact.get("revision") or 1),
                    json.dumps(fact, ensure_ascii=False),
                    actor,
                    reason,
                    recorded_at,
                ),
            )
            await db.commit()
        await self._emit_revision_audit(
            tenant_id=str(fact["tenant_id"]),
            entity_type="fact",
            entity_id=str(fact["fact_id"]),
            event_type="archive",
            revision=int(fact.get("revision") or 1),
            actor=actor,
            reason=reason,
            detail={"revision_row_id": row_id},
        )
        return entry

    async def list_fact_revisions(
        self,
        fact_id: str,
        *,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """列出 Fact 修订历史（归档 + 当前头）。

        Args:
            fact_id: Fact ID。
            tenant_id: 调用方租户。

        Returns:
            按 revision 升序的条目（含 snapshot）。
        """
        import aiosqlite

        if not tenant_id:
            raise FactLedgerError("tenant_id required")
        out: List[Dict[str, Any]] = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                """
                SELECT * FROM fact_revisions
                WHERE fact_id=? AND tenant_id=?
                ORDER BY revision ASC
                """,
                (fact_id, tenant_id),
            )
            rows = await cur.fetchall()
        for row in rows:
            out.append(
                {
                    "revision_row_id": row["revision_row_id"],
                    "fact_id": row["fact_id"],
                    "tenant_id": row["tenant_id"],
                    "revision": int(row["revision"]),
                    "snapshot": json.loads(row["snapshot_json"] or "{}"),
                    "actor": row["actor"],
                    "reason": row["reason"],
                    "recorded_at": row["recorded_at"],
                    "is_head": False,
                }
            )
        head = await self.get_fact(fact_id, tenant_id=tenant_id)
        if head is not None:
            out.append(
                {
                    "revision_row_id": "",
                    "fact_id": fact_id,
                    "tenant_id": tenant_id,
                    "revision": int(head.get("revision") or 1),
                    "snapshot": head,
                    "actor": "head",
                    "reason": "current",
                    "recorded_at": head.get("recorded_at") or "",
                    "is_head": True,
                }
            )
        return out

    async def get_fact_at_revision(
        self,
        fact_id: str,
        *,
        tenant_id: str,
        revision: int,
    ) -> Optional[Dict[str, Any]]:
        """按 revision 读取 Fact 快照（头或归档）。

        Args:
            fact_id: Fact ID。
            tenant_id: 调用方租户。
            revision: 目标修订号。

        Returns:
            快照 dict；不存在则 None。
        """
        import aiosqlite

        head = await self.get_fact(fact_id, tenant_id=tenant_id)
        if head is not None and int(head.get("revision") or 1) == int(revision):
            return head
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                """
                SELECT snapshot_json FROM fact_revisions
                WHERE fact_id=? AND tenant_id=? AND revision=?
                """,
                (fact_id, tenant_id, int(revision)),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return json.loads(row["snapshot_json"] or "{}")

    async def diff_fact_revisions(
        self,
        fact_id: str,
        *,
        tenant_id: str,
        from_revision: int,
        to_revision: int,
    ) -> Dict[str, Any]:
        """比较两个 revision 的内容字段差。

        Args:
            fact_id: Fact ID。
            tenant_id: 调用方租户。
            from_revision: 旧修订。
            to_revision: 新修订。

        Returns:
            diff 回执（changed 字段映射）。

        Raises:
            FactLedgerError: 任一 revision 缺失。
        """
        left = await self.get_fact_at_revision(
            fact_id, tenant_id=tenant_id, revision=int(from_revision)
        )
        right = await self.get_fact_at_revision(
            fact_id, tenant_id=tenant_id, revision=int(to_revision)
        )
        if left is None or right is None:
            raise FactLedgerError(
                f"revision not found: from={from_revision} to={to_revision}"
            )
        changed: Dict[str, Any] = {}
        for key in self._FACT_CONTENT_KEYS:
            lv = left.get(key)
            rv = right.get(key)
            if key == "evidence":
                same = json.dumps(lv or [], ensure_ascii=False, sort_keys=True) == json.dumps(
                    rv or [], ensure_ascii=False, sort_keys=True
                )
            elif key == "confidence":
                same = float(lv or 0.0) == float(rv or 0.0)
            elif key == "inferred":
                same = bool(lv) == bool(rv)
            else:
                same = ("" if lv is None else lv) == ("" if rv is None else rv)
            if not same:
                changed[key] = {"from": lv, "to": rv}
        return {
            "fact_id": fact_id,
            "tenant_id": tenant_id,
            "from_revision": int(from_revision),
            "to_revision": int(to_revision),
            "changed": changed,
            "unchanged": [k for k in self._FACT_CONTENT_KEYS if k not in changed],
        }

    async def restore_fact_at_revision(
        self,
        fact_id: str,
        *,
        tenant_id: str,
        target_revision: int,
        actor: str,
        reason: str,
        enforce_write_gates: bool = False,
        source_policy_db_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """按目标 revision 恢复 Fact 内容为新头（抬号；保留当前审核/生命周期态）。

        Args:
            fact_id: Fact ID。
            tenant_id: 调用方租户。
            target_revision: 要恢复的归档/历史修订号。
            actor: 操作者（必填）。
            reason: 理由（必填）。
            enforce_write_gates: 透传 put_fact 硬门（默认关，与 revision suite 一致）。
            source_policy_db_path: 策略库路径。

        Returns:
            restore 回执（含 ``restored`` / ``idempotent`` / ``fact``）。

        Raises:
            FactLedgerError: 缺 actor/reason、头或目标 revision 缺失。
        """
        who = (actor or "").strip()
        why = (reason or "").strip()
        if not who or not why:
            raise FactLedgerError("restore requires actor and reason")
        head = await self.get_fact(fact_id, tenant_id=tenant_id)
        if head is None:
            raise FactLedgerError(f"fact not found: {fact_id}")
        snap = await self.get_fact_at_revision(
            fact_id, tenant_id=tenant_id, revision=int(target_revision)
        )
        if snap is None:
            raise FactLedgerError(f"fact revision not found: {target_revision}")
        # 为什么：恢复内容字段，但审核/生命周期态保留当前头，避免绕过 transition
        effective = dict(snap)
        effective["review_status"] = head.get("review_status")
        effective["status"] = head.get("status")
        from_rev = int(head.get("revision") or 1)
        if self._fact_content_equal(head, effective):
            return {
                "restored": False,
                "idempotent": True,
                "fact_id": fact_id,
                "tenant_id": tenant_id,
                "target_revision": int(target_revision),
                "from_revision": from_rev,
                "to_revision": from_rev,
                "fact": head,
                "actor": who,
                "reason": why,
            }
        updated = await self.put_fact(
            tenant_id=tenant_id,
            collection_id=str(snap.get("collection_id") or head.get("collection_id") or ""),
            subject=str(snap.get("subject") or ""),
            predicate=str(snap.get("predicate") or ""),
            object=str(snap.get("object") or ""),
            evidence=list(snap.get("evidence") or []),
            source_policy=str(snap.get("source_policy") or ""),
            extractor_version=str(snap.get("extractor_version") or ""),
            review_status=str(head.get("review_status") or "draft"),
            confidence=float(snap.get("confidence") or 0.0),
            domain_id=str(snap.get("domain_id") or head.get("domain_id") or ""),
            fact_id=fact_id,
            status=str(head.get("status") or "active"),
            inferred=bool(snap.get("inferred")),
            valid_from=snap.get("valid_from"),
            valid_to=snap.get("valid_to"),
            revision=from_rev + 1,
            enforce_write_gates=enforce_write_gates,
            source_policy_db_path=source_policy_db_path,
            revision_actor=who,
            revision_reason=why,
        )
        to_rev = int(updated.get("revision") or (from_rev + 1))
        await self._emit_revision_audit(
            tenant_id=tenant_id,
            entity_type="fact",
            entity_id=fact_id,
            event_type="restore",
            revision=int(target_revision),
            to_revision=to_rev,
            actor=who,
            reason=why,
            detail={"from_revision": from_rev},
        )
        return {
            "restored": True,
            "idempotent": False,
            "fact_id": fact_id,
            "tenant_id": tenant_id,
            "target_revision": int(target_revision),
            "from_revision": from_rev,
            "to_revision": to_rev,
            "fact": updated,
            "actor": who,
            "reason": why,
        }

    async def restore_claim_at_revision(
        self,
        claim_id: str,
        *,
        tenant_id: str,
        target_revision: int,
        actor: str,
        reason: str,
        enforce_write_gates: bool = False,
        source_policy_db_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """按目标 revision 恢复 Claim 内容为新头（抬号；保留当前审核/状态）。

        Args:
            claim_id: Claim ID。
            tenant_id: 调用方租户。
            target_revision: 目标修订号。
            actor: 操作者（必填）。
            reason: 理由（必填）。
            enforce_write_gates: 透传 put_claim 硬门。
            source_policy_db_path: 策略库路径。

        Returns:
            restore 回执。

        Raises:
            FactLedgerError: 缺 actor/reason、头或目标 revision 缺失。
        """
        who = (actor or "").strip()
        why = (reason or "").strip()
        if not who or not why:
            raise FactLedgerError("restore requires actor and reason")
        head = await self.get_claim(claim_id, tenant_id=tenant_id)
        if head is None:
            raise FactLedgerError(f"claim not found: {claim_id}")
        snap = await self.get_claim_at_revision(
            claim_id, tenant_id=tenant_id, revision=int(target_revision)
        )
        if snap is None:
            raise FactLedgerError(f"claim revision not found: {target_revision}")
        effective = dict(snap)
        effective["review_status"] = head.get("review_status")
        effective["status"] = head.get("status")
        from_rev = int(head.get("revision") or 1)
        if self._claim_content_equal(head, effective):
            return {
                "restored": False,
                "idempotent": True,
                "claim_id": claim_id,
                "tenant_id": tenant_id,
                "target_revision": int(target_revision),
                "from_revision": from_rev,
                "to_revision": from_rev,
                "claim": head,
                "actor": who,
                "reason": why,
            }
        updated = await self.put_claim(
            tenant_id=tenant_id,
            collection_id=str(snap.get("collection_id") or head.get("collection_id") or ""),
            text=str(snap.get("text") or ""),
            evidence=list(snap.get("evidence") or []),
            source_policy=str(snap.get("source_policy") or ""),
            extractor_version=str(snap.get("extractor_version") or ""),
            review_status=str(head.get("review_status") or "draft"),
            confidence=float(snap.get("confidence") or 0.0),
            domain_id=str(snap.get("domain_id") or head.get("domain_id") or ""),
            claim_id=claim_id,
            status=str(head.get("status") or "accepted"),
            valid_from=snap.get("valid_from"),
            valid_to=snap.get("valid_to"),
            revision=from_rev + 1,
            conflict_key=str(snap.get("conflict_key") or ""),
            enforce_write_gates=enforce_write_gates,
            source_policy_db_path=source_policy_db_path,
            revision_actor=who,
            revision_reason=why,
        )
        to_rev = int(updated.get("revision") or (from_rev + 1))
        await self._emit_revision_audit(
            tenant_id=tenant_id,
            entity_type="claim",
            entity_id=claim_id,
            event_type="restore",
            revision=int(target_revision),
            to_revision=to_rev,
            actor=who,
            reason=why,
            detail={"from_revision": from_rev},
        )
        return {
            "restored": True,
            "idempotent": False,
            "claim_id": claim_id,
            "tenant_id": tenant_id,
            "target_revision": int(target_revision),
            "from_revision": from_rev,
            "to_revision": to_rev,
            "claim": updated,
            "actor": who,
            "reason": why,
        }

    async def restore_source_at_revision(
        self,
        source_id: str,
        *,
        tenant_id: str,
        target_revision: int,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """按目标 revision 恢复 Source 元数据+Raw 为新头（抬号；旧文件保留）。

        Args:
            source_id: Source ID。
            tenant_id: 调用方租户。
            target_revision: 目标修订号。
            actor: 操作者（必填）。
            reason: 理由（必填）。

        Returns:
            restore 回执。

        Raises:
            FactLedgerError: 缺 actor/reason、头/目标缺失、归档快照文件不可读。
        """
        who = (actor or "").strip()
        why = (reason or "").strip()
        if not who or not why:
            raise FactLedgerError("restore requires actor and reason")
        head = await self.get_source(source_id, tenant_id=tenant_id)
        if head is None:
            raise FactLedgerError(f"source not found: {source_id}")
        snap = await self.get_source_at_revision(
            source_id, tenant_id=tenant_id, revision=int(target_revision)
        )
        if snap is None:
            raise FactLedgerError(f"source revision not found: {target_revision}")
        effective = dict(snap)
        effective["status"] = head.get("status")
        from_rev = int(head.get("revision") or 1)
        # 为什么：Source 幂等以 sha256/内容键为准；status 取当前头
        content_same = True
        for key in self._SOURCE_CONTENT_KEYS:
            if key == "status":
                continue
            lv = head.get(key)
            rv = effective.get(key)
            if key == "acl":
                same = json.dumps(lv or [], ensure_ascii=False, sort_keys=True) == json.dumps(
                    rv or [], ensure_ascii=False, sort_keys=True
                )
            else:
                same = ("" if lv is None else lv) == ("" if rv is None else rv)
            if not same:
                content_same = False
                break
        if content_same:
            return {
                "restored": False,
                "idempotent": True,
                "source_id": source_id,
                "tenant_id": tenant_id,
                "target_revision": int(target_revision),
                "from_revision": from_rev,
                "to_revision": from_rev,
                "source": head,
                "actor": who,
                "reason": why,
            }
        snap_path = Path(str(snap.get("snapshot_uri") or ""))
        if not snap_path.is_file():
            raise FactLedgerError(f"archived snapshot missing: {snap_path}")
        content = snap_path.read_bytes()
        digest = _sha256_bytes(content)
        if digest != str(snap.get("sha256") or ""):
            raise FactLedgerError(
                f"archived snapshot hash mismatch: file={digest} meta={snap.get('sha256')}"
            )
        updated = await self.register_source(
            tenant_id=tenant_id,
            collection_id=str(snap.get("collection_id") or head.get("collection_id") or ""),
            kind=str(snap.get("kind") or "file"),
            uri=str(snap.get("uri") or ""),
            content=content,
            connector=str(snap.get("connector") or ""),
            acl=list(snap.get("acl") or head.get("acl") or []),
            domain_id=str(snap.get("domain_id") or head.get("domain_id") or ""),
            license=str(snap.get("license") or "company-internal"),
            source_id=source_id,
            revision=from_rev + 1,
            revision_actor=who,
            revision_reason=why,
        )
        to_rev = int(updated.get("revision") or (from_rev + 1))
        await self._emit_revision_audit(
            tenant_id=tenant_id,
            entity_type="source",
            entity_id=source_id,
            event_type="restore",
            revision=int(target_revision),
            to_revision=to_rev,
            actor=who,
            reason=why,
            detail={"from_revision": from_rev},
        )
        return {
            "restored": True,
            "idempotent": False,
            "source_id": source_id,
            "tenant_id": tenant_id,
            "target_revision": int(target_revision),
            "from_revision": from_rev,
            "to_revision": to_rev,
            "source": updated,
            "actor": who,
            "reason": why,
        }

    async def _emit_revision_audit(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        event_type: str,
        revision: int,
        actor: str,
        reason: str,
        to_revision: Optional[int] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """写入一条 append-only revision_audit 事件。

        Args:
            tenant_id: 租户。
            entity_type: ``fact`` / ``claim`` / ``source``。
            entity_id: 实体 ID。
            event_type: ``archive`` / ``restore`` / ``restore_request`` /
                ``restore_approve`` / ``restore_reject``。
            revision: 归档修订号，或 restore 的目标修订号。
            actor: 操作者。
            reason: 理由。
            to_revision: restore 后新头修订号（可选）。
            detail: 附加详情。

        Returns:
            审计事件摘要。

        Raises:
            FactLedgerError: 参数非法。
        """
        import aiosqlite

        et = (entity_type or "").strip()
        eid = (entity_id or "").strip()
        ev = (event_type or "").strip()
        who = (actor or "").strip()
        why = (reason or "").strip()
        if not tenant_id or not et or not eid or not ev or not who or not why:
            raise FactLedgerError("revision_audit requires tenant/entity/event/actor/reason")
        if et not in ("fact", "claim", "source"):
            raise FactLedgerError(f"unsupported entity_type: {et}")
        if ev not in (
            "archive",
            "restore",
            "restore_request",
            "restore_approve",
            "restore_reject",
        ):
            raise FactLedgerError(f"unsupported event_type: {ev}")
        audit_id = f"raud-{uuid.uuid4().hex[:12]}"
        recorded_at = _utc_now()
        detail_obj = dict(detail or {})
        entry = {
            "audit_id": audit_id,
            "tenant_id": tenant_id,
            "entity_type": et,
            "entity_id": eid,
            "event_type": ev,
            "revision": int(revision),
            "to_revision": None if to_revision is None else int(to_revision),
            "actor": who,
            "reason": why,
            "detail": detail_obj,
            "recorded_at": recorded_at,
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                INSERT INTO revision_audit (
                    audit_id, tenant_id, entity_type, entity_id, event_type,
                    revision, to_revision, actor, reason, detail_json, recorded_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    audit_id,
                    tenant_id,
                    et,
                    eid,
                    ev,
                    int(revision),
                    None if to_revision is None else int(to_revision),
                    who,
                    why,
                    json.dumps(detail_obj, ensure_ascii=False),
                    recorded_at,
                ),
            )
            await db.commit()
        # 为什么：N24 J5 — revision_audit 热路径 best-effort 写入统一审计总线（非 ActionStore 合并）
        try:
            from core.harness.knowledge_pipeline.unified_audit_bus import (
                append_unified_audit_event,
            )

            occ = 0.0
            try:
                from datetime import datetime

                occ = datetime.fromisoformat(
                    str(recorded_at).replace("Z", "+00:00")
                ).timestamp()
            except (TypeError, ValueError, AttributeError):
                occ = 0.0
            append_unified_audit_event(
                tenant_id=tenant_id,
                event_id=audit_id,
                stream="revision_audit",
                event_type=ev,
                occurred_at=occ,
                actor=who,
                subject=f"{et}:{eid}",
                refs={
                    "revision": int(revision),
                    "to_revision": None if to_revision is None else int(to_revision),
                    "reason": why,
                },
                payload=entry,
            )
        except Exception:
            logger.warning(
                "unified_audit_bus append failed for revision_audit %s",
                audit_id,
                exc_info=True,
            )
        return entry

    async def list_revision_audit(
        self,
        *,
        tenant_id: str,
        entity_type: str = "",
        entity_id: str = "",
        event_type: str = "",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """按租户列出 revision_audit 事件（可选实体/事件过滤）。

        Args:
            tenant_id: 调用方租户（必填；召回前过滤）。
            entity_type: 可选 ``fact`` / ``claim`` / ``source``。
            entity_id: 可选实体 ID。
            event_type: 可选 ``archive`` / ``restore``。
            limit: 最大返回条数（1–500）。

        Returns:
            按 recorded_at 升序的事件列表。

        Raises:
            FactLedgerError: tenant_id 为空。
        """
        import aiosqlite

        if not tenant_id:
            raise FactLedgerError("tenant_id required")
        lim = max(1, min(int(limit or 100), 500))
        clauses = ["tenant_id=?"]
        params: List[Any] = [tenant_id]
        et = (entity_type or "").strip()
        eid = (entity_id or "").strip()
        ev = (event_type or "").strip()
        if et:
            clauses.append("entity_type=?")
            params.append(et)
        if eid:
            clauses.append("entity_id=?")
            params.append(eid)
        if ev:
            clauses.append("event_type=?")
            params.append(ev)
        where = " AND ".join(clauses)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                f"""
                SELECT * FROM revision_audit
                WHERE {where}
                ORDER BY recorded_at ASC, audit_id ASC
                LIMIT ?
                """,
                (*params, lim),
            )
            rows = await cur.fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "audit_id": row["audit_id"],
                    "tenant_id": row["tenant_id"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "event_type": row["event_type"],
                    "revision": int(row["revision"]),
                    "to_revision": (
                        None
                        if row["to_revision"] is None
                        else int(row["to_revision"])
                    ),
                    "actor": row["actor"],
                    "reason": row["reason"],
                    "detail": json.loads(row["detail_json"] or "{}"),
                    "recorded_at": row["recorded_at"],
                }
            )
        return out

    async def request_revision_restore(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        target_revision: int,
        requester: str,
        reason: str,
    ) -> Dict[str, Any]:
        """提交审批式 restore 请求（不立即写回头）。

        Args:
            tenant_id: 租户。
            entity_type: ``fact`` / ``claim`` / ``source``。
            entity_id: 实体 ID。
            target_revision: 目标修订号。
            requester: 请求人（必填）。
            reason: 请求理由（必填）。

        Returns:
            pending 请求摘要。

        Raises:
            FactLedgerError: 参数非法、目标缺失、已有 pending。
        """
        import aiosqlite

        who = (requester or "").strip()
        why = (reason or "").strip()
        et = (entity_type or "").strip()
        eid = (entity_id or "").strip()
        if not tenant_id or not who or not why or not et or not eid:
            raise FactLedgerError("restore request requires tenant/entity/requester/reason")
        if et not in ("fact", "claim", "source"):
            raise FactLedgerError(f"unsupported entity_type: {et}")
        # 为什么：请求前确认目标 revision 可读，避免空批
        if et == "fact":
            snap = await self.get_fact_at_revision(
                eid, tenant_id=tenant_id, revision=int(target_revision)
            )
        elif et == "claim":
            snap = await self.get_claim_at_revision(
                eid, tenant_id=tenant_id, revision=int(target_revision)
            )
        else:
            snap = await self.get_source_at_revision(
                eid, tenant_id=tenant_id, revision=int(target_revision)
            )
        if snap is None:
            raise FactLedgerError(f"{et} revision not found: {target_revision}")
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                """
                SELECT request_id FROM revision_restore_requests
                WHERE tenant_id=? AND entity_type=? AND entity_id=? AND status='pending'
                """,
                (tenant_id, et, eid),
            )
            if await cur.fetchone() is not None:
                raise FactLedgerError(
                    f"pending restore request already exists for {et}:{eid}"
                )
            request_id = f"rrq-{uuid.uuid4().hex[:12]}"
            created_at = _utc_now()
            await db.execute(
                """
                INSERT INTO revision_restore_requests (
                    request_id, tenant_id, entity_type, entity_id, target_revision,
                    requester, request_reason, status, created_at
                ) VALUES (?,?,?,?,?,?,?,'pending',?)
                """,
                (
                    request_id,
                    tenant_id,
                    et,
                    eid,
                    int(target_revision),
                    who,
                    why,
                    created_at,
                ),
            )
            await db.commit()
        await self._emit_revision_audit(
            tenant_id=tenant_id,
            entity_type=et,
            entity_id=eid,
            event_type="restore_request",
            revision=int(target_revision),
            actor=who,
            reason=why,
            detail={"request_id": request_id},
        )
        return {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "entity_type": et,
            "entity_id": eid,
            "target_revision": int(target_revision),
            "requester": who,
            "request_reason": why,
            "status": "pending",
            "created_at": created_at,
        }

    async def list_revision_restore_requests(
        self,
        *,
        tenant_id: str,
        status: str = "",
        entity_type: str = "",
        entity_id: str = "",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """列出审批式 restore 请求。

        Args:
            tenant_id: 租户（必填）。
            status: 可选 ``pending`` / ``approved`` / ``rejected``。
            entity_type: 可选实体类型。
            entity_id: 可选实体 ID。
            limit: 最大条数。

        Returns:
            请求列表（created_at 升序）。
        """
        import aiosqlite

        if not tenant_id:
            raise FactLedgerError("tenant_id required")
        lim = max(1, min(int(limit or 100), 500))
        clauses = ["tenant_id=?"]
        params: List[Any] = [tenant_id]
        st = (status or "").strip()
        et = (entity_type or "").strip()
        eid = (entity_id or "").strip()
        if st:
            clauses.append("status=?")
            params.append(st)
        if et:
            clauses.append("entity_type=?")
            params.append(et)
        if eid:
            clauses.append("entity_id=?")
            params.append(eid)
        where = " AND ".join(clauses)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                f"""
                SELECT * FROM revision_restore_requests
                WHERE {where}
                ORDER BY created_at ASC, request_id ASC
                LIMIT ?
                """,
                (*params, lim),
            )
            rows = await cur.fetchall()
        return [self._row_to_restore_request(r) for r in rows]

    def _row_to_restore_request(self, row: Any) -> Dict[str, Any]:
        """将 revision_restore_requests 行转为 dict。

        Args:
            row: aiosqlite.Row。
        """
        receipt = None
        raw = row["restore_receipt_json"]
        if raw:
            receipt = json.loads(raw)
        return {
            "request_id": row["request_id"],
            "tenant_id": row["tenant_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "target_revision": int(row["target_revision"]),
            "requester": row["requester"],
            "request_reason": row["request_reason"],
            "status": row["status"],
            "approver": row["approver"],
            "decision_reason": row["decision_reason"],
            "restore_receipt": receipt,
            "created_at": row["created_at"],
            "decided_at": row["decided_at"],
        }

    async def approve_revision_restore(
        self,
        request_id: str,
        *,
        tenant_id: str,
        approver: str,
        reason: str,
    ) -> Dict[str, Any]:
        """批准并执行 restore；审批人不得与请求人相同。

        Args:
            request_id: 请求 ID。
            tenant_id: 租户。
            approver: 审批人（必填，且 ≠ requester）。
            reason: 批准理由（必填）。

        Returns:
            含 restore 回执的请求摘要。

        Raises:
            FactLedgerError: 缺失/非 pending/自批/执行失败。
        """
        import aiosqlite

        who = (approver or "").strip()
        why = (reason or "").strip()
        if not tenant_id or not who or not why:
            raise FactLedgerError("approve requires tenant/approver/reason")
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                """
                SELECT * FROM revision_restore_requests
                WHERE request_id=? AND tenant_id=?
                """,
                (request_id, tenant_id),
            )
            row = await cur.fetchone()
        if row is None:
            raise FactLedgerError(f"restore request not found: {request_id}")
        req = self._row_to_restore_request(row)
        if req["status"] != "pending":
            raise FactLedgerError(
                f"restore request not pending: {req['status']}"
            )
        if who == str(req["requester"] or "").strip():
            # 为什么：审批式硬门 — 禁止自批
            raise FactLedgerError("approver must differ from requester")
        et = req["entity_type"]
        eid = req["entity_id"]
        target = int(req["target_revision"])
        if et == "fact":
            receipt = await self.restore_fact_at_revision(
                eid,
                tenant_id=tenant_id,
                target_revision=target,
                actor=who,
                reason=why,
                enforce_write_gates=False,
            )
        elif et == "claim":
            receipt = await self.restore_claim_at_revision(
                eid,
                tenant_id=tenant_id,
                target_revision=target,
                actor=who,
                reason=why,
                enforce_write_gates=False,
            )
        else:
            receipt = await self.restore_source_at_revision(
                eid,
                tenant_id=tenant_id,
                target_revision=target,
                actor=who,
                reason=why,
            )
        decided_at = _utc_now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                UPDATE revision_restore_requests SET
                    status='approved',
                    approver=?,
                    decision_reason=?,
                    restore_receipt_json=?,
                    decided_at=?
                WHERE request_id=? AND tenant_id=? AND status='pending'
                """,
                (
                    who,
                    why,
                    json.dumps(receipt, ensure_ascii=False),
                    decided_at,
                    request_id,
                    tenant_id,
                ),
            )
            await db.commit()
        audit = await self._emit_revision_audit(
            tenant_id=tenant_id,
            entity_type=et,
            entity_id=eid,
            event_type="restore_approve",
            revision=target,
            to_revision=receipt.get("to_revision"),
            actor=who,
            reason=why,
            detail={"request_id": request_id, "restored": receipt.get("restored")},
        )
        bridge = await self.bridge_revision_audit_to_action(
            audit_event=audit,
            action_id="knowledge_revision:restore_approve",
        )
        req.update(
            {
                "status": "approved",
                "approver": who,
                "decision_reason": why,
                "restore_receipt": receipt,
                "decided_at": decided_at,
                "action_bridge": bridge,
            }
        )
        return req

    async def reject_revision_restore(
        self,
        request_id: str,
        *,
        tenant_id: str,
        rejector: str,
        reason: str,
    ) -> Dict[str, Any]:
        """拒绝 pending restore 请求（不写回头）。

        Args:
            request_id: 请求 ID。
            tenant_id: 租户。
            rejector: 拒绝人（必填）。
            reason: 拒绝理由（必填）。

        Returns:
            拒绝后的请求摘要。

        Raises:
            FactLedgerError: 缺失/非 pending。
        """
        import aiosqlite

        who = (rejector or "").strip()
        why = (reason or "").strip()
        if not tenant_id or not who or not why:
            raise FactLedgerError("reject requires tenant/rejector/reason")
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                """
                SELECT * FROM revision_restore_requests
                WHERE request_id=? AND tenant_id=?
                """,
                (request_id, tenant_id),
            )
            row = await cur.fetchone()
        if row is None:
            raise FactLedgerError(f"restore request not found: {request_id}")
        req = self._row_to_restore_request(row)
        if req["status"] != "pending":
            raise FactLedgerError(
                f"restore request not pending: {req['status']}"
            )
        decided_at = _utc_now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                UPDATE revision_restore_requests SET
                    status='rejected',
                    approver=?,
                    decision_reason=?,
                    decided_at=?
                WHERE request_id=? AND tenant_id=? AND status='pending'
                """,
                (who, why, decided_at, request_id, tenant_id),
            )
            await db.commit()
        audit = await self._emit_revision_audit(
            tenant_id=tenant_id,
            entity_type=str(req["entity_type"]),
            entity_id=str(req["entity_id"]),
            event_type="restore_reject",
            revision=int(req["target_revision"]),
            actor=who,
            reason=why,
            detail={"request_id": request_id},
        )
        bridge = await self.bridge_revision_audit_to_action(
            audit_event=audit,
            action_id="knowledge_revision:restore_reject",
        )
        req.update(
            {
                "status": "rejected",
                "approver": who,
                "decision_reason": why,
                "decided_at": decided_at,
                "action_bridge": bridge,
            }
        )
        return req

    async def bridge_revision_audit_to_action(
        self,
        *,
        audit_event: Dict[str, Any],
        action_id: str,
    ) -> Dict[str, Any]:
        """将 revision_audit 事件桥接到 ActionExecution（幂等）。

        Args:
            audit_event: ``_emit_revision_audit`` 回执。
            action_id: ActionExecution.action_id（如 ``knowledge_revision:restore_approve``）。

        Returns:
            bridge 摘要（含 execution_id）。

        Raises:
            FactLedgerError: 审计事件缺字段。
        """
        import aiosqlite
        import time as _time

        from core.harness.infrastructure.action_execution import persist_execution

        tenant_id = str(audit_event.get("tenant_id") or "").strip()
        audit_id = str(audit_event.get("audit_id") or "").strip()
        et = str(audit_event.get("entity_type") or "").strip()
        eid = str(audit_event.get("entity_id") or "").strip()
        ev = str(audit_event.get("event_type") or "").strip()
        aid = (action_id or "").strip()
        if not tenant_id or not audit_id or not et or not eid or not ev or not aid:
            raise FactLedgerError("bridge requires audit_event fields and action_id")
        # 为什么：同 audit_id 幂等，避免批准重试双写 ActionExecution
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                """
                SELECT * FROM revision_action_bridge
                WHERE tenant_id=? AND audit_id=?
                """,
                (tenant_id, audit_id),
            )
            existing = await cur.fetchone()
        if existing is not None:
            return {
                "bridge_id": existing["bridge_id"],
                "tenant_id": existing["tenant_id"],
                "audit_id": existing["audit_id"],
                "execution_id": existing["execution_id"],
                "entity_type": existing["entity_type"],
                "entity_id": existing["entity_id"],
                "event_type": existing["event_type"],
                "action_id": existing["action_id"],
                "recorded_at": existing["recorded_at"],
                "idempotent": True,
            }
        idem = f"rev-bridge:{audit_id}"
        now = _time.time()
        exec_rec = persist_execution(
            {
                "tenant_id": tenant_id,
                "idempotency_key": idem,
                "action_id": aid,
                "actor": str(audit_event.get("actor") or ""),
                "target": f"{et}:{eid}",
                "status": "succeeded",
                "policy_decision": "allow",
                "before_snapshot": {
                    "revision": audit_event.get("revision"),
                    "event_type": ev,
                },
                "after_snapshot": {
                    "to_revision": audit_event.get("to_revision"),
                    "detail": audit_event.get("detail") or {},
                },
                "result": {
                    "audit_id": audit_id,
                    "bridged": True,
                },
                "evidence_ref": audit_id,
                "started_at": now,
                "completed_at": now,
            },
            db_path=self.action_execution_db_path,
        )
        bridge_id = f"rabr-{uuid.uuid4().hex[:12]}"
        recorded_at = _utc_now()
        execution_id = str(exec_rec.get("execution_id") or "")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                INSERT INTO revision_action_bridge (
                    bridge_id, tenant_id, audit_id, execution_id,
                    entity_type, entity_id, event_type, action_id, recorded_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    bridge_id,
                    tenant_id,
                    audit_id,
                    execution_id,
                    et,
                    eid,
                    ev,
                    aid,
                    recorded_at,
                ),
            )
            await db.commit()
        return {
            "bridge_id": bridge_id,
            "tenant_id": tenant_id,
            "audit_id": audit_id,
            "execution_id": execution_id,
            "entity_type": et,
            "entity_id": eid,
            "event_type": ev,
            "action_id": aid,
            "recorded_at": recorded_at,
            "idempotent": False,
        }

    async def list_revision_action_bridges(
        self,
        *,
        tenant_id: str,
        entity_type: str = "",
        entity_id: str = "",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """列出 revision→ActionExecution 桥接行。

        Args:
            tenant_id: 租户（必填）。
            entity_type: 可选实体类型。
            entity_id: 可选实体 ID。
            limit: 最大条数。

        Returns:
            桥接列表。
        """
        import aiosqlite

        if not tenant_id:
            raise FactLedgerError("tenant_id required")
        lim = max(1, min(int(limit or 100), 500))
        clauses = ["tenant_id=?"]
        params: List[Any] = [tenant_id]
        et = (entity_type or "").strip()
        eid = (entity_id or "").strip()
        if et:
            clauses.append("entity_type=?")
            params.append(et)
        if eid:
            clauses.append("entity_id=?")
            params.append(eid)
        where = " AND ".join(clauses)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=5000")
            cur = await db.execute(
                f"""
                SELECT * FROM revision_action_bridge
                WHERE {where}
                ORDER BY recorded_at ASC, bridge_id ASC
                LIMIT ?
                """,
                (*params, lim),
            )
            rows = await cur.fetchall()
        return [
            {
                "bridge_id": r["bridge_id"],
                "tenant_id": r["tenant_id"],
                "audit_id": r["audit_id"],
                "execution_id": r["execution_id"],
                "entity_type": r["entity_type"],
                "entity_id": r["entity_id"],
                "event_type": r["event_type"],
                "action_id": r["action_id"],
                "recorded_at": r["recorded_at"],
            }
            for r in rows
        ]

    def _row_to_fact(self, row: Any) -> Dict[str, Any]:
        """将 facts 表行转为 Fact dict。

        Args:
            row: aiosqlite.Row 或兼容映射。
        """
        return {
            "fact_id": row["fact_id"],
            "tenant_id": row["tenant_id"],
            "collection_id": row["collection_id"],
            "domain_id": row["domain_id"],
            "subject": row["subject"],
            "predicate": row["predicate"],
            "object": row["object"],
            "evidence": json.loads(row["evidence_json"] or "[]"),
            "source_policy": row["source_policy"],
            "extractor_version": row["extractor_version"],
            "review_status": row["review_status"],
            "confidence": row["confidence"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "recorded_at": row["recorded_at"],
            "revision": row["revision"],
            "status": row["status"],
            "inferred": bool(row["inferred"]),
        }

    async def get_fact(
        self,
        fact_id: str,
        *,
        tenant_id: str,
    ) -> Optional[Dict[str, Any]]:
        """按 ID 读取 Fact（租户前置）。

        Args:
            fact_id: Fact ID。
            tenant_id: 租户。

        Returns:
            Fact 记录；不存在或不属于该租户则 None。

        Raises:
            FactLedgerError: tenant_id 为空。
        """
        import aiosqlite

        if not tenant_id:
            raise FactLedgerError("tenant_id required before recall")
        fid = (fact_id or "").strip()
        if not fid:
            return None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM facts WHERE fact_id=? AND tenant_id=?",
                (fid, tenant_id),
            )
            row = await cur.fetchone()
        return self._row_to_fact(row) if row else None

    async def query_facts(
        self,
        *,
        tenant_id: str,
        collection_id: Optional[str] = None,
        domain_id: Optional[str] = None,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        review_status: Optional[str] = None,
        limit: int = 50,
        record_hotpath_audit: bool = True,
        stamp_constraint_hotpath: bool = True,
    ) -> List[Dict[str, Any]]:
        """查询 Fact；``tenant_id`` 必填且在 SQL WHERE 中过滤。

        Args:
            tenant_id: 租户（缺失则报错——禁止无租户全表扫）。
            collection_id: 可选集合过滤。
            domain_id: 可选域过滤。
            subject / predicate: 可选三元组过滤。
            review_status: 可选审核状态。
            limit: 上限。
            record_hotpath_audit: N19 list 旁路热路径；gateway 调用时关以免双写。
            stamp_constraint_hotpath: N20 list 旁路挂约束观测；gateway 调用时关以免双挂。

        Returns:
            Fact 列表（永不返回其他租户行；可为 ConstraintAwareHitList）。

        Raises:
            FactLedgerError: tenant_id 为空。
        """
        import aiosqlite

        if not tenant_id:
            raise FactLedgerError("tenant_id required before recall")

        clauses = ["tenant_id=?"]
        params: List[Any] = [tenant_id]
        if collection_id:
            clauses.append("collection_id=?")
            params.append(collection_id)
        if domain_id:
            clauses.append("domain_id=?")
            params.append(domain_id)
        if subject:
            clauses.append("subject=?")
            params.append(subject)
        if predicate:
            clauses.append("predicate=?")
            params.append(predicate)
        if review_status:
            clauses.append("review_status=?")
            params.append(review_status)
        params.append(max(1, min(int(limit), 500)))

        sql = (
            "SELECT * FROM facts WHERE "
            + " AND ".join(clauses)
            + " ORDER BY recorded_at DESC LIMIT ?"
        )
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            db.row_factory = aiosqlite.Row
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
        hits = [self._row_to_fact(row) for row in rows]
        if record_hotpath_audit:
            # 为什么：N19 — 直调 query_facts list 旁路也落审计（gateway 已关此开关）
            try:
                from core.harness.knowledge_pipeline.fact_query_audit import (
                    maybe_record_query_facts_list_hotpath,
                )

                maybe_record_query_facts_list_hotpath(
                    tenant_id=tenant_id,
                    hits=hits,
                    filters={
                        "collection_id": collection_id or "",
                        "domain_id": domain_id or "",
                        "subject": subject or "",
                        "predicate": predicate or "",
                        "review_status": review_status or "",
                        "limit": int(limit),
                    },
                )
            except Exception:
                logger.warning(
                    "fact_query_audit query_facts list hotpath failed",
                    exc_info=True,
                )
        if stamp_constraint_hotpath:
            # 为什么：N20 — 直调 list 旁路挂观测；主返回仍为 list（子类属性）
            try:
                from core.harness.knowledge_pipeline.constraint_layers import (
                    maybe_stamp_bare_list_constraint_hotpath,
                )

                hits = maybe_stamp_bare_list_constraint_hotpath(
                    hits, channel="fact_list"
                )
            except Exception:
                logger.warning(
                    "constraint_layers query_facts list hotpath failed",
                    exc_info=True,
                )
        return hits

    async def query_facts_gateway(
        self,
        *,
        tenant_id: str,
        query: str = "",
        collection_id: Optional[str] = None,
        domain_id: Optional[str] = None,
        top_k: int = 8,
        require_citations: bool = True,
        calibration_db_path: Optional[str] = None,
        calibration_query_type: str = "fact_gateway",
        record_hotpath_audit: bool = True,
        attach_constraint_hotpath: bool = True,
    ) -> Dict[str, Any]:
        """附录 M 最小查询入口：租户前置 + 无证据 abstain + N13 校准封顶。

        Args:
            tenant_id: 租户。
            query: 查询串（用于 subject/predicate 子串匹配的简化）。
            collection_id: 集合。
            domain_id: 业务域过滤（可选；有值时启用校准天花板）。
            top_k: 返回条数。
            require_citations: 为 True 时无 citations 则 abstain。
            calibration_db_path: 可选校准库（测试/探针）。
            calibration_query_type: 校准 query_type（默认 fact_gateway）。
            record_hotpath_audit: N19 旁路热路径落快照；统一 Gateway 调用时关以免双写。
            attach_constraint_hotpath: N20 旁路挂约束信封；统一 Gateway 调用时关以免双挂。

        Returns:
            查询响应（含 abstained / citations）。
        """
        facts = await self.query_facts(
            tenant_id=tenant_id,
            collection_id=collection_id,
            domain_id=domain_id,
            limit=top_k * 3,
            # 为什么：gateway 自有 N19/N20；关 list 审计与约束 stamp 防双写/双挂
            record_hotpath_audit=False,
            stamp_constraint_hotpath=False,
        )
        q = (query or "").strip().lower()
        if q:
            facts = [
                f
                for f in facts
                if q in f["subject"].lower()
                or q in f["predicate"].lower()
                or q in str(f["object"]).lower()
            ]
        facts = facts[:top_k]
        citations: List[Dict[str, str]] = []
        for f in facts:
            for ev in f.get("evidence") or []:
                citations.append(
                    {
                        "fact_id": f["fact_id"],
                        "source_id": str(ev.get("source_id", "")),
                        "locator": str(ev.get("locator", "")),
                    }
                )
        abstained = bool(require_citations and not citations)
        # 为什么：拒答时清空 answer/citations，满足附录 F 语义（abstain 无引用）
        if abstained:
            citations = []
            answer = ""
            confidence = "low"
            evidence_coverage = 0.0
        else:
            answer = ""
            if facts:
                f0 = facts[0]
                answer = f"{f0['subject']}.{f0['predicate']}={f0['object']}"
            confidence = "high" if citations else "low"
            evidence_coverage = 1.0 if citations else 0.0
        cal_capped = False
        # 为什么：有 domain 时走 N13 校准天花板，未达标诚实封顶 medium
        if (domain_id or "").strip() and confidence != "low":
            from core.harness.knowledge_pipeline.confidence_calibration import (
                apply_calibration_ceiling,
            )

            capped = apply_calibration_ceiling(
                tenant_id=tenant_id,
                domain=str(domain_id),
                query_type=calibration_query_type or "fact_gateway",
                confidence=confidence,
                db_path=calibration_db_path,
            )
            confidence = str(capped.get("confidence") or confidence)
            cal_capped = bool(capped.get("capped"))
        resp = {
            "answer": answer,
            "citations": citations,
            "route_plan": ["fact"],
            "route_reason": "fact_ledger",
            "confidence": confidence,
            "confidence_factors": {
                "evidence_coverage": evidence_coverage,
                "source_authority": "high" if citations else "low",
                "conflict": False,
                "coverage": evidence_coverage,
                "freshness": "valid" if citations else "unknown",
            },
            "partial": False,
            "degraded": False,
            "abstained": abstained,
            "conflicts": [],
            "facts": facts,
            "tenant_id": tenant_id,
            "calibration_capped": cal_capped,
        }
        gate = validate_gateway_response(resp)
        resp["gateway_contract_ok"] = gate["ok"]
        if record_hotpath_audit:
            # 为什么：N19 — 直调 query_facts_gateway 旁路也落审计（统一入口已关此开关）
            try:
                from core.harness.knowledge_pipeline.fact_query_audit import (
                    maybe_record_query_facts_gateway_hotpath,
                )

                maybe_record_query_facts_gateway_hotpath(
                    tenant_id=tenant_id,
                    query=query or "",
                    response=resp,
                )
            except Exception:
                logger.warning(
                    "fact_query_audit query_facts_gateway hotpath failed",
                    exc_info=True,
                )
        if attach_constraint_hotpath:
            # 为什么：N20 — 直调旁路挂约束观测信封（统一入口由 _finish 挂，关此开关）
            try:
                from core.harness.knowledge_pipeline.constraint_layers import (
                    maybe_attach_query_facts_gateway_constraint_hotpath,
                )

                resp = maybe_attach_query_facts_gateway_constraint_hotpath(resp)
            except Exception:
                logger.warning(
                    "constraint_layers query_facts_gateway hotpath failed",
                    exc_info=True,
                )
        return resp


_GATEWAY_REQUIRED = (
    "answer",
    "citations",
    "route_plan",
    "route_reason",
    "confidence",
    "confidence_factors",
    "partial",
    "degraded",
    "abstained",
    "conflicts",
)
_GATEWAY_CONFIDENCE = frozenset({"high", "medium", "low"})
_GATEWAY_FACTOR_KEYS = (
    "evidence_coverage",
    "source_authority",
    "conflict",
    "coverage",
    "freshness",
)


def validate_gateway_response(response: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """校验附录 F 查询响应最小契约（N06）；不宣称全量 Gateway。

    Args:
        response: ``query_facts_gateway`` 形状的响应。

    Returns:
        ``{ok, errors, certified=False, n06_full_conformance=False}``。
    """
    r = dict(response or {})
    errors: List[str] = []
    for key in _GATEWAY_REQUIRED:
        if key not in r:
            errors.append(f"missing:{key}")
    plan = r.get("route_plan")
    if not isinstance(plan, list) or not plan:
        errors.append("route_plan_min_items")
    if not str(r.get("route_reason") or "").strip():
        errors.append("route_reason_required")
    conf = r.get("confidence")
    if conf not in _GATEWAY_CONFIDENCE:
        errors.append("invalid_confidence")
    factors = r.get("confidence_factors")
    if not isinstance(factors, dict):
        errors.append("confidence_factors_required")
    else:
        for fk in _GATEWAY_FACTOR_KEYS:
            if fk not in factors:
                errors.append(f"missing_factor:{fk}")
    if r.get("abstained") is True:
        cits = r.get("citations") or []
        if cits:
            errors.append("abstained_must_not_have_citations")
        if str(r.get("answer") or "").strip():
            errors.append("abstained_must_not_have_answer")
    if r.get("certified") is True or r.get("n06_full_conformance") is True:
        # 为什么：响应体误标认证不得过门
        errors.append("honesty_certified_flag_forbidden")
    return {
        "ok": not errors,
        "errors": errors,
        "certified": False,
        "n06_full_conformance": False,
    }


def evaluate_gateway_contract_gate(
    responses: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """N06 Gateway 契约门槛门：汇总 validate；certified 恒 false。

    Args:
        responses: 网关响应列表。

    Returns:
        gate 字典；``certified`` / ``n06_full_conformance`` 恒 false。
    """
    items = list(responses or [])
    issues: List[str] = []
    if not items:
        issues.append("no_gateway_responses")
    checked = [validate_gateway_response(x) for x in items]
    passed = sum(1 for g in checked if g.get("ok") is True)
    if items and passed != len(items):
        issues.append("gateway_contract_failures")
    for g in checked:
        if "honesty_certified_flag_forbidden" in (g.get("errors") or []):
            issues.append("honesty_certified_flag_forbidden")
            break
    ok = bool(items) and passed == len(items) and not issues
    return {
        "gate": "gateway_contract",
        "ok": ok,
        "passed": passed,
        "total": len(items),
        "required": True,
        "issues": issues,
        "certified": False,
        "n06_full_conformance": False,
        "note": "FactLedger query gateway F.1 slice; not unified Appendix-F Gateway",
    }


# 为什么：N06 统一入口含 wiki/index/materials_chat/graphrag；其它 Agent 全出口仍可并行
UNIFIED_QUERY_GATEWAY_ROUTES: Tuple[str, ...] = (
    "fact",
    "object_set",
    "wiki",
    "index",
    "materials_chat",
    "graphrag",
)


def unified_query_gateway_routes() -> Dict[str, Any]:
    """返回 N06 统一 Query Gateway 当前支持的路由轴。

    Returns:
        routes；``certified`` 恒 false。
    """
    return {
        "routes": list(UNIFIED_QUERY_GATEWAY_ROUTES),
        "certified": False,
        "n06_full_conformance": False,
        "wiki_index_routes": True,
        "materials_chat_route": True,
        "materials_nonrag_gateway": True,
        "graphrag_route": True,
        "note": (
            "Core unified entry for fact+object_set+wiki+index+materials_chat"
            "+graphrag F.1; not all other apps / not N06 certified"
        ),
    }


def require_unified_query_route(route: str) -> str:
    """校验统一 Gateway 路由名。

    Args:
        route: ``fact`` / ``object_set`` / ``wiki`` / ``index`` /
            ``materials_chat`` / ``graphrag``。

    Returns:
        规范化小写路由名。

    Raises:
        FactLedgerError: 不在矩阵内。
    """
    r = (route or "").strip().lower()
    if r not in UNIFIED_QUERY_GATEWAY_ROUTES:
        raise FactLedgerError(
            f"unified_query_gateway unsupported route={route!r}; "
            f"routes={list(UNIFIED_QUERY_GATEWAY_ROUTES)}"
        )
    return r


def graphrag_to_f1_envelope(
    *,
    tenant_id: str,
    result: Optional[Dict[str, Any]],
    query: str = "",
) -> Dict[str, Any]:
    """GraphRAG retrieve 结果经 N21 信封后映射为附录 F.1。

    Args:
        tenant_id: 租户。
        result: GraphRAGRetriever.retrieve 回执（可已含 ``n21_query``）。
        query: 原始查询。
    """
    from core.harness.knowledge_pipeline.query_abstain_citations import (
        attach_graphrag_n21_envelope,
    )

    raw = result if isinstance(result, dict) else {}
    n21 = raw.get("n21_query") if isinstance(raw.get("n21_query"), dict) else None
    if n21 is None:
        wrapped = attach_graphrag_n21_envelope(raw, query=query)
        n21 = wrapped.get("n21_query") if isinstance(wrapped, dict) else {}
    return _n21_to_f1_envelope(
        tenant_id=tenant_id,
        route="graphrag",
        n21=n21 if isinstance(n21, dict) else {},
    )


def materials_chat_to_f1_envelope(
    *,
    tenant_id: str,
    output: Optional[Dict[str, Any]],
    kind: str = "auto",
) -> Dict[str, Any]:
    """MaterialsChat 输出经 N21 enforce 后映射为附录 F.1 信封。

    Args:
        tenant_id: 租户。
        output: MaterialsChat Agent 输出 dict。
        kind: ``auto`` / ``rag`` / ``shortcut`` / ``cache_hit``；已 enforce 则直映。
    """
    from core.harness.knowledge_pipeline.query_abstain_citations import (
        enforce_materials_chat_cache_hit_output,
        enforce_materials_chat_output,
        enforce_materials_chat_shortcut_output,
        is_materials_cache_hit,
        is_materials_trivial_bypass,
    )

    raw = output if isinstance(output, dict) else {}
    k = (kind or "auto").strip().lower()
    # 为什么：已过 N21 门的输出勿二次 RAG enforce（trivial 会被误 abstain）
    if raw.get("n21_enforced") is True and str(raw.get("n21_channel") or "").strip():
        n21 = raw
    elif k == "shortcut" or (
        k == "auto" and is_materials_trivial_bypass(raw)
    ):
        n21 = enforce_materials_chat_shortcut_output(raw)
    elif k == "cache_hit" or (k == "auto" and is_materials_cache_hit(raw)):
        n21 = enforce_materials_chat_cache_hit_output(raw)
    else:
        n21 = enforce_materials_chat_output(raw)
    # 为什么：trivial 捷径允许无 citations 的确定性答案进 F.1
    allow_empty = n21.get("n21_shortcut") is True
    return _n21_to_f1_envelope(
        tenant_id=tenant_id,
        route="materials_chat",
        n21=n21,
        allow_empty_citations=allow_empty,
    )


def _n21_to_f1_envelope(
    *,
    tenant_id: str,
    route: str,
    n21: Dict[str, Any],
    allow_empty_citations: bool = False,
) -> Dict[str, Any]:
    """将 N21 查询形响应映射为附录 F.1 信封。

    Args:
        tenant_id: 租户。
        route: ``wiki`` / ``index`` / ``materials_chat`` / ``graphrag``。
        n21: N21 查询形 / MaterialsChat enforce 回执。
        allow_empty_citations: trivial 捷径允许无引用命中。
    """
    abstained = n21.get("abstained") is True
    cites_raw = n21.get("citations") or []
    citations: List[Dict[str, str]] = []
    if isinstance(cites_raw, list) and not abstained:
        for c in cites_raw:
            if not isinstance(c, dict):
                continue
            sid = str(c.get("source_id") or c.get("source") or "").strip()
            if not sid:
                continue
            citations.append(
                {
                    "fact_id": "",
                    "source_id": sid,
                    "locator": str(c.get("locator") or ""),
                }
            )
    answer = str(n21.get("answer") or "").strip()
    if abstained or (not citations and not (allow_empty_citations and answer)):
        return _empty_f1_envelope(
            tenant_id=tenant_id,
            route_reason=f"unified:{route}:abstain",
            abstained=True,
        )
    hit_tag = "trivial" if allow_empty_citations and not citations else "hit"
    env = _empty_f1_envelope(
        tenant_id=tenant_id,
        route_reason=f"unified:{route}:{hit_tag}",
        abstained=False,
        answer=answer or f"{route}_hit",
        citations=citations,
        confidence="low" if allow_empty_citations and not citations else "medium",
    )
    plan = list(env.get("route_plan") or [])
    if "unified" not in plan:
        env["route_plan"] = ["unified", *plan]
    env["n21_enforced"] = n21.get("n21_enforced") is True
    env["n21_channel"] = str(n21.get("n21_channel") or "")
    env["certified"] = False
    env["n06_full_conformance"] = False
    return env


def _empty_f1_envelope(
    *,
    tenant_id: str,
    route_reason: str,
    abstained: bool = True,
    answer: str = "",
    citations: Optional[List[Dict[str, str]]] = None,
    facts: Optional[List[Dict[str, Any]]] = None,
    confidence: str = "low",
) -> Dict[str, Any]:
    """构造附录 F.1 最小信封（统一 Gateway 共用）。"""
    cites = list(citations or [])
    cov = 1.0 if cites and not abstained else 0.0
    resp = {
        "answer": answer if not abstained else "",
        "citations": [] if abstained else cites,
        "route_plan": [route_reason.split(":", 1)[0] if ":" in route_reason else route_reason],
        "route_reason": route_reason,
        "confidence": confidence if not abstained else "low",
        "confidence_factors": {
            "evidence_coverage": cov,
            "source_authority": "high" if cites and not abstained else "low",
            "conflict": False,
            "coverage": cov,
            "freshness": "valid" if cites and not abstained else "unknown",
        },
        "partial": False,
        "degraded": False,
        "abstained": abstained,
        "conflicts": [],
        "facts": list(facts or []),
        "tenant_id": tenant_id,
    }
    gate = validate_gateway_response(resp)
    resp["gateway_contract_ok"] = gate["ok"]
    return resp


async def unified_query_gateway(
    *,
    tenant_id: str,
    query: str = "",
    route: str = "fact",
    collection_id: Optional[str] = None,
    domain_id: Optional[str] = None,
    top_k: int = 8,
    object_set_request: Optional[Dict[str, Any]] = None,
    permissions: Optional[List[str]] = None,
    role: str = "",
    ledger: Optional["FactLedger"] = None,
    bindings_path: Optional[Any] = None,
    calibration_db_path: Optional[str] = None,
    calibration_query_type: str = "fact_gateway",
    materials_output: Optional[Dict[str, Any]] = None,
    graphrag_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N06 deepen：统一 Query Gateway（含 materials_chat/graphrag → F.1）。

    Args:
        tenant_id: 租户。
        query: 查询串（fact/wiki/index 路由使用）。
        route: ``fact`` / ``object_set`` / ``wiki`` / ``index`` /
            ``materials_chat`` / ``graphrag``。
        collection_id / domain_id / top_k: fact/wiki/index 路由参数。
        object_set_request: object_set 路由请求 dict。
        permissions / role: object_set L1/ACL。
        ledger: 可选 FactLedger。
        bindings_path: 可选 ObjectType 绑定路径（object_set 探针/测试）。
        calibration_db_path / calibration_query_type: N13 校准封顶透传。
        materials_output: materials_chat 路由的 Agent 输出（缺省则 abstain）。
        graphrag_result: graphrag 路由的 retrieve 回执（缺省则 abstain）。

    Returns:
        附录 F.1 信封；``certified`` 不在此回执宣称。

    Raises:
        FactLedgerError: 路由不在矩阵内。
    """
    r = require_unified_query_route(route)
    tid = (tenant_id or "").strip()
    if not tid:
        raise FactLedgerError("tenant_id required")

    def _finish(resp: Dict[str, Any]) -> Dict[str, Any]:
        # 为什么：N19 — Gateway 热路径 best-effort 落 Query 快照（失败不改 F.1）
        out = resp
        try:
            from core.harness.knowledge_pipeline.fact_query_audit import (
                maybe_record_query_gateway_hotpath,
            )

            out = maybe_record_query_gateway_hotpath(
                tenant_id=tid,
                route=r,
                query=query or "",
                response=out,
            )
        except Exception:
            logger.warning(
                "fact_query_audit query_gateway hotpath failed route=%s",
                r,
                exc_info=True,
            )
        # 为什么：N20 — Gateway 热路径挂约束栈观测信封（不阻断 F.1）
        try:
            from core.harness.knowledge_pipeline.constraint_layers import (
                maybe_attach_constraint_stack_hotpath,
            )

            out = maybe_attach_constraint_stack_hotpath(
                out,
                route=r,
                actor_permissions=permissions,
            )
        except Exception:
            logger.warning(
                "constraint_layers gateway hotpath failed route=%s",
                r,
                exc_info=True,
            )
        return out

    if r == "fact":
        lg = ledger or get_fact_ledger()
        await lg.initialize()
        resp = await lg.query_facts_gateway(
            tenant_id=tid,
            query=query,
            collection_id=collection_id,
            domain_id=domain_id,
            top_k=top_k,
            calibration_db_path=calibration_db_path,
            calibration_query_type=calibration_query_type,
            # 为什么：统一入口由 _finish 落 N19/N20，避免旁路+统一双写
            record_hotpath_audit=False,
            attach_constraint_hotpath=False,
        )
        # 统一入口标记（不改变 F.1 字段）
        plan = list(resp.get("route_plan") or [])
        if "unified" not in plan:
            resp["route_plan"] = ["unified", *plan]
        resp["route_reason"] = f"unified:fact:{resp.get('route_reason') or 'fact_ledger'}"
        gate = validate_gateway_response(resp)
        resp["gateway_contract_ok"] = gate["ok"]
        return _finish(resp)

    if r == "wiki":
        from core.harness.knowledge_pipeline.query_abstain_citations import (
            query_wiki_with_abstain,
        )

        cids = [collection_id] if (collection_id or "").strip() else ["default"]
        n21 = query_wiki_with_abstain(
            query or "",
            tenant_id=tid,
            collection_ids=cids,
            top_k=int(top_k),
        )
        return _finish(_n21_to_f1_envelope(tenant_id=tid, route="wiki", n21=n21))

    if r == "index":
        # 为什么：Index 路由映射 KB 查询形
        from core.harness.knowledge_pipeline.query_abstain_citations import (
            query_kb_with_abstain,
        )

        n21 = query_kb_with_abstain(
            query or "",
            tenant_id=tid,
            collection_id=(collection_id or "").strip(),
            top_k=int(top_k),
        )
        return _finish(_n21_to_f1_envelope(tenant_id=tid, route="index", n21=n21))

    if r == "materials_chat":
        # 为什么：MaterialsChat 经 N21 RAG enforce → F.1；无输出则 abstain（非跑全 Agent）
        return _finish(
            materials_chat_to_f1_envelope(
                tenant_id=tid,
                output=materials_output
                if isinstance(materials_output, dict)
                else {
                    "answer": "",
                    "citations": [],
                    "strategy": "direct_retrieve",
                    "query": query or "",
                },
            )
        )

    if r == "graphrag":
        # 为什么：GraphRAG 经 N21 信封 → F.1；无结果则 abstain（非跑全检索）
        return _finish(
            graphrag_to_f1_envelope(
                tenant_id=tid,
                result=graphrag_result if isinstance(graphrag_result, dict) else {},
                query=query or "",
            )
        )

    # object_set → F.1 信封（无命中则 abstain）
    from core.harness.knowledge_pipeline.object_set import (
        query_object_set as _query_os,
    )

    req = dict(object_set_request or {})
    if not req.get("object_type") and (query or "").strip():
        req.setdefault("object_type", (query or "").strip())
    if "limit" not in req:
        req["limit"] = int(top_k)
    os_kwargs: Dict[str, Any] = {}
    if ledger is not None:
        os_kwargs["ledger"] = ledger
    if bindings_path is not None:
        os_kwargs["bindings_path"] = bindings_path
    out = await _query_os(
        req,
        tenant_id=tid,
        permissions=permissions,
        role=role or "",
        **os_kwargs,
    )
    objects = list(out.get("objects") or out.get("items") or [])
    if out.get("status") in ("policy_denied", "not_found") or not objects:
        return _finish(
            _empty_f1_envelope(
                tenant_id=tid,
                route_reason="unified:object_set:abstain",
                abstained=True,
            )
        )
    citations = [
        {
            "fact_id": "",
            "source_id": str(obj.get("id") or obj.get("object_id") or ""),
            "locator": "object_set",
        }
        for obj in objects[: int(top_k)]
    ]
    first = objects[0]
    answer = str(
        first.get("name")
        or first.get("id")
        or first.get("object_id")
        or "object_set_hit"
    )
    return _finish(
        _empty_f1_envelope(
            tenant_id=tid,
            route_reason="unified:object_set:hit",
            abstained=False,
            answer=answer,
            citations=citations,
            confidence="medium",
        )
    )


_N06_UNIFIED_GATEWAY_CASES = (
    "routes_declare_fact_object_set_wiki_index",
    "fact_route_f1_ok",
    "object_set_route_f1_ok",
    "wiki_route_f1_ok",
    "index_route_f1_ok",
    "materials_chat_route_f1_ok",
    "materials_nonrag_gateway_f1_ok",
    "graphrag_route_f1_ok",
    "honesty_certified_false",
)


async def run_unified_query_gateway_suite(
    *,
    ledger: Optional["FactLedger"] = None,
    tenant_id: str = "n06-unified-gw-tenant",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N06 统一 Gateway 加深套件（含 materials/graphrag；非其它全应用/非 certified）。

    Args:
        ledger: 可选账本。
        tenant_id: 写入租户。
        domain_id: 可选域。

    Returns:
        套件汇总；``certified`` / ``n06_full_conformance`` 恒 false。
    """
    import tempfile

    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n06-unified-gw-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await lg.initialize()
    else:
        lg = ledger  # type: ignore[assignment]
        await lg.initialize()

    cases: List[Dict[str, Any]] = []
    try:
        meta = unified_query_gateway_routes()
        routes_ok = (
            list(meta.get("routes") or []) == list(UNIFIED_QUERY_GATEWAY_ROUTES)
            and meta.get("wiki_index_routes") is True
            and meta.get("materials_chat_route") is True
            and meta.get("materials_nonrag_gateway") is True
            and meta.get("graphrag_route") is True
            and meta.get("certified") is False
        )
        cases.append(
            {
                "id": "routes_declare_fact_object_set_wiki_index",
                "ok": routes_ok,
                "detail": "" if routes_ok else "routes_mismatch",
            }
        )

        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n06-unified",
            kind="file",
            uri="file://n06/unified.txt",
            content=b"n06-unified",
            connector="n06",
            domain_id=domain_id,
        )
        await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n06-unified",
            subject="door",
            predicate="state",
            object="locked",
            evidence=[
                {
                    "source_id": src["source_id"],
                    "locator": "x",
                    "quote": "locked",
                    "fetched_at": src["fetched_at"],
                }
            ],
            source_policy="n06",
            extractor_version="n06",
            review_status="published",
            confidence=0.9,
            domain_id=domain_id,
            allow_bootstrap_published=True,
        )
        fact_resp = await unified_query_gateway(
            tenant_id=tenant_id,
            query="door",
            route="fact",
            collection_id="n06-unified",
            domain_id=domain_id,
            ledger=lg,
        )
        fact_ok = (
            validate_gateway_response(fact_resp).get("ok") is True
            and fact_resp.get("abstained") is False
            and "unified" in (fact_resp.get("route_plan") or [])
        )
        cases.append(
            {
                "id": "fact_route_f1_ok",
                "ok": fact_ok,
                "detail": "" if fact_ok else "fact_route_failed",
            }
        )

        os_resp = await unified_query_gateway(
            tenant_id=tenant_id,
            query="NonexistentTypeXYZ",
            route="object_set",
            object_set_request={"object_type": "NonexistentTypeXYZ", "limit": 3},
            permissions=["kb:read", "*"],
            ledger=lg,
        )
        os_ok = validate_gateway_response(os_resp).get("ok") is True
        cases.append(
            {
                "id": "object_set_route_f1_ok",
                "ok": os_ok,
                "detail": "" if os_ok else "object_set_route_failed",
            }
        )

        wiki_resp = await unified_query_gateway(
            tenant_id=tenant_id,
            query="n06-wiki-no-such-page-xyz",
            route="wiki",
            collection_id=DomainRouter.default_collection(),
            ledger=lg,
        )
        wiki_ok = (
            validate_gateway_response(wiki_resp).get("ok") is True
            and require_unified_query_route("wiki") == "wiki"
            and wiki_resp.get("abstained") is True
            and str(wiki_resp.get("route_reason") or "").startswith("unified:wiki:")
        )
        cases.append(
            {
                "id": "wiki_route_f1_ok",
                "ok": wiki_ok,
                "detail": "" if wiki_ok else "wiki_route_failed",
            }
        )

        index_resp = await unified_query_gateway(
            tenant_id=tenant_id,
            query="n06-index-no-such-doc-xyz",
            route="index",
            ledger=lg,
        )
        index_ok = (
            validate_gateway_response(index_resp).get("ok") is True
            and require_unified_query_route("index") == "index"
            and index_resp.get("abstained") is True
            and str(index_resp.get("route_reason") or "").startswith("unified:index:")
        )
        cases.append(
            {
                "id": "index_route_f1_ok",
                "ok": index_ok,
                "detail": "" if index_ok else "index_route_failed",
            }
        )

        mat_hit = await unified_query_gateway(
            tenant_id=tenant_id,
            route="materials_chat",
            materials_output={
                "answer": "grounded materials",
                "citations": [{"source": "wiki:M", "text": "grounded"}],
                "strategy": "direct_retrieve",
            },
            ledger=lg,
        )
        mat_empty = await unified_query_gateway(
            tenant_id=tenant_id,
            route="materials_chat",
            materials_output={
                "answer": "fake materials",
                "citations": [],
                "strategy": "direct_retrieve",
            },
            ledger=lg,
        )
        mat_ok = (
            validate_gateway_response(mat_hit).get("ok") is True
            and mat_hit.get("abstained") is False
            and bool(mat_hit.get("citations"))
            and str(mat_hit.get("route_reason") or "").startswith(
                "unified:materials_chat:"
            )
            and mat_empty.get("abstained") is True
            and require_unified_query_route("materials_chat") == "materials_chat"
        )
        cases.append(
            {
                "id": "materials_chat_route_f1_ok",
                "ok": mat_ok,
                "detail": "" if mat_ok else "materials_chat_route_failed",
            }
        )

        # trivial 捷径：无 citations 仍可 F.1 hit；cache_hit 无引用 abstain
        sc_f1 = materials_chat_to_f1_envelope(
            tenant_id=tenant_id,
            output={
                "answer": "14:30",
                "citations": [],
                "strategy": "trivial_bypass",
                "intent": "trivial",
                "quality": "trivial",
            },
            kind="shortcut",
        )
        ch_f1 = materials_chat_to_f1_envelope(
            tenant_id=tenant_id,
            output={
                "answer": "cached grounded",
                "citations": [{"source": "wiki:C", "text": "cached"}],
                "strategy": "cache_hit",
                "quality": "cached",
                "mode": "cache",
            },
            kind="cache_hit",
        )
        ch_empty_f1 = materials_chat_to_f1_envelope(
            tenant_id=tenant_id,
            output={
                "answer": "cached fake",
                "citations": [],
                "strategy": "cache_hit",
                "quality": "cached",
                "mode": "cache",
            },
            kind="cache_hit",
        )
        nonrag_ok = (
            validate_gateway_response(sc_f1).get("ok") is True
            and sc_f1.get("abstained") is False
            and sc_f1.get("answer") == "14:30"
            and sc_f1.get("citations") == []
            and str(sc_f1.get("route_reason") or "").endswith(":trivial")
            and validate_gateway_response(ch_f1).get("ok") is True
            and ch_f1.get("abstained") is False
            and bool(ch_f1.get("citations"))
            and ch_empty_f1.get("abstained") is True
            and meta.get("materials_nonrag_gateway") is True
        )
        cases.append(
            {
                "id": "materials_nonrag_gateway_f1_ok",
                "ok": nonrag_ok,
                "detail": "" if nonrag_ok else "materials_nonrag_gateway_failed",
            }
        )

        gr_hit = await unified_query_gateway(
            tenant_id=tenant_id,
            route="graphrag",
            query="graphrag grounded",
            graphrag_result={
                "mode": "graphrag",
                "chunks": [
                    {
                        "title": "G1",
                        "content": "grounded graph chunk",
                        "source": "wiki:G1",
                    }
                ],
            },
            ledger=lg,
        )
        gr_empty = await unified_query_gateway(
            tenant_id=tenant_id,
            route="graphrag",
            query="graphrag empty",
            graphrag_result={"mode": "vector_only", "chunks": []},
            ledger=lg,
        )
        gr_ok = (
            validate_gateway_response(gr_hit).get("ok") is True
            and gr_hit.get("abstained") is False
            and bool(gr_hit.get("citations"))
            and str(gr_hit.get("route_reason") or "").startswith("unified:graphrag:")
            and gr_empty.get("abstained") is True
            and require_unified_query_route("graphrag") == "graphrag"
            and meta.get("graphrag_route") is True
        )
        cases.append(
            {
                "id": "graphrag_route_f1_ok",
                "ok": gr_ok,
                "detail": "" if gr_ok else "graphrag_route_failed",
            }
        )

        honesty_ok = (
            meta.get("certified") is False
            and meta.get("n06_full_conformance") is False
            and fact_resp.get("certified") is not True
            and wiki_resp.get("n06_full_conformance") is not True
            and mat_hit.get("n06_full_conformance") is not True
            and sc_f1.get("n06_full_conformance") is not True
            and gr_hit.get("n06_full_conformance") is not True
        )
        cases.append(
            {
                "id": "honesty_certified_false",
                "ok": honesty_ok,
                "detail": "" if honesty_ok else "honesty_broken",
            }
        )
    finally:
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N06_UNIFIED_GATEWAY_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "unified_query_gateway",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "routes": unified_query_gateway_routes(),
        "certified": False,
        "n06_full_conformance": False,
        "wiki_index_routes": True,
        "materials_chat_route": True,
        "materials_nonrag_gateway": True,
        "graphrag_route": True,
        "note": (
            "Unified fact+object_set+wiki+index+materials_chat+graphrag F.1; "
            "not all other apps / not N06 certified"
        ),
    }


def evaluate_unified_query_gateway_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N06 统一 Gateway 门槛门；certified 恒 false。

    Args:
        suite: ``run_unified_query_gateway_suite`` 回执。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n06_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    # 为什么：本 deepen 须声明 wiki/index + materials RAG/nonrag 已接线
    if s.get("wiki_index_routes") is not True:
        issues.append("wiki_index_routes_required")
    if s.get("materials_chat_route") is not True:
        issues.append("materials_chat_route_required")
    if s.get("materials_nonrag_gateway") is not True:
        issues.append("materials_nonrag_gateway_required")
    if s.get("graphrag_route") is not True:
        issues.append("graphrag_route_required")
    return {
        "gate": "unified_query_gateway",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n06_full_conformance": False,
        "wiki_index_routes": True,
        "materials_chat_route": True,
        "materials_nonrag_gateway": True,
        "graphrag_route": True,
        "note": (
            "fact+object_set+wiki+index+materials_chat+graphrag unify; "
            "not all other apps / N06 certified"
        ),
    }


def load_object_type_bindings(path: Path) -> List[Dict[str, Any]]:
    """从 JSON 文件加载附录 B 形状的 ObjectType 绑定（域无关）。

    Args:
        path: JSON 文件路径（数组或 ``{"object_types": [...]}``）。

    Returns:
        ObjectType 字典列表。

    Raises:
        FactLedgerError: 文件缺失或格式非法。
    """
    p = Path(path)
    if not p.is_file():
        raise FactLedgerError(f"object type bindings missing: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        items = data.get("object_types") or data.get("types") or []
    else:
        items = data
    if not isinstance(items, list):
        raise FactLedgerError("object type bindings must be a list")
    return [x for x in items if isinstance(x, dict)]


def evaluate_raw_integrity_gate(
    results: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """N01 Raw 完整性门槛门：汇总 verify 回执；certified 恒 false。

    Args:
        results: ``verify_raw_integrity`` 回执列表（可含 ok=False 的探测结果）。

    Returns:
        gate 字典：passed/total/ok；``certified`` / ``n01_full_conformance`` 永远为 False。
    """
    items = list(results or [])
    total = len(items)
    passed = sum(1 for r in items if isinstance(r, dict) and r.get("ok") is True)
    issues: List[str] = []
    if total == 0:
        issues.append("no_verify_results")
    elif passed != total:
        issues.append("integrity_failures")
    # 为什么：调用方误标 certified 仍不得冒充 N01 全量认证
    for r in items:
        if isinstance(r, dict) and (
            r.get("certified") is True or r.get("n01_full_conformance") is True
        ):
            issues.append("honesty_certified_flag_forbidden")
            break
    ok = total > 0 and passed == total and not issues
    return {
        "gate": "raw_integrity",
        "ok": ok,
        "passed": passed,
        "total": total,
        "required": True,
        "issues": issues,
        # 诚实锁：单测/试点加深 ≠ 附录 N N01 certified
        "certified": False,
        "n01_full_conformance": False,
        "note": "FactLedger verify-on-read; DataSourceConfig path via ingest_datasource_raw (Batch G)",
    }


async def ingest_datasource_raw(
    *,
    tenant_id: str,
    collection_id: str,
    content: bytes,
    content_hash: str = "",
    name: str = "",
    uri: str = "",
    locator: str = "",
    connector: str = "datasource",
    domain_id: str = "",
    require_hash: bool = True,
    ledger: Optional["FactLedger"] = None,
    source_id: Optional[str] = None,
) -> Dict[str, Any]:
    """DataSource → FactLedger Raw：强制/校验 content_hash 后登记不可变快照（N01 G）。

    Args:
        tenant_id: 租户。
        collection_id: 集合。
        content: 原始字节（file 原文或抓取快照）。
        content_hash: 期望 sha256；空且 require_hash=True 则拒绝。
        name: 数据源名（写入 connector 旁注）。
        uri: 来源 URI；默认 file:// 或 datasource://name。
        locator: 可选定位说明。
        connector: 连接器标签。
        domain_id: 可选域（调用方传入）。
        require_hash: 是否强制声明 hash。
        ledger: 可选账本；默认单例。
        source_id: 可选显式 Source ID。

    Returns:
        含 source 记录 + integrity 回执；``certified`` 恒 false。

    Raises:
        FactLedgerError: hash 缺失/不一致或登记失败。
    """
    from core.harness.ontology_engine.data_source import (
        DataSourceConfig,
        DataSourceIntegrityError,
        validate_datasource_content_hash,
    )

    cfg = DataSourceConfig(
        name=name or "datasource",
        source_type="file",
        connection={},
        mapping={},
        content_hash=(content_hash or "").strip().lower(),
        locator=locator or "",
    )
    try:
        check = validate_datasource_content_hash(
            cfg, content, require_hash=require_hash
        )
    except DataSourceIntegrityError as exc:
        raise FactLedgerError(str(exc)) from exc

    lg = ledger or get_fact_ledger()
    await lg.initialize()
    uri_final = (uri or "").strip() or (
        f"file://{locator}" if locator else f"datasource://{cfg.name}"
    )
    src = await lg.register_source(
        tenant_id=tenant_id,
        collection_id=collection_id,
        kind="file",
        uri=uri_final,
        content=content,
        connector=connector,
        domain_id=domain_id,
        source_id=source_id,
    )
    # 为什么：声明 hash 必须与登记后存储一致（防 register 路径漂移）
    if check.get("hash_declared") and str(src.get("sha256") or "") != check["actual"]:
        raise FactLedgerError(
            "ingest_datasource_raw sha256 drifted after register_source"
        )
    verify = await lg.verify_raw_integrity(src["source_id"], tenant_id=tenant_id)
    return {
        "source": src,
        "integrity": verify,
        "hash_check": check,
        "certified": False,
        "n01_full_conformance": False,
        "note": "DataSourceConfig content_hash → FactLedger Raw; not N01 certified",
    }


_N01_DATASOURCE_CASES = (
    "missing_hash_rejected",
    "hash_mismatch_rejected",
    "hash_ok_ingest_and_verify",
)


async def run_datasource_raw_suite(
    *,
    ledger: Optional["FactLedger"] = None,
    tenant_id: str = "n01-ds-tenant",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N01 DataSourceConfig → Raw 完整性加深套件。

    Args:
        ledger: 可选账本；默认临时目录。
        tenant_id: 写入租户。
        domain_id: 可选域（调用方传入）。

    Returns:
        套件汇总；``certified`` / ``n01_full_conformance`` 恒 false。
    """
    import tempfile

    from core.harness.ontology_engine.data_source import (
        DataSourceConfig,
        DataSourceIntegrityError,
        read_file_datasource_bytes,
        sha256_bytes,
        validate_datasource_content_hash,
    )

    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n01-datasource-raw-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await lg.initialize()
        work = root
    else:
        lg = ledger  # type: ignore[assignment]
        await lg.initialize()
        work = Path(tempfile.mkdtemp(prefix="n01-ds-files-"))

    cases: List[Dict[str, Any]] = []
    try:
        # 1) 缺 hash 强制拒绝
        missing_ok = False
        try:
            await ingest_datasource_raw(
                tenant_id=tenant_id,
                collection_id="n01-ds",
                content=b"no-hash",
                content_hash="",
                name="missing-hash",
                require_hash=True,
                ledger=lg,
                domain_id=domain_id,
            )
        except FactLedgerError:
            missing_ok = True
        cases.append(
            {
                "id": "missing_hash_rejected",
                "ok": missing_ok,
                "detail": "" if missing_ok else "missing_hash_accepted",
            }
        )

        # 2) mismatch 拒绝（file 路径 + validate）
        bad_path = work / "payload.bin"
        bad_path.write_bytes(b"payload-v1")
        bad_cfg = DataSourceConfig(
            name="mismatch",
            source_type="file",
            connection={"file_path": str(bad_path)},
            content_hash="0" * 64,
        )
        mismatch_ok = False
        try:
            blob = read_file_datasource_bytes(bad_cfg)
            validate_datasource_content_hash(bad_cfg, blob, require_hash=True)
        except DataSourceIntegrityError:
            mismatch_ok = True
        cases.append(
            {
                "id": "hash_mismatch_rejected",
                "ok": mismatch_ok,
                "detail": "" if mismatch_ok else "mismatch_accepted",
            }
        )

        # 3) 正确 hash → 登记 + verify
        good = b"payload-ok-n01"
        digest = sha256_bytes(good)
        good_path = work / "ok.bin"
        good_path.write_bytes(good)
        good_cfg = DataSourceConfig(
            name="ok-ds",
            source_type="file",
            connection={"file_path": str(good_path)},
            content_hash=digest,
            locator=str(good_path),
        )
        blob = read_file_datasource_bytes(good_cfg)
        receipt = await ingest_datasource_raw(
            tenant_id=tenant_id,
            collection_id="n01-ds",
            content=blob,
            content_hash=good_cfg.content_hash,
            name=good_cfg.name,
            locator=good_cfg.locator,
            require_hash=True,
            ledger=lg,
            domain_id=domain_id,
        )
        ok_ingest = (
            receipt.get("integrity", {}).get("ok") is True
            and receipt.get("hash_check", {}).get("ok") is True
            and receipt.get("certified") is False
        )
        cases.append(
            {
                "id": "hash_ok_ingest_and_verify",
                "ok": ok_ingest,
                "detail": "" if ok_ingest else "ingest_or_verify_failed",
            }
        )
    finally:
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N01_DATASOURCE_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "datasource_raw_integrity",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n01_full_conformance": False,
        "note": "DataSourceConfig content_hash → FactLedger; not full connector matrix / N01 certified",
    }


def evaluate_datasource_raw_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N01 DataSource Raw 门槛门；certified 恒 false。

    Args:
        suite: ``run_datasource_raw_suite`` 回执。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n01_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "datasource_raw_integrity",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n01_full_conformance": False,
        "note": "DataSourceConfig hash path; not all connectors / N01 certified",
    }


_N01_CONNECTOR_MATRIX_CASES = (
    "matrix_declares_file_sql_api",
    "file_hash_snapshot_ok",
    "sql_hash_snapshot_ok",
    "api_hash_snapshot_ok",
    "sql_hash_mismatch_rejected",
    "api_hash_mismatch_rejected",
)


async def run_datasource_connector_matrix_suite(
    *,
    ledger: Optional["FactLedger"] = None,
    tenant_id: str = "n01-matrix-tenant",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N01 Core 连接器矩阵：file/sql/api 均走 hash 强制快照 → Raw。

    Args:
        ledger: 可选账本；默认临时目录。
        tenant_id: 写入租户。
        domain_id: 可选域（调用方传入）。

    Returns:
        套件汇总；``certified`` / ``n01_full_conformance`` 恒 false。
    """
    import tempfile

    from core.harness.ontology_engine.data_source import (
        DataSourceConfig,
        DataSourceIntegrityError,
        DATASOURCE_RAW_CONNECTOR_MATRIX,
        datasource_raw_connector_matrix,
        sha256_bytes,
        snapshot_datasource_bytes,
        validate_datasource_content_hash,
    )

    matrix_meta = datasource_raw_connector_matrix()
    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n01-connector-matrix-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await lg.initialize()
        work = root
    else:
        lg = ledger  # type: ignore[assignment]
        await lg.initialize()
        work = Path(tempfile.mkdtemp(prefix="n01-matrix-files-"))

    cases: List[Dict[str, Any]] = []
    try:
        meta = matrix_meta
        matrix_ok = (
            list(meta.get("connectors") or []) == list(DATASOURCE_RAW_CONNECTOR_MATRIX)
            and meta.get("certified") is False
        )
        cases.append(
            {
                "id": "matrix_declares_file_sql_api",
                "ok": matrix_ok,
                "detail": "" if matrix_ok else "matrix_mismatch",
            }
        )

        # file
        fpath = work / "matrix-file.json"
        fpath.write_bytes(b'[{"id":1}]')
        fcfg = DataSourceConfig(
            name="matrix-file",
            source_type="file",
            connection={"file_path": str(fpath), "format": "json"},
            content_hash="",
            locator=str(fpath),
        )
        fblob = snapshot_datasource_bytes(fcfg)
        fcfg.content_hash = sha256_bytes(fblob)
        freceipt = await ingest_datasource_raw(
            tenant_id=tenant_id,
            collection_id="n01-matrix",
            content=fblob,
            content_hash=fcfg.content_hash,
            name=fcfg.name,
            locator=fcfg.locator,
            connector="datasource:file",
            require_hash=True,
            ledger=lg,
            domain_id=domain_id,
        )
        file_ok = (
            freceipt.get("integrity", {}).get("ok") is True
            and freceipt.get("certified") is False
        )
        cases.append(
            {
                "id": "file_hash_snapshot_ok",
                "ok": file_ok,
                "detail": "" if file_ok else "file_ingest_failed",
            }
        )

        # sql / api：稳定 JSON 快照 + hash 强制
        records = [{"b": 2, "a": 1}]
        for st, case_ok, case_bad in (
            ("sql", "sql_hash_snapshot_ok", "sql_hash_mismatch_rejected"),
            ("api", "api_hash_snapshot_ok", "api_hash_mismatch_rejected"),
        ):
            cfg = DataSourceConfig(
                name=f"matrix-{st}",
                source_type=st,
                connection={},
                mapping={},
                content_hash="",
                locator=f"{st}://matrix",
            )
            blob = snapshot_datasource_bytes(cfg, records=records)
            cfg.content_hash = sha256_bytes(blob)
            receipt = await ingest_datasource_raw(
                tenant_id=tenant_id,
                collection_id="n01-matrix",
                content=blob,
                content_hash=cfg.content_hash,
                name=cfg.name,
                locator=cfg.locator,
                connector=f"datasource:{st}",
                require_hash=True,
                ledger=lg,
                domain_id=domain_id,
            )
            ok_ingest = (
                receipt.get("integrity", {}).get("ok") is True
                and receipt.get("certified") is False
            )
            cases.append(
                {
                    "id": case_ok,
                    "ok": ok_ingest,
                    "detail": "" if ok_ingest else f"{st}_ingest_failed",
                }
            )

            bad = DataSourceConfig(
                name=f"matrix-{st}-bad",
                source_type=st,
                connection={},
                content_hash="0" * 64,
            )
            mismatch_ok = False
            try:
                validate_datasource_content_hash(
                    bad,
                    snapshot_datasource_bytes(bad, records=records),
                    require_hash=True,
                )
            except DataSourceIntegrityError:
                mismatch_ok = True
            cases.append(
                {
                    "id": case_bad,
                    "ok": mismatch_ok,
                    "detail": "" if mismatch_ok else f"{st}_mismatch_accepted",
                }
            )
    finally:
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N01_CONNECTOR_MATRIX_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "datasource_connector_matrix",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "matrix": matrix_meta,
        "certified": False,
        "n01_full_conformance": False,
        "note": (
            "Core file/sql/api hash-forced snapshots; "
            "not vendor-driver matrix / not N01 certified"
        ),
    }


def evaluate_datasource_connector_matrix_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N01 连接器矩阵门槛门；certified 恒 false。

    Args:
        suite: ``run_datasource_connector_matrix_suite`` 回执。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n01_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "datasource_connector_matrix",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n01_full_conformance": False,
        "note": "Core source_type matrix; not vendor / N01 certified",
    }


_N01_VENDOR_MATRIX_CASES = (
    "matrix_declares_sqlite_postgresql_mysql_oracle",
    "probe_sqlite_honest",
    "probe_postgresql_honest",
    "probe_mysql_honest",
    "oracle_declared_unavailable",
    "missing_driver_not_fake_green",
    "honesty_flags_false",
)


def run_datasource_vendor_matrix_suite() -> Dict[str, Any]:
    """N01 SQL vendor 驱动矩阵：软依赖探测 + 诚实声明；certified 恒 false。

    Returns:
        套件汇总；``certified`` / ``n01_full_conformance`` 恒 false。
        缺驱动时 ``available=false``，不要求装齐驱动即可过套件。
    """
    from core.harness.ontology_engine.data_source import (
        DATASOURCE_VENDOR_DRIVER_MATRIX,
        datasource_vendor_driver_matrix,
        probe_vendor_driver,
    )

    matrix_meta = datasource_vendor_driver_matrix()
    cases: List[Dict[str, Any]] = []

    vendors = list(matrix_meta.get("vendors") or [])
    matrix_ok = (
        vendors == list(DATASOURCE_VENDOR_DRIVER_MATRIX)
        and matrix_meta.get("certified") is False
        and matrix_meta.get("n01_full_conformance") is False
        and "oracle" in (matrix_meta.get("declared_unavailable") or [])
    )
    cases.append(
        {
            "id": "matrix_declares_sqlite_postgresql_mysql_oracle",
            "ok": matrix_ok,
            "detail": "" if matrix_ok else "matrix_mismatch",
        }
    )

    for vendor in ("sqlite", "postgresql", "mysql"):
        probe = probe_vendor_driver(vendor)
        honest = (
            probe.get("vendor") == vendor
            and probe.get("certified") is False
            and probe.get("n01_full_conformance") is False
            and isinstance(probe.get("available"), bool)
            and (
                (probe.get("available") is True and probe.get("status") == "available")
                or (
                    probe.get("available") is False
                    and probe.get("status") == "unavailable"
                )
            )
        )
        cases.append(
            {
                "id": f"probe_{vendor}_honest",
                "ok": honest,
                "detail": "" if honest else f"{vendor}_probe_dishonest",
                "probe": probe,
            }
        )

    oracle = probe_vendor_driver("oracle")
    oracle_ok = (
        oracle.get("status") == "declared_unavailable"
        and oracle.get("available") is False
        and oracle.get("certified") is False
    )
    cases.append(
        {
            "id": "oracle_declared_unavailable",
            "ok": oracle_ok,
            "detail": "" if oracle_ok else "oracle_not_declared_unavailable",
            "probe": oracle,
        }
    )

    # 为什么：缺驱动不得假绿 — 任一 soft_probe unavailable 时 certified 必须仍为 false
    fake_green = False
    for v, p in (matrix_meta.get("probes") or {}).items():
        if p.get("available") is False and p.get("certified") is True:
            fake_green = True
        if p.get("status") == "declared_unavailable" and p.get("available") is True:
            fake_green = True
    cases.append(
        {
            "id": "missing_driver_not_fake_green",
            "ok": not fake_green,
            "detail": "" if not fake_green else "fake_green_detected",
        }
    )

    honesty_ok = (
        matrix_meta.get("certified") is False
        and matrix_meta.get("n01_full_conformance") is False
    )
    cases.append(
        {
            "id": "honesty_flags_false",
            "ok": honesty_ok,
            "detail": "" if honesty_ok else "honesty_flags_set",
        }
    )

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N01_VENDOR_MATRIX_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "datasource_vendor_matrix",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "matrix": matrix_meta,
        "certified": False,
        "n01_full_conformance": False,
        "note": (
            "SQL vendor soft-probe matrix; not production cluster acceptance / "
            "not N01 certified"
        ),
    }


def evaluate_datasource_vendor_matrix_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N01 vendor 驱动矩阵门槛门；certified 恒 false。

    Args:
        suite: ``run_datasource_vendor_matrix_suite`` 回执。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n01_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "datasource_vendor_matrix",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n01_full_conformance": False,
        "note": "vendor soft-probe matrix; not production / N01 certified",
    }


_N09_CASES = (
    "query_facts_no_leak",
    "get_source_no_leak",
    "gateway_no_leak",
    "unified_gateway_fact_no_leak",
    "unified_gateway_object_set_no_leak",
    "verify_raw_no_leak",
    "object_set_no_leak",
    "unified_audit_no_leak",
    "kb_retrieve_no_leak",
    "wiki_retrieve_no_leak",
    "graphrag_no_leak",
    "graphrag_caller_passthrough",
    "graphindex_no_leak",
    "graph_write_tenant",
    "cross_domain_resolve_tenant",
)


async def run_cross_tenant_isolation_suite(
    *,
    ledger: Optional["FactLedger"] = None,
    tenant_a: str = "n09-tenant-a",
    tenant_b: str = "n09-tenant-b",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N09 跨租户 0 泄漏加深套件（含跨域写边 / publish snapshot 租户）。

    Args:
        ledger: 可选账本；默认临时目录新建（不污染单例）。
        tenant_a: 写入租户。
        tenant_b: 负向查询租户。
        domain_id: 可选域过滤（由调用方传入；harness 不默认业务域名）。

    Returns:
        套件汇总；``certified`` / ``n09_full_conformance`` 恒 false。
    """
    import os
    import tempfile

    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    root: Optional[Path] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n09-cross-tenant-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await lg.initialize()
    else:
        lg = ledger  # type: ignore[assignment]
        await lg.initialize()

    cases: List[Dict[str, Any]] = []
    prev_kb_tenants = os.environ.get("AIPLAT_KB_TENANTS_DIR")
    prev_embed_backend = os.environ.get("AIPLAT_EMBED_BACKEND")
    prev_aiplat_home = os.environ.get("AIPLAT_HOME")
    try:
        src = await lg.register_source(
            tenant_id=tenant_a,
            collection_id="n09-kb",
            kind="file",
            uri="file://n09/secret.txt",
            content=b"n09-secret-payload",
            connector="n09_cross_tenant",
            domain_id=domain_id,
        )
        # 为什么：K1 用临时 ObjectType 绑定，避免 harness 依赖业务域种子
        import json as _json

        probe_domain = (domain_id or "n09-probe").strip() or "n09-probe"
        probe_type = "N09Probe"
        bind_dir = root or Path(tempfile.mkdtemp(prefix="n09-bindings-"))
        bindings_path = bind_dir / "n09-object-types.json"
        bindings_path.write_text(
            _json.dumps(
                {
                    "domain_id": probe_domain,
                    "object_types": [
                        {
                            "object_type_id": probe_type,
                            "label": "N09 probe",
                            "primary_key": "id",
                            "domain_id": probe_domain,
                            "properties": [
                                {"id": "note", "type": "string", "indexed": True}
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        fact = await lg.put_fact(
            tenant_id=tenant_a,
            collection_id="n09-kb",
            subject=f"{probe_type}:n09-secret",
            predicate="note",
            object="secret",
            evidence=[
                {
                    "source_id": src["source_id"],
                    "locator": "1",
                    "quote": "secret",
                    "fetched_at": src["fetched_at"],
                }
            ],
            source_policy="n09",
            extractor_version="n09",
            review_status="published",
            confidence=0.9,
            allow_bootstrap_published=True,
            domain_id=probe_domain,
        )
        same = await lg.query_facts(tenant_id=tenant_a, domain_id=domain_id or None)
        other = await lg.query_facts(tenant_id=tenant_b, domain_id=domain_id or None)
        q_ok = any(r.get("fact_id") == fact["fact_id"] for r in same) and not any(
            r.get("fact_id") == fact["fact_id"] for r in other
        )
        cases.append(
            {
                "id": "query_facts_no_leak",
                "ok": q_ok,
                "detail": "" if q_ok else "query_facts_leak_or_miss",
            }
        )

        got_a = await lg.get_source(src["source_id"], tenant_id=tenant_a)
        got_b = await lg.get_source(src["source_id"], tenant_id=tenant_b)
        s_ok = got_a is not None and got_b is None
        cases.append(
            {
                "id": "get_source_no_leak",
                "ok": s_ok,
                "detail": "" if s_ok else "get_source_leak",
            }
        )

        gw = await lg.query_facts_gateway(
            tenant_id=tenant_b, query="secret", require_citations=True
        )
        g_ok = (
            not gw.get("facts")
            and gw.get("abstained") is True
            and not gw.get("citations")
        )
        cases.append(
            {
                "id": "gateway_no_leak",
                "ok": g_ok,
                "detail": "" if g_ok else "gateway_leak",
            }
        )

        # N09 deepen：统一 Gateway fact/object_set 路由同样不得跨租户泄漏
        ug_fact_b = await unified_query_gateway(
            tenant_id=tenant_b,
            query="secret",
            route="fact",
            ledger=lg,
        )
        ug_fact_ok = (
            ug_fact_b.get("abstained") is True
            and not ug_fact_b.get("citations")
            and not ug_fact_b.get("facts")
        )
        cases.append(
            {
                "id": "unified_gateway_fact_no_leak",
                "ok": ug_fact_ok,
                "detail": "" if ug_fact_ok else "unified_gateway_fact_leak",
            }
        )

        ug_os_a = await unified_query_gateway(
            tenant_id=tenant_a,
            route="object_set",
            object_set_request={
                "object_type": probe_type,
                "domain_id": probe_domain,
            },
            permissions=["kb:read"],
            ledger=lg,
            bindings_path=bindings_path,
        )
        ug_os_b = await unified_query_gateway(
            tenant_id=tenant_b,
            route="object_set",
            object_set_request={
                "object_type": probe_type,
                "domain_id": probe_domain,
            },
            permissions=["kb:read"],
            ledger=lg,
            bindings_path=bindings_path,
        )
        ug_os_ok = (
            ug_os_a.get("abstained") is False
            and bool(ug_os_a.get("citations"))
            and ug_os_b.get("abstained") is True
            and not ug_os_b.get("citations")
        )
        cases.append(
            {
                "id": "unified_gateway_object_set_no_leak",
                "ok": ug_os_ok,
                "detail": "" if ug_os_ok else "unified_gateway_object_set_leak",
            }
        )

        v_ok = False
        try:
            await lg.verify_raw_integrity(src["source_id"], tenant_id=tenant_b)
        except FactLedgerError:
            v_ok = True
        cases.append(
            {
                "id": "verify_raw_no_leak",
                "ok": v_ok,
                "detail": "" if v_ok else "verify_allowed_cross_tenant",
            }
        )

        # K1：ObjectSet 入口跨租户（经 FactLedger 租户前置；临时 ObjectType）
        from core.harness.knowledge_pipeline.object_set import query_object_set

        os_kwargs: Dict[str, Any] = {"ledger": lg}
        if bindings_path is not None:
            os_kwargs["bindings_path"] = bindings_path
        os_a = await query_object_set(
            {"object_type": probe_type, "domain_id": probe_domain},
            tenant_id=tenant_a,
            permissions=["kb:read"],
            **os_kwargs,
        )
        os_b = await query_object_set(
            {"object_type": probe_type, "domain_id": probe_domain},
            tenant_id=tenant_b,
            permissions=["kb:read"],
            **os_kwargs,
        )
        ids_a = {
            str(i.get("id") or i.get("order_id") or "")
            for i in (os_a.get("items") or [])
        }
        ids_b = {
            str(i.get("id") or i.get("order_id") or "")
            for i in (os_b.get("items") or [])
        }
        os_ok = (
            bindings_path is not None
            and os_a.get("status") == "ok"
            and "n09-secret" in ids_a
            and os_b.get("status") == "ok"
            and "n09-secret" not in ids_b
            and int(os_b.get("total") or 0) == 0
        )
        cases.append(
            {
                "id": "object_set_no_leak",
                "ok": os_ok,
                "detail": "" if os_ok else "object_set_leak_or_miss",
            }
        )

        # K1：Unified Audit / ActionStore 跨租户（物理 tenant_id 召回前过滤）
        from core.harness.infrastructure.action_store import ActionStore
        from core.harness.knowledge_pipeline.unified_audit_view import (
            list_unified_audit_events,
        )

        store_root = root or Path(tempfile.mkdtemp(prefix="n09-audit-"))
        store_db = str(store_root / "action_store.sqlite3")
        store = ActionStore(store_db)
        await store.initialize()
        await store.insert_audit(
            {
                "action_id": "n09:probe",
                "entity_id": "n09-secret",
                "domain_id": (domain_id or "n09").strip() or "n09",
                "actor": "n09-suite",
                "result_status": "executed",
                "tenant_id": tenant_a,
                "params": {"tenant_id": tenant_a},
            }
        )
        view_a = await list_unified_audit_events(
            tenant_id=tenant_a,
            streams=["action_store"],
            action_store_db_path=store_db,
            limit=50,
        )
        view_b = await list_unified_audit_events(
            tenant_id=tenant_b,
            streams=["action_store"],
            action_store_db_path=store_db,
            limit=50,
        )
        ua_ok = (
            view_a.get("certified") is False
            and int(view_a.get("count") or 0) >= 1
            and int(view_b.get("count") or 0) == 0
            and view_b.get("certified") is False
        )
        cases.append(
            {
                "id": "unified_audit_no_leak",
                "ok": ua_ok,
                "detail": "" if ua_ok else "unified_audit_leak_or_miss",
            }
        )

        # K2：KB 入口跨租户（per-tenant sqlite 路径隔离）
        import json as _json_kb
        import sqlite3 as _sqlite3

        from core.harness.knowledge.embedder import hash_embed as _hash_embed
        from core.harness.syscalls.retrieval import sys_kb_retrieve

        kb_root = root or Path(tempfile.mkdtemp(prefix="n09-kb-"))
        kb_tenants = kb_root / "kb_tenants"
        os.environ["AIPLAT_KB_TENANTS_DIR"] = str(kb_tenants)
        os.environ["AIPLAT_EMBED_BACKEND"] = "hash"
        tenant_a_dir = kb_tenants / tenant_a
        tenant_a_dir.mkdir(parents=True, exist_ok=True)
        kb_db = tenant_a_dir / "kb.sqlite3"
        secret_text = "n09-secret-payload"
        with _sqlite3.connect(str(kb_db)) as kb_conn:
            kb_conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kb_elements (
                    element_id TEXT PRIMARY KEY, doc_id TEXT, type TEXT,
                    page_idx INTEGER, text TEXT, cells_json TEXT,
                    meta_json TEXT, tenant_id TEXT);
                CREATE TABLE IF NOT EXISTS kb_embeddings (
                    element_id TEXT PRIMARY KEY, vector_json TEXT, tenant_id TEXT);
                """
            )
            kb_conn.execute(
                "INSERT OR REPLACE INTO kb_elements"
                "(element_id, doc_id, type, page_idx, text, cells_json, "
                "meta_json, tenant_id) VALUES (?,?,?,?,?,?,?,?)",
                (
                    "n09-secret-el",
                    "n09-secret-doc",
                    "paragraph",
                    0,
                    secret_text,
                    None,
                    "{}",
                    tenant_a,
                ),
            )
            # 为什么：K3 GraphRAG 向量层探针需要同库 embedding（hash，离线可复现）
            kb_conn.execute(
                "INSERT OR REPLACE INTO kb_embeddings"
                "(element_id, vector_json, tenant_id) VALUES (?,?,?)",
                (
                    "n09-secret-el",
                    _json_kb.dumps(_hash_embed(secret_text)),
                    tenant_a,
                ),
            )
            kb_conn.commit()
        kb_a = sys_kb_retrieve(
            secret_text,
            [],
            tenant_id=tenant_a,
            top_k=5,
        )
        kb_b = sys_kb_retrieve(
            secret_text,
            [],
            tenant_id=tenant_b,
            top_k=5,
        )
        secret_hit = any(
            secret_text in str(r.get("text") or "") for r in (kb_a or [])
        )
        kb_ok = secret_hit and not (kb_b or [])
        cases.append(
            {
                "id": "kb_retrieve_no_leak",
                "ok": kb_ok,
                "detail": "" if kb_ok else "kb_retrieve_leak_or_miss",
            }
        )

        # K2：Wiki 入口跨租户（retriever/query tenant_id mismatch 硬门）
        # 为什么：Wiki 页按 collection 存；现网硬隔离点是 mismatch→空，非全域 collection ACL
        from core.harness.knowledge.types import KnowledgeQuery
        from core.harness.knowledge.wiki_retriever import WikiPageRetriever

        wiki_ret = WikiPageRetriever(
            wiki_titles=["N09 Secret"],
            collection_ids=["n09-wiki-probe"],
            tenant_id=tenant_a,
        )
        wiki_leak = await wiki_ret.retrieve(
            KnowledgeQuery(query="n09-secret", limit=5, tenant_id=tenant_b)
        )
        wiki_same = await wiki_ret.retrieve(
            KnowledgeQuery(query="n09-secret", limit=5, tenant_id=tenant_a)
        )
        wiki_ok = wiki_leak == [] and isinstance(wiki_same, list)
        cases.append(
            {
                "id": "wiki_retrieve_no_leak",
                "ok": wiki_ok,
                "detail": "" if wiki_ok else "wiki_retrieve_leak_or_miss",
            }
        )

        # K3：GraphRAG 向量层跨租户（显式 tenant_id 不回退 default/wiki）
        from core.harness.knowledge_pipeline.retriever import GraphRAGRetriever

        gr = GraphRAGRetriever()
        probe_domain = (domain_id or "n09-probe").strip() or "n09-probe"
        gr_a = await gr._vector_search(
            secret_text, probe_domain, 5, tenant_id=tenant_a
        )
        gr_b = await gr._vector_search(
            secret_text, probe_domain, 5, tenant_id=tenant_b
        )
        gr_hit = any(secret_text in str(c.get("content") or "") for c in (gr_a or []))
        gr_ok = gr_hit and not (gr_b or [])
        cases.append(
            {
                "id": "graphrag_no_leak",
                "ok": gr_ok,
                "detail": "" if gr_ok else "graphrag_leak_or_miss",
            }
        )

        # K4：CRAG / 治理入口透传 tenant_id → GraphRAG.retrieve
        captured: Dict[str, Any] = {}
        _orig_retrieve = GraphRAGRetriever.retrieve

        async def _capture_retrieve(
            self: Any,
            query: str,
            domain_id: str = DomainRouter.PLATFORM_DEFAULT_GRAPH_DOMAIN,
            top_k: int = 10,
            run_id: str = "",
            tenant_id: str = "",
            actor_role: str = "",
            actor_scopes: Any = None,
            collection_id: str = "",
            **_kwargs: Any,
        ) -> Dict[str, Any]:
            # 为什么：N07 field ACL 后 CRAG 会传 actor_*；签名须兼容否则 TypeError→静默降 Level1
            captured["tenant_id"] = tenant_id
            captured["domain_id"] = domain_id
            # 为什么：提前返回 graphrag 命中，避免 CRAG 继续走 Level1+ 拉长探针
            return {
                "mode": "graphrag",
                "chunks": [{"title": "n09", "content": "passthrough"}],
                "reasoning_paths": [],
                "subgraph_size": 1,
            }

        GraphRAGRetriever.retrieve = _capture_retrieve  # type: ignore[method-assign]
        crag_tid: Any = None
        gov_tid: Any = None
        try:
            # 为什么：经 CoreFacade + importlib，避免 harness AST 直导 apps/
            import importlib

            from core.api.core_facade import governance_locate_view
            from core.harness.syscalls.retrieval_crag import sys_crag_retrieve

            await sys_crag_retrieve(
                "n09 passthrough probe",
                domain_id=probe_domain,
                tenant_id=tenant_a,
                top_k=3,
                enable_hyde=False,
            )
            crag_tid = captured.get("tenant_id")
            captured.clear()

            _gov = importlib.import_module("core.apps.fde.service.governance_deepen")
            _orig_locate = _gov.locate_via_ontology

            def _fake_locate(
                domain_id: str, query: str, *, top_k: int = 8
            ) -> Dict[str, Any]:
                return {
                    "hits": [{"id": "n09-hit", "name": "n09"}],
                    "domain_id": domain_id,
                    "query": query,
                }

            _gov.locate_via_ontology = _fake_locate  # type: ignore[assignment]
            try:
                await governance_locate_view(
                    probe_domain,
                    "n09 passthrough probe",
                    top_k=3,
                    with_graphrag=True,
                    tenant_id=tenant_a,
                )
            finally:
                _gov.locate_via_ontology = _orig_locate  # type: ignore[assignment]
            gov_tid = captured.get("tenant_id")
            pass_ok = crag_tid == tenant_a and gov_tid == tenant_a
        except Exception as exc:
            pass_ok = False
            captured["error"] = str(exc)[:200]
        finally:
            GraphRAGRetriever.retrieve = _orig_retrieve  # type: ignore[method-assign]
        cases.append(
            {
                "id": "graphrag_caller_passthrough",
                "ok": pass_ok,
                "detail": (
                    ""
                    if pass_ok
                    else (
                        "passthrough_miss "
                        f"crag={crag_tid!r} gov={gov_tid!r} "
                        f"err={captured.get('error', '')!r}"
                    )
                ),
            }
        )

        # K5：GraphIndex 图层跨租户（per-tenant db 前缀 + GraphRAG _find_node 透传）
        from core.harness.ontology_engine.graph_index import GraphIndex

        home_root = root or Path(tempfile.mkdtemp(prefix="n09-gi-home-"))
        os.environ["AIPLAT_HOME"] = str(home_root)
        GraphIndex._loaded_instances.clear()
        secret_name = "N09SecretEntity"
        gi_a = GraphIndex(probe_domain, tenant_id=tenant_a)
        gi_a.add_entity("n09-secret-node", secret_name, "概念")
        # 为什么：强制落盘并清缓存，确保 tenant_b load 不会命中内存脏图
        GraphIndex._loaded_instances.clear()
        found_a = gr._find_node(
            secret_name, probe_domain, tenant_id=tenant_a
        )
        found_b = gr._find_node(
            secret_name, probe_domain, tenant_id=tenant_b
        )
        gi_ok = (
            found_a is not None
            and found_a.get("name") == secret_name
            and found_b is None
        )
        cases.append(
            {
                "id": "graphindex_no_leak",
                "ok": gi_ok,
                "detail": "" if gi_ok else "graphindex_leak_or_miss",
            }
        )

        # K6：图写入路径强制 tenant（缺省拒绝；写入落到对应租户库）
        from core.harness.knowledge_pipeline.extractor import (
            write_extraction_to_graph_index,
        )

        GraphIndex._loaded_instances.clear()
        denied = write_extraction_to_graph_index(
            probe_domain,
            [{"name": "N09WriteDenied", "class_type": "概念"}],
            [],
            source_doc_id="n09-k6-denied",
            tenant_id="",
        )
        write_name = "N09WriteSecret"
        wrote = write_extraction_to_graph_index(
            probe_domain,
            [{"name": write_name, "class_type": "概念"}],
            [],
            source_doc_id="n09-k6-write",
            tenant_id=tenant_a,
        )
        GraphIndex._loaded_instances.clear()
        wrote_a = gr._find_node(write_name, probe_domain, tenant_id=tenant_a)
        wrote_b = gr._find_node(write_name, probe_domain, tenant_id=tenant_b)
        # 为什么：created_entities 是 entity_id slug；跨租户断言以 _find_node 为准
        gw_ok = (
            denied.get("error") == "tenant_id_required"
            and denied.get("ok") is False
            and wrote.get("ok") is True
            and wrote.get("tenant_id") == tenant_a
            and wrote_a is not None
            and wrote_a.get("name") == write_name
            and wrote_b is None
        )
        cases.append(
            {
                "id": "graph_write_tenant",
                "ok": gw_ok,
                "detail": "" if gw_ok else "graph_write_tenant_miss",
            }
        )

        # K7：跨域写边 + publish snapshot 按租户分库
        from core.harness.knowledge_pipeline.resolver import CrossDomainResolver

        left_dom = f"{probe_domain}-left"
        right_dom = f"{probe_domain}-right"
        GraphIndex._loaded_instances.clear()
        g_la = GraphIndex(left_dom, tenant_id=tenant_a)
        g_ra = GraphIndex(right_dom, tenant_id=tenant_a)
        g_la.add_entity("n09-left", "N09Left", "概念")
        g_ra.add_entity("n09-right", "N09Right", "概念")
        GraphIndex._loaded_instances.clear()
        denied_resolve = CrossDomainResolver.resolve(
            "n09-view",
            "n09-left",
            "n09-right",
            left_dom,
            right_dom,
            0.9,
            tenant_id="",
        )
        ok_resolve = CrossDomainResolver.resolve(
            "n09-view",
            "n09-left",
            "n09-right",
            left_dom,
            right_dom,
            0.9,
            tenant_id=tenant_a,
        )
        GraphIndex._loaded_instances.clear()
        meta_a = (
            GraphIndex.load(left_dom, tenant_id=tenant_a)
            .get_node("n09-left")
        )
        meta_b = (
            GraphIndex.load(left_dom, tenant_id=tenant_b)
            .get_node("n09-left")
        )
        cross_a = (
            isinstance(getattr(meta_a, "metadata", None), dict)
            and isinstance(meta_a.metadata.get("_cross_domain"), dict)
            and meta_a.metadata["_cross_domain"].get("tenant_id") == tenant_a
        )
        # publish snapshot：同租户分库落盘（无需真实 ontology YAML；直接测 GraphIndex 路径）
        from core.api import core_facade as _facade

        snap_ok = False
        try:
            GraphIndex._loaded_instances.clear()
            g_pub = GraphIndex.load(left_dom, tenant_id=tenant_a)
            snap = g_pub.snapshot("n09-k7-pre-publish")
            snaps_a = g_pub.list_snapshots(limit=5)
            GraphIndex._loaded_instances.clear()
            snaps_b = GraphIndex.load(left_dom, tenant_id=tenant_b).list_snapshots(
                limit=5
            )
            snap_ok = (
                isinstance(snap, dict)
                and any(
                    "n09-k7-pre-publish" in str(s.get("label") or "")
                    for s in (snaps_a or [])
                )
                and not any(
                    "n09-k7-pre-publish" in str(s.get("label") or "")
                    for s in (snaps_b or [])
                )
            )
            # 覆盖 facade 透传签名（不依赖真实域 YAML）
            _ = _facade.list_rule_versions(left_dom, tenant_id=tenant_a)
        except Exception:
            snap_ok = False
        cd_ok = (
            denied_resolve is False
            and ok_resolve is True
            and cross_a
            and meta_b is None
            and snap_ok
        )
        cases.append(
            {
                "id": "cross_domain_resolve_tenant",
                "ok": cd_ok,
                "detail": "" if cd_ok else "cross_domain_resolve_tenant_miss",
            }
        )
        GraphIndex._loaded_instances.clear()
    finally:
        if prev_kb_tenants is None:
            os.environ.pop("AIPLAT_KB_TENANTS_DIR", None)
        else:
            os.environ["AIPLAT_KB_TENANTS_DIR"] = prev_kb_tenants
        if prev_embed_backend is None:
            os.environ.pop("AIPLAT_EMBED_BACKEND", None)
        else:
            os.environ["AIPLAT_EMBED_BACKEND"] = prev_embed_backend
        if prev_aiplat_home is None:
            os.environ.pop("AIPLAT_HOME", None)
        else:
            os.environ["AIPLAT_HOME"] = prev_aiplat_home
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N09_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "cross_tenant_isolation",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n09_full_conformance": False,
        "note": (
            "FactLedger+unified Gateway fact/object_set+ObjectSet+UnifiedAudit+"
            "Wiki/KB+GraphRAG+caller+GraphIndex+graph_write+cross_domain/snapshot; "
            "not global zero-leak / not N09 certified"
        ),
    }


def evaluate_cross_tenant_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N09 跨租户门槛门；certified 恒 false。

    Args:
        suite: ``run_cross_tenant_isolation_suite`` 回执。

    Returns:
        gate 字典。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n09_full_conformance") is True:
        # 为什么：套件误标认证仍拒绝
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "cross_tenant_isolation",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n09_full_conformance": False,
        "note": (
            "FactLedger+ObjectSet+UnifiedAudit+Wiki/KB+GraphRAG+caller+"
            "GraphIndex+graph_write+cross_domain/snapshot deepen; "
            "not platform-wide zero-leak certified"
        ),
    }


_N03_CASES = (
    "published_without_evidence_rejected",
    "published_with_evidence_ok",
    "claim_conflict_recorded",
)


async def run_claim_evidence_suite(
    *,
    ledger: Optional["FactLedger"] = None,
    tenant_id: str = "n03-tenant",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N03 Claim 证据硬门 + 冲突记录最小加深套件。

    Args:
        ledger: 可选账本；默认临时目录新建。
        tenant_id: 写入租户。
        domain_id: 可选域（调用方传入；harness 不默认业务域名）。

    Returns:
        套件汇总；``certified`` / ``n03_full_conformance`` 恒 false。
    """
    import tempfile

    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n03-claim-evidence-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await lg.initialize()
    else:
        lg = ledger  # type: ignore[assignment]
        await lg.initialize()

    cases: List[Dict[str, Any]] = []
    try:
        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n03-kb",
            kind="file",
            uri="file://n03/claim-evidence.txt",
            content=b"n03-claim-evidence",
            connector="n03",
            domain_id=domain_id,
        )
        evidence = [
            {
                "source_id": src["source_id"],
                "locator": "extract",
                "quote": "n03",
                "fetched_at": src["fetched_at"],
            }
        ]

        rejected = False
        try:
            await lg.put_claim(
                tenant_id=tenant_id,
                collection_id="n03-kb",
                text="published without evidence",
                evidence=[],
                source_policy="n03_policy",
                extractor_version="n03",
                review_status="published",
                confidence=0.5,
                domain_id=domain_id,
            )
        except FactLedgerError:
            rejected = True
        cases.append(
            {
                "id": "published_without_evidence_rejected",
                "ok": rejected,
                "detail": "" if rejected else "empty_evidence_accepted",
            }
        )

        claim_a = await lg.put_claim(
            tenant_id=tenant_id,
            collection_id="n03-kb",
            text="door is locked",
            evidence=evidence,
            source_policy="n03_policy",
            extractor_version="n03",
            review_status="published",
            confidence=0.8,
            domain_id=domain_id,
            conflict_key="door.lock_state",
        )
        # 为什么：生产路径读回 Claim，避免 get_claim 零 caller
        roundtrip = await lg.get_claim(claim_a["claim_id"], tenant_id=tenant_id)
        ok_write = (
            bool(claim_a.get("claim_id"))
            and not claim_a.get("conflict_id")
            and roundtrip is not None
            and roundtrip.get("text") == "door is locked"
        )
        cases.append(
            {
                "id": "published_with_evidence_ok",
                "ok": ok_write,
                "detail": "" if ok_write else "write_failed",
            }
        )

        claim_b = await lg.put_claim(
            tenant_id=tenant_id,
            collection_id="n03-kb",
            text="door is unlocked",
            evidence=evidence,
            source_policy="n03_policy",
            extractor_version="n03",
            review_status="published",
            confidence=0.7,
            domain_id=domain_id,
            conflict_key="door.lock_state",
        )
        conflicts = await lg.list_claim_conflicts(
            tenant_id=tenant_id,
            collection_id="n03-kb",
            conflict_key="door.lock_state",
            status="open",
        )
        conf_ok = bool(claim_b.get("conflict_id")) and len(conflicts) >= 1
        cases.append(
            {
                "id": "claim_conflict_recorded",
                "ok": conf_ok,
                "detail": "" if conf_ok else "conflict_missing",
            }
        )
    finally:
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N03_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "claim_evidence",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n03_full_conformance": False,
        "note": "Claim evidence + conflict record slice; not N03 full certification",
    }


def evaluate_claim_evidence_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N03 Claim 证据门槛门；certified 恒 false。

    Args:
        suite: ``run_claim_evidence_suite`` 回执。

    Returns:
        gate 字典。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n03_full_conformance") is True:
        # 为什么：套件误标认证仍拒绝
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "claim_evidence",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n03_full_conformance": False,
        "note": "Claim evidence harden; not N03/N24 certified",
    }


_N24_REVISION_CASES = (
    "overwrite_without_revision_bump_rejected",
    "revision_archived_on_update",
    "get_fact_at_revision_roundtrip",
    "diff_fact_revisions_ok",
)


async def run_fact_revision_suite(
    *,
    ledger: Optional["FactLedger"] = None,
    tenant_id: str = "n24-tenant",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N24 Fact Revision 最小加深套件（禁止无记录覆盖）。

    Args:
        ledger: 可选账本；默认临时目录新建。
        tenant_id: 写入租户。
        domain_id: 可选域（调用方传入；harness 不默认业务域名）。

    Returns:
        套件汇总；``certified`` / ``n24_full_conformance`` 恒 false。
    """
    import tempfile

    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n24-fact-revision-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await lg.initialize()
    else:
        lg = ledger  # type: ignore[assignment]
        await lg.initialize()

    cases: List[Dict[str, Any]] = []
    try:
        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            kind="file",
            uri="file://n24/fact-revision.txt",
            content=b"n24-fact-revision",
            connector="n24",
            domain_id=domain_id,
        )
        evidence = [
            {
                "source_id": src["source_id"],
                "locator": "extract",
                "quote": "n24",
                "fetched_at": src["fetched_at"],
            }
        ]
        # 为什么关写入硬门：本套件只测 revision 归档/抬号；策略门另有 N04 套件
        fact = await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            subject="Door:d1",
            predicate="state",
            object="locked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="draft",
            confidence=0.8,
            domain_id=domain_id,
            revision=1,
            enforce_write_gates=False,
        )
        fid = fact["fact_id"]

        rejected = False
        try:
            await lg.put_fact(
                tenant_id=tenant_id,
                collection_id="n24-kb",
                subject="Door:d1",
                predicate="state",
                object="unlocked",
                evidence=evidence,
                source_policy="n24_policy",
                extractor_version="n24",
                review_status="draft",
                confidence=0.8,
                domain_id=domain_id,
                fact_id=fid,
                revision=1,
                enforce_write_gates=False,
            )
        except FactLedgerError:
            rejected = True
        cases.append(
            {
                "id": "overwrite_without_revision_bump_rejected",
                "ok": rejected,
                "detail": "" if rejected else "silent_overwrite",
            }
        )

        updated = await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            subject="Door:d1",
            predicate="state",
            object="unlocked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="draft",
            confidence=0.8,
            domain_id=domain_id,
            fact_id=fid,
            revision=2,
            revision_actor="n24-suite",
            revision_reason="state_change",
            enforce_write_gates=False,
        )
        hist = await lg.list_fact_revisions(fid, tenant_id=tenant_id)
        archived = [h for h in hist if not h.get("is_head")]
        arch_ok = (
            int(updated.get("revision") or 0) == 2
            and len(archived) >= 1
            and int(archived[0].get("revision") or 0) == 1
            and (archived[0].get("snapshot") or {}).get("object") == "locked"
        )
        cases.append(
            {
                "id": "revision_archived_on_update",
                "ok": arch_ok,
                "detail": "" if arch_ok else "archive_missing",
            }
        )

        old = await lg.get_fact_at_revision(fid, tenant_id=tenant_id, revision=1)
        new = await lg.get_fact_at_revision(fid, tenant_id=tenant_id, revision=2)
        rt_ok = (
            old is not None
            and new is not None
            and old.get("object") == "locked"
            and new.get("object") == "unlocked"
        )
        cases.append(
            {
                "id": "get_fact_at_revision_roundtrip",
                "ok": rt_ok,
                "detail": "" if rt_ok else "revision_read_failed",
            }
        )

        diff = await lg.diff_fact_revisions(
            fid, tenant_id=tenant_id, from_revision=1, to_revision=2
        )
        diff_ok = "object" in (diff.get("changed") or {})
        cases.append(
            {
                "id": "diff_fact_revisions_ok",
                "ok": diff_ok,
                "detail": "" if diff_ok else "diff_missing_object",
            }
        )
    finally:
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N24_REVISION_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "fact_revision",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Fact revision archive + bump; not full N24 certification",
    }


def evaluate_fact_revision_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N24 Fact Revision 门槛门；certified 恒 false。

    Args:
        suite: ``run_fact_revision_suite`` 回执。

    Returns:
        gate 字典。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n24_full_conformance") is True:
        # 为什么：套件误标认证仍拒绝
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "fact_revision",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Fact revision harden; not N24 certified",
    }


_N24_CLAIM_REVISION_CASES = (
    "overwrite_without_revision_bump_rejected",
    "revision_archived_on_update",
    "get_claim_at_revision_roundtrip",
    "diff_claim_revisions_ok",
)


async def run_claim_revision_suite(
    *,
    ledger: Optional["FactLedger"] = None,
    tenant_id: str = "n24-claim-tenant",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N24 Claim Revision 最小加深套件（禁止无记录覆盖）。

    Args:
        ledger: 可选账本；默认临时目录新建。
        tenant_id: 写入租户。
        domain_id: 可选域（调用方传入；harness 不默认业务域名）。

    Returns:
        套件汇总；``certified`` / ``n24_full_conformance`` 恒 false。
    """
    import tempfile

    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n24-claim-revision-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await lg.initialize()
    else:
        lg = ledger  # type: ignore[assignment]
        await lg.initialize()

    cases: List[Dict[str, Any]] = []
    try:
        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            kind="file",
            uri="file://n24/claim-revision.txt",
            content=b"n24-claim-revision",
            connector="n24",
            domain_id=domain_id,
        )
        evidence = [
            {
                "source_id": src["source_id"],
                "locator": "extract",
                "quote": "n24",
                "fetched_at": src["fetched_at"],
            }
        ]
        claim = await lg.put_claim(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            text="door is locked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="published",
            confidence=0.8,
            domain_id=domain_id,
            revision=1,
        )
        cid = claim["claim_id"]

        rejected = False
        try:
            await lg.put_claim(
                tenant_id=tenant_id,
                collection_id="n24-kb",
                text="door is unlocked",
                evidence=evidence,
                source_policy="n24_policy",
                extractor_version="n24",
                review_status="published",
                confidence=0.8,
                domain_id=domain_id,
                claim_id=cid,
                revision=1,
            )
        except FactLedgerError:
            rejected = True
        cases.append(
            {
                "id": "overwrite_without_revision_bump_rejected",
                "ok": rejected,
                "detail": "" if rejected else "silent_overwrite",
            }
        )

        updated = await lg.put_claim(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            text="door is unlocked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="published",
            confidence=0.8,
            domain_id=domain_id,
            claim_id=cid,
            revision=2,
            revision_actor="n24-suite",
            revision_reason="text_change",
        )
        hist = await lg.list_claim_revisions(cid, tenant_id=tenant_id)
        archived = [h for h in hist if not h.get("is_head")]
        arch_ok = (
            int(updated.get("revision") or 0) == 2
            and len(archived) >= 1
            and int(archived[0].get("revision") or 0) == 1
            and (archived[0].get("snapshot") or {}).get("text") == "door is locked"
        )
        cases.append(
            {
                "id": "revision_archived_on_update",
                "ok": arch_ok,
                "detail": "" if arch_ok else "archive_missing",
            }
        )

        old = await lg.get_claim_at_revision(cid, tenant_id=tenant_id, revision=1)
        new = await lg.get_claim_at_revision(cid, tenant_id=tenant_id, revision=2)
        rt_ok = (
            old is not None
            and new is not None
            and old.get("text") == "door is locked"
            and new.get("text") == "door is unlocked"
        )
        cases.append(
            {
                "id": "get_claim_at_revision_roundtrip",
                "ok": rt_ok,
                "detail": "" if rt_ok else "revision_read_failed",
            }
        )

        diff = await lg.diff_claim_revisions(
            cid, tenant_id=tenant_id, from_revision=1, to_revision=2
        )
        diff_ok = "text" in (diff.get("changed") or {})
        cases.append(
            {
                "id": "diff_claim_revisions_ok",
                "ok": diff_ok,
                "detail": "" if diff_ok else "diff_missing_text",
            }
        )
    finally:
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N24_CLAIM_REVISION_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "claim_revision",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Claim revision archive + bump; not full N24 certification",
    }


def evaluate_claim_revision_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N24 Claim Revision 门槛门；certified 恒 false。

    Args:
        suite: ``run_claim_revision_suite`` 回执。

    Returns:
        gate 字典。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n24_full_conformance") is True:
        # 为什么：套件误标认证仍拒绝
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "claim_revision",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Claim revision harden; not N24 certified",
    }


_N24_SOURCE_REVISION_CASES = (
    "overwrite_without_revision_bump_rejected",
    "revision_archived_on_update",
    "get_source_at_revision_roundtrip",
    "diff_source_revisions_ok",
)


async def run_source_revision_suite(
    *,
    ledger: Optional["FactLedger"] = None,
    tenant_id: str = "n24-source-tenant",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N24 Source Revision 最小加深套件（禁止无记录内容覆盖）。

    Args:
        ledger: 可选账本；默认临时目录新建。
        tenant_id: 写入租户。
        domain_id: 可选域（调用方传入；harness 不默认业务域名）。

    Returns:
        套件汇总；``certified`` / ``n24_full_conformance`` 恒 false。
    """
    import tempfile

    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n24-source-revision-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await lg.initialize()
    else:
        lg = ledger  # type: ignore[assignment]
        await lg.initialize()

    cases: List[Dict[str, Any]] = []
    try:
        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            kind="file",
            uri="file://n24/source-revision-v1.txt",
            content=b"n24-source-v1",
            connector="n24",
            domain_id=domain_id,
            source_id="src-n24-source-rev",
            revision=1,
        )
        sid = src["source_id"]

        rejected = False
        try:
            await lg.register_source(
                tenant_id=tenant_id,
                collection_id="n24-kb",
                kind="file",
                uri="file://n24/source-revision-v2.txt",
                content=b"n24-source-v2",
                connector="n24",
                domain_id=domain_id,
                source_id=sid,
                revision=1,
            )
        except FactLedgerError:
            rejected = True
        cases.append(
            {
                "id": "overwrite_without_revision_bump_rejected",
                "ok": rejected,
                "detail": "" if rejected else "silent_overwrite",
            }
        )

        updated = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            kind="file",
            uri="file://n24/source-revision-v2.txt",
            content=b"n24-source-v2",
            connector="n24",
            domain_id=domain_id,
            source_id=sid,
            revision=2,
            revision_actor="n24-suite",
            revision_reason="content_change",
        )
        hist = await lg.list_source_revisions(sid, tenant_id=tenant_id)
        archived = [h for h in hist if not h.get("is_head")]
        arch_ok = (
            int(updated.get("revision") or 0) == 2
            and len(archived) >= 1
            and int(archived[0].get("revision") or 0) == 1
            and (archived[0].get("snapshot") or {}).get("sha256") == src.get("sha256")
        )
        cases.append(
            {
                "id": "revision_archived_on_update",
                "ok": arch_ok,
                "detail": "" if arch_ok else "archive_missing",
            }
        )

        old = await lg.get_source_at_revision(sid, tenant_id=tenant_id, revision=1)
        new = await lg.get_source_at_revision(sid, tenant_id=tenant_id, revision=2)
        rt_ok = (
            old is not None
            and new is not None
            and old.get("sha256") == src.get("sha256")
            and new.get("sha256") == updated.get("sha256")
            and old.get("sha256") != new.get("sha256")
        )
        cases.append(
            {
                "id": "get_source_at_revision_roundtrip",
                "ok": rt_ok,
                "detail": "" if rt_ok else "revision_read_failed",
            }
        )

        diff = await lg.diff_source_revisions(
            sid, tenant_id=tenant_id, from_revision=1, to_revision=2
        )
        changed = diff.get("changed") or {}
        diff_ok = "sha256" in changed and "uri" in changed
        cases.append(
            {
                "id": "diff_source_revisions_ok",
                "ok": diff_ok,
                "detail": "" if diff_ok else "diff_missing_fields",
            }
        )
    finally:
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N24_SOURCE_REVISION_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "source_revision",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Source revision archive + bump; not full N24 certification",
    }


def evaluate_source_revision_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N24 Source Revision 门槛门；certified 恒 false。

    Args:
        suite: ``run_source_revision_suite`` 回执。

    Returns:
        gate 字典。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n24_full_conformance") is True:
        # 为什么：套件误标认证仍拒绝
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "source_revision",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Source revision harden; not N24 certified",
    }


_N24_REVISION_RESTORE_CASES = (
    "restore_requires_actor_reason",
    "restore_missing_revision_rejected",
    "restore_fact_bumps_and_archives",
    "restore_claim_and_source_ok",
    "restore_idempotent_when_same_content",
)


async def run_revision_restore_suite(
    *,
    ledger: Optional["FactLedger"] = None,
    tenant_id: str = "n24-restore-tenant",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N24 Revision Restore 最小加深套件（程序化恢复；非 UI）。

    Args:
        ledger: 可选账本；默认临时目录新建。
        tenant_id: 写入租户。
        domain_id: 可选域（调用方传入）。

    Returns:
        套件汇总；``certified`` / ``n24_full_conformance`` 恒 false。
    """
    import tempfile

    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n24-revision-restore-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await lg.initialize()
    else:
        lg = ledger  # type: ignore[assignment]
        await lg.initialize()

    cases: List[Dict[str, Any]] = []
    try:
        src_v1 = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            kind="file",
            uri="file://n24/restore-v1.txt",
            content=b"n24-restore-v1",
            connector="n24",
            domain_id=domain_id,
            source_id="src-n24-restore",
            revision=1,
        )
        sid = src_v1["source_id"]
        evidence = [
            {
                "source_id": sid,
                "locator": "extract",
                "quote": "n24",
                "fetched_at": src_v1["fetched_at"],
            }
        ]
        fact = await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            subject="door",
            predicate="state",
            object="locked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="draft",
            confidence=0.7,
            domain_id=domain_id,
            revision=1,
            enforce_write_gates=False,
        )
        fid = fact["fact_id"]
        await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            subject="door",
            predicate="state",
            object="unlocked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="draft",
            confidence=0.7,
            domain_id=domain_id,
            fact_id=fid,
            revision=2,
            enforce_write_gates=False,
            revision_actor="n24-suite",
            revision_reason="mutate",
        )
        claim = await lg.put_claim(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            text="door is locked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="published",
            confidence=0.8,
            domain_id=domain_id,
            revision=1,
        )
        cid = claim["claim_id"]
        await lg.put_claim(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            text="door is unlocked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="published",
            confidence=0.8,
            domain_id=domain_id,
            claim_id=cid,
            revision=2,
            revision_actor="n24-suite",
            revision_reason="mutate",
        )
        await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            kind="file",
            uri="file://n24/restore-v2.txt",
            content=b"n24-restore-v2",
            connector="n24",
            domain_id=domain_id,
            source_id=sid,
            revision=2,
            revision_actor="n24-suite",
            revision_reason="mutate",
        )

        rejected_actor = False
        try:
            await lg.restore_fact_at_revision(
                fid, tenant_id=tenant_id, target_revision=1, actor="", reason="x"
            )
        except FactLedgerError:
            rejected_actor = True
        cases.append(
            {
                "id": "restore_requires_actor_reason",
                "ok": rejected_actor,
                "detail": "" if rejected_actor else "empty_actor_accepted",
            }
        )

        rejected_missing = False
        try:
            await lg.restore_fact_at_revision(
                fid,
                tenant_id=tenant_id,
                target_revision=99,
                actor="n24-suite",
                reason="missing",
            )
        except FactLedgerError:
            rejected_missing = True
        cases.append(
            {
                "id": "restore_missing_revision_rejected",
                "ok": rejected_missing,
                "detail": "" if rejected_missing else "missing_accepted",
            }
        )

        fact_rcpt = await lg.restore_fact_at_revision(
            fid,
            tenant_id=tenant_id,
            target_revision=1,
            actor="n24-suite",
            reason="restore_fact_r1",
            enforce_write_gates=False,
        )
        fact_head = fact_rcpt.get("fact") or {}
        hist = await lg.list_fact_revisions(fid, tenant_id=tenant_id)
        archived = [h for h in hist if not h.get("is_head")]
        fact_ok = (
            fact_rcpt.get("restored") is True
            and int(fact_head.get("revision") or 0) == 3
            and fact_head.get("object") == "locked"
            and len(archived) >= 2
        )
        cases.append(
            {
                "id": "restore_fact_bumps_and_archives",
                "ok": fact_ok,
                "detail": "" if fact_ok else "fact_restore_failed",
            }
        )

        claim_rcpt = await lg.restore_claim_at_revision(
            cid,
            tenant_id=tenant_id,
            target_revision=1,
            actor="n24-suite",
            reason="restore_claim_r1",
        )
        src_rcpt = await lg.restore_source_at_revision(
            sid,
            tenant_id=tenant_id,
            target_revision=1,
            actor="n24-suite",
            reason="restore_source_r1",
        )
        claim_head = claim_rcpt.get("claim") or {}
        src_head = src_rcpt.get("source") or {}
        cs_ok = (
            claim_rcpt.get("restored") is True
            and claim_head.get("text") == "door is locked"
            and int(claim_head.get("revision") or 0) == 3
            and src_rcpt.get("restored") is True
            and src_head.get("sha256") == src_v1.get("sha256")
            and int(src_head.get("revision") or 0) == 3
        )
        cases.append(
            {
                "id": "restore_claim_and_source_ok",
                "ok": cs_ok,
                "detail": "" if cs_ok else "claim_or_source_restore_failed",
            }
        )

        idem = await lg.restore_fact_at_revision(
            fid,
            tenant_id=tenant_id,
            target_revision=1,
            actor="n24-suite",
            reason="restore_again",
            enforce_write_gates=False,
        )
        idem_ok = (
            idem.get("idempotent") is True
            and idem.get("restored") is False
            and int((idem.get("fact") or {}).get("revision") or 0) == 3
        )
        cases.append(
            {
                "id": "restore_idempotent_when_same_content",
                "ok": idem_ok,
                "detail": "" if idem_ok else "not_idempotent",
            }
        )
    finally:
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N24_REVISION_RESTORE_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "revision_restore",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Revision restore API; not rollback UI / not N24 certified",
    }


def evaluate_revision_restore_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N24 Revision Restore 门槛门；certified 恒 false。

    Args:
        suite: ``run_revision_restore_suite`` 回执。

    Returns:
        gate 字典。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n24_full_conformance") is True:
        # 为什么：套件误标认证仍拒绝
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "revision_restore",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Revision restore harden; not N24 certified",
    }


_N24_REVISION_AUDIT_CASES = (
    "archive_emits_audit",
    "restore_emits_audit",
    "list_filters_by_entity",
    "cross_tenant_audit_empty",
)


async def run_revision_audit_suite(
    *,
    ledger: Optional["FactLedger"] = None,
    tenant_id: str = "n24-audit-tenant",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N24 Revision Audit 最小加深套件（账本内 append-only；非统一总线）。

    Args:
        ledger: 可选账本；默认临时目录新建。
        tenant_id: 写入租户。
        domain_id: 可选域（调用方传入）。

    Returns:
        套件汇总；``certified`` / ``n24_full_conformance`` 恒 false。
    """
    import tempfile

    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n24-revision-audit-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await lg.initialize()
    else:
        lg = ledger  # type: ignore[assignment]
        await lg.initialize()

    cases: List[Dict[str, Any]] = []
    try:
        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            kind="file",
            uri="file://n24/audit-v1.txt",
            content=b"n24-audit-v1",
            connector="n24",
            domain_id=domain_id,
            source_id="src-n24-audit",
            revision=1,
        )
        evidence = [
            {
                "source_id": src["source_id"],
                "locator": "x",
                "quote": "a",
                "fetched_at": src["fetched_at"],
            }
        ]
        fact = await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            subject="door",
            predicate="state",
            object="locked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="draft",
            confidence=0.5,
            domain_id=domain_id,
            revision=1,
            enforce_write_gates=False,
        )
        fid = fact["fact_id"]
        await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            subject="door",
            predicate="state",
            object="unlocked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="draft",
            confidence=0.5,
            domain_id=domain_id,
            fact_id=fid,
            revision=2,
            enforce_write_gates=False,
            revision_actor="n24-suite",
            revision_reason="mutate",
        )
        archives = await lg.list_revision_audit(
            tenant_id=tenant_id,
            entity_type="fact",
            entity_id=fid,
            event_type="archive",
        )
        arch_ok = len(archives) >= 1 and archives[0].get("revision") == 1
        cases.append(
            {
                "id": "archive_emits_audit",
                "ok": arch_ok,
                "detail": "" if arch_ok else "archive_audit_missing",
            }
        )

        await lg.restore_fact_at_revision(
            fid,
            tenant_id=tenant_id,
            target_revision=1,
            actor="n24-suite",
            reason="restore_for_audit",
            enforce_write_gates=False,
        )
        restores = await lg.list_revision_audit(
            tenant_id=tenant_id,
            entity_type="fact",
            entity_id=fid,
            event_type="restore",
        )
        rest_ok = (
            len(restores) >= 1
            and int(restores[-1].get("revision") or 0) == 1
            and int(restores[-1].get("to_revision") or 0) == 3
        )
        cases.append(
            {
                "id": "restore_emits_audit",
                "ok": rest_ok,
                "detail": "" if rest_ok else "restore_audit_missing",
            }
        )

        all_fact = await lg.list_revision_audit(
            tenant_id=tenant_id, entity_type="fact", entity_id=fid
        )
        filt_ok = all(e.get("entity_id") == fid for e in all_fact) and len(all_fact) >= 2
        cases.append(
            {
                "id": "list_filters_by_entity",
                "ok": filt_ok,
                "detail": "" if filt_ok else "filter_failed",
            }
        )

        other = await lg.list_revision_audit(tenant_id="other-tenant", entity_id=fid)
        xt_ok = len(other) == 0
        cases.append(
            {
                "id": "cross_tenant_audit_empty",
                "ok": xt_ok,
                "detail": "" if xt_ok else "cross_tenant_leak",
            }
        )
    finally:
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N24_REVISION_AUDIT_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "revision_audit",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Revision audit ledger events; not Package/Action bus / not N24 certified",
    }


def evaluate_revision_audit_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N24 Revision Audit 门槛门；certified 恒 false。

    Args:
        suite: ``run_revision_audit_suite`` 回执。

    Returns:
        gate 字典。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n24_full_conformance") is True:
        # 为什么：套件误标认证仍拒绝
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "revision_audit",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Revision audit harden; not N24 certified",
    }


_N24_RESTORE_APPROVAL_CASES = (
    "request_creates_pending",
    "self_approve_rejected",
    "approve_applies_restore",
    "reject_leaves_head",
)


async def run_restore_approval_suite(
    *,
    ledger: Optional["FactLedger"] = None,
    tenant_id: str = "n24-restore-appr-tenant",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N24 审批式 Restore 最小加深套件（非 UI）。

    Args:
        ledger: 可选账本；默认临时目录新建。
        tenant_id: 写入租户。
        domain_id: 可选域。

    Returns:
        套件汇总；``certified`` / ``n24_full_conformance`` 恒 false。
    """
    import tempfile

    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n24-restore-appr-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await lg.initialize()
    else:
        lg = ledger  # type: ignore[assignment]
        await lg.initialize()

    cases: List[Dict[str, Any]] = []
    try:
        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            kind="file",
            uri="file://n24/appr-v1.txt",
            content=b"n24-appr-v1",
            connector="n24",
            domain_id=domain_id,
            revision=1,
        )
        evidence = [
            {
                "source_id": src["source_id"],
                "locator": "x",
                "quote": "a",
                "fetched_at": src["fetched_at"],
            }
        ]
        fact = await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            subject="door",
            predicate="state",
            object="locked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="draft",
            confidence=0.5,
            domain_id=domain_id,
            revision=1,
            enforce_write_gates=False,
        )
        fid = fact["fact_id"]
        await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            subject="door",
            predicate="state",
            object="unlocked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="draft",
            confidence=0.5,
            domain_id=domain_id,
            fact_id=fid,
            revision=2,
            enforce_write_gates=False,
            revision_actor="n24-suite",
            revision_reason="mutate",
        )

        req = await lg.request_revision_restore(
            tenant_id=tenant_id,
            entity_type="fact",
            entity_id=fid,
            target_revision=1,
            requester="alice",
            reason="need_old",
        )
        pending = await lg.list_revision_restore_requests(
            tenant_id=tenant_id, status="pending", entity_id=fid
        )
        req_ok = req.get("status") == "pending" and len(pending) == 1
        cases.append(
            {
                "id": "request_creates_pending",
                "ok": req_ok,
                "detail": "" if req_ok else "pending_missing",
            }
        )

        self_rej = False
        try:
            await lg.approve_revision_restore(
                req["request_id"],
                tenant_id=tenant_id,
                approver="alice",
                reason="self",
            )
        except FactLedgerError:
            self_rej = True
        cases.append(
            {
                "id": "self_approve_rejected",
                "ok": self_rej,
                "detail": "" if self_rej else "self_approve_ok",
            }
        )

        approved = await lg.approve_revision_restore(
            req["request_id"],
            tenant_id=tenant_id,
            approver="bob",
            reason="ok",
        )
        head = await lg.get_fact(fid, tenant_id=tenant_id)
        appr_ok = (
            approved.get("status") == "approved"
            and head is not None
            and head.get("object") == "locked"
            and int(head.get("revision") or 0) == 3
        )
        cases.append(
            {
                "id": "approve_applies_restore",
                "ok": appr_ok,
                "detail": "" if appr_ok else "approve_failed",
            }
        )

        # 再抬号后请求并拒绝，头应保持
        await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            subject="door",
            predicate="state",
            object="ajar",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="draft",
            confidence=0.5,
            domain_id=domain_id,
            fact_id=fid,
            revision=4,
            enforce_write_gates=False,
            revision_actor="n24-suite",
            revision_reason="mutate2",
        )
        req2 = await lg.request_revision_restore(
            tenant_id=tenant_id,
            entity_type="fact",
            entity_id=fid,
            target_revision=1,
            requester="alice",
            reason="again",
        )
        rejected = await lg.reject_revision_restore(
            req2["request_id"],
            tenant_id=tenant_id,
            rejector="bob",
            reason="no",
        )
        head2 = await lg.get_fact(fid, tenant_id=tenant_id)
        rej_ok = (
            rejected.get("status") == "rejected"
            and head2 is not None
            and head2.get("object") == "ajar"
            and int(head2.get("revision") or 0) == 4
        )
        cases.append(
            {
                "id": "reject_leaves_head",
                "ok": rej_ok,
                "detail": "" if rej_ok else "reject_changed_head",
            }
        )
    finally:
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N24_RESTORE_APPROVAL_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "restore_approval",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Approval-gated restore; not rollback UI / not N24 certified",
    }


def evaluate_restore_approval_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N24 审批式 Restore 门槛门；certified 恒 false。

    Args:
        suite: ``run_restore_approval_suite`` 回执。

    Returns:
        gate 字典。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n24_full_conformance") is True:
        # 为什么：套件误标认证仍拒绝
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "restore_approval",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Restore approval harden; not N24 certified",
    }


_N24_REVISION_ACTION_BRIDGE_CASES = (
    "approve_creates_bridge",
    "execution_lookup_ok",
    "bridge_idempotent",
    "cross_tenant_bridge_empty",
)


async def run_revision_action_bridge_suite(
    *,
    ledger: Optional["FactLedger"] = None,
    tenant_id: str = "n24-rev-action-tenant",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N24 Revision→ActionExecution 桥接最小套件（非全量总线）。

    Args:
        ledger: 可选账本；默认临时目录新建（含独立 ActionExecution DB）。
        tenant_id: 写入租户。
        domain_id: 可选域。

    Returns:
        套件汇总；``certified`` / ``n24_full_conformance`` 恒 false。
    """
    import tempfile

    from core.harness.infrastructure.action_execution import lookup_execution

    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n24-rev-action-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
            action_execution_db_path=str(root / "action_execution.sqlite3"),
        )
        await lg.initialize()
    else:
        lg = ledger  # type: ignore[assignment]
        await lg.initialize()

    cases: List[Dict[str, Any]] = []
    try:
        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            kind="file",
            uri="file://n24/bridge-v1.txt",
            content=b"n24-bridge-v1",
            connector="n24",
            domain_id=domain_id,
            revision=1,
        )
        evidence = [
            {
                "source_id": src["source_id"],
                "locator": "x",
                "quote": "a",
                "fetched_at": src["fetched_at"],
            }
        ]
        fact = await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            subject="door",
            predicate="state",
            object="locked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="draft",
            confidence=0.5,
            domain_id=domain_id,
            revision=1,
            enforce_write_gates=False,
        )
        fid = fact["fact_id"]
        await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            subject="door",
            predicate="state",
            object="unlocked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="draft",
            confidence=0.5,
            domain_id=domain_id,
            fact_id=fid,
            revision=2,
            enforce_write_gates=False,
            revision_actor="n24-suite",
            revision_reason="mutate",
        )
        req = await lg.request_revision_restore(
            tenant_id=tenant_id,
            entity_type="fact",
            entity_id=fid,
            target_revision=1,
            requester="alice",
            reason="bridge",
        )
        approved = await lg.approve_revision_restore(
            req["request_id"],
            tenant_id=tenant_id,
            approver="bob",
            reason="ok",
        )
        bridge = approved.get("action_bridge") or {}
        bridges = await lg.list_revision_action_bridges(
            tenant_id=tenant_id, entity_type="fact", entity_id=fid
        )
        create_ok = (
            bridge.get("execution_id")
            and len(bridges) >= 1
            and bridges[-1].get("event_type") == "restore_approve"
        )
        cases.append(
            {
                "id": "approve_creates_bridge",
                "ok": create_ok,
                "detail": "" if create_ok else "bridge_missing",
            }
        )

        exec_row = lookup_execution(
            tenant_id,
            f"rev-bridge:{bridge.get('audit_id')}",
            db_path=lg.action_execution_db_path,
        )
        lookup_ok = (
            exec_row is not None
            and exec_row.get("execution_id") == bridge.get("execution_id")
            and str(exec_row.get("action_id") or "").startswith("knowledge_revision:")
        )
        cases.append(
            {
                "id": "execution_lookup_ok",
                "ok": lookup_ok,
                "detail": "" if lookup_ok else "execution_missing",
            }
        )

        again = await lg.bridge_revision_audit_to_action(
            audit_event={
                "tenant_id": tenant_id,
                "audit_id": bridge.get("audit_id"),
                "entity_type": "fact",
                "entity_id": fid,
                "event_type": "restore_approve",
                "revision": 1,
                "actor": "bob",
                "reason": "ok",
            },
            action_id="knowledge_revision:restore_approve",
        )
        idem_ok = again.get("idempotent") is True and again.get(
            "execution_id"
        ) == bridge.get("execution_id")
        cases.append(
            {
                "id": "bridge_idempotent",
                "ok": idem_ok,
                "detail": "" if idem_ok else "not_idempotent",
            }
        )

        other = await lg.list_revision_action_bridges(tenant_id="other-tenant")
        xt_ok = len(other) == 0
        cases.append(
            {
                "id": "cross_tenant_bridge_empty",
                "ok": xt_ok,
                "detail": "" if xt_ok else "cross_tenant_leak",
            }
        )
    finally:
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N24_REVISION_ACTION_BRIDGE_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "revision_action_bridge",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Revision→ActionExecution bridge; not full bus merge / not N24 certified",
    }


def evaluate_revision_action_bridge_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N24 Revision→Action 桥接门槛门；certified 恒 false。

    Args:
        suite: ``run_revision_action_bridge_suite`` 回执。

    Returns:
        gate 字典。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n24_full_conformance") is True:
        # 为什么：套件误标认证仍拒绝
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "revision_action_bridge",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Revision action bridge harden; not N24 certified",
    }


_ledger_singleton: Optional[FactLedger] = None


def get_fact_ledger() -> FactLedger:
    """进程内 FactLedger 单例。

    Returns:
        共享 ``FactLedger`` 实例。
    """
    global _ledger_singleton
    if _ledger_singleton is None:
        _ledger_singleton = FactLedger()
    return _ledger_singleton


async def record_extraction_as_claim(
    *,
    tenant_id: str,
    domain_id: str,
    extraction_id: str,
    source_doc: str,
    text: str,
    evidence_quote: str = "",
) -> Dict[str, Any]:
    """将已确认抽取登记为 Raw + published Claim（生产接线入口）。

    Args:
        tenant_id: 租户。
        domain_id: 业务域 ID（由调用方传入）。
        extraction_id: 抽取 ID。
        source_doc: 来源文档标识。
        text: Claim 文本。
        evidence_quote: 证据摘录。

    Returns:
        ``{"source": ..., "claim": ...}``。
    """
    ledger = get_fact_ledger()
    await ledger.initialize()
    body = (
        f"extraction_id={extraction_id}\nsource_doc={source_doc}\n"
        f"quote={evidence_quote or text}"
    ).encode("utf-8")
    src = await ledger.register_source(
        tenant_id=tenant_id,
        collection_id=f"{domain_id}-extractions",
        kind="file",
        uri=f"extract://{extraction_id}",
        content=body,
        connector="extraction_confirm",
        domain_id=domain_id,
    )
    evidence = [
        {
            "source_id": src["source_id"],
            "locator": "extract",
            "quote": (evidence_quote or text)[:500],
            "fetched_at": src["fetched_at"],
        }
    ]
    from core.harness.knowledge_pipeline.fact_state_machine import (
        transition_fact_review,
    )
    from core.harness.knowledge_pipeline.source_policy import register_source_policy

    # 确保确认抽取策略已登记（幂等）
    try:
        register_source_policy(
            tenant_id=tenant_id,
            policy_id="extraction_confirm_v1",
            authority="system",
            freshness={"valid_days": 3650},
            scope=["extraction_confirm"],
            license="internal",
            trust="high",
            conflict_rule="prefer_newer_primary_then_human_review",
        )
    except Exception as exc:  # noqa: BLE001 — 已存在策略时忽略
        if "fixed" in str(exc).lower():
            raise
    claim = await ledger.put_claim(
        tenant_id=tenant_id,
        collection_id=f"{domain_id}-extractions",
        text=text[:2000],
        evidence=evidence,
        source_policy="extraction_confirm_v1",
        extractor_version="knowledge_pipeline.extractor",
        review_status="published",
        confidence=0.8,
        domain_id=domain_id,
        status="accepted",
    )
    # 同步写 Fact：draft → reviewed → published（写入硬门）
    fact = await ledger.put_fact(
        tenant_id=tenant_id,
        collection_id=f"{domain_id}-extractions",
        subject=f"Extraction:{extraction_id}",
        predicate="confirmed",
        object="true",
        evidence=evidence,
        source_policy="extraction_confirm_v1",
        extractor_version="knowledge_pipeline.extractor",
        review_status="draft",
        confidence=0.8,
        domain_id=domain_id,
        status="active",
        inferred=False,
    )
    await transition_fact_review(
        ledger,
        fact_id=fact["fact_id"],
        tenant_id=tenant_id,
        to_status="reviewed",
        actor="extraction_confirm",
        reason="confirm extraction",
        role="reviewer",
    )
    published = await transition_fact_review(
        ledger,
        fact_id=fact["fact_id"],
        tenant_id=tenant_id,
        to_status="published",
        actor="extraction_confirm",
        reason="confirm extraction",
        role="reviewer",
    )
    return {"source": src, "claim": claim, "fact": published["fact"]}
