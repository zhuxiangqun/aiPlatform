"""
Skill Contract utilities (P0-1).

目标：把 Skill 的“可治理字段”收敛成一份稳定 contract，并生成可回放的 digest。
注意：contract 不包含 SOP 正文（SOP 属于可加载资源，不应进入稳定契约散列）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Tuple


def normalize_permissions(perms: Any) -> List[str]:
    if perms is None:
        return []
    if isinstance(perms, str):
        s = perms.strip()
        return [s] if s else []
    if isinstance(perms, list):
        out: List[str] = []
        for p in perms:
            try:
                s = str(p).strip()
                if s:
                    out.append(s)
            except Exception:
                continue
        return out
    try:
        s = str(perms).strip()
        return [s] if s else []
    except Exception:
        return []


def derive_risk_level(*, permissions: List[str], explicit: str | None = None) -> str:
    e = str(explicit or "").strip().lower()
    if e in {"low", "medium", "high"}:
        return e
    try:
        # reuse linter logic to keep a single source of truth
        from core.management.skill_linter import risk_level_from_permissions

        return str(risk_level_from_permissions(permissions) or "low")
    except Exception:
        # conservative fallback
        if any("write" in p.lower() or "delete" in p.lower() or "exec" in p.lower() for p in (permissions or [])):
            return "high"
        if permissions:
            return "medium"
        return "low"


def build_contract_and_digest(*, name: str, version: str, kind: str, input_schema: Dict[str, Any], output_schema: Dict[str, Any], metadata: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    perms = normalize_permissions(metadata.get("permissions") or metadata.get("permission"))
    risk_level = derive_risk_level(permissions=perms, explicit=metadata.get("risk_level"))

    # Governance defaults (safe by default):
    # - high risk skills should not be auto-triggered unless explicitly allowed
    auto_trigger_allowed = metadata.get("auto_trigger_allowed")
    if auto_trigger_allowed is None:
        auto_trigger_allowed = False if risk_level == "high" else True
    auto_trigger_allowed = bool(auto_trigger_allowed)

    requires_approval = metadata.get("requires_approval")
    if requires_approval is None:
        requires_approval = True if risk_level == "high" else False
    requires_approval = bool(requires_approval)

    contract: Dict[str, Any] = {
        "name": str(name or "").strip(),
        "version": str(version or "").strip(),
        "kind": str(kind or "").strip().lower() or "rule",
        "permissions": perms,
        "risk_level": risk_level,
        "auto_trigger_allowed": auto_trigger_allowed,
        "requires_approval": requires_approval,
        "input_schema": input_schema if isinstance(input_schema, dict) else {},
        "output_schema": output_schema if isinstance(output_schema, dict) else {},
    }

    raw = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return contract, digest

