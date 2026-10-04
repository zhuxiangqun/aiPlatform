"""Shared helpers for asset config AI audit (Agent/Skill/Tool/MCP/Workflow)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

# Stable headings for Agent SOP one-click fixes (append skeleton only — no step rewrite).
SOP_SKILL_REFS_HEADING = "## 已绑定 Skill（审核附录）"
SOP_QUALITY_HEADING = "## 验收与质量约束（审核附录）"
SOP_HANDOFF_HEADING = "## 交接协议（审核附录）"
SOP_ROLE_HEADING = "## 角色（审核附录）"
SOP_FLOW_HEADING = "## 工作流程（审核附录）"
SOP_GOAL_HEADING = "## 目标与产出（审核附录）"


_APPENDIX_HEADINGS = (
    SOP_ROLE_HEADING,
    SOP_GOAL_HEADING,
    SOP_FLOW_HEADING,
    SOP_SKILL_REFS_HEADING,
    SOP_QUALITY_HEADING,
    SOP_HANDOFF_HEADING,
)
_APPENDIX_SPLIT = re.compile(r"(?=^## [^\n]*（审核附录）\s*$)", re.M)
_SKELETON_ROLE = re.compile(
    r"(?:\n|^)# 角色\n你是本任务的执行 Agent。职责边界：只做本阶段约定工作，不越权改上游契约。\s*",
    re.M,
)


def _collapse_audit_appendices(body: str) -> str:
    """Keep original SOP plus at most one copy of each 审核附录 heading.

    Repeat 一键修复 used to append GOAL/SKILL/HANDOFF plus a headless ``# 角色``
    skeleton. Regex-per-heading upsert still left stacks when inner ``## 目标``
    split the body on save. Collapse by split, last copy wins.
    """
    text = str(body or "").replace("\r\n", "\n")
    starts: List[int] = []
    m_skel = _SKELETON_ROLE.search(text)
    if m_skel:
        starts.append(int(m_skel.start()))
    for h in _APPENDIX_HEADINGS:
        for m in re.finditer(rf"(?:^|\n){re.escape(h)}\s*$", text, re.M):
            starts.append(int(m.start()) + (1 if text[m.start()] == "\n" else 0))
            break
    if not starts:
        return text.rstrip()
    idx = min(starts)
    core = text[:idx].rstrip()
    rest = _SKELETON_ROLE.sub("\n", text[idx:]).strip()
    blocks: Dict[str, str] = {}
    extra_order: List[str] = []
    for part in _APPENDIX_SPLIT.split(rest):
        part = str(part or "").strip()
        if not part:
            continue
        heading = part.split("\n", 1)[0].strip()
        if heading.startswith("## ") and heading.endswith("（审核附录）"):
            if heading not in blocks:
                extra_order.append(heading)
            blocks[heading] = part
            continue
        if "你是本任务的执行 Agent。职责边界" in part:
            continue
        if part:
            core = f"{core}\n\n{part}".strip() if core else part
    chunks: List[str] = [core] if core else []
    seen: Set[str] = set()
    for h in _APPENDIX_HEADINGS:
        if h in blocks:
            chunks.append(blocks[h])
            seen.add(h)
    for h in extra_order:
        if h not in seen:
            chunks.append(blocks[h])
    out = "\n\n".join(c for c in chunks if c).rstrip()
    return f"{out}\n" if out else ""


def upsert_sop_appendix(body: str, heading: str, appendix: str) -> str:
    """Idempotently append/replace a ## appendix block; leaves prior steps unchanged.

    Removes *all* prior copies of ``heading`` (repeat apply / stacked drafts) before
    writing a single appendix. Adjacent audit skeletons without a blank line before
    the next ``##`` are still matched.
    """
    heading = str(heading or "").strip()
    appendix = str(appendix or "").strip()
    if not heading or not appendix:
        return _collapse_audit_appendices(body or "").rstrip()
    if not appendix.startswith(heading):
        appendix = f"{heading}\n\n{appendix}"
    text = _collapse_audit_appendices(body or "").rstrip()
    # Stop only at the next 审核附录 H2 or EOF.
    # Do **not** stop at ``\n# `` — ``build_sop_role_appendix`` contains ``# 角色``,
    # which truncated the match and stacked copies on every 一键修复.
    pat = re.compile(
        rf"(?:^|\n){re.escape(heading)}\s*(?:\n[\s\S]*?)"
        rf"(?=\n## [^\n]*（审核附录）|\Z)",
        re.MULTILINE,
    )
    # Loop: overlapping / broken stacks may leave a second copy after one sub.
    for _ in range(32):
        nxt = pat.sub("", text).rstrip()
        if nxt == text:
            break
        text = nxt
    text = _strip_orphan_audit_skeleton(text, heading)
    text = _strip_orphan_audit_skeleton(text, SOP_ROLE_HEADING)
    if text:
        return f"{text}\n\n{appendix}\n"
    return f"{appendix}\n"


def _strip_orphan_audit_skeleton(text: str, heading: str) -> str:
    """Remove headless skeleton bullets left by a previous bad append."""
    t = (text or "").rstrip()
    if heading == SOP_QUALITY_HEADING:
        # Headless block starting at "### 验收标准" that looks like our skeleton
        orphan = re.compile(
            r"(?:\n|^)### 验收标准\n"
            r"- 必须：输出满足约定字段/格式；关键路径可验证\n"
            r"- 禁止：臆造接口、跳过验收、「跑通即合格」\n"
            r"- Checklist\n"
            r"  - \[ \] 产物路径与字段完整\n"
            r"  - \[ \] 验证步骤已执行并记录结果\n"
            r"\n### 约束\n"
            r"- 不得省略验收；不要用模糊形容词代替可检查条件\s*",
            re.MULTILINE,
        )
        t = orphan.sub("\n", t)
    elif heading == SOP_HANDOFF_HEADING:
        orphan = re.compile(
            r"(?:\n|^)- \*\*做了什么\*\*：（本阶段完成的工作摘要）\n"
            r"- \*\*产出物在哪\*\*：（产物路径 / artifact key / 字段）\n"
            r"- \*\*如何验证\*\*：（命令、检查项或验收标准）\n"
            r"- \*\*已知问题\*\*：（风险、未决项；无则写无）\n"
            r"- \*\*下一步\*\*：（下游 Agent / 阶段应接手的动作）\s*",
            re.MULTILINE,
        )
        # Only strip if placeholder skeleton (not the real 交接规范 values)
        if "（本阶段完成的工作摘要）" in t:
            t = orphan.sub("\n", t)
    elif heading == SOP_ROLE_HEADING:
        orphan = re.compile(
            r"(?:\n|^)# 角色\n"
            r"你是本任务的执行 Agent。职责边界：只做本阶段约定工作，不越权改上游契约。\s*",
            re.MULTILINE,
        )
        t = orphan.sub("\n", t)
    elif heading == SOP_GOAL_HEADING:
        orphan = re.compile(
            r"(?:\n|^)## 目标\n"
            r"完成本阶段交付并写出可交接的产出。\n\n"
            r"## 输出要求\n"
            r"- 产出：结构化结果（字段 / 文件路径 / artifact key）\n"
            r"- 输出格式：与上游契约一致；禁止臆造\s*",
            re.MULTILINE,
        )
        t = orphan.sub("\n", t)
    elif heading == SOP_FLOW_HEADING:
        orphan = re.compile(
            r"(?:\n|^)## 工作流程\n"
            r"1\. 读取输入与上游产物\n"
            r"2\. 调用约定 Skill / Tool 完成主交付\n"
            r"3\. 按输出要求整理产物\n"
            r"4\. 自检验收后结束（DONE）\s*",
            re.MULTILINE,
        )
        t = orphan.sub("\n", t)
    return t.rstrip()


def build_sop_skill_refs_appendix(skills: List[str]) -> str:
    """Markdown section listing bound skill ids in backticks (audit-clearable)."""
    ids = [str(s).strip() for s in (skills or []) if str(s).strip()]
    if not ids:
        return ""
    lines = [
        SOP_SKILL_REFS_HEADING,
        "",
        "以下 Skill 已在能力绑定中启用；步骤中优先用反引号引用对应 id：",
        "",
    ]
    for sid in ids:
        lines.append(f"- `{sid}`")
    return "\n".join(lines)


def upsert_sop_skill_refs_appendix(body: str, skills: List[str]) -> str:
    """Idempotently append/replace the skill-refs appendix; leaves prior steps unchanged."""
    appendix = build_sop_skill_refs_appendix(skills)
    if not appendix:
        return (body or "").rstrip()
    return upsert_sop_appendix(body, SOP_SKILL_REFS_HEADING, appendix)


def build_sop_quality_appendix() -> str:
    """Skeleton acceptance / anti-pattern block that clears sop_missing_quality keywords."""
    return "\n".join(
        [
            SOP_QUALITY_HEADING,
            "",
            "以下为审核一键补齐的骨架，请按本 Agent 真实产物改写：",
            "",
            "### 验收标准",
            "- 必须：输出满足约定字段/格式；关键路径可验证",
            "- 禁止：臆造接口、跳过验收、「跑通即合格」",
            "- Checklist",
            "  - [ ] 产物路径与字段完整",
            "  - [ ] 验证步骤已执行并记录结果",
            "",
            "### 约束",
            "- 不得省略验收；不要用模糊形容词代替可检查条件",
        ]
    )


def build_sop_handoff_appendix() -> str:
    """Skeleton pipeline handoff (CLAUDE.md §5.27) — labels must match HANDOFF_FIELDS."""
    # Keep exact substrings: 做了什么 / 产出物在哪 / 如何验证 / 已知问题 / 下一步
    return "\n".join(
        [
            SOP_HANDOFF_HEADING,
            "",
            "以下为流水线交接骨架，请按本阶段真实情况改写：",
            "",
            "- **做了什么**：（本阶段完成的工作摘要）",
            "- **产出物在哪**：（产物路径 / artifact key / 字段）",
            "- **如何验证**：（命令、检查项或验收标准）",
            "- **已知问题**：（风险、未决项；无则写无）",
            "- **下一步**：（下游 Agent / 阶段应接手的动作）",
        ]
    )


def fix_append_sop_quality() -> Dict[str, Any]:
    return {
        "type": "append_sop_appendix",
        "section_heading": SOP_QUALITY_HEADING,
        "appendix": build_sop_quality_appendix(),
        "label": "追加质量约束",
    }


def fix_append_sop_handoff() -> Dict[str, Any]:
    return {
        "type": "append_sop_appendix",
        "section_heading": SOP_HANDOFF_HEADING,
        "appendix": build_sop_handoff_appendix(),
        "label": "追加交接协议",
    }


def build_sop_role_appendix() -> str:
    return "\n".join(
        [
            SOP_ROLE_HEADING,
            "",
            "以下为审核一键补齐的骨架，请按本 Agent 真实职责改写：",
            "",
            "# 角色",
            "你是本任务的执行 Agent。职责边界：只做本阶段约定工作，不越权改上游契约。",
        ]
    )


def build_sop_flow_appendix() -> str:
    return "\n".join(
        [
            SOP_FLOW_HEADING,
            "",
            "以下为审核一键补齐的骨架，请按本 Agent 真实步骤改写：",
            "",
            "## 工作流程",
            "1. 读取输入与上游产物",
            "2. 调用约定 Skill / Tool 完成主交付",
            "3. 按输出要求整理产物",
            "4. 自检验收后结束（DONE）",
        ]
    )


def build_sop_goal_appendix() -> str:
    return "\n".join(
        [
            SOP_GOAL_HEADING,
            "",
            "以下为审核一键补齐的骨架，请按本 Agent 真实产物改写：",
            "",
            "## 目标",
            "完成本阶段交付并写出可交接的产出。",
            "",
            "## 输出要求",
            "- 产出：结构化结果（字段 / 文件路径 / artifact key）",
            "- 输出格式：与上游契约一致；禁止臆造",
        ]
    )


def fix_append_sop_role() -> Dict[str, Any]:
    return {
        "type": "append_sop_appendix",
        "section_heading": SOP_ROLE_HEADING,
        "appendix": build_sop_role_appendix(),
        "label": "追加角色说明",
    }


def fix_append_sop_flow() -> Dict[str, Any]:
    return {
        "type": "append_sop_appendix",
        "section_heading": SOP_FLOW_HEADING,
        "appendix": build_sop_flow_appendix(),
        "label": "追加工作流程",
    }


def fix_append_sop_goal() -> Dict[str, Any]:
    return {
        "type": "append_sop_appendix",
        "section_heading": SOP_GOAL_HEADING,
        "appendix": build_sop_goal_appendix(),
        "label": "追加目标产出",
    }


def summarize_audit_issues(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute errors/warnings/info counts and letter health grade.

    Info-only tips must not downgrade health (A = no errors/warnings).
    """
    severity_count = {"error": 0, "warning": 0, "info": 0}
    for i in issues:
        sev = str(i.get("severity") or "info")
        if sev not in severity_count:
            sev = "info"
        severity_count[sev] = severity_count.get(sev, 0) + 1
    errors = severity_count["error"]
    warnings = severity_count["warning"]
    total = len(issues)
    health = (
        "A" if errors == 0 and warnings == 0
        else "B" if errors == 0
        else "C" if errors <= 2
        else "D"
    )
    fixable = sum(1 for i in issues if i.get("fix_available") and isinstance(i.get("fix"), dict))
    blocking = [
        i
        for i in issues
        if str(i.get("severity") or "info") in ("error", "warning")
    ]
    unfixable = sum(
        1
        for i in blocking
        if not (i.get("fix_available") and isinstance(i.get("fix"), dict))
    )
    out = {
        "errors": errors,
        "warnings": warnings,
        "info": severity_count["info"],
        "total": total,
        "health": health,
        "fixable": fixable,
        "unfixable": unfixable,
    }
    return out


