"""Knowledge Migration 最小切片（W10 / §15）— 双写 / 对账 / 回滚演练。

职责：登记迁移作业；双写 source+target；按 key/hash 对账并可修复；
记录读指针与回滚演练。source 在切写前始终权威。
N11/N14 deepen：显式切写授权（token+actor+reason+对账干净）；
``process_cutover_authorized`` / 生产 certified 恒 false。
非目标：不做真实生产回填；不自动切写；不宣称 N11/N14/N24 certified。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STORE_SOURCE = "source"
STORE_TARGET = "target"
READ_POINTER_SOURCE = "source"
READ_POINTER_TARGET = "target"
PHASES = (
    "inventory",
    "dual_write",
    "backfill",
    "reconcile",
    "shadow_read",
    "cutover",
    "rollback_drill",
    "retired",
)


def _default_db_path() -> str:
    """解析迁移作业 DB（AIPLAT_HOME 约定）。"""
    env = os.environ.get("AIPLAT_KNOWLEDGE_MIGRATION_DB")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "knowledge_migration.sqlite3")
    return "./data/knowledge_migration.sqlite3"


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """打开/初始化迁移表。

    Args:
        db_path: 可选库路径。
    """
    path = db_path or _default_db_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_jobs (
            job_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            mapping_json TEXT NOT NULL,
            phase TEXT NOT NULL,
            read_pointer TEXT NOT NULL,
            cutover_authorized INTEGER NOT NULL DEFAULT 0,
            created_at REAL,
            updated_at REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_records (
            job_id TEXT NOT NULL,
            store TEXT NOT NULL,
            record_key TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            version INTEGER NOT NULL,
            updated_at REAL,
            PRIMARY KEY(job_id, store, record_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_events (
            event_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            detail_json TEXT NOT NULL,
            created_at REAL
        )
        """
    )
    conn.commit()
    return conn


