"""Fact/Claim 状态机最小切片（附录 N12 / N03 / 白皮书 §7.5）。

职责：
  - 审核态 ``review_status`` 与生命周期 ``status`` 分机、合法边校验
  - 转换必须带 actor/time/reason，并落审计 + 抬升 revision
  - Claim ``status`` 写路径（``transition_claim_status`` → ``put_claim``）
  - 门槛门；``certified`` 恒 false

非目标：
  - 不做 reviewer RBAC 角色源替换
  - 不宣称 N03/N12 全量 / 附录 N 认证
  - transition 写回 ``put_fact`` / ``put_claim(..., enforce_write_gates=False)``（边已在外层校验）
"""
from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# 与 schemas/validate_semantics_v4.3.1.py TRANSITIONS 对齐
FACT_REVIEW_TRANSITIONS: Dict[str, Set[str]] = {
    "draft": {"reviewed", "rejected"},
    "reviewed": {"published", "rejected"},
    "published": {"reviewed", "rejected"},
    "rejected": {"draft"},
}

FACT_LIFECYCLE_TRANSITIONS: Dict[str, Set[str]] = {
    "active": {"superseded", "retracted", "archived"},
    "superseded": {"archived"},
    "retracted": {"archived"},
    "archived": set(),
}

CLAIM_STATUS_TRANSITIONS: Dict[str, Set[str]] = {
    "accepted": {"contested", "retracted", "archived"},
    "contested": {"accepted", "retracted", "archived"},
    "retracted": {"archived"},
    "archived": set(),
}

MACHINES = {
    "fact_review": FACT_REVIEW_TRANSITIONS,
    "fact_lifecycle": FACT_LIFECYCLE_TRANSITIONS,
    "claim_status": CLAIM_STATUS_TRANSITIONS,
}


class FactStateMachineError(ValueError):
    """Fact/Claim 状态机契约错误。"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_db_path() -> str:
    """解析状态机审计库路径。

    Returns:
        SQLite 文件路径。
    """
    env = os.environ.get("AIPLAT_FACT_STATE_DB")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "knowledge_fact_state.sqlite3")
    return "./data/knowledge_fact_state.sqlite3"


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """打开/初始化转换审计表。

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
        CREATE TABLE IF NOT EXISTS fact_state_transitions (
            transition_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            record_kind TEXT NOT NULL,
            record_id TEXT NOT NULL,
            machine TEXT NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            actor TEXT NOT NULL,
            reason TEXT NOT NULL,
            revision INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fact_state_record
        ON fact_state_transitions(tenant_id, record_id, machine)
        """
    )
    conn.commit()
    return conn


def _is_transition_allowed(machine: str, from_state: str, to_state: str) -> bool:
    """判断边是否合法（纯函数）。

    Args:
        machine: fact_review / fact_lifecycle / claim_status。
        from_state: 当前态。
        to_state: 目标态。
    """
    table = MACHINES.get(machine)
    if table is None:
        return False
    return to_state in table.get(from_state, set())


def _assert_transition_allowed(machine: str, from_state: str, to_state: str) -> None:
    """非法边抛错。

    Args:
        machine: 状态机名。
        from_state: 当前态。
        to_state: 目标态。

    Raises:
        FactStateMachineError: 非法转换。
    """
    if machine not in MACHINES:
        raise FactStateMachineError(f"unknown machine: {machine}")
    if from_state == to_state:
        raise FactStateMachineError(f"noop transition forbidden: {from_state}")
    if not _is_transition_allowed(machine, from_state, to_state):
        raise FactStateMachineError(
            f"illegal {machine} transition: {from_state} -> {to_state}"
        )


def validate_sequence(machine: str, steps: List[str]) -> bool:
    """校验状态序列是否逐步合法。

    Args:
        machine: 状态机名。
        steps: 有序状态列表。
    """
    if len(steps) < 2:
        return False
    for i in range(len(steps) - 1):
        if not _is_transition_allowed(machine, steps[i], steps[i + 1]):
            return False
    return True


def _record_audit(
    *,
    tenant_id: str,
    record_kind: str,
    record_id: str,
    machine: str,
    from_state: str,
    to_state: str,
    actor: str,
    reason: str,
    revision: int,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """写入转换审计。

    Args:
        tenant_id: 租户。
        record_kind: fact / claim。
        record_id: 记录 ID。
        machine: 状态机。
        from_state / to_state: 边。
        actor / reason: 人因。
        revision: 新修订号。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    actor_s = (actor or "").strip()
    reason_s = (reason or "").strip()
    if not tid or not actor_s or not reason_s:
        raise FactStateMachineError("tenant_id, actor, reason required")
    created_at = _utc_now()
    transition_id = f"fst-{uuid.uuid4().hex[:12]}"
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_state_transitions (
                transition_id, tenant_id, record_kind, record_id, machine,
                from_state, to_state, actor, reason, revision, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                transition_id,
                tid,
                record_kind,
                record_id,
                machine,
                from_state,
                to_state,
                actor_s,
                reason_s,
                int(revision),
                created_at,
            ),
        )
        conn.commit()
    return {
        "transition_id": transition_id,
        "tenant_id": tid,
        "record_kind": record_kind,
        "record_id": record_id,
        "machine": machine,
        "from_state": from_state,
        "to_state": to_state,
        "actor": actor_s,
        "reason": reason_s,
        "revision": int(revision),
        "created_at": created_at,
    }


