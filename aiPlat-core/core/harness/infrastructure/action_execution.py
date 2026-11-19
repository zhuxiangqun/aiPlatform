"""ActionExecution 最小切片（附录 C.2 / W7）— customer_action 幂等 + 快照。

职责：对 ``customer_action`` 强制 ``tenant_id`` + ``idempotency_key``；
重复键回放已有执行；落盘 before/after 快照（不改历史）。
非目标：kill switch、Lv4 误报门重设计、字段级 ACL。
Registry 裸 ``_bypass_approval`` 已收紧（仅 approve 重入，见 action_registry）。
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

CUSTOMER_NS = "customer_action"


def _default_db_path() -> str:
    """解析 ActionExecution DB（与 ActionStore 同 AIPLAT_HOME 约定）。"""
    for key in ("AIPLAT_ACTION_EXECUTION_DB", "AIPLAT_ACTION_DB_PATH"):
        env = os.environ.get(key)
        if env:
            return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "action_execution.sqlite3")
    return "./data/action_execution.sqlite3"


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """打开/初始化幂等执行表。

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
        CREATE TABLE IF NOT EXISTS action_executions (
            execution_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            action_id TEXT NOT NULL,
            actor TEXT,
            target TEXT,
            status TEXT,
            policy_decision TEXT,
            before_snapshot TEXT,
            after_snapshot TEXT,
            result_json TEXT,
            error_json TEXT,
            input_hash TEXT,
            audit_hash TEXT,
            run_id TEXT,
            evidence_ref TEXT,
            approval_id TEXT,
            started_at REAL,
            completed_at REAL,
            UNIQUE(tenant_id, idempotency_key)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_action_exec_action "
        "ON action_executions(action_id, tenant_id)"
    )
    conn.commit()
    return conn


def is_customer_action(action_id: str) -> bool:
    """是否 customer_action 命名空间。

    Args:
        action_id: 动作 id。
    """
    aid = (action_id or "").strip()
    return aid.startswith(f"{CUSTOMER_NS}:")


