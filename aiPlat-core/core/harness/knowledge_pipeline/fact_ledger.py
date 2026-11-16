"""v4.3.1 Phase 1 事实账本：Source Registry + Fact/Claim（SQLite）。

职责：
  - 登记不可变 Raw 快照（sha256 + snapshot 文件）
  - 写入 Fact/Claim；``review_status=published`` 时必须有非空 evidence
  - 查询在 SQL 层按 tenant_id 过滤（召回前，非召回后）

非目标：
  - 完整 ObjectSet/SDK、Wiki 只读化、Scenario Package（后续 Phase）
  - 替代现有 DataSourceRegistry 外部连接器（本模块是附录 A/D 契约层）
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
                    status TEXT NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_claims_tenant ON claims(tenant_id)"
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
        self, source_id: str, *, tenant_id: str
    ) -> Optional[Dict[str, Any]]:
        """按租户读取 source（跨租户返回 None）。

        Args:
            source_id: 来源 ID。
            tenant_id: 调用方租户；必须匹配行上 tenant_id。

        Returns:
            source 字典或 None。
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
        return self._row_source(row)

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
    ) -> Dict[str, Any]:
        """写入 Fact；published 必须有 evidence。

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
    ) -> Dict[str, Any]:
        """写入 Claim；published 必须有 evidence。

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

        Returns:
            Claim 记录。
        """
        import aiosqlite

        self._validate_evidence(evidence, review_status=review_status)
        for ev in evidence:
            src = await self.get_source(str(ev["source_id"]), tenant_id=tenant_id)
            if src is None:
                raise FactLedgerError(
                    f"evidence source not found in tenant: {ev['source_id']}"
                )

        cid = claim_id or f"cl-{uuid.uuid4().hex[:12]}"
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
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                INSERT OR REPLACE INTO claims (
                    claim_id, tenant_id, collection_id, domain_id, text,
                    evidence_json, source_policy, extractor_version, review_status,
                    confidence, valid_from, valid_to, recorded_at, revision, status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                ),
            )
            await db.commit()
        return record

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
        answer = None
        if not abstained and facts:
            f0 = facts[0]
            answer = f"{f0['subject']}.{f0['predicate']}={f0['object']}"
        return {
            "answer": answer,
            "citations": citations,
            "route_plan": ["fact"],
            "route_reason": "fact_ledger",
            "confidence": "high" if citations else "low",
            "partial": False,
            "degraded": False,
            "abstained": abstained,
            "conflicts": [],
            "facts": facts,
            "tenant_id": tenant_id,
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
    # 同步写一条 Fact，保证 put_fact 有生产调用链（确认抽取 → Claim + Fact）
    fact = await ledger.put_fact(
        tenant_id=tenant_id,
        collection_id=f"{domain_id}-extractions",
        subject=f"Extraction:{extraction_id}",
        predicate="confirmed",
        object="true",
        evidence=evidence,
        source_policy="extraction_confirm_v1",
        extractor_version="knowledge_pipeline.extractor",
        review_status="published",
        confidence=0.8,
        domain_id=domain_id,
        status="active",
        inferred=False,
    )
    return {"source": src, "claim": claim, "fact": fact}