def list_fact_transitions(
    *,
    tenant_id: str,
    record_id: Optional[str] = None,
    machine: Optional[str] = None,
    db_path: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """列出转换审计。

    Args:
        tenant_id: 租户。
        record_id: 可选记录过滤。
        machine: 可选状态机过滤。
        db_path: 可选库路径。
        limit: 上限。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        return []
    clauses = ["tenant_id=?"]
    params: List[Any] = [tid]
    if record_id:
        clauses.append("record_id=?")
        params.append(record_id)
    if machine:
        clauses.append("machine=?")
        params.append(machine)
    params.append(max(1, min(int(limit), 500)))
    sql = (
        "SELECT * FROM fact_state_transitions WHERE "
        + " AND ".join(clauses)
        + " ORDER BY created_at DESC LIMIT ?"
    )
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


async def transition_fact_review(
    ledger: Any,
    *,
    fact_id: str,
    tenant_id: str,
    to_status: str,
    actor: str,
    reason: str,
    db_path: Optional[str] = None,
    source_policy_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """审核态转换（须 actor/reason；published 须 evidence + active）。

    Args:
        ledger: FactLedger。
        fact_id: Fact ID。
        tenant_id: 租户。
        to_status: 目标 review_status。
        actor: 操作人。
        reason: 理由。
        db_path: 审计库路径。
        source_policy_db_path: 来源策略/冲突库路径。

    Returns:
        更新后的 Fact + transition 审计。
    """
    fact = await ledger.get_fact(fact_id, tenant_id=tenant_id)
    if fact is None:
        raise FactStateMachineError(f"fact not found: {fact_id}")
    from_state = str(fact.get("review_status") or "")
    to_s = (to_status or "").strip()
    _assert_transition_allowed("fact_review", from_state, to_s)
    if to_s == "published":
        if not fact.get("evidence"):
            raise FactStateMachineError("published requires non-empty evidence")
        if str(fact.get("status") or "") != "active":
            raise FactStateMachineError(
                "published review requires lifecycle status=active"
            )
        # N04：未裁决冲突 / 未登记策略不得经 transition 发布
        from core.harness.knowledge_pipeline.source_policy import (
            SourcePolicyError,
            assert_publish_allowed,
        )

        try:
            assert_publish_allowed(
                tenant_id=tenant_id,
                source_policy=str(fact.get("source_policy") or ""),
                subject=str(fact.get("subject") or ""),
                predicate=str(fact.get("predicate") or ""),
                db_path=source_policy_db_path,
            )
        except SourcePolicyError as exc:
            raise FactStateMachineError(str(exc)) from exc
    new_rev = int(fact.get("revision") or 1) + 1
    audit = _record_audit(
        tenant_id=tenant_id,
        record_kind="fact",
        record_id=fact_id,
        machine="fact_review",
        from_state=from_state,
        to_state=to_s,
        actor=actor,
        reason=reason,
        revision=new_rev,
        db_path=db_path,
    )
    updated = await ledger.put_fact(
        tenant_id=tenant_id,
        collection_id=fact["collection_id"],
        subject=fact["subject"],
        predicate=fact["predicate"],
        object=fact["object"],
        evidence=list(fact.get("evidence") or []),
        source_policy=fact["source_policy"],
        extractor_version=fact["extractor_version"],
        review_status=to_s,
        confidence=float(fact.get("confidence") or 0.0),
        domain_id=fact.get("domain_id") or "",
        fact_id=fact_id,
        status=str(fact.get("status") or "active"),
        inferred=bool(fact.get("inferred")),
        valid_from=fact.get("valid_from"),
        valid_to=fact.get("valid_to"),
        revision=new_rev,
        # 为什么关硬门：边与冲突门已在本函数校验；避免「改状态须走 transition」自锁
        enforce_write_gates=False,
        revision_actor=actor,
        revision_reason=reason,
    )
    return {"fact": updated, "transition": audit}


async def transition_fact_lifecycle(
    ledger: Any,
    *,
    fact_id: str,
    tenant_id: str,
    to_status: str,
    actor: str,
    reason: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """生命周期转换（retracted/superseded 不物理删除）。

    Args:
        ledger: FactLedger。
        fact_id: Fact ID。
        tenant_id: 租户。
        to_status: 目标 lifecycle status。
        actor: 操作人。
        reason: 理由。
        db_path: 审计库路径。

    Returns:
        更新后的 Fact + transition 审计。
    """
    fact = await ledger.get_fact(fact_id, tenant_id=tenant_id)
    if fact is None:
        raise FactStateMachineError(f"fact not found: {fact_id}")
    from_state = str(fact.get("status") or "")
    to_s = (to_status or "").strip()
    _assert_transition_allowed("fact_lifecycle", from_state, to_s)
    # 为什么：语义校验要求 active 必须已 published
    if to_s == "active" and str(fact.get("review_status") or "") != "published":
        raise FactStateMachineError(
            "lifecycle active requires review_status=published"
        )
    new_rev = int(fact.get("revision") or 1) + 1
    audit = _record_audit(
        tenant_id=tenant_id,
        record_kind="fact",
        record_id=fact_id,
        machine="fact_lifecycle",
        from_state=from_state,
        to_state=to_s,
        actor=actor,
        reason=reason,
        revision=new_rev,
        db_path=db_path,
    )
    updated = await ledger.put_fact(
        tenant_id=tenant_id,
        collection_id=fact["collection_id"],
        subject=fact["subject"],
        predicate=fact["predicate"],
        object=fact["object"],
        evidence=list(fact.get("evidence") or []),
        source_policy=fact["source_policy"],
        extractor_version=fact["extractor_version"],
        review_status=str(fact.get("review_status") or "draft"),
        confidence=float(fact.get("confidence") or 0.0),
        domain_id=fact.get("domain_id") or "",
        fact_id=fact_id,
        status=to_s,
        inferred=bool(fact.get("inferred")),
        valid_from=fact.get("valid_from"),
        valid_to=fact.get("valid_to"),
        revision=new_rev,
        enforce_write_gates=False,
        revision_actor=actor,
        revision_reason=reason,
    )
    return {"fact": updated, "transition": audit}


def transition_claim_status_pure(
    *,
    from_status: str,
    to_status: str,
    actor: str,
    reason: str,
    claim_id: str,
    tenant_id: str,
    db_path: Optional[str] = None,
    revision: int = 1,
) -> Dict[str, Any]:
    """Claim 生命周期边校验 + 审计（不写 Claim 表；供诊断/纯边探针）。

    Args:
        from_status / to_status: 边。
        actor / reason: 人因。
        claim_id: Claim ID。
        tenant_id: 租户。
        db_path: 审计库。
        revision: 新修订号。
    """
    _assert_transition_allowed("claim_status", from_status, to_status)
    return _record_audit(
        tenant_id=tenant_id,
        record_kind="claim",
        record_id=claim_id,
        machine="claim_status",
        from_state=from_status,
        to_state=to_status,
        actor=actor,
        reason=reason,
        revision=revision,
        db_path=db_path,
    )


async def transition_claim_status(
    ledger: Any,
    *,
    claim_id: str,
    tenant_id: str,
    to_status: str,
    actor: str,
    reason: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Claim 状态写路径：读当前态 → 合法边 → 审计 → ``put_claim`` 写回。

    Args:
        ledger: FactLedger。
        claim_id: Claim ID。
        tenant_id: 租户。
        to_status: 目标 Claim ``status``。
        actor: 操作人。
        reason: 理由。
        db_path: 审计库路径。

    Returns:
        ``claim`` + ``transition``；``certified`` 不在此回执宣称。

    Raises:
        FactStateMachineError: Claim 缺失或非法边。
    """
    claim = await ledger.get_claim(claim_id, tenant_id=tenant_id)
    if claim is None:
        raise FactStateMachineError(f"claim not found: {claim_id}")
    from_state = str(claim.get("status") or "")
    to_s = (to_status or "").strip()
    _assert_transition_allowed("claim_status", from_state, to_s)
    new_rev = int(claim.get("revision") or 1) + 1
    audit = _record_audit(
        tenant_id=tenant_id,
        record_kind="claim",
        record_id=claim_id,
        machine="claim_status",
        from_state=from_state,
        to_state=to_s,
        actor=actor,
        reason=reason,
        revision=new_rev,
        db_path=db_path,
    )
    # 为什么关硬门：边已在外层校验；避免「改状态须走 transition」自锁
    updated = await ledger.put_claim(
        tenant_id=tenant_id,
        collection_id=claim["collection_id"],
        text=claim["text"],
        evidence=list(claim.get("evidence") or []),
        source_policy=claim["source_policy"],
        extractor_version=claim["extractor_version"],
        review_status=str(claim.get("review_status") or "draft"),
        confidence=float(claim.get("confidence") or 0.0),
        domain_id=claim.get("domain_id") or "",
        claim_id=claim_id,
        status=to_s,
        valid_from=claim.get("valid_from"),
        valid_to=claim.get("valid_to"),
        revision=new_rev,
        conflict_key=str(claim.get("conflict_key") or ""),
        enforce_write_gates=False,
        revision_actor=actor,
        revision_reason=reason,
    )
    return {"claim": updated, "transition": audit}


_N03_CLAIM_STATUS_WRITE_CASES = (
    "accepted_to_contested_persisted",
    "illegal_edge_rejected",
    "actor_reason_required",
    "audit_recorded",
)


async def run_claim_status_write_suite(
    *,
    ledger: Any = None,
    tenant_id: str = "n03-claim-status-tenant",
    domain_id: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """N03 Claim 状态写路径加深套件（合法边写回 + 非法边拒 + 审计）。

    Args:
        ledger: 可选 FactLedger；默认临时目录。
        tenant_id: 写入租户。
        domain_id: 可选域（调用方传入）。
        db_path: 状态机审计库；默认临时文件。

    Returns:
        套件汇总；``certified`` / ``n03_full_conformance`` 恒 false。
    """
    import tempfile

    from core.harness.knowledge_pipeline.fact_ledger import FactLedger

    own = ledger is None
    tmp: Optional[tempfile.TemporaryDirectory] = None
    orphan_audit: Optional[str] = None
    if own:
        tmp = tempfile.TemporaryDirectory(prefix="n03-claim-status-write-")
        root = Path(tmp.name)
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
        )
        await lg.initialize()
        audit_db = str(root / "fact_state.sqlite3")
    else:
        lg = ledger
        await lg.initialize()
        if db_path:
            audit_db = db_path
        else:
            orphan_audit = str(
                Path(tempfile.mkdtemp(prefix="n03-claim-status-aud-"))
                / "fact_state.sqlite3"
            )
            audit_db = orphan_audit

    cases: List[Dict[str, Any]] = []
    try:
        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n03-claim-status",
            kind="file",
            uri="file://n03/claim-status.txt",
            content=b"n03-claim-status",
            connector="n03",
            domain_id=domain_id,
        )
        evidence = [
            {
                "source_id": src["source_id"],
                "locator": "extract",
                "quote": "n03-status",
                "fetched_at": src["fetched_at"],
            }
        ]
        claim = await lg.put_claim(
            tenant_id=tenant_id,
            collection_id="n03-claim-status",
            text="door is locked",
            evidence=evidence,
            source_policy="n03_policy",
            extractor_version="n03",
            review_status="published",
            confidence=0.8,
            domain_id=domain_id,
            status="accepted",
        )
        cid = claim["claim_id"]

        mid = await transition_claim_status(
            lg,
            claim_id=cid,
            tenant_id=tenant_id,
            to_status="contested",
            actor="reviewer-1",
            reason="peer conflict",
            db_path=audit_db,
        )
        roundtrip = await lg.get_claim(cid, tenant_id=tenant_id)
        persist_ok = (
            mid["claim"].get("status") == "contested"
            and roundtrip is not None
            and roundtrip.get("status") == "contested"
            and int(mid["claim"].get("revision") or 0)
            > int(claim.get("revision") or 1)
            and mid.get("transition", {}).get("machine") == "claim_status"
        )
        cases.append(
            {
                "id": "accepted_to_contested_persisted",
                "ok": persist_ok,
                "detail": "" if persist_ok else "write_or_persist_failed",
            }
        )

        # archived 终态不可回到 accepted
        archived_claim = await lg.put_claim(
            tenant_id=tenant_id,
            collection_id="n03-claim-status",
            text="archived claim",
            evidence=evidence,
            source_policy="n03_policy",
            extractor_version="n03",
            review_status="published",
            confidence=0.5,
            domain_id=domain_id,
            status="archived",
        )
        illegal_ok = False
        try:
            await transition_claim_status(
                lg,
                claim_id=archived_claim["claim_id"],
                tenant_id=tenant_id,
                to_status="accepted",
                actor="reviewer-1",
                reason="illegal reopen",
                db_path=audit_db,
            )
        except FactStateMachineError:
            illegal_ok = True
        cases.append(
            {
                "id": "illegal_edge_rejected",
                "ok": illegal_ok,
                "detail": "" if illegal_ok else "illegal_edge_accepted",
            }
        )

        actor_ok = False
        claim2 = await lg.put_claim(
            tenant_id=tenant_id,
            collection_id="n03-claim-status",
            text="window is open",
            evidence=evidence,
            source_policy="n03_policy",
            extractor_version="n03",
            review_status="published",
            confidence=0.7,
            domain_id=domain_id,
            status="accepted",
        )
        try:
            await transition_claim_status(
                lg,
                claim_id=claim2["claim_id"],
                tenant_id=tenant_id,
                to_status="contested",
                actor="",
                reason="missing actor",
                db_path=audit_db,
            )
        except FactStateMachineError:
            actor_ok = True
        cases.append(
            {
                "id": "actor_reason_required",
                "ok": actor_ok,
                "detail": "" if actor_ok else "empty_actor_accepted",
            }
        )

        audits = list_fact_transitions(
            tenant_id=tenant_id,
            record_id=cid,
            machine="claim_status",
            db_path=audit_db,
        )
        audit_ok = len(audits) >= 1 and all(
            a.get("actor") and a.get("reason") for a in audits
        )
        cases.append(
            {
                "id": "audit_recorded",
                "ok": audit_ok,
                "detail": "" if audit_ok else "audit_missing",
            }
        )
    finally:
        if tmp is not None:
            tmp.cleanup()
        if orphan_audit is not None:
            try:
                Path(orphan_audit).unlink(missing_ok=True)
                Path(orphan_audit).parent.rmdir()
            except OSError:  # noqa: best-effort temp audit cleanup
                pass

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N03_CLAIM_STATUS_WRITE_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "claim_status_write",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n03_full_conformance": False,
        "note": (
            "Claim status write path (put_claim + audit); "
            "not full Claim lifecycle product / not N03 certified"
        ),
    }


