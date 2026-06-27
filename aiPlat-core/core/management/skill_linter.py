"""
Skill Linter (system-level) — facade.

Architecture:
  - lint_skill()  → delegates to RuleRegistry (skill_linter_base.py)
  - Simple checks → YAML config (lint_rules.yaml) → YAMLRule
  - Complex checks → Python classes (lint_rules/*.py) → LintRule subclass

Adding a new rule:
  - Simple: add 5 lines to lint_rules.yaml, zero code change
  - Complex: create a class in lint_rules/, auto-discovered

This module retains helper functions (risk_level_from_permissions, lint_summary,
propose_skill_fixes) for backward compatibility with existing API callers.
"""

from __future__ import annotations
import logging

import re
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional


@dataclass
class LintIssue:
    level: str  # error|warning
    code: str
    message: str
    location: Optional[str] = None


@dataclass
class LintReport:
    skill_id: str
    risk_level: str  # low|medium|high
    blocked: bool
    errors: List[LintIssue] = field(default_factory=list)
    warnings: List[LintIssue] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["errors"] = [asdict(x) for x in self.errors]
        d["warnings"] = [asdict(x) for x in self.warnings]
        d["summary"] = {
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "risk_level": self.risk_level,
            "blocked": self.blocked,
        }
        return d


def _as_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, str):
        s = x.strip()
        return [s] if s else []
    if isinstance(x, list):
        out: List[str] = []
        for it in x:
            try:
                s = str(it).strip()
                if s:
                    out.append(s)
            except Exception:
                continue
        return out


def _norm_text(s: str) -> str:
    s0 = str(s or "").strip().lower()
    s0 = re.sub(r"[\s\-\._/]+", " ", s0)
    s0 = re.sub(r"[^\w\u4e00-\u9fff ]+", "", s0)
    return s0.strip()


def _token_set_for_conflict(*, triggers: List[str], keywords: Dict[str, Any], negative_triggers: List[str]) -> set:
    toks: set = set()
    for it in (triggers or []):
        s = _norm_text(str(it))
        if s:
            toks.add(s)
            for w in s.split():
                if len(w) >= 2:
                    toks.add(w)
    kw = keywords if isinstance(keywords, dict) else {}
    for k in ("objects", "actions", "constraints", "synonyms"):
        for it in (kw.get(k) or []) if isinstance(kw.get(k), list) else []:
            s = _norm_text(str(it))
            if s:
                toks.add(s)
    for it in (negative_triggers or []):
        s = _norm_text(str(it))
        if s:
            toks.add(s)
    return toks


def risk_level_from_permissions(perms: List[str]) -> str:
    # Re-export from base to avoid circular imports
    from core.management.skill_linter_base import risk_level_from_permissions as _rlp
    return _rlp(perms)


def _read_skill_md_body(skill: Any) -> str:
    """
    Best-effort: read SKILL.md body via skill.metadata.filesystem.skill_md.
    Returns empty string when unavailable.
    """
    try:
        meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else (skill.get("metadata") if isinstance(skill.get("metadata"), dict) else {})
        fs = meta.get("filesystem") if isinstance(meta, dict) and isinstance(meta.get("filesystem"), dict) else {}
        p = fs.get("skill_md")
        if not p:
            return ""
        from pathlib import Path

        raw = Path(str(p)).read_text(encoding="utf-8")
        # split front matter if present
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                return (parts[2] or "").strip()
        return raw.strip()
    except Exception:
        return ""


def lint_skill(skill: Any) -> Dict[str, Any]:
    """
    Lint a SkillInfo-like object (from SkillManager) or a dict with similar keys.
    Returns dict(report).

    Delegates to extensible RuleRegistry. Add new rules via:
      - lint_rules.yaml (declarative, 5 lines each)
      - lint_rules/*.py (complex logic, auto-discovered)
    """
    from core.management.skill_linter_base import get_registry
    return get_registry().run_all(skill).to_dict()


