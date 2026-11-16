"""Knowledge Scenario 最小切片（附录 H.2 / W9）— 模拟分支隔离。

职责：创建 Scenario 分支；记录 dry_run 变更；合并须人审。
非目标：不写主 FactLedger / 主 ActionExecution；不做 Package 版本/签名；
合并通过后也不自动回写主事实（apply 另立切片）。
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _default_db_path() -> str:
    """解析 Scenario DB（AIPLAT_HOME 约定）。"""
    env = os.environ.get("AIPLAT_SCENARIO_DB")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "knowledge_scenario.sqlite3")
    return "./data/knowledge_scenario.sqlite3"


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """打开/初始化 Scenario 表。

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
        CREATE TABLE IF NOT EXISTS scenarios (
            scenario_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            branch TEXT NOT NULL,
            owner TEXT,
            status TEXT NOT NULL,
            dry_run INTEGER NOT NULL DEFAULT 1,
            base_snapshot_at TEXT,
            expires_at REAL,
            approval_id TEXT,
            created_at REAL,
            updated_at REAL,
            UNIQUE(tenant_id, branch)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scenario_changes (
            change_id TEXT PRIMARY KEY,
            scenario_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT,
            params_json TEXT,
            status TEXT NOT NULL,
            recorded_at REAL,
            FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id)
        )
        """
    )
    conn.commit()
    return conn


def create_scenario(
    *,
    tenant_id: str,
    branch: str,
    owner: str = "",
    base_snapshot_at: str = "",
    expires_at: Optional[float] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """创建 Scenario 分支（默认 dry_run）。

    Args:
        tenant_id: 租户。
        branch: 分支名。
        owner: 分支 owner。
        base_snapshot_at: 基线时间戳（RFC3339 或任意字符串）。
        expires_at: 过期 epoch；可选。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    br = (branch or "").strip()
    if not tid:
        return {"status": "invalid", "error": "tenant_id_required"}
    if not br:
        return {"status": "invalid", "error": "branch_required"}

    now = time.time()
    sid = f"scn_{uuid.uuid4().hex[:16]}"
    conn = _connect(db_path)
    try:
        try:
            conn.execute(
                """
                INSERT INTO scenarios (
                    scenario_id, tenant_id, branch, owner, status, dry_run,
                    base_snapshot_at, expires_at, approval_id, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sid,
                    tid,
                    br,
                    owner or "",
                    "open",
                    1,
                    base_snapshot_at or "",
                    expires_at,
                    "",
                    now,
                    now,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return {
                "status": "conflict",
                "error": "branch_exists",
                "tenant_id": tid,
                "branch": br,
            }
    finally:
        conn.close()
    return get_scenario(sid, tenant_id=tid, db_path=db_path) or {
        "status": "error",
        "error": "create_lookup_failed",
    }


def get_scenario(
    scenario_id: str,
    *,
    tenant_id: str,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """按租户读取 Scenario（跨租户返回 None）。

    Args:
        scenario_id: 场景 id。
        tenant_id: 租户。
        db_path: 可选库路径。
    """
    if not scenario_id or not tenant_id:
        return None
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM scenarios WHERE scenario_id=? AND tenant_id=?",
            (scenario_id, tenant_id),
        ).fetchone()
        if not row:
            return None
        changes = conn.execute(
            "SELECT * FROM scenario_changes WHERE scenario_id=? ORDER BY recorded_at",
            (scenario_id,),
        ).fetchall()
        return _scenario_to_dict(row, changes)
    finally:
        conn.close()


def _scenario_to_dict(
    row: sqlite3.Row, changes: Optional[List[sqlite3.Row]] = None
) -> Dict[str, Any]:
    """Row → Scenario 形字典。"""
    ch_out: List[Dict[str, Any]] = []
    for c in changes or []:
        params = {}
        raw = c["params_json"]
        if raw:
            try:
                params = json.loads(raw)
            except Exception:
                params = {"_raw": raw}
        ch_out.append(
            {
                "change_id": c["change_id"],
                "action": c["action"],
                "target": c["target"],
                "params": params,
                "status": c["status"],
                "recorded_at": c["recorded_at"],
            }
        )
    return {
        "status": "ok",
        "scenario_id": row["scenario_id"],
        "tenant_id": row["tenant_id"],
        "branch": row["branch"],
        "owner": row["owner"] or "",
        "scenario_status": row["status"],
        "dry_run": bool(row["dry_run"]),
        "base_snapshot_at": row["base_snapshot_at"] or "",
        "expires_at": row["expires_at"],
        "approval_id": row["approval_id"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "changes": ch_out,
    }


def _assert_writable(row: sqlite3.Row) -> Optional[Dict[str, Any]]:
    """过期/终态检查。"""
    if row["expires_at"] is not None and float(row["expires_at"]) < time.time():
        return {"status": "expired", "error": "scenario_expired"}
    st = str(row["status"] or "")
    if st in ("merged", "rejected", "closed"):
        return {"status": "invalid", "error": f"scenario_{st}"}
    return None


def simulate_change(
    *,
    scenario_id: str,
    tenant_id: str,
    action: str,
    target: str = "",
    params: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """追加模拟变更（dry_run）；不写主 Fact / ActionExecution。

    Args:
        scenario_id: 场景 id。
        tenant_id: 租户。
        action: 拟执行动作（如 ticket.close / customer_action:...）。
        target: 目标实体。
        params: 附加参数。
        db_path: 可选库路径。
    """
    if not (action or "").strip():
        return {"status": "invalid", "error": "action_required"}
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM scenarios WHERE scenario_id=? AND tenant_id=?",
            (scenario_id, tenant_id),
        ).fetchone()
        if not row:
            return {"status": "not_found", "error": "scenario_not_found"}
        denied = _assert_writable(row)
        if denied:
            return denied
        # 为什么：H.2 强制 dry_run；本切片永不触碰主事实账本
        if not row["dry_run"]:
            return {"status": "invalid", "error": "dry_run_required"}

        cid = f"chg_{uuid.uuid4().hex[:16]}"
        now = time.time()
        conn.execute(
            """
            INSERT INTO scenario_changes (
                change_id, scenario_id, action, target, params_json, status, recorded_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                cid,
                scenario_id,
                action.strip(),
                target or "",
                json.dumps(params or {}, ensure_ascii=False, default=str),
                "simulated",
                now,
            ),
        )
        conn.execute(
            "UPDATE scenarios SET status=?, updated_at=? WHERE scenario_id=?",
            ("simulated", now, scenario_id),
        )
        conn.commit()
    finally:
        conn.close()
    sc = get_scenario(scenario_id, tenant_id=tenant_id, db_path=db_path)
    return {
        "status": "simulated",
        "change_id": cid,
        "scenario": sc,
        "wrote_main_facts": False,
    }