def _fix_has_ops(fix: Dict[str, Any]) -> bool:
    patch = fix.get("patch") if isinstance(fix.get("patch"), dict) else {}
    ops = patch.get("ops") if isinstance(patch.get("ops"), list) else []
    return any(isinstance(op, dict) and op.get("op") == "upsert" and op.get("path") for op in ops)


def index_skill_lint_fixes(fixes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map lint issue codes → best applyable fix.

    Previously only auto_applicable fixes were linked, so UI showed「建议修复」
    with no Apply button even when propose_skill_fixes already had patch ops.
    """
    fix_by_code: Dict[str, Dict[str, Any]] = {}

    def _covers(f: Dict[str, Any]) -> Set[str]:
        codes: Set[str] = set()
        c = str(f.get("issue_code") or "").strip()
        if c:
            codes.add(c)
        for x in f.get("covers_issue_codes") or []:
            s = str(x).strip()
            if s:
                codes.add(s)
        return codes

    def _better(new: Dict[str, Any], old: Optional[Dict[str, Any]]) -> bool:
        if old is None:
            return True
        # Prefer auto_applicable; then prefer ones with ops
        na, oa = bool(new.get("auto_applicable")), bool(old.get("auto_applicable"))
        if na != oa:
            return na
        return _fix_has_ops(new) and not _fix_has_ops(old)

    for f in fixes:
        if not isinstance(f, dict):
            continue
        # Suggestion-only (no ops) cannot be one-click applied
        if not _fix_has_ops(f) and not f.get("auto_applicable"):
            continue
        if not _fix_has_ops(f):
            continue
        for code in _covers(f):
            if _better(f, fix_by_code.get(code)):
                fix_by_code[code] = f
    return fix_by_code


def issue(
    *,
    severity: str,
    category: str,
    field: str,
    message: str,
    suggestion: str = "",
    current: Any = None,
    fix: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "severity": severity,
        "category": category,
        "field": field,
        "message": message,
    }
    if suggestion:
        out["suggestion"] = suggestion
    if current is not None:
        out["current"] = current
    if fix:
        out["fix_available"] = True
        out["fix"] = fix
    else:
        out["fix_available"] = False
    return out


_SKIP_TOOL_ARGS = frozenset({
    "self", "cls", "params", "kwargs", "args", "context", "ctx", "config", "request",
})
_PLACEHOLDER_MCP_URL = re.compile(
    r"(?i)127\.0\.0\.1:8080|localhost:8080|example\.com|placeholder",
)
_DICT_GET_RE = re.compile(
    r"""(?:params|args)\.get\(\s*['"]([a-zA-Z_][a-zA-Z0-9_]*)['"]""",
)


def _ann_to_json_type(ann: Any) -> str:
    import ast

    if ann is None:
        return "string"
    if isinstance(ann, ast.Name):
        return {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "dict": "object",
            "list": "array",
        }.get(ann.id, "string")
    if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
        return _ann_to_json_type(ast.Name(id=ann.value, ctx=ast.Load()))
    return "string"


def _live_tool_source(tool: Any) -> str:
    import inspect

    for obj in (getattr(tool, "execute", None), type(tool)):
        try:
            s = inspect.getsource(obj)
            if s and str(s).strip():
                return str(s)
        except Exception:
            continue
    return ""


def _schema_from_dict_gets(src: str) -> Optional[Dict[str, Any]]:
    """params.get / args.get field names from execute body. No invented 'input'."""
    blob = str(src or "")
    names: List[str] = []
    seen = set()
    for m in _DICT_GET_RE.finditer(blob):
        name = m.group(1)
        if name in _SKIP_TOOL_ARGS or name in seen:
            continue
        seen.add(name)
        names.append(name)
    if not names:
        return None
    props: Dict[str, Any] = {}
    required: List[str] = []
    for name in names:
        esc = re.escape(name)
        typ = "string"
        if re.search(rf"\bint\(\s*(?:{esc}|(?:params|args)\.get\(\s*['\"]{esc}['\"])", blob):
            typ = "integer"
        elif re.search(rf"\bbool\(\s*(?:{esc}|(?:params|args)\.get\(\s*['\"]{esc}['\"])", blob):
            typ = "boolean"
        props[name] = {"type": typ, "description": name}
        if re.search(rf"if\s+not\s+{esc}\b", blob) or f"{name}_required" in blob:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


def infer_tool_parameters_schema(tool: Any, *, source: str = "") -> Optional[Dict[str, Any]]:
    """Build parameters JSON Schema from TOOL_DEF / execute signature / input_schema. No fake input."""
    import ast

    def _as_schema(raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict) or not raw:
            return None
        if "properties" in raw and isinstance(raw.get("properties"), dict) and raw["properties"]:
            out = dict(raw)
            out.setdefault("type", "object")
            return out
        # Skill-style {field: {type, ...}}
        if all(isinstance(v, dict) for v in raw.values()):
            return {"type": "object", "properties": dict(raw), "required": [
                k for k, v in raw.items() if isinstance(v, dict) and v.get("required") is True
            ]}
        return None

    schema = getattr(tool, "input_schema", None)
    if callable(schema) and not isinstance(schema, dict):
        try:
            schema = schema()
        except Exception:
            schema = None
    hit = _as_schema(schema if isinstance(schema, dict) else None)
    if hit:
        return hit

    cfg = getattr(tool, "_config", None)
    cfg_in = getattr(cfg, "input_schema", None) if cfg is not None else None
    hit = _as_schema(cfg_in if isinstance(cfg_in, dict) else None)
    if hit:
        return hit

    src = str(source or "")
    if not src:
        meta = getattr(cfg, "metadata", None) if cfg is not None else None
        prov = (meta or {}).get("provenance", {}) if isinstance(meta, dict) else {}
        p = str((prov or {}).get("tool_path") or "")
        if p:
            try:
                from pathlib import Path as _P
                src = _P(p).read_text(encoding="utf-8", errors="replace")
            except Exception:
                src = ""
    if not src:
        src = _live_tool_source(tool)
    if src.strip():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name) and t.id == "TOOL_DEF" and isinstance(node.value, ast.Dict):
                            try:
                                obj = ast.literal_eval(node.value)
                            except Exception:
                                obj = None
                            if isinstance(obj, dict):
                                hit = _as_schema(obj.get("parameters"))
                                if hit:
                                    return hit
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ("execute", "run"):
                    props: Dict[str, Any] = {}
                    required: List[str] = []
                    defaults = list(node.args.defaults or [])
                    pos = list(node.args.args or [])
                    n_def = len(defaults)
                    n_pos = len(pos)
                    for i, arg in enumerate(pos):
                        name = str(arg.arg or "")
                        if name in _SKIP_TOOL_ARGS:
                            continue
                        props[name] = {
                            "type": _ann_to_json_type(arg.annotation),
                            "description": name,
                        }
                        has_default = i >= n_pos - n_def
                        if not has_default:
                            required.append(name)
                    if props:
                        return {"type": "object", "properties": props, "required": required}

        hit = _schema_from_dict_gets(src)
        if hit:
            return hit

    desc = ""
    try:
        desc = str(tool.get_description() or "")
    except Exception:
        desc = str(getattr(cfg, "description", "") or "") if cfg is not None else ""
    names = re.findall(r"`([a-z][a-z0-9_]{1,40})`", desc, re.I)
    if names:
        props = {n: {"type": "string", "description": n} for n in names}
        return {"type": "object", "properties": props, "required": list(names)}
    hit = _schema_from_io_clause(desc)
    if hit:
        return hit
    return None


def _schema_from_io_clause(desc: str) -> Optional[Dict[str, Any]]:
    m = re.search(r"(?:入参|输入参数|parameters)[:：]\s*(.+)", str(desc or ""), re.I)
    if not m:
        return None
    chunk = m.group(1)
    names = re.findall(r"`([a-z][a-z0-9_]{1,40})`", chunk, re.I)
    if not names:
        names = [n for n in re.findall(r"\b([a-z][a-z0-9_]{1,40})\b", chunk) if n not in _SKIP_TOOL_ARGS]
    seen = []
    for n in names:
        nl = n.lower()
        if nl in seen:
            continue
        seen.append(nl)
    if not seen:
        return None
    props = {n: {"type": "string", "description": n} for n in seen}
    return {"type": "object", "properties": props, "required": seen[:1]}


def _mcp_evidence_metadata(server: Any, yaml_data: Any = None) -> Dict[str, Any]:
    """Merge runtime object + YAML notes so infer can see description/url/command."""
    md: Dict[str, Any] = {}
    raw = getattr(server, "metadata", None)
    if isinstance(raw, dict):
        md.update(raw)
    for key, attr in (
        ("description", "description"),
        ("url", "url"),
        ("command", "command"),
        ("notes", "notes"),
        ("endpoint", "endpoint"),
    ):
        val = getattr(server, attr, None)
        if val and not md.get(key):
            md[key] = val
    if isinstance(yaml_data, dict):
        nested = yaml_data.get("metadata")
        if isinstance(nested, dict):
            for k, v in nested.items():
                if v and not md.get(k):
                    md[k] = v
        for key in (
            "description", "notes", "endpoint", "base_url", "url", "command",
            "tools", "allowed_tools", "discovered_tools",
        ):
            val = yaml_data.get(key)
            if val and not md.get(key):
                md[key] = val
    return md


def infer_http_url_from_text(*blobs: Any) -> Optional[str]:
    """First non-placeholder http(s) URL in free text. Empty if none."""
    text = " ".join(str(b or "") for b in blobs)
    for m in re.finditer(r"https?://[^\s\"'<>]+", text, re.I):
        cand = m.group(0).rstrip(".,);")
        if cand.startswith(("http://", "https://")) and not _PLACEHOLDER_MCP_URL.search(cand):
            return cand
    return None


def _slug_id(text: str) -> str:
    s = str(text or "").strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^a-z0-9_]+", "", s)
    return s.strip("_")