def lint_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(report, dict):
        return {"risk_level": "low", "error_count": 0, "warning_count": 0, "blocked": False}
    s = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if s:
        return {
            "risk_level": s.get("risk_level") or report.get("risk_level") or "low",
            "error_count": int(s.get("error_count") or len(report.get("errors") or [])),
            "warning_count": int(s.get("warning_count") or len(report.get("warnings") or [])),
            "blocked": bool(s.get("blocked") if s.get("blocked") is not None else report.get("blocked")),
        }
    return {
        "risk_level": report.get("risk_level") or "low",
        "error_count": len(report.get("errors") or []),
        "warning_count": len(report.get("warnings") or []),
        "blocked": bool(report.get("blocked")),
    }


# ---------------------------------------------------------------------
# Fix Proposals (Phase 1) - deterministic, safe-by-default
# ---------------------------------------------------------------------


def _yaml_like(obj: Any, indent: int = 0) -> str:
    """
    A tiny YAML-like serializer for preview snippets.
    - stable ordering not guaranteed, but ok for previews
    - only supports dict/list/primitive
    """
    sp = "  " * indent
    if isinstance(obj, dict):
        lines: List[str] = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{sp}{k}:")
                lines.append(_yaml_like(v, indent + 1))
            else:
                vv = "null" if v is None else str(v)
                lines.append(f"{sp}{k}: {vv}")
        return "\n".join(lines)
    if isinstance(obj, list):
        lines = []
        for it in obj:
            if isinstance(it, (dict, list)):
                lines.append(f"{sp}-")
                lines.append(_yaml_like(it, indent + 1))
            else:
                lines.append(f"{sp}- {it}")
        return "\n".join(lines)
    return f"{sp}{obj}"


def _standard_markdown_schema() -> Dict[str, Any]:
    return {"type": "string", "required": True, "description": "面向人阅读的 Markdown 输出，与结构化字段一致"}


def _standard_change_contract_schema() -> Dict[str, Dict[str, Any]]:
    """
    Output contract fields for coding/executable skills.
    Keep it simple and machine-checkable.
    """
    return {
        "change_plan": {"type": "string", "required": True, "description": "变更计划：做什么/不做什么/风险点"},
        "changed_files": {"type": "array", "required": True, "description": "本次改动涉及的文件列表（路径）"},
        "unrelated_changes": {"type": "boolean", "required": True, "description": "是否包含无关改动（必须为 false；如为 true 需解释原因）"},
        "acceptance_criteria": {"type": "array", "required": True, "description": "验收标准/验证步骤（测试用例/复现步骤/检查清单）"},
        "rollback_plan": {"type": "string", "required": True, "description": "回滚策略（如何撤销/恢复）"},
    }