def evaluate_claim_status_write_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N03 Claim 状态写路径门槛门；certified 恒 false。

    Args:
        suite: ``run_claim_status_write_suite`` 回执。

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
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "claim_status_write",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n03_full_conformance": False,
        "note": "Claim status write deepen; not N03 certified",
    }


def evaluate_fact_state_gate(
    *,
    checks: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """N12 门槛门：结构检查通过 ≠ 全量认证。

    Args:
        checks: 各探针布尔结果；缺省视为未跑。
    """
    required = [
        "review_edges",
        "lifecycle_edges",
        "claim_edges",
        "actor_reason_audit",
        "skip_review_forbidden",
        "retracted_not_deleted",
    ]
    issues: List[str] = []
    if not checks:
        issues.append("suite_not_run")
    else:
        for key in required:
            if not checks.get(key):
                issues.append(f"case_failed:{key}")
    return {
        "pass": len(issues) == 0,
        "issues": issues,
        "required": required,
        # 为什么恒 false：最小切片 ≠ 全写入路径强制 / 全量认证
        "certified": False,
        "n12_full_conformance": False,
    }


def dump_machines() -> Dict[str, Any]:
    """导出状态机表（供诊断/HTTP）。

    Returns:
        三机边集（list 化）。
    """
    return {
        name: {k: sorted(v) for k, v in table.items()}
        for name, table in MACHINES.items()
    }
