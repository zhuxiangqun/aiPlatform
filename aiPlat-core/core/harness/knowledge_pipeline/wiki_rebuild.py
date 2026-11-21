"""Wiki 有条件重建（附录 N N05 deepen）。

职责：
  - 从 FactLedger 按租户/域生成 Wiki 派生页（SQLite 读模型视图）
  - 复用 Fact→Graph 三分类 ``rebuild_mode`` / ``rebuild_reason``
  - non_rebuildable 不写页；exact/semantic 写派生视图（非人工 Wiki HTTP）

非目标：
  - 不替换 wiki_engine 全量索引 / FTS 热路径
  - 不开放人工写绕过读模型硬门
  - 不宣称 N05 certified / Wiki 全量认证
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    FactLedgerError,
    get_fact_ledger,
)
from core.harness.knowledge_pipeline.fact_projector import (
    REBUILD_MODE_EXACT,
    REBUILD_MODE_NON,
    REBUILD_MODE_SEMANTIC,
    classify_rebuild,
    validate_rebuild_receipt,
)

logger = logging.getLogger(__name__)

_WIKI_PROJECTION_SOURCE = "fact_ledger_wiki"
_SUITE_CASES = (
    "exact_writes_pages",
    "non_skips_write",
    "semantic_writes_marked",
    "tenant_required",
    "gate_receipt_ok",
    "honesty_certified_false",
)


class WikiRebuildError(ValueError):
    """Wiki 重建契约错误。"""


def _default_db_path() -> str:
    """解析 Wiki 重建派生库路径（AIPLAT_HOME 约定）。"""
    env = os.environ.get("AIPLAT_WIKI_REBUILD_DB")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "knowledge_wiki_rebuild.sqlite3")
    return "./data/knowledge_wiki_rebuild.sqlite3"


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """打开/初始化 Wiki 重建派生表。

    Args:
        db_path: 可选库路径。
    """
    path = db_path or _default_db_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wiki_rebuild_pages (
            page_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            body_json TEXT NOT NULL,
            rebuild_mode TEXT NOT NULL,
            rebuild_reason TEXT NOT NULL,
            fact_ids_json TEXT NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(tenant_id, domain_id, subject)
        )
        """
    )
    conn.commit()
    return conn


def _parse_subject(subject: str) -> tuple[str, str]:
    """解析 ``Type:id`` 主体。

    Args:
        subject: Fact subject。
    """
    s = (subject or "").strip()
    if ":" in s:
        left, right = s.split(":", 1)
        return left.strip() or "Entity", right.strip() or s
    return "Entity", s or "unknown"


def list_wiki_rebuild_pages(
    *,
    tenant_id: str,
    domain_id: str = "",
    limit: int = 200,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """列出 Wiki 重建派生页（租户前置）。

    Args:
        tenant_id: 租户。
        domain_id: 可选域过滤。
        limit: 最大条数。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        return []
    lim = max(1, min(int(limit or 200), 1000))
    did = (domain_id or "").strip()
    conn = _connect(db_path)
    try:
        if did:
            rows = conn.execute(
                """
                SELECT * FROM wiki_rebuild_pages
                WHERE tenant_id=? AND domain_id=?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (tid, did, lim),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM wiki_rebuild_pages
                WHERE tenant_id=?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (tid, lim),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "page_id": r["page_id"],
                    "tenant_id": r["tenant_id"],
                    "domain_id": r["domain_id"],
                    "subject": r["subject"],
                    "title": r["title"],
                    "body": json.loads(r["body_json"] or "{}"),
                    "rebuild_mode": r["rebuild_mode"],
                    "rebuild_reason": r["rebuild_reason"],
                    "fact_ids": json.loads(r["fact_ids_json"] or "[]"),
                    "updated_at": r["updated_at"],
                }
            )
        return out
    finally:
        conn.close()