def propose_skill_fixes(*, skill: Any, lint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate deterministic fix proposals based on lint results.

    Output contract (Phase 1):
      {
        "skill_id": str,
        "scope": "engine"|"workspace"|"unknown",
        "fixes": [ ... ],
        "summary": { ... }
      }
    """
    sid = str(getattr(skill, "id", "") or (skill.get("id") if isinstance(skill, dict) else "") or "").strip() or "<unknown>"
    meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
    meta = meta if isinstance(meta, dict) else {}
    desc = str(getattr(skill, "description", "") or (skill.get("description") if isinstance(skill, dict) else "") or "").strip()
    scope = str(meta.get("scope") or meta.get("skill_scope") or meta.get("source_scope") or "").strip().lower() or "unknown"
    if scope not in {"engine", "workspace"}:
        # best-effort: infer from filesystem path
        try:
            fs = meta.get("filesystem") if isinstance(meta.get("filesystem"), dict) else {}
            p = str(fs.get("skill_dir") or fs.get("skill_md") or "")
            if "/workspace_seeds/" in p or "/core/workspace_seeds/" in p:
                scope = "engine"
            elif "/workspace/" in p or "/.aiplat/" in p:
                scope = "workspace"
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    errors = lint.get("errors") if isinstance(lint, dict) else []
    warnings = lint.get("warnings") if isinstance(lint, dict) else []
    codes = {str(x.get("code") or "").strip() for x in (errors or []) if isinstance(x, dict)}
    codes |= {str(x.get("code") or "").strip() for x in (warnings or []) if isinstance(x, dict)}
    codes.discard("")

    fixes: List[Dict[str, Any]] = []

    def add_fix(
        *,
        fix_id: str,
        issue_code: str,
        title: str,
        priority: str,
        risk_level: str,
        auto_applicable: bool,
        requires_approval: bool,
        touches: List[str],
        ops: List[Dict[str, Any]],
        before: Optional[str] = None,
        after: Optional[str] = None,
        md: Optional[str] = None,
    ) -> None:
        fixes.append(
            {
                "fix_id": fix_id,
                "issue_code": issue_code,
                "title": title,
                "priority": priority,
                "risk_level": risk_level,
                "auto_applicable": auto_applicable,
                "requires_approval": requires_approval,
                "touches": touches,
                "patch": {"format": "frontmatter_merge", "ops": ops},
                "preview": {"before_snippet": before or "", "after_snippet": after or ""},
                "markdown": md or "",
            }
        )

    # ---- Fix: output_schema.markdown ----
    out_schema = getattr(skill, "output_schema", None) if not isinstance(skill, dict) else skill.get("output_schema")
    out_schema = out_schema if isinstance(out_schema, dict) else {}
    md_schema = out_schema.get("markdown") if isinstance(out_schema, dict) else None

    if "missing_markdown" in codes:
        before = "output_schema:\n" + _yaml_like(out_schema, 1) + "\n"
        after_obj = dict(out_schema)
        after_obj["markdown"] = _standard_markdown_schema()
        after = "output_schema:\n" + _yaml_like(after_obj, 1) + "\n"
        add_fix(
            fix_id="fix_missing_markdown",
            issue_code="missing_markdown",
            title="补齐 output_schema.markdown",
            priority="P0",
            risk_level="low",
            auto_applicable=True,
            requires_approval=False,
            touches=["SKILL.md.frontmatter.output_schema"],
            ops=[{"op": "upsert", "path": ["output_schema", "markdown"], "value": _standard_markdown_schema()}],
            before=before,
            after=after,
            md="### 补齐 output_schema.markdown\n- 原因：缺少 `markdown`，平台统一输出要求为 JSON+Markdown。\n- 修改：在 `output_schema` 下新增标准 `markdown` 字段。\n",
        )

    if "invalid_markdown_schema" in codes or "markdown_type" in codes:
        before = "output_schema:\n" + _yaml_like(out_schema, 1) + "\n"
        after_obj = dict(out_schema)
        after_obj["markdown"] = _standard_markdown_schema()
        after = "output_schema:\n" + _yaml_like(after_obj, 1) + "\n"
        add_fix(
            fix_id="fix_normalize_markdown_schema",
            issue_code="invalid_markdown_schema" if "invalid_markdown_schema" in codes else "markdown_type",
            title="规范化 output_schema.markdown 为标准 schema",
            priority="P0",
            risk_level="low",
            auto_applicable=True,
            requires_approval=False,
            touches=["SKILL.md.frontmatter.output_schema.markdown"],
            ops=[{"op": "upsert", "path": ["output_schema", "markdown"], "value": _standard_markdown_schema()}],
            before=before,
            after=after,
            md="### 规范化 output_schema.markdown\n- 原因：`markdown` 字段存在但 schema 不符合平台约定。\n- 修改：覆盖为标准 markdown schema（type=string, required=true）。\n",
        )

    # ---- Fix: coding/executable change contract ----
    if "missing_change_contract" in codes:
        contract = _standard_change_contract_schema()
        before = "output_schema:\n" + _yaml_like(out_schema, 1) + "\n"
        after_obj = dict(out_schema)
        # keep existing keys; only upsert missing
        ops = []
        touches = ["SKILL.md.frontmatter.output_schema"]
        for k, v in contract.items():
            if k not in after_obj:
                after_obj[k] = v
                ops.append({"op": "upsert", "path": ["output_schema", k], "value": v})
        after = "output_schema:\n" + _yaml_like(after_obj, 1) + "\n"
        if ops:
            add_fix(
                fix_id="fix_add_change_contract",
                issue_code="missing_change_contract",
                title="补齐 coding/executable 输出契约（变更/验收/回滚）",
                priority="P1",
                risk_level="low",
                # Workspace skill: safe to apply directly; Engine skill: require explicit selection and goes through change-control anyway.
                auto_applicable=(scope == "workspace"),
                requires_approval=(scope == "engine"),
                touches=touches,
                ops=ops,
                before=before,
                after=after,
                md="### 补齐输出契约（Surgical + Goal-driven）\n- 新增字段：change_plan / changed_files / unrelated_changes / acceptance_criteria / rollback_plan\n- 目的：让技能输出可审核、可验证、可回滚，并降低无关改动。\n",
            )

    # ---- Fix: permissions ----
    perms = meta.get("permissions") if isinstance(meta.get("permissions"), list) else []
    if "missing_permissions" in codes:
        before = "permissions:\n" + _yaml_like(perms, 1) + "\n"
        after = "permissions:\n" + _yaml_like(["llm:generate"], 1) + "\n"
        # For engine scope, require approval by default (more conservative).
        req_appr = scope == "engine"
        add_fix(
            fix_id="fix_missing_permissions",
            issue_code="missing_permissions",
            title="补齐 permissions（至少 llm:generate）",
            priority="P0",
            risk_level="medium",
            auto_applicable=True,
            requires_approval=req_appr,
            touches=["SKILL.md.frontmatter.permissions"],
            ops=[{"op": "upsert", "path": ["permissions"], "value": ["llm:generate"]}],
            before=before,
            after=after,
            md="### 补齐 permissions\n- 原因：executable skill 必须声明 permissions（至少 `llm:generate`）。\n- 修改：增加 `permissions: [\"llm:generate\"]`。\n",
        )

    # ---- Fix: triggers ----
    tc = meta.get("trigger_conditions") or meta.get("trigger_keywords") or []
    tc_list = _as_list(tc)
    if "missing_triggers" in codes:
        # Phase-1: suggest-only, because auto-generated triggers may be wrong.
        add_fix(
            fix_id="fix_missing_triggers_suggestion",
            issue_code="missing_triggers",
            title="补齐 trigger_conditions（建议手工补）",
            priority="P1",
            risk_level="low",
            auto_applicable=False,
            requires_approval=False,
            touches=["SKILL.md.frontmatter.trigger_conditions"],
            ops=[],
            before="trigger_conditions:\n" + _yaml_like(tc_list, 1) + "\n",
            after="trigger_conditions:\n  - <用户常用说法1>\n  - <用户常用说法2>\n",
            md="### 补齐 trigger_conditions\n- 原因：缺少触发词会降低路由命中与可解释性。\n- 建议：补充 3-10 条用户真实表达（短词/短句），避免长段文本。\n",
        )

    # ---- Fix: recall/precision/safety hints (explicit apply required) ----
    if {"triggers_too_few", "generic_description", "missing_negative_triggers", "missing_keywords", "missing_required_questions"} & codes:
        kw = meta.get("keywords") if isinstance(meta.get("keywords"), dict) else {}
        objects = _as_list((kw or {}).get("objects")) or ["代码", "SQL", "日志"]
        actions = _as_list((kw or {}).get("actions")) or []
        constraints = _as_list((kw or {}).get("constraints")) or ["按项目", "最近7天"]

        gen_triggers: List[str] = []
        for a in actions[:2]:
            for o in objects[:2]:
                gen_triggers.append(f"帮我{a}{o}")
                gen_triggers.append(f"{a}{o}并给出建议")
        if objects and constraints:
            gen_triggers.append(f"{objects[0]} {constraints[0]}")
        if actions and objects and len(constraints) >= 2:
            gen_triggers.append(f"{actions[0]} {objects[0]} {constraints[1]}")
        dedup: List[str] = []
        for t in gen_triggers:
            if t and t not in dedup:
                dedup.append(t)
        dedup = dedup[:12]

        before = "trigger_conditions:\n" + _yaml_like(_as_list(meta.get("trigger_conditions")), 1) + "\n"
        after = "trigger_conditions:\n" + _yaml_like(dedup, 1) + "\n"
        add_fix(
            fix_id="fix_generate_triggers_keywords",
            issue_code="triggers_too_few" if "triggers_too_few" in codes else "generic_description",
            title="补齐触发语义（trigger/keywords/负向/追问）",
            priority="P1",
            risk_level="low",
            auto_applicable=False,
            requires_approval=False,
            touches=[
                "SKILL.md.frontmatter.trigger_conditions",
                "SKILL.md.frontmatter.keywords",
                "SKILL.md.frontmatter.negative_triggers",
                "SKILL.md.frontmatter.required_questions",
            ],
            ops=[
                {"op": "upsert", "path": ["keywords"], "value": {"objects": objects, "actions": actions, "constraints": constraints, "synonyms": []}},
                {"op": "upsert", "path": ["trigger_conditions"], "value": dedup},
                {"op": "upsert", "path": ["negative_triggers"], "value": ["不做图片 OCR", "不做线上部署/发布"]},
                {"op": "upsert", "path": ["required_questions"], "value": ["目标环境/范围是什么？（dev/staging/prod）", "影响面有多大？（单条/批量）", "需要回滚策略吗？"]},
            ],
            before=before,
            after=after,
            md="### 补齐触发语义（建议人工确认后应用）\n- 将补齐：keywords、trigger_conditions、negative_triggers、required_questions\n- 目标：提升命中率、降低误触发，并增强高风险门控下的稳定召回\n",
        )

        add_fix(
            fix_id="fix_rewrite_description_contract",
            issue_code="generic_description",
            title="重写 description 为触发式契约（可复制）",
            priority="P2",
            risk_level="low",
            auto_applicable=False,
            requires_approval=False,
            touches=["SKILL.md.frontmatter.description"],
            ops=[
                {
                    "op": "upsert",
                    "path": ["description"],
                    "value": f"当用户提到{objects[0] if objects else '具体内容'}/{objects[1] if len(objects)>1 else (objects[0] if objects else '场景')}并希望{actions[0] if actions else '操作'}时触发；关键词覆盖：{objects[0] if objects else ''}/{actions[0] if actions else ''}/{constraints[0] if constraints else ''}；输入需要：关键上下文/文件/范围；输出为：结构化建议+markdown；不适用于：OCR/部署。",
                }
            ],
            before="description: " + (desc[:80] + "..." if len(desc) > 80 else desc) + "\n",
            after="description: <触发场景+动作+对象+输出+不适用>\n",
            md="### 重写 description（触发式契约）\n- 说明：description 不是宣传文案，而是“检索入口+边界+输入输出线索”。\n",
        )

    if "routing_needs_disambiguation" in codes:
        kw = meta.get("keywords") if isinstance(meta.get("keywords"), dict) else {}
        objects = _as_list((kw or {}).get("objects")) or ["业务对象"]
        actions = _as_list((kw or {}).get("actions")) or ["处理"]
        constraints = _as_list((kw or {}).get("constraints")) or []
        neg = _as_list(meta.get("negative_triggers")) or []

        # Add a small set of generic disambiguation constraints if missing
        add_constraints = []
        for c in []:
            if c not in constraints:
                add_constraints.append(c)
            if len(add_constraints) >= 2:
                break
        add_negs = []
        for n in ["不做通用闲聊/文案", "不做部署/发布"]:
            if n not in neg:
                add_negs.append(n)
            if len(add_negs) >= 2:
                break

        new_constraints = (constraints + add_constraints)[:10]
        new_negs = (neg + add_negs)[:20]

        add_fix(
            fix_id="fix_routing_disambiguate",
            issue_code="routing_needs_disambiguation",
            title="路由优化：补充 constraints/negative_triggers（降低错命中）",
            priority="P1",
            risk_level="low",
            auto_applicable=False,
            requires_approval=False,
            touches=["SKILL.md.frontmatter.keywords.constraints", "SKILL.md.frontmatter.negative_triggers"],
            ops=[
                {"op": "upsert", "path": ["keywords"], "value": {"objects": objects, "actions": actions, "constraints": new_constraints, "synonyms": _as_list((kw or {}).get("synonyms")) or []}},
                {"op": "upsert", "path": ["negative_triggers"], "value": new_negs},
            ],
            before="keywords.constraints:\n" + _yaml_like(_as_list((kw or {}).get("constraints")), 1) + "\nnegative_triggers:\n" + _yaml_like(_as_list(meta.get("negative_triggers")), 1) + "\n",
            after="keywords.constraints:\n" + _yaml_like(new_constraints, 1) + "\nnegative_triggers:\n" + _yaml_like(new_negs, 1) + "\n",
            md="### 路由优化建议\n- 现象：该 Skill 的 wrong_top1 / rank≥3 偏高，说明容易被相似 Skill 抢占或选择不稳定\n- 操作：补充 keywords.constraints 与 negative_triggers，提升区分度与稳定召回\n",
        )

    if "conflict_pair_high_overlap" in codes:
        confs = meta.get("_conflicts") if isinstance(meta.get("_conflicts"), list) else []
        top = confs[0] if confs and isinstance(confs[0], dict) else {}
        a = (top.get("skill_a") or {}) if isinstance(top.get("skill_a"), dict) else {}
        b = (top.get("skill_b") or {}) if isinstance(top.get("skill_b"), dict) else {}
        other = b if str(a.get("skill_id") or "") == sid else a
        other_id = str(other.get("skill_id") or "")
        other_name = str(other.get("name") or other_id or "other_skill")
        overlap = top.get("overlap_tokens") if isinstance(top.get("overlap_tokens"), list) else []
        other_skill = top.get("other_skill") if isinstance(top.get("other_skill"), dict) else {}

        neg = _as_list(meta.get("negative_triggers")) or []
        kw = meta.get("keywords") if isinstance(meta.get("keywords"), dict) else {}
        constraints = _as_list((kw or {}).get("constraints")) or []
        triggers = _as_list(meta.get("trigger_conditions")) or _as_list(getattr(skill, "trigger_conditions", None))

        # remove most generic triggers that directly appear in overlap tokens (best-effort)
        overlap_set = set([_norm_text(x) for x in overlap if str(x).strip()])
        removed = []
        kept = []
        for t in triggers:
            nt = _norm_text(t)
            if nt in overlap_set and len(removed) < 3:
                removed.append(t)
            else:
                kept.append(t)
        # ensure not to wipe triggers entirely
        new_triggers = kept if len(kept) >= 3 else triggers

        # More precise disambiguation: mine opponent-only tokens to form neg triggers.
        add_negs = []
        try:
            other_tr = _as_list(other_skill.get("trigger_conditions"))
            other_kw = other_skill.get("keywords") if isinstance(other_skill.get("keywords"), dict) else {}
            other_neg = _as_list(other_skill.get("negative_triggers"))
            mine_tokens = _token_set_for_conflict(triggers=triggers, keywords=kw, negative_triggers=neg)
            other_tokens = _token_set_for_conflict(triggers=other_tr, keywords=other_kw, negative_triggers=other_neg)
            opp_only = sorted([t for t in (other_tokens - mine_tokens) if len(t) >= 2])[:8]
            # prefer tokens not already in overlap
            overlap_norm = set([_norm_text(x) for x in overlap if str(x).strip()])
            opp_only2 = [t for t in opp_only if t not in overlap_norm][:5] or opp_only[:3]
            for t in opp_only2:
                cand = f"当用户提到“{t}”时，不选择本技能；优先使用 {other_name}（{other_id}）"
                if cand not in neg and cand not in add_negs:
                    add_negs.append(cand)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        # fallback generic lines
        for cand in [
            f"不处理 {other_name}（{other_id}）相关的请求",
        ]:
            if cand not in neg and cand not in add_negs:
                add_negs.append(cand)
        new_negs = (neg + add_negs)[:25]

        add_constraints = []
        for cand in [
            "仅在用户给出明确范围/文件/模块时执行",
            "默认不做跨模块重构或大范围改动",
        ]:
            if cand not in constraints:
                add_constraints.append(cand)
        new_constraints = (constraints + add_constraints)[:12]
        new_kw = dict(kw or {})
        new_kw["constraints"] = new_constraints

        ops = [
            {"op": "upsert", "path": ["negative_triggers"], "value": new_negs},
            {"op": "upsert", "path": ["keywords"], "value": new_kw},
        ]
        if new_triggers != triggers:
            ops.append({"op": "upsert", "path": ["trigger_conditions"], "value": new_triggers})

        before = (
            "trigger_conditions:\n"
            + _yaml_like(triggers, 1)
            + "\nnegative_triggers:\n"
            + _yaml_like(neg, 1)
            + "\nkeywords.constraints:\n"
            + _yaml_like(constraints, 1)
            + "\n"
        )
        after = (
            "trigger_conditions:\n"
            + _yaml_like(new_triggers, 1)
            + "\nnegative_triggers:\n"
            + _yaml_like(new_negs, 1)
            + "\nkeywords.constraints:\n"
            + _yaml_like(new_constraints, 1)
            + "\n"
        )
        add_fix(
            fix_id="fix_conflict_pair_disambiguate",
            issue_code="conflict_pair_high_overlap",
            title=f"冲突对消歧：与 {other_name} 定向区分",
            priority="P1",
            risk_level="low",
            auto_applicable=False,
            requires_approval=(scope == "engine"),
            touches=["SKILL.md.frontmatter.negative_triggers", "SKILL.md.frontmatter.keywords.constraints", "SKILL.md.frontmatter.trigger_conditions"],
            ops=ops,
            before=before,
            after=after,
            md="### 冲突对定向消歧\n"
            f"- 冲突对象：{other_name}（{other_id}）\n"
            f"- overlap_tokens（Top）：{', '.join([str(x) for x in overlap[:10]])}\n"
            + (f"- 对手独有 tokens（用于生成 negative_triggers）：{', '.join([str(x) for x in (opp_only2 if 'opp_only2' in locals() else [])][:10])}\n" if "opp_only2" in locals() else "")
            + ("- 建议：移除最泛化的 triggers（减少重合召回）\n" if removed else "")
            + "- 建议：补充 negative_triggers（明确不适用场景）与 keywords.constraints（执行边界）\n",
        )

    # Summary
    auto_n = sum(1 for f in fixes if f.get("auto_applicable"))
    appr_n = sum(1 for f in fixes if f.get("requires_approval"))
    # Highest priority: P0 > P1 > P2
    pri_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    hp = None
    for f in fixes:
        p = str(f.get("priority") or "")
        if not hp or pri_rank.get(p, 999) < pri_rank.get(hp, 999):
            hp = p
    return {
        "skill_id": sid,
        "scope": scope,
        "fixes": fixes,
        "summary": {
            "fix_count": len(fixes),
            "auto_applicable_count": auto_n,
            "requires_approval_count": appr_n,
            "highest_priority": hp or "",
        },
    }
