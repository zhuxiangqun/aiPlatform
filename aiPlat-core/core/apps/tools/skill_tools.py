"""
Skill discovery/load tools (OpenCode find-skills style).

These tools are intentionally "metadata-first":
- `skill_find` returns only an index (name/description/metadata) and never returns full SOP by default.
- `skill_load` loads the SOP body (SKILL.md) on-demand.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from ...harness.interfaces import ToolConfig, ToolResult
from core.apps.skills.registry import get_skill_registry
from .base import BaseTool


def _load_permission_rules() -> Dict[str, str]:
    """
    Read OpenCode-style permission rules for skills from env.

    Example:
      AIPLAT_SKILL_PERMISSION_RULES='{"*":"allow","internal-*":"deny","experimental-*":"ask"}'
    """
    raw = (os.getenv("AIPLAT_SKILL_PERMISSION_RULES") or "").strip()
    if not raw:
        return {"*": "allow"}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            out: Dict[str, str] = {}
            for k, v in data.items():
                if not isinstance(k, str):
                    continue
                s = str(v).strip().lower()
                if s not in {"allow", "deny", "ask"}:
                    continue
                out[k.strip()] = s
            return out or {"*": "allow"}
    except Exception:
        pass
    return {"*": "allow"}


def resolve_skill_permission(skill_name: str) -> str:
    """
    Returns: allow | deny | ask

    Note: this function is also used by PolicyGate to decide whether `skill_load`
    requires approval.
    """
    name = str(skill_name or "").strip()
    if not name:
        return "deny"
    rules = _load_permission_rules()
    # Deterministic: choose the most specific pattern (longest) that matches.
    matched: List[tuple[int, str]] = []
    for pat, decision in rules.items():
        try:
            if fnmatch.fnmatch(name, pat):
                matched.append((len(pat), decision))
        except Exception:
            continue
    if not matched:
        return "allow"
    matched.sort(key=lambda x: x[0], reverse=True)
    return matched[0][1]


def _load_exec_skill_permission_rules() -> Dict[str, str]:
    """
    Executable-skill permission rules (separate from skill_load).

    Example:
      AIPLAT_EXEC_SKILL_PERMISSION_RULES='{"*":"ask","trusted-*":"allow","danger-*":"deny"}'
    Default: ask (safer) because executable skills can have side effects.
    """
    raw = (os.getenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES") or "").strip()
    if not raw:
        return {"*": "ask"}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            out: Dict[str, str] = {}
            for k, v in data.items():
                if not isinstance(k, str):
                    continue
                s = str(v).strip().lower()
                if s not in {"allow", "deny", "ask"}:
                    continue
                out[k.strip()] = s
            return out or {"*": "ask"}
    except Exception:
        pass
    return {"*": "ask"}


def resolve_executable_skill_permission(skill_name: str) -> str:
    """
    Returns: allow | deny | ask
    """
    name = str(skill_name or "").strip()
    if not name:
        return "deny"
    rules = _load_exec_skill_permission_rules()
    matched: List[tuple[int, str]] = []
    for pat, decision in rules.items():
        try:
            if fnmatch.fnmatch(name, pat):
                matched.append((len(pat), decision))
        except Exception:
            continue
    if not matched:
        return "ask"
    matched.sort(key=lambda x: x[0], reverse=True)
    return matched[0][1]


class SkillFindTool(BaseTool):
    """
    搜索/列出可用技能（目录化 SKILL.md 与内置技能统一视图）。

    - 默认仅返回摘要（name/description/kind/version/category），不返回 SOP 正文
    - 会过滤掉 permission=deny 的技能
    """

    def __init__(self):
        config = ToolConfig(
            name="skill_find",
            description="搜索/列出可用技能（返回摘要索引，不返回 SOP 正文）",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键字（匹配 name/description/metadata）"},
                    "name": {"type": "string", "description": "精确查询某个技能名（优先）"},
                    "kind": {"type": "string", "description": "过滤：rule|executable", "enum": ["rule", "executable"]},
                    "category": {"type": "string", "description": "过滤：分类（metadata.category）"},
                    "limit": {"type": "integer", "description": "返回条数上限（默认 20）"},
                    "include_metadata": {"type": "boolean", "description": "是否返回 metadata（默认 true）"},
                },
            },
            metadata={"category": "skills", "risk_level": "safe", "risk_weight": 1},
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        async def handler() -> ToolResult:
            reg = get_skill_registry()
            name = str(params.get("name") or "").strip()
            query = str(params.get("query") or "").strip().lower()
            kind = str(params.get("kind") or "").strip().lower()
            category = str(params.get("category") or "").strip().lower()
            limit = int(params.get("limit") or 20)
            include_metadata = bool(params.get("include_metadata", True))
            limit = max(1, min(limit, 200))

            def _match(text: str) -> bool:
                return (not query) or (query in (text or "").lower())

            def _extract_item(skill_name: str) -> Optional[Dict[str, Any]]:
                s = reg.get(skill_name)
                if not s:
                    return None
                cfg = s.get_config()
                meta = dict(getattr(cfg, "metadata", {}) or {}) if hasattr(cfg, "metadata") else {}
                # Permission filter for discovery: deny -> hidden
                if resolve_skill_permission(skill_name) == "deny":
                    return None
                skind = str(meta.get("skill_kind") or meta.get("kind") or "").strip().lower() or "rule"
                if kind and skind != kind:
                    return None
                cat = str(meta.get("category") or "").strip().lower()
                if category and cat != category:
                    return None
                desc = str(getattr(cfg, "description", "") or "")
                meta_s = ""
                try:
                    meta_s = json.dumps(meta, ensure_ascii=False, sort_keys=True)
                except Exception:
                    meta_s = str(meta)
                if not (_match(skill_name) or _match(desc) or _match(meta_s)):
                    return None
                out: Dict[str, Any] = {
                    "name": cfg.name,
                    "description": desc[:1024],
                    "kind": skind,
                    "version": str(meta.get("version") or ""),
                    "category": str(meta.get("category") or ""),
                }
                if include_metadata:
                    # Strip big fields
                    meta2 = dict(meta)
                    for k in ["sop_markdown", "sop", "body", "content"]:
                        if k in meta2:
                            meta2.pop(k, None)
                    out["metadata"] = meta2
                return out

            if name:
                item = _extract_item(name)
                items = [item] if item else []
                return ToolResult(success=True, output={"items": items, "total": len(items)})

            results: List[Dict[str, Any]] = []
            for skill_name in reg.list_skills():
                item = _extract_item(skill_name)
                if item:
                    results.append(item)
                if len(results) >= limit:
                    break
            return ToolResult(success=True, output={"items": results, "total": len(results)})

        return await self._call_with_tracking(params, handler, timeout=10)


class SkillLoadTool(BaseTool):
    """
    按需加载规则型技能（SKILL.md 的 SOP 正文）。

    注意：
    - 该工具主要服务于“规则型 Skill（Rule Skill）”
    - 可执行型 Skill 应走 skill_execute / sys_skill_call（并受更严格治理）
    """

    def __init__(self):
        config = ToolConfig(
            name="skill_load",
            description="按需加载某个技能的 SOP 正文（SKILL.md body），用于注入/参考",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名（必填）"},
                    "max_chars": {"type": "integer", "description": "返回正文最大字符数（可选）"},
                },
                "required": ["name"],
            },
            metadata={"category": "skills", "risk_level": "safe", "risk_weight": 5},
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        async def handler() -> ToolResult:
            reg = get_skill_registry()
            name = str(params.get("name") or "").strip()
            if not name:
                return ToolResult(success=False, error="name_required")

            # permission=deny should be hidden/blocked
            perm = resolve_skill_permission(name)
            if perm == "deny":
                return ToolResult(success=False, error="skill_denied")

            s = reg.get(name)
            if not s:
                return ToolResult(success=False, error=f"skill_not_found:{name}")
            cfg = s.get_config()
            meta = dict(getattr(cfg, "metadata", {}) or {}) if hasattr(cfg, "metadata") else {}
            sop = str(meta.get("sop_markdown") or "")

            # enforce max chars budget
            env_max = int(os.getenv("AIPLAT_SKILL_SOP_MAX_CHARS", "8000") or "8000")
            req_max = params.get("max_chars")
            try:
                req_max_i = int(req_max) if req_max is not None else 0
            except Exception:
                req_max_i = 0
            max_chars = env_max
            if req_max_i > 0:
                max_chars = min(max_chars, req_max_i)
            max_chars = max(256, min(max_chars, 200000))

            truncated = False
            if max_chars > 0 and len(sop) > max_chars:
                sop = sop[: max(0, max_chars - 16)] + " …(truncated)"
                truncated = True

            h = hashlib.sha256(sop.encode("utf-8")).hexdigest()
            out = {
                "name": cfg.name,
                "kind": str(meta.get("skill_kind") or meta.get("kind") or "rule"),
                "version": str(meta.get("version") or ""),
                "hash": h,
                "truncated": truncated,
                "sop_markdown": sop,
            }
            return ToolResult(success=True, output=out)

        return await self._call_with_tracking(params, handler, timeout=10)