def infer_id_from_label(
    label: str,
    ids: Any,
    aliases: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Map a canvas label to exactly one catalog id. Empty if ambiguous or none."""
    raw = str(label or "").strip()
    if not raw:
        return None
    catalog = [str(x).strip() for x in (ids or []) if str(x).strip()]
    if not catalog:
        return None
    by_lower = {}
    for i in catalog:
        by_lower.setdefault(i.lower(), i)
    if raw.lower() in by_lower:
        return by_lower[raw.lower()]
    slug = _slug_id(raw)
    if slug and slug in by_lower:
        return by_lower[slug]
    hits: List[str] = []
    for alias, aid in (aliases or {}).items():
        aid_s = str(aid or "").strip()
        if not aid_s:
            continue
        canon = by_lower.get(aid_s.lower())
        if not canon:
            continue
        alias_slug = _slug_id(alias)
        if (slug and alias_slug and alias_slug == slug) or str(alias).strip().lower() == raw.lower():
            hits.append(canon)
    hits = list(dict.fromkeys(hits))
    if len(hits) == 1:
        return hits[0]
    contain: List[str] = []
    rl = raw.lower()
    for i in catalog:
        il = i.lower()
        if il == rl:
            continue
        if len(il) >= 3 and (il in rl or (len(rl) >= 3 and rl in il)):
            contain.append(i)
    contain = list(dict.fromkeys(contain))
    if len(contain) == 1:
        return contain[0]
    return None


def list_workspace_agent_catalog(home: Any = None) -> Dict[str, str]:
    """Workspace agent id → display_name (disk)."""
    import os
    from pathlib import Path

    root = Path(home) if home else Path(os.path.expanduser("~/.aiplat"))
    agents_dir = root / "agents"
    out: Dict[str, str] = {}
    if not agents_dir.is_dir():
        return out
    try:
        import yaml as _yaml
    except Exception:
        _yaml = None
    for d in sorted(agents_dir.iterdir()):
        if not d.is_dir():
            continue
        md = d / "AGENT.md"
        if not md.exists():
            continue
        display = d.name
        if _yaml is not None:
            try:
                raw = md.read_text(encoding="utf-8", errors="ignore")
                parts = raw.split("---", 2)
                fm = _yaml.safe_load(parts[1]) if len(parts) >= 2 else {}
                if isinstance(fm, dict):
                    display = str(fm.get("display_name") or fm.get("name") or d.name).strip() or d.name
            except Exception:
                display = d.name
        out[d.name] = display
    return out


def list_workspace_tool_names(home: Any = None) -> List[str]:
    """Workspace tool ids from ~/.aiplat/tools (filename + TOOL_DEF name)."""
    import json
    import os
    from pathlib import Path

    root = Path(home) if home else Path(os.path.expanduser("~/.aiplat"))
    tdir = root / "tools"
    names: List[str] = []
    if not tdir.is_dir():
        return names
    for p in sorted(tdir.iterdir()):
        if p.suffix == ".py":
            names.append(p.stem)
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")[:8000]
                m = re.search(r'["\']name["\']\s*:\s*["\']([^"\']+)["\']', txt)
                if m and m.group(1).strip():
                    names.append(m.group(1).strip())
            except Exception:
                pass  # noqa: cleanup-best-effort
        elif p.name.endswith(".TOOL.manifest.json"):
            names.append(p.name.replace(".TOOL.manifest.json", ""))
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(data, dict):
                    n = data.get("name") or data.get("id")
                    if n:
                        names.append(str(n).strip())
            except Exception:
                pass  # noqa: cleanup-best-effort
    seen = set()
    out: List[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _tool_names_from_blob(raw: Any) -> List[str]:
    names: List[str] = []
    if isinstance(raw, str):
        n = raw.strip()
        if n:
            names.append(n)
    elif isinstance(raw, dict):
        n = raw.get("name") or raw.get("tool") or raw.get("id")
        if n:
            names.append(str(n).strip())
        for k in ("tools", "allowed_tools", "discovered_tools", "items"):
            if k in raw:
                names.extend(_tool_names_from_blob(raw.get(k)))
    elif isinstance(raw, (list, tuple)):
        for item in raw:
            names.extend(_tool_names_from_blob(item))
    seen = set()
    out: List[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
        if len(out) >= 32:
            break
    return out


def infer_mcp_allowed_tools(
    *,
    metadata: Any = None,
    yaml_data: Any = None,
    policy_data: Any = None,
) -> List[str]:
    """Whitelist from policy.yaml / declared tools / last tools/list cache. Never invent names."""
    md = metadata if isinstance(metadata, dict) else {}
    yaml_data = yaml_data if isinstance(yaml_data, dict) else {}
    policy_data = policy_data if isinstance(policy_data, dict) else {}
    for blob in (
        yaml_data.get("allowed_tools"),
        policy_data.get("allowed_tools"),
        (policy_data.get("policy") or {}).get("allowed_tools") if isinstance(policy_data.get("policy"), dict) else None,
        yaml_data.get("tools"),
        md.get("allowed_tools"),
        md.get("discovered_tools"),
        md.get("last_discovered_tools"),
        md.get("tools"),
        md.get("recommended_tools"),
    ):
        names = _tool_names_from_blob(blob)
        if names:
            return names
    return []


def infer_mcp_endpoint(*, name: str, transport: str, url: str, command: str, metadata: Any = None, env: Optional[Dict[str, str]] = None, description: str = "") -> Dict[str, str]:
    """Evidence-only MCP fill. Never returns placeholder localhost:8080."""
    import os

    out: Dict[str, str] = {}
    transport = str(transport or "").strip().lower()
    url = str(url or "").strip()
    command = str(command or "").strip()
    md = metadata if isinstance(metadata, dict) else {}
    env = env if isinstance(env, dict) else dict(os.environ)
    key = re.sub(r"[^A-Z0-9]+", "_", str(name or "").strip().upper()).strip("_")
    if not url:
        for cand in (
            str(md.get("url") or "").strip(),
            str(env.get(f"AIPLAT_MCP_{key}_URL") or "").strip() if key else "",
            str(env.get(f"MCP_{key}_URL") or "").strip() if key else "",
        ):
            if cand.startswith(("http://", "https://")) and not _PLACEHOLDER_MCP_URL.search(cand):
                out["url"] = cand
                break
        if "url" not in out:
            found = infer_http_url_from_text(
                description,
                *(md.get(k) for k in ("description", "notes", "endpoint", "base_url")),
            )
            if found:
                out["url"] = found
    if not command:
        for cand in (
            str(md.get("command") or "").strip(),
            str(env.get(f"AIPLAT_MCP_{key}_COMMAND") or "").strip() if key else "",
            str(env.get(f"MCP_{key}_COMMAND") or "").strip() if key else "",
        ):
            if cand and cand.lower() not in {"python", "python3", "echo", "true", "false"}:
                out["command"] = cand
                break
    if command and transport in ("sse", "http", "streamable_http", "") and not url and "url" not in out:
        out["transport"] = "stdio"
    return out
