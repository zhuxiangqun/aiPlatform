"""来源策略与冲突裁决最小切片（附录 K / W3 / N04）。

职责：
  - 登记 Source Policy（authority/freshness/scope/license/trust/conflict_rule）
  - 检测同 subject+predicate 多 object 冲突并显式落库（不自动选边）
  - 人审裁决（actor/reason/accepted_fact_id）
  - publish 前门：未注册策略 / 未裁决冲突 → 拒绝

非目标：
  - 不把 FactLedger 全量改写为唯一写入口（提供 guarded 包装）
  - 不做 conflict_rule 自动选边并发布
  - 不宣称 N04 全量 / 附录 N 认证
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

REQUIRED_POLICY_FIELDS = (
    "authority",
    "freshness",
    "scope",
    "license",
    "trust",
    "conflict_rule",
)

# 为什么不按 Raw>KG>Wiki 硬排：附录 K 禁止固定层序；冲突必须显式裁决
FORBIDDEN_LAYER_ORDER_RULES = frozenset(
    {
        "raw_gt_kg_gt_wiki",
        "raw>kg>wiki",
        "fixed_raw_over_kg",
    }
)


class SourcePolicyError(ValueError):
    """来源策略或冲突裁决契约错误。"""


def _default_db_path() -> str:
    """解析来源策略/冲突库路径（AIPLAT_HOME 约定）。

    Returns:
        SQLite 文件路径。
    """
    env = os.environ.get("AIPLAT_SOURCE_POLICY_DB")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "knowledge_source_policy.sqlite3")
    return "./data/knowledge_source_policy.sqlite3"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """打开/初始化来源策略与冲突表。

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
        CREATE TABLE IF NOT EXISTS source_policies (
            policy_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, policy_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conflicts (
            conflict_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            collection_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            fact_ids_json TEXT NOT NULL,
            objects_json TEXT NOT NULL,
            status TEXT NOT NULL,
            suggestion_json TEXT,
            decision_json TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conflicts_open
        ON conflicts(tenant_id, subject, predicate, status)
        """
    )
    conn.commit()
    return conn


def _validate_policy_payload(payload: Dict[str, Any]) -> None:
    """校验附录 K 必填字段。

    Args:
        payload: 策略正文。

    Raises:
        SourcePolicyError: 缺字段或禁止的固定层序规则。
    """
    for key in REQUIRED_POLICY_FIELDS:
        if key not in payload or payload[key] in (None, "", []):
            raise SourcePolicyError(f"source_policy.{key} required")
    freshness = payload.get("freshness")
    if not isinstance(freshness, dict) or "valid_days" not in freshness:
        raise SourcePolicyError("source_policy.freshness.valid_days required")
    try:
        days = int(freshness["valid_days"])
    except (TypeError, ValueError) as exc:
        raise SourcePolicyError("source_policy.freshness.valid_days must be int") from exc
    if days < 1:
        raise SourcePolicyError("source_policy.freshness.valid_days must be >= 1")
    scope = payload.get("scope")
    if not isinstance(scope, list) or not scope:
        raise SourcePolicyError("source_policy.scope must be non-empty list")
    rule = str(payload.get("conflict_rule") or "").strip().lower()
    if rule in FORBIDDEN_LAYER_ORDER_RULES:
        raise SourcePolicyError(
            "fixed Raw>KG>Wiki layer order is forbidden; use explicit adjudication"
        )


def register_source_policy(
    *,
    tenant_id: str,
    policy_id: str,
    authority: str,
    freshness: Dict[str, Any],
    scope: Sequence[str],
    license: str,
    trust: str,
    conflict_rule: str,
    source_id: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """登记来源策略（附录 K）。

    Args:
        tenant_id: 租户。
        policy_id: 策略 ID（Fact/Claim 的 source_policy 引用）。
        authority: 权威级别。
        freshness: 含 valid_days。
        scope: 适用范围列表。
        license: 许可。
        trust: 可信等级。
        conflict_rule: 冲突处理规则名（不得为固定层序）。
        source_id: 可选绑定来源。
        db_path: 可选库路径。

    Returns:
        已登记策略记录。

    Raises:
        SourcePolicyError: 参数非法。
    """
    tid = (tenant_id or "").strip()
    pid = (policy_id or "").strip()
    if not tid or not pid:
        raise SourcePolicyError("tenant_id and policy_id required")
    payload: Dict[str, Any] = {
        "policy_id": pid,
        "source_id": (source_id or "").strip(),
        "authority": authority,
        "freshness": freshness,
        "scope": list(scope),
        "license": license,
        "trust": trust,
        "conflict_rule": conflict_rule,
    }
    _validate_policy_payload(payload)
    created_at = _utc_now()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO source_policies
            (policy_id, tenant_id, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (pid, tid, json.dumps(payload, ensure_ascii=False), created_at),
        )
        conn.commit()
    return {**payload, "tenant_id": tid, "created_at": created_at}


def get_source_policy(
    policy_id: str,
    *,
    tenant_id: str,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """读取来源策略。

    Args:
        policy_id: 策略 ID。
        tenant_id: 租户。
        db_path: 可选库路径。

    Returns:
        策略记录；不存在则 None。
    """
    tid = (tenant_id or "").strip()
    pid = (policy_id or "").strip()
    if not tid or not pid:
        return None
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT policy_id, tenant_id, payload_json, created_at
            FROM source_policies
            WHERE tenant_id=? AND policy_id=?
            """,
            (tid, pid),
        ).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"] or "{}")
    payload["tenant_id"] = row["tenant_id"]
    payload["policy_id"] = row["policy_id"]
    payload["created_at"] = row["created_at"]
    return payload


def detect_object_conflicts(
    facts: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """纯计算：同 subject+predicate 出现多个不同 object 即冲突候选。

    不自动选边；仅返回冲突组。

    Args:
        facts: Fact 记录列表（需含 subject/predicate/object/fact_id）。

    Returns:
        冲突候选列表（每项含 subject/predicate/fact_ids/objects）。
    """
    groups: Dict[tuple, Dict[str, Any]] = {}
    for fact in facts:
        if (fact.get("status") or "active") != "active":
            continue
        key = (str(fact.get("subject") or ""), str(fact.get("predicate") or ""))
        if not key[0] or not key[1]:
            continue
        bucket = groups.setdefault(
            key,
            {
                "subject": key[0],
                "predicate": key[1],
                "fact_ids": [],
                "objects": set(),
                "by_object": {},
            },
        )
        fid = str(fact.get("fact_id") or "")
        obj = str(fact.get("object") or "")
        if fid:
            bucket["fact_ids"].append(fid)
        bucket["objects"].add(obj)
        bucket["by_object"].setdefault(obj, []).append(fid)
    out: List[Dict[str, Any]] = []
    for bucket in groups.values():
        if len(bucket["objects"]) < 2:
            continue
        out.append(
            {
                "subject": bucket["subject"],
                "predicate": bucket["predicate"],
                "fact_ids": list(bucket["fact_ids"]),
                "objects": sorted(bucket["objects"]),
                "by_object": {
                    k: list(v) for k, v in bucket["by_object"].items()
                },
                # 为什么恒无 winner：禁止自动选边
                "auto_winner": None,
            }
        )
    return out


def _suggest_by_conflict_rule(
    *,
    facts: Sequence[Dict[str, Any]],
    policies: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """按 conflict_rule 给出**建议**（不落库、不发布）。

    仅支持 ``prefer_newer_primary_then_human_review``：按 authority=primary
    优先，再按 recorded_at 新者建议；仍须人审。

    Args:
        facts: 冲突组内 Fact。
        policies: policy_id → 策略。

    Returns:
        建议 dict；无法建议则 None。
    """
    if not facts:
        return None
    ranked: List[tuple] = []
    for fact in facts:
        pol = policies.get(str(fact.get("source_policy") or ""), {})
        authority = str(pol.get("authority") or "").lower()
        primary_boost = 1 if authority == "primary" else 0
        recorded = str(fact.get("recorded_at") or "")
        ranked.append((primary_boost, recorded, str(fact.get("fact_id") or "")))
    ranked.sort(reverse=True)
    if not ranked or not ranked[0][2]:
        return None
    return {
        "suggested_fact_id": ranked[0][2],
        "rule": "prefer_newer_primary_then_human_review",
        "requires_human_review": True,
    }


def record_conflict(
    *,
    tenant_id: str,
    collection_id: str,
    subject: str,
    predicate: str,
    fact_ids: Sequence[str],
    objects: Sequence[str],
    suggestion: Optional[Dict[str, Any]] = None,
    conflict_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """显式记录冲突（open）；不自动选边。

    Args:
        tenant_id: 租户。
        collection_id: 集合。
        subject / predicate: 冲突键。
        fact_ids: 涉事 Fact。
        objects: 冲突取值。
        suggestion: 可选规则建议（非裁决）。
        conflict_id: 可选显式 ID。
        db_path: 可选库路径。

    Returns:
        冲突记录。
    """
    tid = (tenant_id or "").strip()
    cid = (collection_id or "").strip()
    sub = (subject or "").strip()
    pred = (predicate or "").strip()
    if not tid or not cid or not sub or not pred:
        raise SourcePolicyError(
            "tenant_id, collection_id, subject, predicate required"
        )
    if len(set(objects)) < 2:
        raise SourcePolicyError("conflict requires >=2 distinct objects")
    if len(fact_ids) < 2:
        raise SourcePolicyError("conflict requires >=2 fact_ids")
    conf_id = conflict_id or f"cf-{uuid.uuid4().hex[:12]}"
    created_at = _utc_now()
    record = {
        "conflict_id": conf_id,
        "tenant_id": tid,
        "collection_id": cid,
        "subject": sub,
        "predicate": pred,
        "fact_ids": list(fact_ids),
        "objects": list(objects),
        "status": "open",
        "suggestion": suggestion,
        "decision": None,
        "created_at": created_at,
        "resolved_at": None,
    }
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO conflicts (
                conflict_id, tenant_id, collection_id, subject, predicate,
                fact_ids_json, objects_json, status, suggestion_json,
                decision_json, created_at, resolved_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                conf_id,
                tid,
                cid,
                sub,
                pred,
                json.dumps(record["fact_ids"], ensure_ascii=False),
                json.dumps(record["objects"], ensure_ascii=False),
                "open",
                json.dumps(suggestion, ensure_ascii=False) if suggestion else None,
                None,
                created_at,
                None,
            ),
        )
        conn.commit()
    return record


def list_open_conflicts(
    *,
    tenant_id: str,
    subject: Optional[str] = None,
    predicate: Optional[str] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """列出未裁决冲突。

    Args:
        tenant_id: 租户。
        subject: 可选主语过滤。
        predicate: 可选谓词过滤。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        raise SourcePolicyError("tenant_id required")
    clauses = ["tenant_id=?", "status=?"]
    params: List[Any] = [tid, "open"]
    if subject:
        clauses.append("subject=?")
        params.append(subject)
    if predicate:
        clauses.append("predicate=?")
        params.append(predicate)
    sql = f"SELECT * FROM conflicts WHERE {' AND '.join(clauses)} ORDER BY created_at"
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "conflict_id": row["conflict_id"],
                "tenant_id": row["tenant_id"],
                "collection_id": row["collection_id"],
                "subject": row["subject"],
                "predicate": row["predicate"],
                "fact_ids": json.loads(row["fact_ids_json"] or "[]"),
                "objects": json.loads(row["objects_json"] or "[]"),
                "status": row["status"],
                "suggestion": json.loads(row["suggestion_json"])
                if row["suggestion_json"]
                else None,
                "decision": json.loads(row["decision_json"])
                if row["decision_json"]
                else None,
                "created_at": row["created_at"],
                "resolved_at": row["resolved_at"],
            }
        )
    return out


def adjudicate_conflict(
    *,
    conflict_id: str,
    tenant_id: str,
    actor: str,
    reason: str,
    accepted_fact_id: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """人审裁决冲突（写入 decision；status→resolved）。

    Args:
        conflict_id: 冲突 ID。
        tenant_id: 租户。
        actor: 裁决人。
        reason: 裁决理由（可审计）。
        accepted_fact_id: 采纳的 Fact。
        db_path: 可选库路径。

    Returns:
        更新后的冲突记录。

    Raises:
        SourcePolicyError: 冲突不存在或不属于租户 / 参数空。
    """
    tid = (tenant_id or "").strip()
    cid = (conflict_id or "").strip()
    by = (actor or "").strip()
    why = (reason or "").strip()
    accepted = (accepted_fact_id or "").strip()
    if not tid or not cid or not by or not why or not accepted:
        raise SourcePolicyError(
            "conflict_id, tenant_id, actor, reason, accepted_fact_id required"
        )
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM conflicts WHERE conflict_id=? AND tenant_id=?",
            (cid, tid),
        ).fetchone()
        if not row:
            raise SourcePolicyError(f"conflict not found: {cid}")
        fact_ids = json.loads(row["fact_ids_json"] or "[]")
        if accepted not in fact_ids:
            raise SourcePolicyError("accepted_fact_id not in conflict fact_ids")
        resolved_at = _utc_now()
        decision = {
            "by": by,
            "reason": why,
            "accepted_fact_id": accepted,
            "at": resolved_at,
        }
        conn.execute(
            """
            UPDATE conflicts
            SET status=?, decision_json=?, resolved_at=?
            WHERE conflict_id=? AND tenant_id=?
            """,
            (
                "resolved",
                json.dumps(decision, ensure_ascii=False),
                resolved_at,
                cid,
                tid,
            ),
        )
        conn.commit()
    return {
        "conflict_id": cid,
        "tenant_id": tid,
        "collection_id": row["collection_id"],
        "subject": row["subject"],
        "predicate": row["predicate"],
        "fact_ids": fact_ids,
        "objects": json.loads(row["objects_json"] or "[]"),
        "status": "resolved",
        "suggestion": json.loads(row["suggestion_json"])
        if row["suggestion_json"]
        else None,
        "decision": decision,
        "created_at": row["created_at"],
        "resolved_at": resolved_at,
    }


def assert_publish_allowed(
    *,
    tenant_id: str,
    source_policy: str,
    subject: str,
    predicate: str,
    db_path: Optional[str] = None,
) -> None:
    """publish 前门：策略必须已登记，且该键无 open 冲突。

    Args:
        tenant_id: 租户。
        source_policy: 策略 ID。
        subject / predicate: Fact 键。
        db_path: 可选库路径。

    Raises:
        SourcePolicyError: 未注册策略或存在未裁决冲突。
    """
    pol = get_source_policy(source_policy, tenant_id=tenant_id, db_path=db_path)
    if pol is None:
        raise SourcePolicyError(f"unknown source_policy: {source_policy}")
    open_c = list_open_conflicts(
        tenant_id=tenant_id,
        subject=subject,
        predicate=predicate,
        db_path=db_path,
    )
    if open_c:
        ids = ",".join(c["conflict_id"] for c in open_c)
        raise SourcePolicyError(f"unresolved conflicts block publish: {ids}")


async def put_fact_with_source_policy(
    ledger: Any,
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
    db_path: Optional[str] = None,
    actor: str = "",
    reason: str = "",
    role: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """生产写入包装：非 published 走 put_fact 硬门；published 经 transition。

    Args:
        ledger: FactLedger 实例。
        tenant_id / collection_id / subject / predicate / object: Fact 键值。
        evidence: 证据。
        source_policy: 策略 ID。
        extractor_version: 抽取器版本。
        review_status: 审核状态。
        confidence: 置信度。
        db_path: 来源策略库路径。
        actor / reason: ``published`` 时必填（走状态机审计）。
        role: 调用方角色（N04/N12；``published`` 时由状态机校验）。
        **kwargs: 透传 ``put_fact`` 其余参数（含 ``fact_id``）。

    Returns:
        Fact 记录；published 时为 transition 回执中的 fact。

    Raises:
        SourcePolicyError: 策略/冲突门失败或缺少 transition 人因。
    """
    if review_status == "published":
        assert_publish_allowed(
            tenant_id=tenant_id,
            source_policy=source_policy,
            subject=subject,
            predicate=predicate,
            db_path=db_path,
        )
        fid = str(kwargs.get("fact_id") or "").strip()
        act = (actor or "").strip()
        rsn = (reason or "").strip()
        if not fid or not act or not rsn:
            raise SourcePolicyError(
                "published requires fact_id + actor + reason (transition API)"
            )
        from core.harness.knowledge_pipeline.fact_state_machine import (
            transition_fact_review,
        )

        # 先落内容（保持现有 review），再按边推进到 published
        current = await ledger.get_fact(fid, tenant_id=tenant_id)
        if current is None:
            raise SourcePolicyError(f"fact not found for publish: {fid}")
        extra = {k: v for k, v in kwargs.items() if k != "fact_id"}
        keep_rs = str(current.get("review_status") or "draft")
        keep_st = str(current.get("status") or "active")
        # 为什么：N24 内容变更须抬 revision；相等则 put_fact 幂等返回
        proposed = {
            **current,
            "subject": subject,
            "predicate": predicate,
            "object": object,
            "evidence": evidence,
            "source_policy": source_policy,
            "extractor_version": extractor_version,
            "review_status": keep_rs,
            "confidence": float(confidence),
            "status": keep_st,
        }
        rev = int(current.get("revision") or 1)
        if not ledger._fact_content_equal(current, proposed):
            rev += 1
        await ledger.put_fact(
            tenant_id=tenant_id,
            collection_id=collection_id,
            subject=subject,
            predicate=predicate,
            object=object,
            evidence=evidence,
            source_policy=source_policy,
            extractor_version=extractor_version,
            review_status=keep_rs,
            confidence=confidence,
            source_policy_db_path=db_path,
            fact_id=fid,
            status=keep_st,
            inferred=bool(current.get("inferred")),
            valid_from=current.get("valid_from"),
            valid_to=current.get("valid_to"),
            revision=rev,
            revision_actor=act,
            revision_reason=rsn,
            domain_id=str(
                current.get("domain_id") or extra.pop("domain_id", "") or ""
            ),
            **extra,
        )
        cur_rs = str(current.get("review_status") or "draft")
        if cur_rs == "draft":
            await transition_fact_review(
                ledger,
                fact_id=fid,
                tenant_id=tenant_id,
                to_status="reviewed",
                actor=act,
                reason=rsn,
                source_policy_db_path=db_path,
                role=role,
            )
        elif cur_rs not in {"reviewed", "published"}:
            raise SourcePolicyError(
                f"cannot publish from review_status={cur_rs!r}"
            )
        out = await transition_fact_review(
            ledger,
            fact_id=fid,
            tenant_id=tenant_id,
            to_status="published",
            actor=act,
            reason=rsn,
            source_policy_db_path=db_path,
            role=role,
        )
        return out["fact"]

    return await ledger.put_fact(
        tenant_id=tenant_id,
        collection_id=collection_id,
        subject=subject,
        predicate=predicate,
        object=object,
        evidence=evidence,
        source_policy=source_policy,
        extractor_version=extractor_version,
        review_status=review_status,
        confidence=confidence,
        source_policy_db_path=db_path,
        **kwargs,
    )


async def scan_and_record_conflicts(
    ledger: Any,
    *,
    tenant_id: str,
    collection_id: str,
    subject: Optional[str] = None,
    predicate: Optional[str] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """从 FactLedger 扫描并落库冲突（不自动选边）。

    Args:
        ledger: FactLedger。
        tenant_id: 租户。
        collection_id: 集合。
        subject / predicate: 可选过滤。
        db_path: 策略库路径。

    Returns:
        新记录或已存在的 open 冲突列表。
    """
    facts = await ledger.query_facts(
        tenant_id=tenant_id,
        collection_id=collection_id,
        subject=subject,
        predicate=predicate,
    )
    candidates = detect_object_conflicts(facts)
    recorded: List[Dict[str, Any]] = []
    for cand in candidates:
        existing = list_open_conflicts(
            tenant_id=tenant_id,
            subject=cand["subject"],
            predicate=cand["predicate"],
            db_path=db_path,
        )
        if existing:
            recorded.extend(existing)
            continue
        group_facts = [
            f
            for f in facts
            if f.get("subject") == cand["subject"]
            and f.get("predicate") == cand["predicate"]
        ]
        policies: Dict[str, Dict[str, Any]] = {}
        for f in group_facts:
            pid = str(f.get("source_policy") or "")
            if pid and pid not in policies:
                pol = get_source_policy(pid, tenant_id=tenant_id, db_path=db_path)
                if pol:
                    policies[pid] = pol
        suggestion = _suggest_by_conflict_rule(facts=group_facts, policies=policies)
        recorded.append(
            record_conflict(
                tenant_id=tenant_id,
                collection_id=collection_id,
                subject=cand["subject"],
                predicate=cand["predicate"],
                fact_ids=cand["fact_ids"],
                objects=cand["objects"],
                suggestion=suggestion,
                db_path=db_path,
            )
        )
    return recorded


def evaluate_source_policy_gate(
    *,
    checks: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """N04 门槛门：结构检查通过 ≠ 全量认证。

    Args:
        checks: 各探针布尔结果；缺省视为未跑。

    Returns:
        gate 结果；``certified`` / ``n04_full_conformance`` 恒 false。
    """
    required = [
        "policy_register",
        "conflict_detect_no_autopick",
        "adjudicate_with_reason",
        "publish_blocked_when_open",
        "forbid_fixed_layer_order",
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
        # 为什么恒 false：最小切片 ≠ 生产全路径/全量认证
        "certified": False,
        "n04_full_conformance": False,
    }
