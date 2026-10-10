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
from pathlib import Path
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


def _io_list_to_schema(items: Any) -> Dict[str, Any]:
    """Promote legacy frontmatter ``input:`` / ``output:`` lists to object schema."""
    out: Dict[str, Any] = {}
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or it.get("key") or "").strip()
        if not name:
            continue
        spec: Dict[str, Any] = {"type": str(it.get("type") or "string")}
        if it.get("required") in (True, "true", "yes", 1):
            spec["required"] = True
        desc = str(it.get("description") or "").strip()
        if desc:
            spec["description"] = desc
        out[name] = spec
    return out


def _frontmatter_io_lists(skill: Any) -> Dict[str, Any]:
    """Best-effort read input/output lists from object or SKILL.md frontmatter."""
    data: Dict[str, Any] = {}
    if isinstance(skill, dict):
        data = skill
    else:
        meta = getattr(skill, "metadata", None)
        if isinstance(meta, dict):
            data = dict(meta)
            fs = meta.get("filesystem") if isinstance(meta.get("filesystem"), dict) else {}
            p = fs.get("skill_md")
            if p:
                try:
                    raw = Path(str(p)).read_text(encoding="utf-8")
                    if raw.startswith("---"):
                        parts = raw.split("---", 2)
                        if len(parts) >= 3:
                            import yaml

                            loaded = yaml.safe_load(parts[1]) or {}
                            if isinstance(loaded, dict):
                                data = {**loaded, **data}
                except Exception:
                    pass  # noqa: cleanup-best-effort
    return {
        "input": data.get("input"),
        "output": data.get("output"),
    }


_REQ_NAME_RULES: List[tuple] = [
    (re.compile(r"play_url|播放链接|播放地址|可播放"), "play_url", "string", "out"),
    (re.compile(r"file_size|文件大小"), "file_size", "integer", "in"),
    (re.compile(r"template_path|模版路径|模板路径"), "template_path", "string", "in"),
    (re.compile(r"pptx_path|\.pptx|\.potx"), "pptx_path", "string", "out"),
    (re.compile(r"docx_path|\.docx"), "docx_path", "string", "out"),
    (re.compile(r"error_message|错误提示|错误信息"), "error_message", "string", "out"),
    (re.compile(r"resolution|清晰度|分辨率"), "resolution", "string", "out"),
    (re.compile(r"progress|上传进度|进度百分比"), "progress", "integer", "out"),
    (re.compile(r"duration|时长"), "duration", "string", "out"),
    (re.compile(r"outline|结构化大纲|章节要点"), "outline", "object", "in"),
    (re.compile(r"视频文件|本地文件|上传的文件|上传文件"), "file", "file", "in"),
    (re.compile(r"\btopic\b|主题描述"), "topic", "string", "in"),
    (re.compile(r"\btitle\b|视频标题|标题"), "title", "string", "out"),
]


def _requirement_text(skill: Any) -> str:
    chunks: List[str] = []
    if isinstance(skill, dict):
        chunks.append(str(skill.get("description") or ""))
        chunks.append(str(skill.get("sop") or skill.get("sop_body") or ""))
        meta = skill.get("metadata") if isinstance(skill.get("metadata"), dict) else {}
    else:
        chunks.append(str(getattr(skill, "description", "") or ""))
        meta = getattr(skill, "metadata", None)
        meta = meta if isinstance(meta, dict) else {}
    chunks.append(str(meta.get("sop") or ""))
    fs = meta.get("filesystem") if isinstance(meta.get("filesystem"), dict) else {}
    p = fs.get("skill_md")
    if p:
        try:
            chunks.append(Path(str(p)).read_text(encoding="utf-8"))
        except Exception:
            pass  # noqa: cleanup-best-effort
    chunks.append(_read_skill_md_body(skill))
    return "\n".join(c for c in chunks if str(c).strip())