def extract_execution_keys(params: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """从 params 提取 tenant_id / idempotency_key。

    Args:
        params: 动作入参。
    """
    p = params or {}
    return {
        "tenant_id": str(p.get("tenant_id") or "").strip(),
        "idempotency_key": str(p.get("idempotency_key") or "").strip(),
    }


def hash_input(params: Dict[str, Any]) -> str:
    """稳定 input_hash。

    Args:
        params: 入参。
    """
    blob = json.dumps(params or {}, ensure_ascii=False, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def audit_hash_for(record: Dict[str, Any]) -> str:
    """对执行记录做审计哈希（不含自身 audit_hash）。

    Args:
        record: 执行记录字典。
    """
    payload = {k: v for k, v in record.items() if k != "audit_hash"}
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def require_customer_execution_keys(
    action_id: str,
    params: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """customer_action 缺 tenant/idempotency → 拒绝回执；其它命名空间放行。

    Args:
        action_id: 动作 id。
        params: 入参。

    Returns:
        拒绝时的 dict；通过则 None。
    """
    if not is_customer_action(action_id):
        return None
    keys = extract_execution_keys(params)
    if not keys["tenant_id"]:
        return {
            "status": "invalid",
            "error": "tenant_id_required",
            "constraint_type": "action_execution",
        }
    if not keys["idempotency_key"]:
        return {
            "status": "invalid",
            "error": "idempotency_key_required",
            "constraint_type": "action_execution",
        }
    return None


def lookup_execution(
    tenant_id: str,
    idempotency_key: str,
    *,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """按租户+幂等键查找已有执行。

    Args:
        tenant_id: 租户。
        idempotency_key: 幂等键。
        db_path: 可选库路径。
    """
    if not tenant_id or not idempotency_key:
        return None
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM action_executions WHERE tenant_id=? AND idempotency_key=?",
            (tenant_id, idempotency_key),
        ).fetchone()
        if not row:
            return None
        return _row_to_record(row)
    finally:
        conn.close()


def list_action_executions(
    *,
    tenant_id: str,
    action_id_prefix: str = "",
    limit: int = 100,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """按租户列出 ActionExecution 行（只读；跨租户空）。

    Args:
        tenant_id: 租户（必填）。
        action_id_prefix: 可选 action_id 前缀（LIKE prefix%）。
        limit: 最大条数（1–500）。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        return []
    lim = max(1, min(int(limit or 100), 500))
    prefix = (action_id_prefix or "").strip()
    conn = _connect(db_path)
    try:
        if prefix:
            rows = conn.execute(
                """
                SELECT * FROM action_executions
                WHERE tenant_id=? AND action_id LIKE ?
                ORDER BY COALESCE(completed_at, started_at) ASC, execution_id ASC
                LIMIT ?
                """,
                (tid, f"{prefix}%", lim),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM action_executions
                WHERE tenant_id=?
                ORDER BY COALESCE(completed_at, started_at) ASC, execution_id ASC
                LIMIT ?
                """,
                (tid, lim),
            ).fetchall()
        return [_row_to_record(r) for r in rows]
    finally:
        conn.close()


def _row_to_record(row: sqlite3.Row) -> Dict[str, Any]:
    """Row → ActionExecution 形字典。"""
    def _json(col: str) -> Any:
        raw = row[col]
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return raw

    return {
        "execution_id": row["execution_id"],
        "tenant_id": row["tenant_id"],
        "idempotency_key": row["idempotency_key"],
        "action_id": row["action_id"],
        "actor": row["actor"],
        "target": row["target"],
        "status": row["status"],
        "policy_decision": row["policy_decision"],
        "before_snapshot": _json("before_snapshot") or {},
        "after_snapshot": _json("after_snapshot") or {},
        "result": _json("result_json"),
        "error": _json("error_json"),
        "input_hash": row["input_hash"],
        "audit_hash": row["audit_hash"],
        "run_id": row["run_id"] or "",
        "evidence_ref": row["evidence_ref"] or "",
        "approval_id": row["approval_id"] or "",
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "action_namespace": CUSTOMER_NS,
    }


def persist_execution(
    record: Dict[str, Any],
    *,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """追加写 ActionExecution；冲突时返回已有记录（不改历史）。

    Args:
        record: 执行记录。
        db_path: 可选库路径。
    """
    tenant_id = str(record.get("tenant_id") or "").strip()
    key = str(record.get("idempotency_key") or "").strip()
    if not tenant_id or not key:
        raise ValueError("tenant_id and idempotency_key required")

    existing = lookup_execution(tenant_id, key, db_path=db_path)
    if existing:
        return existing

    execution_id = str(record.get("execution_id") or f"exec_{uuid.uuid4().hex[:16]}")
    payload = dict(record)
    payload["execution_id"] = execution_id
    if not payload.get("audit_hash"):
        payload["audit_hash"] = audit_hash_for(payload)

    conn = _connect(db_path)
    try:
        try:
            conn.execute(
                """
                INSERT INTO action_executions (
                    execution_id, tenant_id, idempotency_key, action_id, actor, target,
                    status, policy_decision, before_snapshot, after_snapshot,
                    result_json, error_json, input_hash, audit_hash,
                    run_id, evidence_ref, approval_id, started_at, completed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    execution_id,
                    tenant_id,
                    key,
                    str(payload.get("action_id") or ""),
                    str(payload.get("actor") or ""),
                    str(payload.get("target") or ""),
                    str(payload.get("status") or ""),
                    str(payload.get("policy_decision") or ""),
                    json.dumps(payload.get("before_snapshot") or {}, ensure_ascii=False),
                    json.dumps(payload.get("after_snapshot") or {}, ensure_ascii=False),
                    json.dumps(payload.get("result"), ensure_ascii=False, default=str)
                    if payload.get("result") is not None
                    else None,
                    json.dumps(payload.get("error"), ensure_ascii=False, default=str)
                    if payload.get("error") is not None
                    else None,
                    str(payload.get("input_hash") or ""),
                    str(payload.get("audit_hash") or ""),
                    str(payload.get("run_id") or ""),
                    str(payload.get("evidence_ref") or ""),
                    str(payload.get("approval_id") or ""),
                    float(payload.get("started_at") or time.time()),
                    float(payload.get("completed_at") or time.time()),
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # 为什么：并发双写时 UNIQUE 冲突 → 回放已有，禁止改历史
            conn.rollback()
            again = lookup_execution(tenant_id, key, db_path=db_path)
            if again:
                return again
            raise
    finally:
        conn.close()
    # 为什么：N24 J6 — ActionExecution 热路径 best-effort 写入统一审计总线（非 ActionStore 合并）
    try:
        from core.harness.knowledge_pipeline.unified_audit_bus import (
            append_unified_audit_event,
        )

        occurred = float(
            payload.get("completed_at") or payload.get("started_at") or time.time()
        )
        append_unified_audit_event(
            tenant_id=tenant_id,
            event_id=str(execution_id),
            stream="action_execution",
            event_type=str(payload.get("status") or "executed"),
            occurred_at=occurred,
            actor=str(payload.get("actor") or ""),
            subject=str(payload.get("action_id") or ""),
            refs={
                "idempotency_key": key,
                "audit_hash": str(payload.get("audit_hash") or ""),
            },
            payload=payload,
        )
    except Exception:
        logger.warning(
            "unified_audit_bus append failed for action_execution %s",
            execution_id,
            exc_info=True,
        )
    return payload


def build_execution_from_result(
    *,
    action_id: str,
    tenant_id: str,
    idempotency_key: str,
    actor: str,
    target: str,
    params: Dict[str, Any],
    registry_result: Dict[str, Any],
    before_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """由 Registry 回执组装 ActionExecution 记录。

    Args:
        action_id: 动作 id。
        tenant_id: 租户。
        idempotency_key: 幂等键。
        actor: 操作者。
        target: 实体目标。
        params: 原始入参。
        registry_result: AsyncActionRegistry.execute 回执。
        before_snapshot: 执行前快照；缺省从 result/params 推导。
    """
    started = time.time()
    status = str((registry_result or {}).get("status") or "")
    success_set = {"executed", "done", "completed", "success", "ok"}
    exec_status = "succeeded" if status in success_set else (
        "pending" if status == "pending_approval" else "failed"
    )
    after = {"status": status}
    result_body = (registry_result or {}).get("result")
    if isinstance(result_body, dict) and result_body.get("new_state"):
        after["state"] = result_body.get("new_state")
    before = before_snapshot or {"status": (params or {}).get("from_state") or "unknown"}
    policy = "allow"
    if status == "policy_denied":
        policy = "deny"
    elif status == "pending_approval":
        policy = "hitl_required"
    record = {
        "execution_id": f"exec_{uuid.uuid4().hex[:16]}",
        "action_id": action_id,
        "action_namespace": CUSTOMER_NS,
        "tenant_id": tenant_id,
        "actor": actor or "system",
        "target": target,
        "input_hash": hash_input(params or {}),
        "idempotency_key": idempotency_key,
        "status": exec_status,
        "policy_decision": policy,
        "approval_id": str((params or {}).get("approval_id") or ""),
        "before_snapshot": before,
        "after_snapshot": after,
        "run_id": str((params or {}).get("run_id") or (params or {}).get("pipeline_run_id") or ""),
        "evidence_ref": str((params or {}).get("evidence_ref") or ""),
        "result": registry_result if exec_status != "failed" else None,
        "error": None
        if exec_status != "failed"
        else {
            "status": status,
            "reason": (registry_result or {}).get("reason")
            or (registry_result or {}).get("error"),
        },
        "started_at": started,
        "completed_at": time.time(),
    }
    record["audit_hash"] = audit_hash_for(record)
    return record


async def run_customer_action_with_execution(
    *,
    action_id: str,
    entity_ref: Any,
    params: Optional[Dict[str, Any]],
    actor: str = "",
    role: str = "",
    permissions: Optional[list] = None,
    execute_fn: Any = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """W7：customer_action 经幂等门后执行并落盘；非 customer 直接透传 execute_fn。

    Args:
        action_id: 动作 id。
        entity_ref: 实体引用。
        params: 入参（须含 tenant_id/idempotency_key 当为 customer_action）。
        actor: 操作者。
        role: 角色。
        permissions: 权限列表。
        execute_fn: 底层执行（默认 ActionRegistry.execute）。
        db_path: 可选执行库路径。
    """
    denied = require_customer_execution_keys(action_id, params)
    if denied:
        return denied

    if not is_customer_action(action_id):
        if execute_fn is None:
            from core.harness.ontology_engine.action_registry import get_action_registry

            execute_fn = get_action_registry().execute
        return await execute_fn(
            action_id=action_id,
            entity_ref=entity_ref,
            params=params or {},
            actor=actor or "system",
            role=role or "",
            permissions=permissions,
        )

    keys = extract_execution_keys(params)
    prior = lookup_execution(
        keys["tenant_id"], keys["idempotency_key"], db_path=db_path
    )
    if prior:
        # 为什么：幂等回放不得再次跑 handler，防止双写副作用
        return {
            "status": "idempotent_replay",
            "execution": prior,
            "audited": True,
        }

    if execute_fn is None:
        from core.harness.ontology_engine.action_registry import get_action_registry

        execute_fn = get_action_registry().execute

    target = entity_ref
    if isinstance(entity_ref, tuple) and len(entity_ref) == 2:
        target = f"{entity_ref[0]}:{entity_ref[1]}"
    elif isinstance(entity_ref, dict):
        target = str(entity_ref.get("id") or entity_ref.get("entity_id") or "")

    result = await execute_fn(
        action_id=action_id,
        entity_ref=entity_ref,
        params=params or {},
        actor=actor or "system",
        role=role or "",
        permissions=permissions,
    )

    # pending_approval 也记一条（after=pending），便于审计；重复提交仍回放
    record = build_execution_from_result(
        action_id=action_id,
        tenant_id=keys["tenant_id"],
        idempotency_key=keys["idempotency_key"],
        actor=actor or "system",
        target=str(target),
        params=params or {},
        registry_result=result or {},
    )
    stored = persist_execution(record, db_path=db_path)
    out = dict(result or {})
    out["execution"] = stored
    out["execution_id"] = stored.get("execution_id")
    return out