def request_merge(
    *,
    scenario_id: str,
    tenant_id: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """请求合并 → pending_review（尚未人审）。

    Args:
        scenario_id: 场景 id。
        tenant_id: 租户。
        db_path: 可选库路径。
    """
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM scenarios WHERE scenario_id=? AND tenant_id=?",
            (scenario_id, tenant_id),
        ).fetchone()
        if not row:
            return {"status": "not_found", "error": "scenario_not_found"}
        denied = _assert_writable(row)
        if denied:
            return denied
        now = time.time()
        conn.execute(
            "UPDATE scenarios SET status=?, updated_at=? WHERE scenario_id=?",
            ("pending_review", now, scenario_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "status": "pending_review",
        "scenario": get_scenario(scenario_id, tenant_id=tenant_id, db_path=db_path),
    }


def approve_merge(
    *,
    scenario_id: str,
    tenant_id: str,
    approver: str,
    approval_id: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """人审通过合并标记；仍不写主事实。

    Args:
        scenario_id: 场景 id。
        tenant_id: 租户。
        approver: 审批人（必填）。
        approval_id: 可选审批单 id。
        db_path: 可选库路径。
    """
    if not (approver or "").strip():
        return {"status": "invalid", "error": "approver_required"}
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM scenarios WHERE scenario_id=? AND tenant_id=?",
            (scenario_id, tenant_id),
        ).fetchone()
        if not row:
            return {"status": "not_found", "error": "scenario_not_found"}
        if row["expires_at"] is not None and float(row["expires_at"]) < time.time():
            return {"status": "expired", "error": "scenario_expired"}
        if str(row["status"]) != "pending_review":
            return {
                "status": "invalid",
                "error": "not_pending_review",
                "scenario_status": row["status"],
            }
        now = time.time()
        aid = (approval_id or "").strip() or f"apr_{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            UPDATE scenarios
            SET status=?, approval_id=?, owner=COALESCE(NULLIF(owner,''), ?), updated_at=?
            WHERE scenario_id=?
            """,
            ("merged", aid, approver.strip(), now, scenario_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "status": "merged",
        "approval_id": aid,
        "approver": approver.strip(),
        "wrote_main_facts": False,
        "scenario": get_scenario(scenario_id, tenant_id=tenant_id, db_path=db_path),
    }


def reject_merge(
    *,
    scenario_id: str,
    tenant_id: str,
    reason: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """拒绝合并。

    Args:
        scenario_id: 场景 id。
        tenant_id: 租户。
        reason: 原因。
        db_path: 可选库路径。
    """
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM scenarios WHERE scenario_id=? AND tenant_id=?",
            (scenario_id, tenant_id),
        ).fetchone()
        if not row:
            return {"status": "not_found", "error": "scenario_not_found"}
        now = time.time()
        conn.execute(
            "UPDATE scenarios SET status=?, updated_at=? WHERE scenario_id=?",
            ("rejected", now, scenario_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "status": "rejected",
        "reason": reason or "",
        "scenario": get_scenario(scenario_id, tenant_id=tenant_id, db_path=db_path),
    }