def _clause_after(text: str, heads: str) -> str:
    m = re.search(
        rf"(?:^|\n)\s*(?:#{1,3}\s*)?(?:{heads})[:：]?\s*(.+?)(?=(?:^|\n)\s*(?:#{1,3}\s*)?(?:输入|入参|输出|出参|返回|功能|限制|执行流程|错误处理|目标|质量)|\Z)",
        text,
        re.S | re.I | re.M,
    )
    return (m.group(1) or "").strip() if m else ""


def _ident_in_phrase(phrase: str) -> str:
    m = re.search(r"`([a-z][a-z0-9_]{1,63})`", phrase, re.I)
    if m:
        return m.group(1).lower()
    m = re.search(r"\b([a-z][a-z0-9_]{1,63})\b", phrase)
    return m.group(1).lower() if m else ""


def _spec_from_phrase(phrase: str, default_side: str) -> Optional[tuple]:
    p = str(phrase or "").strip()
    if len(p) < 2:
        return None
    ident = _ident_in_phrase(p)
    for rx, name, typ, side in _REQ_NAME_RULES:
        if rx.search(p):
            return name, {"type": typ, "required": True, "description": p[:120]}, side
    if ident and ident not in {"http", "https", "mp4", "mov", "avi", "mkv"}:
        typ = "string"
        if re.search(r"文件(?!路径)|file\b", p) and ident in {"file", "video", "upload"}:
            typ = "file"
            ident = "file"
        elif re.search(r"大小|字节|进度|页数|整数", p):
            typ = "integer"
        side = default_side
        if re.search(r"输出|返回|生成", p) and default_side == "in":
            side = "out"
        if re.search(r"输入|接收|上传|校验", p) and default_side == "out":
            side = "in"
        return ident, {"type": typ, "required": True, "description": p[:120]}, side
    return None


def _extract_io_from_requirement(text: str) -> Dict[str, Dict[str, Any]]:
    """Fill schemas from SOP/需求 wording. Skip unnamed fragments; never invent prompt/result."""
    inn: Dict[str, Any] = {}
    out: Dict[str, Any] = {}
    blob = str(text or "")
    if not blob.strip():
        return {"input": inn, "output": out}

    def consume(chunk: str, default_side: str) -> None:
        parts = re.split(r"[+；;\n]|、", chunk)
        for raw in parts:
            hit = _spec_from_phrase(raw, default_side)
            if not hit:
                continue
            name, spec, side = hit
            target = inn if side == "in" else out
            if name not in target:
                target[name] = spec

    consume(_clause_after(blob, "输入|入参|input"), "in")
    consume(_clause_after(blob, "输出|出参|返回|output"), "out")
    # Whole-doc noun scan when clauses were empty (功能/限制/流程里已写清合同).
    if not inn or not out:
        for rx, name, typ, side in _REQ_NAME_RULES:
            if not rx.search(blob):
                continue
            target = inn if side == "in" else out
            if name in target:
                continue
            if side == "in" and inn and name not in inn and len(inn) >= 4:
                continue
            target[name] = {"type": typ, "required": True}
    return {"input": inn, "output": out}


_ALLOWED_CATEGORIES = (
    "general", "execution", "retrieval", "analysis", "generation",
    "transformation", "reasoning", "coding", "search", "tool", "communication",
)
_GENERIC_KW_OBJECTS = ("代码", "SQL", "日志")
_GENERIC_KW_CONSTRAINTS = ("按项目", "最近7天")
_GENERIC_KW_ACTIONS = ("分析", "生成")


def _description_from_requirement(text: str, *, min_len: int = 8, max_len: int = 280) -> str:
    blob = str(text or "")
    para = ""
    m = re.search(r"(?:^|\n)##\s*功能\s*\n+(.+?)(?=\n## |\Z)", blob, re.S)
    if m:
        para = (m.group(1) or "").strip()
    if not para:
        body = blob
        if body.lstrip().startswith("---"):
            parts = body.split("---", 2)
            body = parts[2] if len(parts) >= 3 else body
        for line in body.splitlines():
            s = line.strip()
            if s and not s.startswith("#") and not s.startswith("-") and len(s) >= min_len:
                para = s
                break
    para = re.sub(r"\s+", " ", para).strip()
    if len(para) < min_len:
        return ""
    return para[:max_len]


