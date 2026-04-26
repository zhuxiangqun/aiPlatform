from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Request


def permission_detail(p: str) -> Dict[str, Any]:
    """Centralized permission explanation model for wizard UX."""
    pl = (p or "").strip().lower()
    detail: Dict[str, Any] = {
        "permission": str(p),
        "risk_level": "low",
        "category": "llm",
        "description": "",
        "suggestions": [],
        "implied_operations": [],
    }
    if not pl:
        return detail

    if pl == "llm:generate":
        detail["risk_level"] = "low"
        detail["category"] = "llm"
        detail["description"] = "模型生成能力（常规）。"
        detail["suggestions"] = ["确保输出契约包含 markdown；避免编造不确定内容。"]
        return detail

    if pl in ("tool:websearch", "tool:webfetch") or "websearch" in pl or "webfetch" in pl:
        detail["risk_level"] = "medium"
        detail["category"] = "network"
        detail["description"] = "联网搜索/抓取外部内容。"
        detail["suggestions"] = ["在输出中附带 sources，并在 markdown 中引用；标注时间/范围，避免幻觉。"]
        detail["implied_operations"] = ["tool:web"]
        return detail

    if pl in ("tool:run_command",):
        detail["risk_level"] = "high"
        detail["category"] = "execution"
        detail["description"] = "执行命令（高风险）。"
        detail["suggestions"] = ["优先使用更窄的专用工具/脚本替代通用命令执行；启用二次确认与审计；限制可执行命令范围。"]
        detail["implied_operations"] = ["tool:file_operations", "tool:code"]
        return detail

    if pl in ("tool:workspace_fs_write", "tool:file_operations", "tool:workspace_write"):
        detail["risk_level"] = "high"
        detail["category"] = "filesystem"
        detail["description"] = "写入/修改文件（高风险）。"
        detail["suggestions"] = ["限制写入目录与文件类型；启用 require_confirmation=true；保留 revisions 便于回滚。"]
        detail["implied_operations"] = ["tool:file_operations"]
        return detail

    if "database" in pl:
        detail["risk_level"] = "high"
        detail["category"] = "database"
        detail["description"] = "数据库访问/写入（高风险）。"
        detail["suggestions"] = ["默认只读；写入需审批；最小化权限；记录审计日志。"]
        detail["implied_operations"] = ["tool:database"]
        return detail

    if pl.startswith("tool:") or pl.startswith("mcp:"):
        detail["risk_level"] = "medium"
        detail["category"] = "tool"
        detail["description"] = "外部工具/连接器调用。"
        detail["suggestions"] = ["最小权限原则；对外部副作用操作启用二次确认；输出中解释工具调用结果。"]
        detail["implied_operations"] = ["tool:external"]
        return detail

    detail["description"] = "自定义权限。"
    detail["suggestions"] = ["请确认该权限的风险与审批策略，并在 SOP 中说明边界与回滚。"]
    return detail


def permission_catalog(*, scope: str) -> Dict[str, Any]:
    """Predefined permissions catalog for UI. Can be extended/overridden in the future."""
    scope0 = (scope or "workspace").strip().lower()
    base = ["llm:generate", "tool:websearch", "tool:webfetch", "tool:run_command", "tool:workspace_fs_write"]
    items = []
    for p in base:
        d = permission_detail(p)
        items.append(
            {
                "permission": p,
                "label": p,
                "risk_level": d.get("risk_level"),
                "category": d.get("category"),
                "description": d.get("description"),
                "suggestions": d.get("suggestions") or [],
                "implied_operations": d.get("implied_operations") or [],
                "default_selected": True if p == "llm:generate" else False,
            }
        )
    return {"scope": scope0, "items": items, "default_permissions": ["llm:generate"]}


def load_skill_spec_v2_schema() -> Dict[str, Any]:
    try:
        # repo layout: core/api/utils/skills_meta.py -> core/resources/skillSpecV2.schema.json
        p = Path(__file__).resolve().parents[2] / "resources" / "skillSpecV2.schema.json"
        raw = p.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception:
        return {"$schema": "http://json-schema.org/draft-07/schema#", "title": "SkillSpecV2", "type": "object", "properties": {}}


def schema_version(schema_obj: Dict[str, Any]) -> str:
    try:
        raw = json.dumps(schema_obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:12]
    except Exception:
        return "unknown"


