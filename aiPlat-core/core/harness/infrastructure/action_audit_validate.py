"""
Action audit_schema validation — register-time checks for ActionContractModel.

Aligned with docs/contracts/FDE_WORKBENCH_CONTRACT.md and
core/harness/schemas/audit_schema.v1.yaml.

Does NOT replace AsyncActionRegistry; call validate_action_contract() from register().
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

# Core audit fields required for customer_action (subset of audit_schema.v1)
CUSTOMER_AUDIT_CORE_FIELDS: Set[str] = {
    "audit_id",
    "timestamp",
    "actor_type",
    "actor_id",
    "action_namespace",
    "action_name",
    "domain_id",
    "target_entity_type",
    "target_entity_id",
    "input_params_hash",
    "before_state_snapshot",
    "after_state_snapshot",
    "result_status",
    "policy_gate_decision",
    "retention",
}

PLATFORM_TRACKING_DOMAINS = frozenset({"fde-delivery", "platform"})


class ActionNamespace(str, Enum):
    CUSTOMER = "customer_action"
    PLATFORM = "platform_action"


def default_audit_schema_path() -> Path:
    return Path(__file__).resolve().parent.parent / "schemas" / "audit_schema.v1.yaml"


@lru_cache(maxsize=4)
def load_audit_schema(path: Optional[str] = None) -> Dict[str, Any]:
    p = Path(path) if path else default_audit_schema_path()
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def eval_gate_ids(schema: Optional[Dict[str, Any]] = None) -> Set[str]:
    sch = schema or load_audit_schema()
    gates = (sch.get("eval_gate") or {}).get("gates") or {}
    return set(gates.keys())


def validate_action_contract(
    *,
    action_id: str,
    action_namespace: str,
    domain_id: str,
    eval_gate: str = "",
    risk_level: str = "low",
    require_approval: bool = False,
    schema: Optional[Dict[str, Any]] = None,
) -> None:
    """Raise ValueError if contract violates audit_schema / FDE workbench rules.

    Legacy contracts with empty action_namespace are skipped (transition period).
    """
    if not action_namespace:
        return

    try:
        ns = ActionNamespace(action_namespace)
    except ValueError as e:
        raise ValueError(
            f"action_namespace must be customer_action|platform_action, got {action_namespace!r}"
        ) from e

    if not action_id.startswith(ns.value + ":"):
        raise ValueError(
            f"action_id {action_id!r} must start with namespace prefix {ns.value}:"
        )

    parts = action_id.split(":")
    if ns == ActionNamespace.CUSTOMER and len(parts) != 3:
        raise ValueError(
            f"customer_action id format must be customer_action:<domain>:<action>, got {action_id}"
        )
    if ns == ActionNamespace.PLATFORM and len(parts) < 3:
        raise ValueError(
            f"platform_action id format must be platform_action:<area>:<action>, got {action_id}"
        )

    if not domain_id:
        raise ValueError(f"Action {action_id} must declare domain_id")

    if ns == ActionNamespace.CUSTOMER and domain_id in PLATFORM_TRACKING_DOMAINS:
        raise ValueError(
            f"客户运营 Action {action_id} 不得使用平台跟踪域 {domain_id}"
        )

    if ns == ActionNamespace.CUSTOMER and risk_level in {"high", "critical"} and not require_approval:
        raise ValueError(
            f"客户运营高风险 Action {action_id} 必须 require_approval=True (HITL)"
        )

    gates = eval_gate_ids(schema)
    if ns == ActionNamespace.CUSTOMER:
        if not eval_gate:
            raise ValueError(f"客户运营 Action {action_id} 必须声明 eval_gate")
        if eval_gate not in gates:
            raise ValueError(f"eval_gate {eval_gate} 未在 audit_schema 中定义")
    elif eval_gate and eval_gate not in gates:
        raise ValueError(f"eval_gate {eval_gate} 未在 audit_schema 中定义")


def hash_params(params: Dict[str, Any]) -> str:
    normalized = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_audit_record(
    *,
    audit_id: str,
    timestamp: str,
    actor_type: str,
    actor_id: str,
    action_namespace: str,
    action_name: str,
    domain_id: str,
    target_entity_type: str,
    target_entity_id: str,
    params: Dict[str, Any],
    before_state_snapshot: Dict[str, Any],
    after_state_snapshot: Dict[str, Any],
    result_status: str,
    policy_gate_decision: Dict[str, Any],
    approver_id: str = "",
    result_message: str = "",
    pipeline_run_id: str = "",
    evidence_ref: str = "",
    rollback_ref: str = "",
    retention: str = "",
) -> Dict[str, Any]:
    """Build an audit_schema.v1 record and validate core fields present."""
    if not retention:
        retention = (
            "permanent"
            if action_namespace == ActionNamespace.CUSTOMER.value
            else "standard"
        )
    record = {
        "audit_id": audit_id,
        "timestamp": timestamp,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "approver_id": approver_id or None,
        "action_namespace": action_namespace,
        "action_name": action_name,
        "domain_id": domain_id,
        "target_entity_type": target_entity_type,
        "target_entity_id": target_entity_id,
        "input_params_hash": hash_params(params),
        "input_params_snapshot": params,
        "before_state_snapshot": before_state_snapshot or {},
        "after_state_snapshot": after_state_snapshot or {},
        "result_status": result_status,
        "result_message": result_message,
        "pipeline_run_id": pipeline_run_id or None,
        "evidence_ref": evidence_ref or None,
        "policy_gate_decision": policy_gate_decision,
        "rollback_ref": rollback_ref or None,
        "retention": retention,
    }
    missing = CUSTOMER_AUDIT_CORE_FIELDS - set(record.keys())
    if missing:
        raise ValueError(f"审计记录缺少字段：{missing}")
    if action_namespace == ActionNamespace.CUSTOMER.value:
        if not record.get("approver_id") and result_status == "success":
            # Soft: caller should set approver for HITL success path
            pass
    return record


def map_audit_to_action_store(record: Dict[str, Any]) -> Dict[str, Any]:
    """Map audit_schema.v1 → ActionStore.insert_audit columns (Phase 1 embed)."""
    return {
        "audit_id": record.get("audit_id"),
        "action_id": record.get("action_name"),
        "entity_id": record.get("target_entity_id", ""),
        "domain_id": record.get("domain_id", ""),
        "from_state": (record.get("before_state_snapshot") or {}).get("status"),
        "to_state": (record.get("after_state_snapshot") or {}).get("status"),
        "actor": record.get("actor_id"),
        "role": record.get("actor_type"),
        "params": {
            "schema": "audit.v1",
            "params_hash": record.get("input_params_hash"),
            "action_namespace": record.get("action_namespace"),
            "approver_id": record.get("approver_id"),
            "redacted": record.get("input_params_snapshot"),
            "pipeline_run_id": record.get("pipeline_run_id"),
            "evidence_ref": record.get("evidence_ref"),
            "policy_gate_decision": record.get("policy_gate_decision"),
            "retention": record.get("retention"),
            "target_entity_type": record.get("target_entity_type"),
        },
        "result_status": record.get("result_status"),
        "effect_summary": record.get("result_message") or "",
        "compensation": record.get("rollback_ref") or "",
        "entity_snapshot": {
            "before": record.get("before_state_snapshot"),
            "after": record.get("after_state_snapshot"),
        },
    }


# ── Phase 1: audit_schema ↔ ActionStore column classification ──────────────

# Physical columns on ActionStore.action_audit (see action_store.initialize)
ACTION_AUDIT_COLUMNS: Set[str] = {
    "audit_id",
    "action_id",
    "entity_id",
    "domain_id",
    "from_state",
    "to_state",
    "actor",
    "role",
    "params",
    "result_status",
    "constraint_type",
    "effect_summary",
    "compensation",
    "entity_snapshot",
    "created_at",
}

# Landing §4.1 — schema field → store strategy
# present = dedicated column; embedded = JSON in params/entity_snapshot; missing = needs ADD COLUMN
_FIELD_STRATEGY: Dict[str, Dict[str, str]] = {
    "audit_id": {"status": "present", "column": "audit_id"},
    "timestamp": {"status": "present", "column": "created_at"},
    "actor_type": {"status": "embedded", "via": "role|params.actor_type"},
    "actor_id": {"status": "present", "column": "actor"},
    "approver_id": {"status": "embedded", "via": "params.approver_id"},
    "action_namespace": {"status": "embedded", "via": "params.action_namespace"},
    "action_name": {"status": "present", "column": "action_id"},
    "domain_id": {"status": "present", "column": "domain_id"},
    "target_entity_type": {"status": "embedded", "via": "params.target_entity_type"},
    "target_entity_id": {"status": "present", "column": "entity_id"},
    "input_params_hash": {"status": "embedded", "via": "params.params_hash"},
    "input_params_snapshot": {"status": "embedded", "via": "params.redacted"},
    "before_state_snapshot": {"status": "embedded", "via": "entity_snapshot.before"},
    "after_state_snapshot": {"status": "embedded", "via": "entity_snapshot.after"},
    "result_status": {"status": "present", "column": "result_status"},
    "result_message": {"status": "present", "column": "effect_summary"},
    "pipeline_run_id": {"status": "embedded", "via": "params.pipeline_run_id"},
    "evidence_ref": {"status": "embedded", "via": "params.evidence_ref"},
    "policy_gate_decision": {"status": "embedded", "via": "params.policy_gate_decision"},
    "rollback_ref": {"status": "embedded", "via": "compensation"},
    "retention": {"status": "embedded", "via": "params.retention"},
}

# Phase 2 candidate ADD COLUMN NULL (only fields still without dedicated column)
PHASE2_ADD_COLUMNS: Dict[str, str] = {
    "action_namespace": "TEXT",
    "approver_id": "TEXT",
    "input_params_hash": "TEXT",
    "pipeline_run_id": "TEXT",
    "target_entity_type": "TEXT",
}


def classify_audit_fields(
    columns: Optional[Set[str]] = None,
    schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, str]]:
    """Classify each audit_schema.v1 field as present / embedded / missing.

    Phase 1 strategy prefers embedded over missing; PHASE2_ADD_COLUMNS are
    reported as embedded (via params) with optional_add_column metadata.
    """
    cols = columns if columns is not None else set(ACTION_AUDIT_COLUMNS)
    sch = schema or load_audit_schema()
    fields = ((sch.get("audit_record") or {}).get("fields") or {})
    out: Dict[str, Dict[str, str]] = {}
    for name in fields:
        strat = _FIELD_STRATEGY.get(name)
        if not strat:
            out[name] = {"status": "missing", "note": "not in Landing §4.1 mapping"}
            continue
        status = strat["status"]
        if status == "present":
            col = strat.get("column", "")
            if col and col not in cols:
                # column expected but not in table → treat as missing with ADD
                out[name] = {
                    "status": "missing",
                    "column": col,
                    "note": f"expected column {col} absent",
                }
            else:
                out[name] = {"status": "present", "column": col}
        else:
            row = {"status": "embedded", "via": strat.get("via", "params")}
            if name in PHASE2_ADD_COLUMNS:
                row["optional_add_column"] = name
                row["sql_type"] = PHASE2_ADD_COLUMNS[name]
            out[name] = row
    return out


def build_add_column_sql(classification: Optional[Dict[str, Dict[str, str]]] = None) -> List[str]:
    """Generate ADD COLUMN NULL statements for Phase 2 optional columns."""
    clf = classification or classify_audit_fields()
    stmts: List[str] = []
    seen: Set[str] = set()
    for name, info in clf.items():
        col = info.get("optional_add_column") or (
            name if info.get("status") == "missing" and name in PHASE2_ADD_COLUMNS else ""
        )
        if not col or col in seen:
            continue
        sql_type = info.get("sql_type") or PHASE2_ADD_COLUMNS.get(col, "TEXT")
        stmts.append(f"ALTER TABLE action_audit ADD COLUMN {col} {sql_type} NULL;")
        seen.add(col)
    return stmts


def build_rollback_sql(add_stmts: Optional[List[str]] = None) -> List[str]:
    """Pair DROP COLUMN rollback for each ADD (SQLite 3.35+)."""
    stmts = add_stmts if add_stmts is not None else build_add_column_sql()
    out: List[str] = []
    for s in stmts:
        # ALTER TABLE action_audit ADD COLUMN foo TEXT NULL;
        parts = s.replace(";", "").split()
        try:
            idx = parts.index("COLUMN")
            col = parts[idx + 1]
        except (ValueError, IndexError):
            continue
        out.append(f"ALTER TABLE action_audit DROP COLUMN {col};")
    return out


def render_mapping_report(
    classification: Optional[Dict[str, Dict[str, str]]] = None,
    *,
    columns: Optional[Set[str]] = None,
) -> str:
    """Markdown report for docs/contracts/audit_mapping_report.md."""
    clf = classification or classify_audit_fields(columns=columns)
    present = [k for k, v in clf.items() if v.get("status") == "present"]
    embedded = [k for k, v in clf.items() if v.get("status") == "embedded"]
    missing = [k for k, v in clf.items() if v.get("status") == "missing"]
    adds = build_add_column_sql(clf)
    rolls = build_rollback_sql(adds)
    lines = [
        "# audit_schema.v1 ↔ ActionStore 映射报告",
        "",
        "| 字段 | 值 |",
        "|------|-----|",
        "| 生成 | Phase 1 dry-run (`scripts/fde_audit_mapping.py`) |",
        f"| present | {len(present)} |",
        f"| embedded | {len(embedded)} |",
        f"| missing | {len(missing)} |",
        "",
        "## 分类明细",
        "",
        "| schema 字段 | 状态 | 落点 / 备注 |",
        "|-------------|------|-------------|",
    ]
    for name, info in sorted(clf.items()):
        note = info.get("column") or info.get("via") or info.get("note") or ""
        if info.get("optional_add_column"):
            note += f" (可选加列 `{info['optional_add_column']}`)"
        lines.append(f"| `{name}` | **{info.get('status')}** | {note} |")
    lines.extend(["", "## Phase 2 可选 ADD COLUMN（全部 NULL）", ""])
    if adds:
        lines.append("```sql")
        lines.extend(adds)
        lines.append("```")
    else:
        lines.append("_无（Phase 1 全部可嵌入）_")
    lines.extend(["", "## 回滚 SQL", ""])
    if rolls:
        lines.append("```sql")
        lines.extend(rolls)
        lines.append("```")
    else:
        lines.append("_无_")
    lines.extend(
        [
            "",
            "## 策略",
            "",
            "- Phase 1：**优先 JSON 嵌入**（`params` / `entity_snapshot`），不改生产表。",
            "- Phase 2：按需加列后可从 embedded 迁到 present；完整率硬门见方案。",
            "",
        ]
    )
    return "\n".join(lines)


def load_change_surface_whitelist(schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Load change_surface_whitelist from audit_schema.v1 (loadable YAML, not hardcode)."""
    sch = schema or load_audit_schema()
    wl = sch.get("change_surface_whitelist") or {}
    return {
        "allowed_keys": list(wl.get("allowed_keys") or []),
        "forbidden_keys": list(wl.get("forbidden_keys") or []),
        "enforcement": dict(wl.get("enforcement") or {}),
    }


def _key_matches(pattern: str, key: str) -> bool:
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return key == prefix or key.startswith(prefix + ".")
    return key == pattern


def check_change_surface(
    keys: List[str],
    schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return {ok, violations, action}. Keys outside whitelist → HITL (on_violation)."""
    wl = load_change_surface_whitelist(schema)
    allowed = wl["allowed_keys"]
    forbidden = wl["forbidden_keys"]
    enforcement = wl["enforcement"]
    violations: List[Dict[str, str]] = []
    for key in keys:
        if any(_key_matches(p, key) for p in forbidden):
            violations.append({"key": key, "reason": "forbidden"})
            continue
        if allowed and not any(_key_matches(p, key) for p in allowed):
            violations.append({"key": key, "reason": "not_in_whitelist"})
    action = enforcement.get("on_violation", "hitl_and_reject")
    return {
        "ok": len(violations) == 0,
        "violations": violations,
        "action": action if violations else "allow",
        "require_hitl": bool(violations),
    }