def _objects_actions_from_requirement(text: str, label: str) -> tuple:
    blob = str(text or "")
    objects: List[str] = []
    actions: List[str] = []
    for rx, word in (
        (r"视频", "视频"),
        (r"大纲|outline", "大纲"),
        (r"PPT|幻灯片|pptx", "PPT"),
        (r"报告", "报告"),
        (r"文件", "文件"),
    ):
        if re.search(rx, blob, re.I) and word not in objects:
            objects.append(word)
    for rx, word in (
        (r"上传", "上传"),
        (r"生成|写出", "生成"),
        (r"分析|审查", "分析"),
        (r"转换", "转换"),
        (r"检索|搜索", "检索"),
    ):
        if re.search(rx, blob, re.I) and word not in actions:
            actions.append(word)
    lab = re.sub(r"[_\-]+", "", str(label or "").strip())
    if lab and lab not in objects and not re.match(r"^[a-z0-9]+$", lab, re.I):
        objects.append(lab[:12])
    if not objects:
        objects.append((str(label or "本技能").replace("_", "") or "本技能")[:12])
    if not actions:
        actions.append("处理")
    return objects[:6], actions[:6]


def _infer_execution_type(skill: Any) -> str:
    from core.management.lint_rules.metadata import ExecTypeDirectoryMismatch
    from core.management.lint_rules.side_effects import UnrealizedSideEffectCheck  # noqa: F401 — discover() registers it
    from core.management.lint_rules.skill_quality import (  # noqa: F401 — discover() registers
        InvocationModeCheck,
        MisplacedFileCompletionCheck,
        SkillNoOpPhrasesCheck,
        UserModeTriggerSoftPass,
    )

    skill_dir = ExecTypeDirectoryMismatch._resolve_skill_dir(skill)
    if not skill_dir:
        return ""
    root = Path(skill_dir)
    has_handler = (root / "handler.py").exists()
    has_scripts = (root / "scripts").is_dir() and bool(list((root / "scripts").glob("*.py")))
    if has_handler or has_scripts:
        return "handler"
    return "prompt"