def _payload_hash(payload: Dict[str, Any]) -> str:
    """稳定 payload 哈希（排序键）。

    Args:
        payload: 记录内容。
    """
    raw = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _append_event(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    tenant_id: str,
    event_type: str,
    detail: Dict[str, Any],
) -> None:
    """追加审计事件。

    Args:
        conn: 连接。
        job_id: 作业 id。
        tenant_id: 租户。
        event_type: 事件类型。
        detail: 详情。
    """
    conn.execute(
        """
        INSERT INTO migration_events(event_id, job_id, tenant_id, event_type, detail_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            job_id,
            tenant_id,
            event_type,
            json.dumps(detail, ensure_ascii=False),
            time.time(),
        ),
    )


def _job_row(
    conn: sqlite3.Connection, job_id: str, tenant_id: str
) -> Optional[sqlite3.Row]:
    """按租户取作业行。

    Args:
        conn: 连接。
        job_id: 作业 id。
        tenant_id: 租户。
    """
    return conn.execute(
        "SELECT * FROM migration_jobs WHERE job_id=? AND tenant_id=?",
        (job_id, tenant_id),
    ).fetchone()


def _job_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """作业行 → API dict。

    Args:
        row: sqlite Row。
    """
    return {
        "job_id": row["job_id"],
        "tenant_id": row["tenant_id"],
        "domain": row["domain"],
        "mapping": json.loads(row["mapping_json"]),
        "phase": row["phase"],
        "read_pointer": row["read_pointer"],
        "cutover_authorized": bool(row["cutover_authorized"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        # 诚实锁：作业级授权 ≠ 生产切写认证
        "process_cutover_authorized": False,
        "production_cutover_certified": False,
        "accuracy_claim": False,
    }


def _cutover_token_ok(token: str) -> bool:
    """校验切写 token（``AIPLAT_KNOWLEDGE_CUTOVER_TOKEN``；未配置则拒绝）。

    Args:
        token: 调用方提供的 token。
    """
    expected = (os.environ.get("AIPLAT_KNOWLEDGE_CUTOVER_TOKEN") or "").strip()
    if not expected:
        return False
    return (token or "").strip() == expected


def start_migration_job(
    *,
    tenant_id: str,
    domain: str,
    mapping: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """创建迁移作业（默认读指针=source）。

    Args:
        tenant_id: 租户。
        domain: 域。
        mapping: 资产映射说明（Wiki/Graph/KB 等）。
        job_id: 可选作业 id。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    dom = (domain or "").strip()
    if not tid or not dom:
        return {"status": "invalid", "error": "tenant_id_and_domain_required"}

    jid = (job_id or "").strip() or str(uuid.uuid4())
    now = time.time()
    payload_mapping = mapping or {
        "wiki": "read_model",
        "graph_index": "object_projection",
        "vector_kb": "raw_index",
    }
    with _connect(db_path) as conn:
        existing = _job_row(conn, jid, tid)
        if existing:
            return {"status": "exists", **_job_to_dict(existing)}
        conn.execute(
            """
            INSERT INTO migration_jobs(
                job_id, tenant_id, domain, mapping_json, phase,
                read_pointer, cutover_authorized, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                jid,
                tid,
                dom,
                json.dumps(payload_mapping, ensure_ascii=False),
                "dual_write",
                READ_POINTER_SOURCE,
                now,
                now,
            ),
        )
        _append_event(
            conn,
            job_id=jid,
            tenant_id=tid,
            event_type="job_started",
            detail={"domain": dom, "phase": "dual_write"},
        )
        conn.commit()
        row = _job_row(conn, jid, tid)
    assert row is not None
    return {"status": "created", **_job_to_dict(row)}


def get_migration_job(
    job_id: str,
    *,
    tenant_id: str,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """读取迁移作业（跨租户隐藏）。

    Args:
        job_id: 作业 id。
        tenant_id: 租户。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    jid = (job_id or "").strip()
    if not tid or not jid:
        return None
    with _connect(db_path) as conn:
        row = _job_row(conn, jid, tid)
        if not row:
            return None
        return _job_to_dict(row)


def write_store_record(
    job_id: str,
    *,
    tenant_id: str,
    store: str,
    record_key: str,
    payload: Dict[str, Any],
    version: Optional[int] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """写入单侧 store（演练用：制造 orphan/单边失败）。

    Args:
        job_id: 作业 id。
        tenant_id: 租户。
        store: source|target。
        record_key: 记录键。
        payload: 内容。
        version: 可选版本；默认自增/1。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    jid = (job_id or "").strip()
    key = (record_key or "").strip()
    side = (store or "").strip().lower()
    if side not in (STORE_SOURCE, STORE_TARGET):
        return {"status": "invalid", "error": "store_must_be_source_or_target"}
    if not tid or not jid or not key:
        return {"status": "invalid", "error": "job_tenant_key_required"}
    if not isinstance(payload, dict):
        return {"status": "invalid", "error": "payload_must_be_object"}

    ph = _payload_hash(payload)
    now = time.time()
    with _connect(db_path) as conn:
        job = _job_row(conn, jid, tid)
        if not job:
            return {"status": "not_found", "error": "job_not_found"}
        cur = conn.execute(
            "SELECT version FROM migration_records WHERE job_id=? AND store=? AND record_key=?",
            (jid, side, key),
        ).fetchone()
        next_ver = int(version) if version is not None else (
            int(cur["version"]) + 1 if cur else 1
        )
        conn.execute(
            """
            INSERT INTO migration_records(
                job_id, store, record_key, payload_hash, payload_json, version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, store, record_key) DO UPDATE SET
                payload_hash=excluded.payload_hash,
                payload_json=excluded.payload_json,
                version=excluded.version,
                updated_at=excluded.updated_at
            """,
            (
                jid,
                side,
                key,
                ph,
                json.dumps(payload, ensure_ascii=False),
                next_ver,
                now,
            ),
        )
        _append_event(
            conn,
            job_id=jid,
            tenant_id=tid,
            event_type="store_write",
            detail={"store": side, "record_key": key, "version": next_ver},
        )
        conn.commit()
    return {
        "status": "ok",
        "job_id": jid,
        "store": side,
        "record_key": key,
        "version": next_ver,
        "payload_hash": ph,
        "process_cutover_authorized": False,
    }


def dual_write_record(
    job_id: str,
    *,
    tenant_id: str,
    record_key: str,
    payload: Dict[str, Any],
    fail_target: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """双写：先写 source（权威），再写 target（影子）。

    Args:
        job_id: 作业 id。
        tenant_id: 租户。
        record_key: 记录键。
        payload: 内容。
        fail_target: 模拟 target 写失败（用于对账演练）。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    jid = (job_id or "").strip()
    key = (record_key or "").strip()
    if not tid or not jid or not key:
        return {"status": "invalid", "error": "job_tenant_key_required"}
    if not isinstance(payload, dict):
        return {"status": "invalid", "error": "payload_must_be_object"}

    src = write_store_record(
        jid,
        tenant_id=tid,
        store=STORE_SOURCE,
        record_key=key,
        payload=payload,
        db_path=db_path,
    )
    if src.get("status") != "ok":
        return src
    target_ok = True
    if fail_target:
        # 为什么：双写非原子；故意只写 source，留给对账修复
        target_ok = False
    else:
        tgt = write_store_record(
            jid,
            tenant_id=tid,
            store=STORE_TARGET,
            record_key=key,
            payload=payload,
            version=src["version"],
            db_path=db_path,
        )
        if tgt.get("status") != "ok":
            target_ok = False

    with _connect(db_path) as conn:
        _append_event(
            conn,
            job_id=jid,
            tenant_id=tid,
            event_type="dual_write",
            detail={
                "record_key": key,
                "payload_hash": src.get("payload_hash"),
                "version": src.get("version"),
                "target_ok": target_ok,
            },
        )
        conn.execute(
            "UPDATE migration_jobs SET phase=?, updated_at=? WHERE job_id=? AND tenant_id=?",
            ("dual_write", time.time(), jid, tid),
        )
        conn.commit()

    return {
        "status": "ok" if target_ok else "partial",
        "job_id": jid,
        "record_key": key,
        "version": src.get("version"),
        "payload_hash": src.get("payload_hash"),
        "source_ok": True,
        "target_ok": target_ok,
        "process_cutover_authorized": False,
    }


def reconcile_migration(
    job_id: str,
    *,
    tenant_id: str,
    repair: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """对账 source vs target；可选按 source 权威修复。

    Args:
        job_id: 作业 id。
        tenant_id: 租户。
        repair: True 时用 source 覆盖/补齐 target，并删除 orphan。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    jid = (job_id or "").strip()
    if not tid or not jid:
        return {"status": "invalid", "error": "job_and_tenant_required"}

    with _connect(db_path) as conn:
        job = _job_row(conn, jid, tid)
        if not job:
            return {"status": "not_found", "error": "job_not_found"}

        src_rows = conn.execute(
            "SELECT record_key, payload_hash, payload_json, version FROM migration_records "
            "WHERE job_id=? AND store=?",
            (jid, STORE_SOURCE),
        ).fetchall()
        tgt_rows = conn.execute(
            "SELECT record_key, payload_hash, payload_json, version FROM migration_records "
            "WHERE job_id=? AND store=?",
            (jid, STORE_TARGET),
        ).fetchall()

        src_map = {r["record_key"]: r for r in src_rows}
        tgt_map = {r["record_key"]: r for r in tgt_rows}
        missing = sorted(set(src_map) - set(tgt_map))
        orphans = sorted(set(tgt_map) - set(src_map))
        stale: List[Dict[str, Any]] = []
        for key in sorted(set(src_map) & set(tgt_map)):
            s, t = src_map[key], tgt_map[key]
            if s["payload_hash"] != t["payload_hash"] or int(s["version"]) != int(t["version"]):
                stale.append(
                    {
                        "record_key": key,
                        "source_hash": s["payload_hash"],
                        "target_hash": t["payload_hash"],
                        "source_version": int(s["version"]),
                        "target_version": int(t["version"]),
                    }
                )

        repaired = {"inserted": 0, "updated": 0, "deleted_orphans": 0}
        now = time.time()
        if repair:
            for key in missing:
                s = src_map[key]
                conn.execute(
                    """
                    INSERT INTO migration_records(
                        job_id, store, record_key, payload_hash, payload_json, version, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        jid,
                        STORE_TARGET,
                        key,
                        s["payload_hash"],
                        s["payload_json"],
                        int(s["version"]),
                        now,
                    ),
                )
                repaired["inserted"] += 1
            for item in stale:
                key = item["record_key"]
                s = src_map[key]
                # 为什么：source 权威；仅当 source 版本 ≥ target 才覆盖，避免旧快照打新写入
                if int(s["version"]) >= int(tgt_map[key]["version"]):
                    conn.execute(
                        """
                        UPDATE migration_records
                        SET payload_hash=?, payload_json=?, version=?, updated_at=?
                        WHERE job_id=? AND store=? AND record_key=?
                        """,
                        (
                            s["payload_hash"],
                            s["payload_json"],
                            int(s["version"]),
                            now,
                            jid,
                            STORE_TARGET,
                            key,
                        ),
                    )
                    repaired["updated"] += 1
            for key in orphans:
                conn.execute(
                    "DELETE FROM migration_records WHERE job_id=? AND store=? AND record_key=?",
                    (jid, STORE_TARGET, key),
                )
                repaired["deleted_orphans"] += 1

            # 修复后再扫一遍
            tgt_rows = conn.execute(
                "SELECT record_key, payload_hash, version FROM migration_records "
                "WHERE job_id=? AND store=?",
                (jid, STORE_TARGET),
            ).fetchall()
            tgt_map = {r["record_key"]: r for r in tgt_rows}
            missing = sorted(set(src_map) - set(tgt_map))
            orphans = sorted(set(tgt_map) - set(src_map))
            stale = []
            for key in sorted(set(src_map) & set(tgt_map)):
                s, t = src_map[key], tgt_map[key]
                if s["payload_hash"] != t["payload_hash"] or int(s["version"]) != int(
                    t["version"]
                ):
                    stale.append({"record_key": key})

        ok = not (missing or orphans or stale)
        _append_event(
            conn,
            job_id=jid,
            tenant_id=tid,
            event_type="reconcile",
            detail={
                "ok": ok,
                "repair": repair,
                "missing": missing,
                "orphans": orphans,
                "stale": stale,
                "repaired": repaired,
            },
        )
        conn.execute(
            "UPDATE migration_jobs SET phase=?, updated_at=? WHERE job_id=? AND tenant_id=?",
            ("reconcile", now, jid, tid),
        )
        conn.commit()

    return {
        "status": "ok" if ok else "drift",
        "ok": ok,
        "job_id": jid,
        "counts": {"source": len(src_map), "target": len(tgt_map)},
        "missing": missing,
        "orphans": orphans,
        "stale": stale,
        "repaired": repaired if repair else None,
        "process_cutover_authorized": False,
        "environment": "local",
    }


def set_read_pointer(
    job_id: str,
    *,
    tenant_id: str,
    pointer: str,
    require_reconcile_ok: bool = True,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """设置读指针（灰度读）。切到 target 需对账干净且本切片永不授权生产 cutover。

    Args:
        job_id: 作业 id。
        tenant_id: 租户。
        pointer: source|target。
        require_reconcile_ok: 切 target 前强制对账通过。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    jid = (job_id or "").strip()
    ptr = (pointer or "").strip().lower()
    if ptr not in (READ_POINTER_SOURCE, READ_POINTER_TARGET):
        return {"status": "invalid", "error": "pointer_must_be_source_or_target"}
    if not tid or not jid:
        return {"status": "invalid", "error": "job_and_tenant_required"}

    with _connect(db_path) as conn:
        job = _job_row(conn, jid, tid)
        if not job:
            return {"status": "not_found", "error": "job_not_found"}

    if ptr == READ_POINTER_TARGET and require_reconcile_ok:
        # 先释放连接再对账，避免 sqlite 嵌套写锁
        recon = reconcile_migration(
            jid, tenant_id=tid, repair=False, db_path=db_path
        )
        if not recon.get("ok"):
            return {
                "status": "blocked",
                "error": "reconcile_not_ok",
                "reconcile": recon,
                "process_cutover_authorized": False,
            }

    now = time.time()
    with _connect(db_path) as conn:
        # 为什么：target 读=shadow_read 演练，不提升 cutover_authorized
        conn.execute(
            "UPDATE migration_jobs SET read_pointer=?, phase=?, updated_at=? "
            "WHERE job_id=? AND tenant_id=?",
            (
                ptr,
                "shadow_read" if ptr == READ_POINTER_TARGET else "dual_write",
                now,
                jid,
                tid,
            ),
        )
        _append_event(
            conn,
            job_id=jid,
            tenant_id=tid,
            event_type="read_pointer",
            detail={"pointer": ptr},
        )
        conn.commit()
        row = _job_row(conn, jid, tid)
    assert row is not None
    return {"status": "ok", **_job_to_dict(row)}


def record_rollback_drill(
    job_id: str,
    *,
    tenant_id: str,
    note: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """回滚演练：强制读指针回 source 并落审计事件。

    Args:
        job_id: 作业 id。
        tenant_id: 租户。
        note: 演练备注。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    jid = (job_id or "").strip()
    if not tid or not jid:
        return {"status": "invalid", "error": "job_and_tenant_required"}

    with _connect(db_path) as conn:
        job = _job_row(conn, jid, tid)
        if not job:
            return {"status": "not_found", "error": "job_not_found"}
        now = time.time()
        prev = job["read_pointer"]
        conn.execute(
            "UPDATE migration_jobs SET read_pointer=?, phase=?, updated_at=? "
            "WHERE job_id=? AND tenant_id=?",
            (READ_POINTER_SOURCE, "rollback_drill", now, jid, tid),
        )
        detail = {
            "previous_pointer": prev,
            "pointer": READ_POINTER_SOURCE,
            "note": note or "rollback_drill",
            "data_loss": False,
        }
        _append_event(
            conn,
            job_id=jid,
            tenant_id=tid,
            event_type="rollback_drill",
            detail=detail,
        )
        conn.commit()
        row = _job_row(conn, jid, tid)
        events = conn.execute(
            "SELECT event_type, detail_json, created_at FROM migration_events "
            "WHERE job_id=? AND tenant_id=? AND event_type='rollback_drill' "
            "ORDER BY created_at DESC LIMIT 5",
            (jid, tid),
        ).fetchall()
    assert row is not None
    return {
        "status": "ok",
        "drill": detail,
        "job": _job_to_dict(row),
        "recent_drills": [
            {
                "event_type": e["event_type"],
                "detail": json.loads(e["detail_json"]),
                "created_at": e["created_at"],
            }
            for e in events
        ],
        "process_cutover_authorized": False,
    }


def list_migration_events(
    job_id: str,
    *,
    tenant_id: str,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """列出迁移审计事件（租户隔离）。

    Args:
        job_id: 作业 id。
        tenant_id: 租户。
        limit: 条数上限。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    jid = (job_id or "").strip()
    if not tid or not jid:
        return {"status": "invalid", "error": "job_and_tenant_required", "events": []}
    lim = max(1, min(int(limit or 50), 200))
    with _connect(db_path) as conn:
        job = _job_row(conn, jid, tid)
        if not job:
            return {"status": "not_found", "error": "job_not_found", "events": []}
        rows = conn.execute(
            "SELECT event_id, event_type, detail_json, created_at FROM migration_events "
            "WHERE job_id=? AND tenant_id=? ORDER BY created_at DESC LIMIT ?",
            (jid, tid, lim),
        ).fetchall()
    return {
        "status": "ok",
        "job_id": jid,
        "events": [
            {
                "event_id": r["event_id"],
                "event_type": r["event_type"],
                "detail": json.loads(r["detail_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ],
    }


def authorize_migration_cutover(
    job_id: str,
    *,
    tenant_id: str,
    actor: str,
    reason: str,
    token: str,
    require_reconcile_ok: bool = True,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """N11/N14 deepen：作业级切写授权（token+actor+reason；非生产认证）。

    Args:
        job_id: 作业 id。
        tenant_id: 租户。
        actor: 授权人。
        reason: 授权理由。
        token: 须匹配 ``AIPLAT_KNOWLEDGE_CUTOVER_TOKEN``。
        require_reconcile_ok: 授权前强制对账通过。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    jid = (job_id or "").strip()
    act = (actor or "").strip()
    why = (reason or "").strip()
    if not tid or not jid:
        return {"status": "invalid", "error": "job_and_tenant_required"}
    if not act or not why:
        return {"status": "invalid", "error": "actor_and_reason_required"}
    if not _cutover_token_ok(token):
        return {
            "status": "denied",
            "error": "cutover_token_invalid_or_unset",
            "process_cutover_authorized": False,
            "production_cutover_certified": False,
        }

    with _connect(db_path) as conn:
        job = _job_row(conn, jid, tid)
        if not job:
            return {"status": "not_found", "error": "job_not_found"}

    if require_reconcile_ok:
        recon = reconcile_migration(
            jid, tenant_id=tid, repair=False, db_path=db_path
        )
        if not recon.get("ok"):
            return {
                "status": "blocked",
                "error": "reconcile_not_ok",
                "reconcile": recon,
                "process_cutover_authorized": False,
                "production_cutover_certified": False,
            }

    now = time.time()
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE migration_jobs SET cutover_authorized=1, updated_at=? "
            "WHERE job_id=? AND tenant_id=?",
            (now, jid, tid),
        )
        _append_event(
            conn,
            job_id=jid,
            tenant_id=tid,
            event_type="cutover_authorized",
            detail={"actor": act, "reason": why},
        )
        conn.commit()
        row = _job_row(conn, jid, tid)
    assert row is not None
    out = {"status": "ok", **_job_to_dict(row)}
    out["authorized_by"] = act
    return out


def revoke_migration_cutover(
    job_id: str,
    *,
    tenant_id: str,
    actor: str,
    reason: str = "revoke",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """撤销作业级切写授权。

    Args:
        job_id: 作业 id。
        tenant_id: 租户。
        actor: 操作人。
        reason: 理由。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    jid = (job_id or "").strip()
    act = (actor or "").strip()
    if not tid or not jid or not act:
        return {"status": "invalid", "error": "job_tenant_actor_required"}
    with _connect(db_path) as conn:
        job = _job_row(conn, jid, tid)
        if not job:
            return {"status": "not_found", "error": "job_not_found"}
        now = time.time()
        conn.execute(
            "UPDATE migration_jobs SET cutover_authorized=0, phase=?, updated_at=? "
            "WHERE job_id=? AND tenant_id=?",
            ("dual_write", now, jid, tid),
        )
        _append_event(
            conn,
            job_id=jid,
            tenant_id=tid,
            event_type="cutover_revoked",
            detail={"actor": act, "reason": reason or "revoke"},
        )
        conn.commit()
        row = _job_row(conn, jid, tid)
    assert row is not None
    return {"status": "ok", **_job_to_dict(row)}


def request_write_cutover(
    job_id: str,
    *,
    tenant_id: str,
    actor: str,
    reason: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """请求切写阶段（须已作业级授权；仍非生产认证）。

    Args:
        job_id: 作业 id。
        tenant_id: 租户。
        actor: 操作人。
        reason: 理由。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    jid = (job_id or "").strip()
    act = (actor or "").strip()
    why = (reason or "").strip()
    if not tid or not jid or not act or not why:
        return {"status": "invalid", "error": "job_tenant_actor_reason_required"}
    with _connect(db_path) as conn:
        job = _job_row(conn, jid, tid)
        if not job:
            return {"status": "not_found", "error": "job_not_found"}
        if not bool(job["cutover_authorized"]):
            return {
                "status": "denied",
                "error": "cutover_not_authorized",
                "process_cutover_authorized": False,
                "production_cutover_certified": False,
            }
        now = time.time()
        conn.execute(
            "UPDATE migration_jobs SET phase=?, updated_at=? WHERE job_id=? AND tenant_id=?",
            ("cutover", now, jid, tid),
        )
        _append_event(
            conn,
            job_id=jid,
            tenant_id=tid,
            event_type="write_cutover_requested",
            detail={"actor": act, "reason": why, "environment": "local"},
        )
        conn.commit()
        row = _job_row(conn, jid, tid)
    assert row is not None
    return {
        "status": "ok",
        **_job_to_dict(row),
        "environment": "local",
        "note": "job-level cutover only; not production certified",
    }


def run_migration_cutover_auth_suite(
    *,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """N11/N14 deepen：切写授权套件（certified 恒 false）。

    Args:
        db_path: 可选临时库。
    """
    import tempfile

    checks: Dict[str, bool] = {}
    tmp: Optional[tempfile.TemporaryDirectory] = None
    path = db_path
    if not path:
        tmp = tempfile.TemporaryDirectory(prefix="n11-cutover-")
        path = str(Path(tmp.name) / "mig.db")

    prev_token = os.environ.get("AIPLAT_KNOWLEDGE_CUTOVER_TOKEN")
    os.environ["AIPLAT_KNOWLEDGE_CUTOVER_TOKEN"] = "n11-test-token"
    try:
        job = start_migration_job(
            tenant_id="n11-t", domain="lock-service", db_path=path
        )
        jid = job["job_id"]
        dual_write_record(
            jid,
            tenant_id="n11-t",
            record_key="k1",
            payload={"v": 1},
            db_path=path,
        )

        # 1) 无 token / 错 token 拒绝
        bad = authorize_migration_cutover(
            jid,
            tenant_id="n11-t",
            actor="ops",
            reason="pilot",
            token="wrong",
            db_path=path,
        )
        checks["bad_token_denied"] = bad.get("status") == "denied"

        # 2) 未授权切写拒绝
        denied = request_write_cutover(
            jid,
            tenant_id="n11-t",
            actor="ops",
            reason="go",
            db_path=path,
        )
        checks["unauthorized_cutover_denied"] = denied.get("status") == "denied"

        # 3) 正确 token + 对账 → 授权
        ok_auth = authorize_migration_cutover(
            jid,
            tenant_id="n11-t",
            actor="ops",
            reason="pilot-lab",
            token="n11-test-token",
            db_path=path,
        )
        checks["authorize_ok"] = (
            ok_auth.get("status") == "ok" and ok_auth.get("cutover_authorized") is True
        )

        # 4) 授权后可请求切写阶段
        cut = request_write_cutover(
            jid,
            tenant_id="n11-t",
            actor="ops",
            reason="lab-cutover",
            db_path=path,
        )
        checks["cutover_phase_ok"] = (
            cut.get("status") == "ok" and cut.get("phase") == "cutover"
        )

        # 5) 诚实锁：生产认证仍 false
        checks["honesty_process_false"] = cut.get("process_cutover_authorized") is False
        checks["honesty_prod_certified_false"] = (
            cut.get("production_cutover_certified") is False
        )

        # 6) 撤销
        rev = revoke_migration_cutover(
            jid, tenant_id="n11-t", actor="ops", reason="done", db_path=path
        )
        checks["revoke_ok"] = (
            rev.get("status") == "ok" and rev.get("cutover_authorized") is False
        )

        checks["honesty_certified_false"] = True
    finally:
        if prev_token is None:
            os.environ.pop("AIPLAT_KNOWLEDGE_CUTOVER_TOKEN", None)
        else:
            os.environ["AIPLAT_KNOWLEDGE_CUTOVER_TOKEN"] = prev_token
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for v in checks.values() if v)
    return {
        "ok": passed == len(checks),
        "passed": passed,
        "total": len(checks),
        "checks": checks,
        "certified": False,
        "n11_full_conformance": False,
        "n14_full_conformance": False,
        "production_cutover_certified": False,
        "note": (
            "Migration cutover auth deepen; job-level token only; "
            "not production certified / not N11/N14 full"
        ),
    }


def evaluate_migration_cutover_auth_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N11/N14 切写授权门槛门；certified 恒 false。

    Args:
        suite: ``run_migration_cutover_auth_suite`` 回执。
    """
    s = suite if isinstance(suite, dict) else run_migration_cutover_auth_suite()
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if s.get("certified") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("n11_full_conformance") is True:
        issues.append("honesty_n11_full_forbidden")
    if s.get("n14_full_conformance") is True:
        issues.append("honesty_n14_full_forbidden")
    if s.get("production_cutover_certified") is True:
        issues.append("honesty_production_cutover_forbidden")
    required = (
        "bad_token_denied",
        "unauthorized_cutover_denied",
        "authorize_ok",
        "cutover_phase_ok",
        "honesty_process_false",
        "honesty_prod_certified_false",
        "revoke_ok",
        "honesty_certified_false",
    )
    checks = s.get("checks") if isinstance(s.get("checks"), dict) else {}
    for k in required:
        if not checks.get(k):
            issues.append(f"missing_or_failed:{k}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "note": "Migration cutover auth deepen; not N11/N14 certified",
    }
