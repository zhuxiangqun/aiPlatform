"""v4.3.1 Phase 1 事实账本：Source Registry + Fact/Claim（SQLite）。

职责：
  - 登记不可变 Raw 快照（sha256 + snapshot 文件）
  - 写入 Fact/Claim；``review_status=published`` 时必须有非空 evidence
  - 查询在 SQL 层按 tenant_id 过滤（召回前，非召回后）

非目标：
  - 完整 ObjectSet/SDK、Wiki 只读化、Scenario Package（后续 Phase）
  - 替代现有 DataSourceRegistry 外部连接器（本模块是附录 A/D 契约层）
  - 宣称附录 N 全量认证（写入硬门加深仍为 partial）
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
from typing import Any, Dict, List, Optional

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
    ) -> None:
        """初始化账本。

        Args:
            db_path: SQLite 路径；默认 ``default_fact_ledger_db_path()``。
            raw_dir: Raw 快照根目录；默认 ``default_raw_snapshot_dir()``。
        """
        self.db_path = db_path or default_fact_ledger_db_path()
        self.raw_dir = Path(raw_dir) if raw_dir else default_raw_snapshot_dir()

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

        Returns:
            附录 A 形状的 source 记录。

        Raises:
            FactLedgerError: 参数非法。
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

        tenant_dir = self.raw_dir / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
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

        Returns:
            Fact 记录。

        Raises:
            FactLedgerError: 契约违反或 evidence 指向未知 source。
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

        Returns:
            Claim 记录（可能含 ``conflict_id`` 若触发冲突记录）。

        Raises:
            FactLedgerError: 无证据 published / 未知 source / 策略未登记。
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
    ) -> List[Dict[str, Any]]:
        """查询 Fact；``tenant_id`` 必填且在 SQL WHERE 中过滤。

        Args:
            tenant_id: 租户（缺失则报错——禁止无租户全表扫）。
            collection_id: 可选集合过滤。
            domain_id: 可选域过滤。
            subject / predicate: 可选三元组过滤。
            review_status: 可选审核状态。
            limit: 上限。

        Returns:
            Fact 列表（永不返回其他租户行）。

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
        return [self._row_to_fact(row) for row in rows]

    async def query_facts_gateway(
        self,
        *,
        tenant_id: str,
        query: str = "",
        collection_id: Optional[str] = None,
        domain_id: Optional[str] = None,
        top_k: int = 8,
        require_citations: bool = True,
    ) -> Dict[str, Any]:
        """附录 M 最小查询入口：租户前置 + 无证据 abstain。

        Args:
            tenant_id: 租户。
            query: 查询串（用于 subject/predicate 子串匹配的简化）。
            collection_id: 集合。
            domain_id: 业务域过滤（可选）。
            top_k: 返回条数。
            require_citations: 为 True 时无 citations 则 abstain。

        Returns:
            查询响应（含 abstained / citations）。
        """
        facts = await self.query_facts(
            tenant_id=tenant_id,
            collection_id=collection_id,
            domain_id=domain_id,
            limit=top_k * 3,
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
        }
        gate = validate_gateway_response(resp)
        resp["gateway_contract_ok"] = gate["ok"]
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
        "note": "FactLedger verify-on-read only; DataSourceConfig path not forced",
    }


_N09_CASES = (
    "query_facts_no_leak",
    "get_source_no_leak",
    "gateway_no_leak",
    "verify_raw_no_leak",
)


async def run_cross_tenant_isolation_suite(
    *,
    ledger: Optional["FactLedger"] = None,
    tenant_a: str = "n09-tenant-a",
    tenant_b: str = "n09-tenant-b",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N09 跨租户 0 泄漏最小加深套件（FactLedger 四探针）。

    Args:
        ledger: 可选账本；默认临时目录新建（不污染单例）。
        tenant_a: 写入租户。
        tenant_b: 负向查询租户。
        domain_id: 可选域过滤（由调用方传入；harness 不默认业务域名）。

    Returns:
        套件汇总；``certified`` / ``n09_full_conformance`` 恒 false。
    """
    import tempfile

    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
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
        fact = await lg.put_fact(
            tenant_id=tenant_a,
            collection_id="n09-kb",
            subject="InstallOrder:n09-secret",
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
            domain_id=domain_id,
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
    finally:
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
        "note": "FactLedger isolation probes only; not global zero-leak certification",
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
        "note": "FactLedger suite deepen; not platform-wide zero-leak certified",
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
    )
    published = await transition_fact_review(
        ledger,
        fact_id=fact["fact_id"],
        tenant_id=tenant_id,
        to_status="published",
        actor="extraction_confirm",
        reason="confirm extraction",
    )
    return {"source": src, "claim": claim, "fact": published["fact"]}