def _current_execution_type(skill: Any) -> str:
    if isinstance(skill, dict):
        v = skill.get("execution_type") or (skill.get("metadata") or {}).get("execution_type")
        return str(v or "").strip().lower()
    v = getattr(skill, "execution_type", None)
    if v:
        return str(v).strip().lower()
    meta = getattr(skill, "metadata", None)
    if isinstance(meta, dict):
        return str(meta.get("execution_type") or "").strip().lower()
    return ""


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

    req_text = _requirement_text(skill)
    inferred_exec = _infer_execution_type(skill)
    cur_exec = _current_execution_type(skill)
    if "exec_type_dir_mismatch" in codes and inferred_exec and inferred_exec != cur_exec:
        add_fix(
            fix_id="fix_align_execution_type",
            issue_code="exec_type_dir_mismatch",
            title=f"按目录内容将 execution_type 改为 {inferred_exec}",
            priority="P0",
            risk_level="low",
            auto_applicable=True,
            requires_approval=(scope == "engine"),
            touches=["SKILL.md.frontmatter.execution_type"],
            ops=[{"op": "upsert", "path": ["execution_type"], "value": inferred_exec}],
            before=f"execution_type: {cur_exec or '(empty)'}\n",
            after=f"execution_type: {inferred_exec}\n",
            md="### 对齐 execution_type\n- 有 handler.py/scripts 则为 handler，否则 prompt。\n",
        )
    if "missing_name" in codes:
        nm = str(sid).strip() if sid and sid != "<unknown>" else ""
        if not nm:
            fs = meta.get("filesystem") if isinstance(meta.get("filesystem"), dict) else {}
            p = str(fs.get("skill_dir") or fs.get("skill_md") or "")
            nm = Path(p).stem if p else ""
        if nm:
            add_fix(
                fix_id="fix_missing_name",
                issue_code="missing_name",
                title="用目录/id 补齐 name",
                priority="P0",
                risk_level="low",
                auto_applicable=True,
                requires_approval=(scope == "engine"),
                touches=["SKILL.md.frontmatter.name"],
                ops=[{"op": "upsert", "path": ["name"], "value": nm}],
                before="name:\n",
                after=f"name: {nm}\n",
                md="### 补齐 name\n- 使用 skill id 或目录名。\n",
            )
    if "non_semver_version" in codes:
        add_fix(
            fix_id="fix_semver_version",
            issue_code="non_semver_version",
            title="将 version 规范为 1.0.0",
            priority="P2",
            risk_level="low",
            auto_applicable=True,
            requires_approval=False,
            touches=["SKILL.md.frontmatter.version"],
            ops=[{"op": "upsert", "path": ["version"], "value": "1.0.0"}],
            before="version: (non-semver)\n",
            after="version: 1.0.0\n",
            md="### 规范 version\n- 写入 1.0.0。\n",
        )
    if "unknown_category" in codes:
        mapped = "general"
        blob = f"{desc}\n{req_text}\n{sid}"
        for rx, cat in (
            (r"检索|搜索|RAG", "retrieval"),
            (r"生成|PPT|报告|文案", "generation"),
            (r"代码|编程|coding", "coding"),
            (r"分析|审查", "analysis"),
            (r"转换|抽取", "transformation"),
        ):
            if re.search(rx, blob, re.I):
                mapped = cat
                break
        if mapped not in _ALLOWED_CATEGORIES:
            mapped = "general"
        add_fix(
            fix_id="fix_category_enum",
            issue_code="unknown_category",
            title=f"将 category 归入推荐枚举（{mapped}）",
            priority="P2",
            risk_level="low",
            auto_applicable=True,
            requires_approval=False,
            touches=["SKILL.md.frontmatter.category"],
            ops=[{"op": "upsert", "path": ["category"], "value": mapped}],
            before="category: (unknown)\n",
            after=f"category: {mapped}\n",
            md="### 规范 category\n- 映射到 lint 允许枚举，无法判断则为 general。\n",
        )
    if "weak_description" in codes or "generic_description" in codes:
        lifted = _description_from_requirement(req_text) or _description_from_requirement(desc)
        if lifted and lifted != desc:
            add_fix(
                fix_id="fix_lift_description_from_sop",
                issue_code="weak_description" if "weak_description" in codes else "generic_description",
                title="从 SOP/功能段提升 description",
                priority="P1",
                risk_level="low",
                auto_applicable=True,
                requires_approval=(scope == "engine"),
                touches=["SKILL.md.frontmatter.description"],
                ops=[{"op": "upsert", "path": ["description"], "value": lifted}],
                before="description: " + (desc[:80] + ("..." if len(desc) > 80 else "")) + "\n",
                after="description: " + lifted[:80] + "\n",
                md="### 提升 description\n- 使用 SOP「功能」段或首段，不套用代码/SQL 模板。\n",
            )
            if "generic_description" in codes and "weak_description" in codes:
                fixes[-1]["covers_issue_codes"] = ["weak_description", "generic_description"]
            elif "generic_description" in codes and "weak_description" not in codes:
                fixes[-1]["covers_issue_codes"] = ["generic_description"]
    if "missing_sop_body" in codes:
        add_fix(
            fix_id="fix_sop_append_body",
            issue_code="missing_sop_body",
            title="写入 SOP 骨架（目标/流程/质量）",
            priority="P1",
            risk_level="low",
            auto_applicable=True,
            requires_approval=(scope == "engine"),
            touches=["SKILL.md.body"],
            ops=[{
                "op": "upsert",
                "path": ["_sop_append"],
                "value": (
                    "## 目标\n\n明确本技能要交付的结果，以及完成标准。\n\n"
                    "## 执行流程\n\n"
                    "1. 校验入参（input_schema 必填项）\n"
                    "2. 按本技能职责执行主路径\n"
                    "3. 按 output_schema 返回结果；失败写 error_message\n\n"
                    "## 质量要求\n\n"
                    "- [ ] 输出符合 output_schema\n"
                    "- [ ] 关键验收标准可验证\n"
                    "- [ ] 未知项进入 open_questions 或标「待确认」\n"
                ),
            }],
            before="(SOP 正文为空)\n",
            after="## 目标 / ## 执行流程 / ## 质量要求\n",
            md="### 补齐 SOP 正文\n- 空正文时写入骨架，不编造业务步骤。\n",
        )

    # ---- Fix: long_description (truncate for L1 routing) ----
    if "long_description" in codes and desc:
        max_len = 280
        truncated = desc.strip()
        if len(truncated) > max_len:
            cut = truncated[: max_len - 1]
            for sep in ("。", "；", ";", ".", "，", ","):
                idx = cut.rfind(sep)
                if idx >= int(max_len * 0.55):
                    cut = cut[: idx + 1]
                    break
            truncated = cut.rstrip() + "…"
        add_fix(
            fix_id="fix_truncate_description",
            issue_code="long_description",
            title="压缩 description 至 ≤280 字（保留触发信息）",
            priority="P2",
            risk_level="low",
            auto_applicable=(scope == "workspace"),
            requires_approval=(scope == "engine"),
            touches=["SKILL.md.frontmatter.description"],
            ops=[{"op": "upsert", "path": ["description"], "value": truncated}],
            before="description: " + (desc[:80] + "..." if len(desc) > 80 else desc) + "\n",
            after="description: " + (truncated[:80] + "..." if len(truncated) > 80 else truncated) + "\n",
            md="### 压缩 description\n- 原因：过长 description 会稀释路由匹配信号。\n- 修改：截断到约 280 字，优先在句号处切断。\n",
        )

    # ---- Fix: high_risk_missing_constraints ----
    if "high_risk_missing_constraints" in codes:
        kw = meta.get("keywords") if isinstance(meta.get("keywords"), dict) else {}
        objects = _as_list((kw or {}).get("objects")) or []
        actions = _as_list((kw or {}).get("actions")) or []
        constraints = _as_list((kw or {}).get("constraints"))
        add_c = []
        for c in ("写操作需确认范围", "生产环境谨慎", "不可逆操作需审批"):
            if c not in constraints:
                add_c.append(c)
        new_constraints = (constraints + add_c)[:12]
        add_fix(
            fix_id="fix_high_risk_constraints",
            issue_code="high_risk_missing_constraints",
            title="为高风险权限补齐 keywords.constraints",
            priority="P1",
            risk_level="low",
            auto_applicable=(scope == "workspace"),
            requires_approval=(scope == "engine"),
            touches=["SKILL.md.frontmatter.keywords.constraints"],
            ops=[
                {
                    "op": "upsert",
                    "path": ["keywords"],
                    "value": {
                        "objects": objects,
                        "actions": actions,
                        "constraints": new_constraints,
                        "synonyms": _as_list((kw or {}).get("synonyms")),
                    },
                }
            ],
            before="keywords.constraints:\n" + _yaml_like(constraints, 1) + "\n",
            after="keywords.constraints:\n" + _yaml_like(new_constraints, 1) + "\n",
            md="### 高风险约束词\n- 在 keywords.constraints 写入生产/不可逆/确认范围等约束，降低误触发。\n",
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
    existing_triggers = _as_list(meta.get("triggers"))
    if "missing_triggers" in codes:
        label = str(getattr(skill, "name", "") or sid or "本技能").strip() or "本技能"
        seed = []
        for t in (
            label,
            f"帮我{label}",
            f"使用{label}",
            f"运行{label}",
            f"{label}一下",
            f"请{label}",
        ):
            if t and t not in seed:
                seed.append(t)
        seed = (tc_list + existing_triggers + seed)
        dedup_miss: List[str] = []
        for t in seed:
            if t and t not in dedup_miss:
                dedup_miss.append(t)
        dedup_miss = dedup_miss[:12]
        add_fix(
            fix_id="fix_missing_triggers",
            issue_code="missing_triggers",
            title="补齐 trigger_conditions（基于名称生成）",
            priority="P1",
            risk_level="low",
            auto_applicable=(scope == "workspace"),
            requires_approval=(scope == "engine"),
            touches=["SKILL.md.frontmatter.trigger_conditions"],
            ops=[{"op": "upsert", "path": ["trigger_conditions"], "value": dedup_miss}],
            before="trigger_conditions:\n" + _yaml_like(tc_list, 1) + "\n",
            after="trigger_conditions:\n" + _yaml_like(dedup_miss, 1) + "\n",
            md="### 补齐 trigger_conditions\n- 基于 Skill 名称生成口语触发词；可按业务再改。\n",
        )

    # ---- Fix: recall/precision/safety hints ----
    trigger_bundle_codes = {"triggers_too_few", "missing_negative_triggers", "missing_keywords", "missing_required_questions"}
    if (trigger_bundle_codes | {"generic_description"}) & codes:
        kw = meta.get("keywords") if isinstance(meta.get("keywords"), dict) else {}
        objects = _as_list((kw or {}).get("objects"))
        actions = _as_list((kw or {}).get("actions"))
        constraints = _as_list((kw or {}).get("constraints"))
        if not objects or set(objects) <= set(_GENERIC_KW_OBJECTS):
            o2, a2 = _objects_actions_from_requirement(req_text or desc, str(getattr(skill, "name", "") or sid or "本技能"))
            objects = o2
            if not actions or set(actions) <= set(_GENERIC_KW_ACTIONS):
                actions = a2
        if not actions:
            _, a2 = _objects_actions_from_requirement(req_text or desc, str(sid or "本技能"))
            actions = a2
        if not constraints or set(constraints) <= set(_GENERIC_KW_CONSTRAINTS):
            constraints = ["仅本技能职责范围"]
            if re.search(r"大小|GB|字节", req_text or desc):
                constraints.append("遵守文件大小限制")
        constraints = constraints[:12]
        if "high_risk_missing_constraints" in codes:
            for c in ("写操作需确认范围", "生产环境谨慎", "不可逆操作需审批"):
                if c not in constraints:
                    constraints.append(c)
            constraints = constraints[:12]
        existing_neg = _as_list(meta.get("negative_triggers"))
        existing_tc = _as_list(meta.get("trigger_conditions")) + existing_triggers

        gen_triggers: List[str] = list(existing_tc)
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

        new_negs = list(existing_neg)
        for n in ("不做图片 OCR", "不做线上部署/发布", "不适用于闲聊/无上下文请求"):
            if n not in new_negs:
                new_negs.append(n)
        new_negs = new_negs[:20]

        covers = sorted(trigger_bundle_codes & codes)
        if not covers and "generic_description" not in codes:
            covers = []
        primary = (
            "triggers_too_few"
            if "triggers_too_few" in codes
            else ("missing_negative_triggers" if "missing_negative_triggers" in codes else (covers[0] if covers else "triggers_too_few"))
        )
        existing_rq = _as_list(meta.get("required_questions"))
        new_rq = list(existing_rq)
        if "missing_required_questions" in codes and not new_rq:
            for q in (
                "目标产出是什么（文件/格式/页数）？",
                "输入材料有哪些（大纲/模版/约束）？",
                "有无不可改的范围或禁止项？",
            ):
                if q not in new_rq:
                    new_rq.append(q)
        before = "trigger_conditions:\n" + _yaml_like(existing_tc, 1) + "\n"
        after = "trigger_conditions:\n" + _yaml_like(dedup, 1) + "\n"
        if covers:
            ops = [
                {"op": "upsert", "path": ["keywords"], "value": {"objects": objects, "actions": actions, "constraints": constraints, "synonyms": _as_list((kw or {}).get("synonyms"))}},
                {"op": "upsert", "path": ["trigger_conditions"], "value": dedup},
                {"op": "upsert", "path": ["negative_triggers"], "value": new_negs},
            ]
            if new_rq:
                ops.append({"op": "upsert", "path": ["required_questions"], "value": new_rq})
            add_fix(
                fix_id="fix_generate_triggers_keywords",
                issue_code=str(primary),
                title="补齐触发语义（trigger/keywords/负向）",
                priority="P1",
                risk_level="low",
                # Workspace: one-click must actually clear these warnings
                auto_applicable=(scope == "workspace"),
                requires_approval=(scope == "engine"),
                touches=[
                    "SKILL.md.frontmatter.trigger_conditions",
                    "SKILL.md.frontmatter.keywords",
                    "SKILL.md.frontmatter.negative_triggers",
                    "SKILL.md.frontmatter.required_questions",
                ],
                ops=ops,
                before=before,
                after=after,
                md="### 补齐触发语义\n- 合并已有 triggers，补齐至约 6–12 条，并写入 negative_triggers / required_questions\n",
            )
            fixes[-1]["covers_issue_codes"] = covers

        # generic_description: only SOP-lift (above). Never rewrite to 代码/SQL 套话.

    # ---- Fix: SOP goal / checklist scaffolds (workspace auto) ----
    if "sop_missing_goal" in codes:
        add_fix(
            fix_id="fix_sop_append_goal",
            issue_code="sop_missing_goal",
            title="补齐 SOP「目标」章节",
            priority="P1",
            risk_level="low",
            auto_applicable=(scope == "workspace"),
            requires_approval=(scope == "engine"),
            touches=["SKILL.md.body"],
            ops=[{"op": "upsert", "path": ["_sop_append"], "value": "## 目标\n\n明确本技能要交付的结果，以及完成标准。\n"}],
            before="(SOP 缺少目标章节)\n",
            after="## 目标\n\n明确本技能要交付的结果，以及完成标准。\n",
            md="### 补齐目标章节\n- 在 SKILL.md 正文追加 `## 目标`。\n",
        )
    if "sop_missing_checklist" in codes:
        add_fix(
            fix_id="fix_sop_append_checklist",
            issue_code="sop_missing_checklist",
            title="补齐 SOP 质量要求 / Checklist",
            priority="P1",
            risk_level="low",
            auto_applicable=(scope == "workspace"),
            requires_approval=(scope == "engine"),
            touches=["SKILL.md.body", "SKILL.md.frontmatter.completion_criterion"],
            ops=[
                {"op": "upsert", "path": ["_sop_append"], "value": "## 质量要求\n\n- [ ] 输出符合 output_schema\n- [ ] 关键验收标准可验证\n- [ ] 未知项进入 open_questions 或标「待确认」\n"},
                {"op": "upsert", "path": ["completion_criterion"], "value": "输出符合契约；关键验收可验证；未知项待确认。"},
            ],
            before="(SOP 缺少 Checklist/质量要求)\n",
            after="## 质量要求\n\n- [ ] ...\n",
            md="### 补齐质量要求\n- 追加 `## 质量要求` Checklist，并写入 completion_criterion。\n",
        )
    if "sop_missing_flow" in codes:
        add_fix(
            fix_id="fix_sop_append_flow",
            issue_code="sop_missing_flow",
            title="补齐 SOP「流程/步骤」章节",
            priority="P1",
            risk_level="low",
            auto_applicable=(scope == "workspace"),
            requires_approval=(scope == "engine"),
            touches=["SKILL.md.body"],
            ops=[{
                "op": "upsert",
                "path": ["_sop_append"],
                "value": (
                    "## 执行流程\n\n"
                    "1. 校验入参（input_schema 必填项）\n"
                    "2. 按本技能职责执行主路径\n"
                    "3. 按 output_schema 返回结果；失败写 error_message\n"
                ),
            }],
            before="(SOP 缺少流程/步骤)\n",
            after="## 执行流程\n\n1. ...\n",
            md="### 补齐流程章节\n- 追加 `## 执行流程` 步骤列表（lint 识别「执行流程/步骤」）。\n",
        )

    # Lists first; else 需求/SOP wording. Never invent prompt/result.
    io_lists = _frontmatter_io_lists(skill)
    from_req = _extract_io_from_requirement(_requirement_text(skill))
    if "missing_input_schema" in codes:
        promoted_in = _io_list_to_schema(io_lists.get("input")) or dict(from_req.get("input") or {})
        if promoted_in:
            add_fix(
                fix_id="fix_promote_input_schema",
                issue_code="missing_input_schema",
                title="从 input 列表或需求正文补齐 input_schema",
                priority="P1",
                risk_level="low",
                auto_applicable=True,
                requires_approval=(scope == "engine"),
                touches=["SKILL.md.frontmatter.input_schema"],
                ops=[{"op": "upsert", "path": ["input_schema"], "value": promoted_in}],
                before="input_schema: {}\n",
                after="input_schema:\n" + _yaml_like(promoted_in, 1) + "\n",
                md="### 补齐 input_schema\n- 优先提升 `input:` 列表；否则从 SOP/需求中的输入条款抽取，不编造字段。\n",
            )
    if "missing_output_schema" in codes:
        promoted_out = _io_list_to_schema(io_lists.get("output")) or dict(from_req.get("output") or {})
        if promoted_out:
            add_fix(
                fix_id="fix_promote_output_schema",
                issue_code="missing_output_schema",
                title="从 output 列表或需求正文补齐 output_schema",
                priority="P1",
                risk_level="low",
                auto_applicable=True,
                requires_approval=(scope == "engine"),
                touches=["SKILL.md.frontmatter.output_schema"],
                ops=[{"op": "upsert", "path": ["output_schema"], "value": promoted_out}],
                before="output_schema: {}\n",
                after="output_schema:\n" + _yaml_like(promoted_out, 1) + "\n",
                md="### 补齐 output_schema\n- 优先提升 `output:` 列表；否则从 SOP/需求中的输出条款抽取，不编造字段。\n",
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
            auto_applicable=(scope == "workspace"),
            requires_approval=(scope == "engine"),
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

        # Never drop positive triggers — only add negative_triggers / constraints.
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

        before = (
            "negative_triggers:\n"
            + _yaml_like(neg, 1)
            + "\nkeywords.constraints:\n"
            + _yaml_like(constraints, 1)
            + "\n"
        )
        after = (
            "negative_triggers:\n"
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
            auto_applicable=(scope == "workspace"),
            requires_approval=(scope == "engine"),
            touches=["SKILL.md.frontmatter.negative_triggers", "SKILL.md.frontmatter.keywords.constraints"],
            ops=ops,
            before=before,
            after=after,
            md="### 冲突对定向消歧\n"
            f"- 冲突对象：{other_name}（{other_id}）\n"
            f"- overlap_tokens（Top）：{', '.join([str(x) for x in overlap[:10]])}\n"
            + (f"- 对手独有 tokens（用于生成 negative_triggers）：{', '.join([str(x) for x in (opp_only2 if 'opp_only2' in locals() else [])][:10])}\n" if "opp_only2" in locals() else "")
            + "- 补充 negative_triggers（明确不适用场景）与 keywords.constraints；不删除正向触发词。\n",
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