async def project_facts_to_wiki(
    *,
    tenant_id: str,
    domain_id: str,
    ledger: Optional[FactLedger] = None,
    clear_projected: bool = False,
    rebuild_mode: Optional[str] = None,
    rebuild_reason: str = "",
    exact_capable: bool = True,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """将域内 Fact 投影为 Wiki 派生页（租户隔离；三分类）。

    Args:
        tenant_id: 租户。
        domain_id: 业务域。
        ledger: 可选账本；默认进程单例。
        clear_projected: True 时先清除该租户/域既有派生页。
        rebuild_mode: 可选显式分类。
        rebuild_reason: 分类理由。
        exact_capable: 是否可精确重放。
        db_path: 可选派生库路径。

    Returns:
        重建回执（含 ``rebuild_gate``；``certified`` 恒 false）。

    Raises:
        FactLedgerError: tenant/domain 为空。
        WikiRebuildError / RebuildTaxonomyError: 分类非法。
    """
    tid = (tenant_id or "").strip()
    did = (domain_id or "").strip()
    if not tid:
        raise FactLedgerError("tenant_id required")
    if not did:
        # 为什么：Wiki 派生重建必须带域，避免跨域混写派生页
        raise WikiRebuildError("domain_id required")

    mode, reason = classify_rebuild(
        rebuild_mode=rebuild_mode,
        rebuild_reason=rebuild_reason,
        exact_capable=exact_capable,
    )

    store = ledger or get_fact_ledger()
    await store.initialize()
    facts = await store.query_facts(tenant_id=tid, domain_id=did, limit=5000)

    by_subject: Dict[str, Dict[str, Any]] = {}
    for f in facts:
        subj = str(f.get("subject") or "")
        pred = str(f.get("predicate") or "")
        if not subj or not pred:
            continue
        bucket = by_subject.setdefault(subj, {})
        bucket[pred] = f.get("object")
        bucket["_fact_ids"] = list(bucket.get("_fact_ids") or []) + [
            f.get("fact_id")
        ]

    conn = _connect(db_path)
    removed = 0
    try:
        if clear_projected:
            cur = conn.execute(
                "DELETE FROM wiki_rebuild_pages WHERE tenant_id=? AND domain_id=?",
                (tid, did),
            )
            removed = int(cur.rowcount or 0)
            conn.commit()

        # 为什么：non 只记分类不写页，避免假可重建 Wiki 视图
        if mode == REBUILD_MODE_NON:
            receipt = {
                "status": "ok",
                "rebuild_mode": mode,
                "rebuild_reason": reason,
                "projection_source": _WIKI_PROJECTION_SOURCE,
                "target": "wiki",
                "exact_capable": False,
                "tenant_id": tid,
                "domain_id": did,
                "facts_read": len(facts),
                "subjects": len(by_subject),
                "created": [],
                "updated": [],
                "skipped": list(by_subject.keys()),
                "removed_before": removed,
                "written": False,
            }
            # non 不写页；门槛门仍校验 mode/reason（非 exact 源检查）
            gate = validate_rebuild_receipt(receipt)
            receipt["rebuild_gate"] = gate
            return receipt

        created: List[str] = []
        updated: List[str] = []
        now = time.time()
        for subject, props in by_subject.items():
            _cls, eid = _parse_subject(subject)
            fact_ids = list(props.pop("_fact_ids", []) or [])
            title = str(props.get("name") or eid)
            body = {k: v for k, v in props.items() if not str(k).startswith("_")}
            body["subject"] = subject
            body["entity_id"] = eid
            existing = conn.execute(
                """
                SELECT page_id FROM wiki_rebuild_pages
                WHERE tenant_id=? AND domain_id=? AND subject=?
                """,
                (tid, did, subject),
            ).fetchone()
            page_id = (
                existing["page_id"]
                if existing
                else f"wiki-{uuid.uuid4().hex[:16]}"
            )
            conn.execute(
                """
                INSERT INTO wiki_rebuild_pages(
                    page_id, tenant_id, domain_id, subject, title, body_json,
                    rebuild_mode, rebuild_reason, fact_ids_json, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(tenant_id, domain_id, subject) DO UPDATE SET
                    title=excluded.title,
                    body_json=excluded.body_json,
                    rebuild_mode=excluded.rebuild_mode,
                    rebuild_reason=excluded.rebuild_reason,
                    fact_ids_json=excluded.fact_ids_json,
                    updated_at=excluded.updated_at
                """,
                (
                    page_id,
                    tid,
                    did,
                    subject,
                    title,
                    json.dumps(body, ensure_ascii=False),
                    mode,
                    reason,
                    json.dumps([str(x) for x in fact_ids[:50]], ensure_ascii=False),
                    now,
                ),
            )
            if existing:
                updated.append(page_id)
            else:
                created.append(page_id)
        conn.commit()

        receipt = {
            "status": "ok",
            "rebuild_mode": mode,
            "rebuild_reason": reason,
            "projection_source": "fact_ledger",
            "target": "wiki",
            "exact_capable": exact_capable,
            "tenant_id": tid,
            "domain_id": did,
            "facts_read": len(facts),
            "subjects": len(by_subject),
            "created": created,
            "updated": updated,
            "skipped": [],
            "removed_before": removed,
            "written": True,
            "semantic": mode == REBUILD_MODE_SEMANTIC,
        }
        gate = validate_rebuild_receipt(receipt)
        receipt["rebuild_gate"] = gate
        logger.info(
            "wiki_rebuild: domain=%s tenant=%s mode=%s created=%s updated=%s",
            did,
            tid,
            mode,
            len(created),
            len(updated),
        )
        return receipt
    finally:
        conn.close()


def evaluate_wiki_rebuild_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N05 deepen：Wiki 重建门槛门（certified 恒 false）。

    Args:
        suite: ``run_wiki_rebuild_suite`` 回执。
    """
    s = suite or {}
    issues: List[str] = []
    if s.get("certified") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("n05_full_conformance") is True:
        issues.append("honesty_n05_full_flag_forbidden")
    if s.get("wiki_full_certified") is True:
        issues.append("honesty_wiki_full_flag_forbidden")
    cases = s.get("cases") or []
    if cases:
        failed = [c for c in cases if isinstance(c, dict) and not c.get("ok")]
        if failed:
            issues.append(f"suite_cases_failed:{len(failed)}")
        ids = {str(c.get("id") or "") for c in cases if isinstance(c, dict)}
        missing = [x for x in _SUITE_CASES if x not in ids]
        if missing:
            issues.append(f"suite_cases_missing:{','.join(missing)}")
    elif not s.get("ok"):
        issues.append("suite_not_ok")
    return {
        "ok": not issues and bool(s.get("ok", True)),
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n05_full_conformance": False,
        "wiki_full_certified": False,
        "note": "Wiki conditional rebuild deepen; not N05/Wiki-full certified",
    }


async def run_wiki_rebuild_suite(
    *,
    ledger: Any = None,
    tenant_id: str = "n05-wiki-rebuild-tenant",
    domain_id: str = "suite-domain",
) -> Dict[str, Any]:
    """N05 deepen：Wiki 有条件重建套件（certified 恒 false）。

    Args:
        ledger: 可选 FactLedger。
        tenant_id: 租户。
        domain_id: 域（默认 suite 占位，非业务域硬编码）。
    """
    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n05-wiki-rebuild-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await lg.initialize()
        wiki_db = str(root / "wiki_rebuild.sqlite3")
    else:
        lg = ledger
        await lg.initialize()
        root = Path(tempfile.mkdtemp(prefix="n05-wiki-aux-"))
        wiki_db = str(root / "wiki_rebuild.sqlite3")

    cases: List[Dict[str, Any]] = []
    try:
        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n05-wiki",
            kind="file",
            uri="file://n05/wiki.txt",
            content=b"n05-wiki",
            connector="n05",
            domain_id=domain_id,
        )
        evidence = [
            {
                "source_id": src["source_id"],
                "locator": "1",
                "quote": "ok",
                "fetched_at": src["fetched_at"],
            }
        ]
        await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n05-wiki",
            subject="InstallOrder:WO-N05",
            predicate="status",
            object="open",
            evidence=evidence,
            source_policy="n05",
            extractor_version="n05-wiki",
            review_status="published",
            confidence=0.9,
            allow_bootstrap_published=True,
            domain_id=domain_id,
        )

        exact = await project_facts_to_wiki(
            tenant_id=tenant_id,
            domain_id=domain_id,
            ledger=lg,
            clear_projected=True,
            rebuild_mode=REBUILD_MODE_EXACT,
            db_path=wiki_db,
        )
        pages = list_wiki_rebuild_pages(
            tenant_id=tenant_id, domain_id=domain_id, db_path=wiki_db
        )
        cases.append(
            {
                "id": "exact_writes_pages",
                "ok": bool(exact.get("written")) and len(pages) >= 1,
                "detail": "" if pages else "no_pages",
            }
        )

        non = await project_facts_to_wiki(
            tenant_id=tenant_id,
            domain_id=domain_id,
            ledger=lg,
            clear_projected=True,
            rebuild_mode=REBUILD_MODE_NON,
            exact_capable=False,
            db_path=wiki_db,
        )
        pages_non = list_wiki_rebuild_pages(
            tenant_id=tenant_id, domain_id=domain_id, db_path=wiki_db
        )
        cases.append(
            {
                "id": "non_skips_write",
                "ok": non.get("written") is False and len(pages_non) == 0,
                "detail": "" if not pages_non else "pages_written_on_non",
            }
        )

        sem = await project_facts_to_wiki(
            tenant_id=tenant_id,
            domain_id=domain_id,
            ledger=lg,
            clear_projected=True,
            rebuild_mode=REBUILD_MODE_SEMANTIC,
            db_path=wiki_db,
        )
        cases.append(
            {
                "id": "semantic_writes_marked",
                "ok": bool(sem.get("written"))
                and sem.get("rebuild_mode") == REBUILD_MODE_SEMANTIC
                and sem.get("semantic") is True,
                "detail": "",
            }
        )

        tenant_ok = False
        try:
            await project_facts_to_wiki(
                tenant_id="",
                domain_id=domain_id,
                ledger=lg,
                db_path=wiki_db,
            )
        except FactLedgerError:
            tenant_ok = True
        cases.append(
            {
                "id": "tenant_required",
                "ok": tenant_ok,
                "detail": "" if tenant_ok else "empty_tenant_accepted",
            }
        )

        gate_ok = bool((exact.get("rebuild_gate") or {}).get("ok"))
        cases.append(
            {
                "id": "gate_receipt_ok",
                "ok": gate_ok,
                "detail": "" if gate_ok else "exact_gate_failed",
            }
        )

        # 为什么：套件自身不得自称 certified / wiki 全量
        honesty = (
            exact.get("rebuild_gate", {}).get("certified") is False
            and exact.get("rebuild_gate", {}).get("n05_full_conformance") is False
        )
        cases.append(
            {
                "id": "honesty_certified_false",
                "ok": honesty,
                "detail": "" if honesty else "honesty_flags_leaked",
            }
        )

        passed = sum(1 for c in cases if c.get("ok"))
        out = {
            "ok": passed == len(_SUITE_CASES),
            "passed": passed,
            "total": len(_SUITE_CASES),
            "cases": cases,
            "certified": False,
            "n05_full_conformance": False,
            "wiki_full_certified": False,
            "note": "Wiki conditional rebuild deepen; not full Wiki/N05 certified",
        }
        return out
    finally:
        if tmp is not None:
            tmp.cleanup()