def req_tenant_channel(http_request: Optional[Request], *, tenant_id: Optional[str] = None, channel: Optional[str] = None) -> Dict[str, str]:
    # tenant: query param > header > default
    tid = (tenant_id or "").strip()
    if not tid and http_request is not None:
        tid = str(http_request.headers.get("X-AIPLAT-TENANT-ID") or "").strip()
    if not tid:
        tid = "default"

    ch = (channel or "").strip().lower()
    if not ch and http_request is not None:
        ch = str(http_request.headers.get("X-AIPLAT-RELEASE-CHANNEL") or "").strip().lower()
    if ch not in ("stable", "canary"):
        ch = "stable"

    return {"tenant_id": tid, "channel": ch}


def skill_governance_preview(*, scope: str, payload: Dict[str, Any], approval_manager: Any | None = None) -> Dict[str, Any]:
    """
    Governance preview for "product-level wizard" UX.
    Combines:
    - deterministic heuristics (risk_level, confirmation suggestion)
    - server-side approval rules evaluation (ApprovalManager), when available
    """
    scope0 = (scope or "workspace").strip().lower()
    skill_kind = str(payload.get("skill_kind") or payload.get("kind") or "rule").strip().lower()
    perms = payload.get("permissions") or []
    if isinstance(perms, str):
        perms = [x.strip() for x in perms.split(",") if x.strip()]
    if not isinstance(perms, list):
        perms = []
    perms = [str(x).strip() for x in perms if str(x).strip()]
    cfg = payload.get("config") if isinstance(payload.get("config"), dict) else {}

    permission_details = {p: permission_detail(p) for p in perms}

    # ---- risk heuristics (aggregate) ----
    risk = "low"
    reasons: List[str] = []

    def _raise(level: str, reason: str) -> None:
        nonlocal risk
        order = {"low": 0, "medium": 1, "high": 2}
        if order.get(level, 0) > order.get(risk, 0):
            risk = level
        if reason and reason not in reasons:
            reasons.append(reason)

    for p in perms:
        d = permission_details.get(p) or {}
        lv = str(d.get("risk_level") or "low")
        if lv == "high":
            _raise("high", f"包含高风险权限：{p}")
        elif lv == "medium":
            _raise("medium", f"包含中风险权限：{p}")

    if skill_kind == "executable" and not perms:
        _raise("medium", "executable 技能未声明 permissions（建议至少 llm:generate）")

    requires_confirmation = bool(cfg.get("require_confirmation")) or risk == "high"
    confirm_hint = None
    if risk == "high" and not bool(cfg.get("require_confirmation")):
        confirm_hint = "建议在 config 中启用 require_confirmation=true（高风险操作二次确认）"

    # ---- approval manager evaluation (best-effort) ----
    approval = {"required": False, "matched_rule_id": None, "matched_rule_type": None, "matched_rule_name": None, "matched_operations": []}
    try:
        if approval_manager is not None:
            from core.harness.infrastructure.approval.types import ApprovalContext

            ops: List[str] = []
            for p in perms:
                for op in (permission_details.get(p) or {}).get("implied_operations") or []:
                    ops.append(str(op))
            ops = list(dict.fromkeys(ops))
            for op in ops:
                ctx = ApprovalContext(
                    session_id=str(payload.get("session_id") or "wizard"),
                    user_id=str(payload.get("actor_id") or "admin"),
                    operation=str(op),
                    metadata={"tenant_id": payload.get("tenant_id"), "actor_id": payload.get("actor_id")},
                )
                rule = approval_manager.check_approval_required(ctx)
                if rule:
                    approval["required"] = True
                    approval["matched_rule_id"] = rule.rule_id
                    approval["matched_rule_type"] = rule.rule_type.value if getattr(rule, "rule_type", None) else None
                    approval["matched_rule_name"] = rule.name
                    approval["matched_operations"].append(op)
            if approval["required"]:
                _raise("high" if scope0 == "engine" else "medium", "根据审批规则：当前配置可能需要人工审批")
    except Exception:
        pass

    # engine scope is always more conservative
    if scope0 == "engine" and skill_kind == "executable":
        _raise("high", "engine scope + executable：建议启用审批/门控")

    hints: List[str] = []
    if reasons:
        hints.extend(reasons)
    if confirm_hint:
        hints.append(confirm_hint)
    if approval.get("required"):
        hints.append("该配置命中审批规则：建议走审批流程或降低权限范围")

    return {
        "scope": scope0,
        "skill_kind": skill_kind,
        "risk_level": risk,
        "requires_confirmation": requires_confirmation,
        "approval": approval,
        "permission_details": permission_details,
        "recommendations": {"require_confirmation": True if risk == "high" else False, "suggested_min_permissions": ["llm:generate"]},
        "hints": hints[:20],
    }

