"""Shared Skill auto-fill generation (used by HTTP auto-fill + create-dialog)."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple


_FILE_WRITE_RE = re.compile(
    r"\.pptx|\.potx|\.docx|\.xlsx|\.pdf|\.csv|写文件|写出|落盘|文件路径|输出.*路径|模版路径|模板路径",
    re.I,
)
_OFFLINE_RE = re.compile(r"不联网|离线|禁止联网|不要联网|勿联网")
_GEN_RE = re.compile(r"生成|PPT|幻灯片|演示|报告|文案|大纲|草稿", re.I)


def _looks_like_file_write(text: str) -> bool:
    return bool(_FILE_WRITE_RE.search(text or ""))


def _normalize_skill_id(raw: str, fallback: str = "unnamed_skill") -> str:
    s = str(raw or "").strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or not re.match(r"^[a-z]", s) or len(s) < 3:
        fb = re.sub(r"[^a-z0-9_]", "", re.sub(r"[\s\-]+", "_", str(fallback or "").lower())).strip("_")
        if fb and re.match(r"^[a-z]", fb) and len(fb) >= 3:
            return fb[:64]
        return "unnamed_skill"
    return s[:64]


def _parse_skill_md(text: str) -> Tuple[Dict[str, Any], str]:
    """Parse LLM output into (frontmatter_dict, sop_markdown)."""
    import yaml as _yaml

    raw = str(text or "").strip()
    if not raw:
        return {}, ""

    # Prefer fenced block if present (```yaml / ``` / ```markdown)
    fence = re.search(r"```(?:ya?ml|markdown|md)?\s*\n(.*?)```", raw, re.DOTALL | re.I)
    body = fence.group(1).strip() if fence else raw

    # Standard SKILL.md: --- frontmatter --- sop
    if body.startswith("---"):
        parts = body.split("---", 2)
        # parts[0]='' parts[1]=yaml parts[2]=sop when well-formed
        if len(parts) >= 3:
            fm: Dict[str, Any] = {}
            try:
                loaded = _yaml.safe_load(parts[1]) or {}
                if isinstance(loaded, dict):
                    fm = loaded
            except Exception:
                try:
                    docs = list(_yaml.safe_load_all(parts[1]))
                    fm = docs[0] if docs and isinstance(docs[0], dict) else {}
                except Exception as e:
                    logging.warning("skill autofill yaml parse failed: %s", e, exc_info=True)
                    fm = {}
            sop = parts[2].strip()
            return fm, sop

    # YAML-only dump (no --- wrappers): try load whole / first doc
    try:
        loaded = _yaml.safe_load(body)
        if isinstance(loaded, dict) and ("name" in loaded or "display_name" in loaded or "description" in loaded):
            sop = str(loaded.pop("sop", "") or loaded.pop("sop_body", "") or "").strip()
            return loaded, sop
    except Exception:  # noqa: cleanup-best-effort
        pass
    try:
        docs = list(_yaml.safe_load_all(body))
        if docs and isinstance(docs[0], dict):
            fm = dict(docs[0])
            sop = ""
            if len(docs) > 1 and isinstance(docs[1], str):
                sop = docs[1].strip()
            else:
                sop = str(fm.pop("sop", "") or fm.pop("sop_body", "") or "").strip()
            return fm, sop
    except Exception as e:
        logging.warning("skill autofill fallback yaml parse failed: %s", e, exc_info=True)

    return {}, ""


def _as_str_list(val: Any) -> List[str]:
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str) and val.strip():
        return [x.strip() for x in re.split(r"[\n,]", val) if x.strip()]
    return []


def _as_schema(val: Any) -> Dict[str, Any]:
    if isinstance(val, dict):
        return val
    return {}


def _completeness_gaps(draft: Dict[str, Any], seed_desc: str) -> List[str]:
    gaps: List[str] = []
    sop = str(draft.get("sop") or "").strip()
    if len(sop) < 80 or "待补充" in sop:
        gaps.append("SOP 正文（含输入校验、核心步骤、输出回报、约束）")
    if not _as_schema(draft.get("input_schema")):
        gaps.append("input_schema（从描述抽取具体字段）")
    out = _as_schema(draft.get("output_schema"))
    if not out:
        gaps.append("output_schema（含 markdown + 业务产出字段）")
    elif "markdown" not in out:
        gaps.append("output_schema.markdown")
    inv = str(draft.get("invocation_mode") or "user").strip().lower()
    if inv == "auto" and len(_as_str_list(draft.get("trigger_conditions"))) < 3:
        gaps.append("trigger_conditions（invocation_mode=auto 时至少 3 条中文触发说法）")
    perms = _as_str_list(draft.get("permissions"))
    if "llm:generate" not in perms:
        gaps.append("permissions 含 llm:generate")
    if _looks_like_file_write(seed_desc) or _looks_like_file_write(str(draft.get("description") or "")):
        if str(draft.get("skill_kind") or "") != "executable":
            gaps.append("skill_kind=executable（描述含文件产出）")
        if not any("workspace_fs_write" in p or "file_operations" in p for p in perms):
            gaps.append("permissions 含 tool:workspace_fs_write")
    return gaps


def _field(
    typ: str,
    *,
    required: bool,
    description: str,
) -> Dict[str, Any]:
    return {"type": typ, "required": required, "description": description}


def _synthesize_io_schemas(desc: str, *, file_write: bool) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Deterministic I/O schema from description keywords when LLM left them empty."""
    t = desc or ""
    inn: Dict[str, Any] = {}
    out: Dict[str, Any] = {}

    if re.search(r"大纲|outline|章节|每页要点|标题.*要点", t, re.I):
        inn["outline"] = _field(
            "object",
            required=True,
            description="结构化大纲：title / sections[] / pages[]（每页 title + bullets）",
        )
    if re.search(r"模版路径|模板路径|\.pptx|\.potx|template_path", t, re.I):
        inn["template_path"] = _field(
            "string",
            required=False,
            description="可选模版文件路径（.pptx/.potx）；空则用默认模版名",
        )
    if re.search(r"默认模版|模版名|模板名|template_name", t, re.I):
        inn["template_name"] = _field(
            "string",
            required=False,
            description="默认模版名（无 template_path 时使用）",
        )
    if re.search(r"单页字数|字数上限|max_chars", t, re.I):
        inn["max_chars_per_slide"] = _field(
            "integer",
            required=False,
            description="单页字数上限，避免占位符溢出",
        )
    if re.search(r"主题描述|一段主题|topic", t, re.I) and "outline" not in inn:
        inn["topic"] = _field("string", required=True, description="主题或需求描述")
    if re.search(r"Markdown|markdown|\.md", t) and "outline" not in inn:
        inn["markdown"] = _field("string", required=True, description="Markdown 正文输入")
    if re.search(r"已有文档|源文件|source", t, re.I) and "outline" not in inn:
        inn["source_path"] = _field("string", required=False, description="可选源文件路径")

    if not inn:
        inn["prompt"] = _field("string", required=True, description="任务输入（从描述未能抽出更细字段时的兜底）")

    if re.search(r"\.pptx|pptx|幻灯片|演示文稿", t, re.I):
        out["pptx_path"] = _field("string", required=True, description="生成的 .pptx 绝对路径")
    elif re.search(r"\.docx|docx", t, re.I):
        out["docx_path"] = _field("string", required=True, description="生成的 .docx 绝对路径")
    elif re.search(r"\.xlsx|xlsx", t, re.I):
        out["xlsx_path"] = _field("string", required=True, description="生成的 .xlsx 绝对路径")
    elif file_write:
        out["file_path"] = _field("string", required=True, description="生成文件的绝对路径")

    if re.search(r"页数|page_count|页码", t, re.I):
        out["page_count"] = _field("integer", required=True, description="生成页数/幻灯片数")
    if re.search(r"所用模版|所用模板|template_used|模版名", t, re.I):
        out["template_used"] = _field("string", required=True, description="实际使用的模版名或路径")
    if re.search(r"元信息|meta", t, re.I) and "metadata" not in out:
        out["metadata"] = _field("object", required=False, description="其它元信息（时间、字数等）")

    if not any(k != "markdown" for k in out):
        out["result"] = _field("string", required=True, description="业务主结果")

    out["markdown"] = _field(
        "string",
        required=True,
        description="面向人阅读的 Markdown，与结构化字段一致",
    )
    return inn, out


def _synthesize_triggers(display_name: str, name: str, desc: str) -> List[str]:
    """Build ≥3 short Chinese trigger phrases from display name / keywords."""
    label = str(display_name or "").strip()
    if not re.search(r"[\u4e00-\u9fff]", label):
        # derive rough label from desc head
        m = re.search(r"([\u4e00-\u9fff]{2,12})", desc or "")
        label = m.group(1) if m else "该技能"
    label = re.sub(r"(技能|Skill)$", "", label).strip() or "该技能"
    short = label.replace("生成器", "").replace("助手", "").strip() or label
    candidates = [
        label,
        f"生成{short}" if not short.startswith("生成") else short,
        f"做一份{short}",
        f"帮我写{short}",
        f"根据大纲做{short}" if re.search(r"大纲|outline", desc or "", re.I) else f"用{short}",
        f"输出{short}文件" if _looks_like_file_write(desc) else f"运行{short}",
    ]
    # de-dupe
    seen = set()
    out: List[str] = []
    for c in candidates:
        c = str(c).strip()
        if not c or c in seen or len(c) < 2:
            continue
        seen.add(c)
        out.append(c)
        if len(out) >= 6:
            break
    while len(out) < 3:
        out.append(f"{label}相关任务{len(out)+1}")
    return out


def _is_generic_sop(sop: str) -> bool:
    s = sop or ""
    return "执行核心动作：严格按用户提供的信息处理" in s or len(s.strip()) < 80


def _enrich_draft(draft: Dict[str, Any], *, seed_name: str, seed_desc: str) -> Dict[str, Any]:
    """Generic post-process: governance defaults from description (no domain hardcoding)."""
    desc = str(draft.get("description") or seed_desc or "").strip() or seed_desc
    name = _normalize_skill_id(str(draft.get("name") or seed_name), fallback=seed_name)
    display = str(draft.get("display_name") or "").strip() or name
    category = str(draft.get("category") or "general").strip() or "general"
    if category in ("general",) and _GEN_RE.search(f"{name}\n{desc}"):
        category = "generation"

    perms = _as_str_list(draft.get("permissions"))
    if "llm:generate" not in perms:
        perms.insert(0, "llm:generate")

    file_write = _looks_like_file_write(desc) or _looks_like_file_write(seed_desc)
    skill_kind = str(draft.get("skill_kind") or "rule").strip().lower()
    if file_write:
        skill_kind = "executable"
        if not any("workspace_fs_write" in p or "file_operations" in p for p in perms):
            perms.append("tool:workspace_fs_write")

    if _OFFLINE_RE.search(desc) or _OFFLINE_RE.search(seed_desc):
        perms = [p for p in perms if "websearch" not in p and "webfetch" not in p]

    # de-dupe preserve order
    seen = set()
    perms_u: List[str] = []
    for p in perms:
        if p not in seen:
            seen.add(p)
            perms_u.append(p)

    cfg = draft.get("config") if isinstance(draft.get("config"), dict) else {}
    cfg = dict(cfg)
    risky = any(
        any(h in p for h in ("workspace_fs_write", "run_command", "file_operations"))
        for p in perms_u
    )
    if risky:
        cfg.setdefault("require_confirmation", True)
        cfg.setdefault("timeout_seconds", 120)

    triggers = _as_str_list(draft.get("trigger_conditions"))
    in_schema = _as_schema(draft.get("input_schema"))
    out_schema = _as_schema(draft.get("output_schema"))

    inv = str(draft.get("invocation_mode") or "user").strip().lower()
    if inv not in ("user", "auto"):
        inv = "user"
    ata = draft.get("auto_trigger_allowed")
    if ata is None:
        ata = inv == "auto"
    else:
        ata = bool(ata)
    if inv == "user":
        ata = False

    # Fill empty schemas / triggers from description (LLM often drops these)
    if not in_schema or not out_schema:
        syn_in, syn_out = _synthesize_io_schemas(desc, file_write=file_write)
        if not in_schema:
            in_schema = syn_in
        if not out_schema:
            out_schema = syn_out
    if out_schema and "markdown" not in out_schema:
        out_schema = {
            **out_schema,
            "markdown": _field(
                "string",
                required=True,
                description="面向人阅读的 Markdown，与结构化字段一致",
            ),
        }
    # Only pad triggers for auto-routed skills
    if inv == "auto" and len(triggers) < 3:
        triggers = _synthesize_triggers(display, name, desc)

    sop = str(draft.get("sop") or "").strip()
    if len(sop) < 40 or _is_generic_sop(sop):
        sop = _synthesize_sop(desc, file_write=file_write, display_name=display)

    return {
        "name": name,
        "display_name": display,
        "description": desc,
        "category": category,
        "version": str(draft.get("version") or "1.0.0"),
        "skill_kind": skill_kind,
        "invocation_mode": inv,
        "auto_trigger_allowed": ata,
        "permissions": perms_u,
        "trigger_conditions": triggers,
        "capabilities": _as_str_list(draft.get("capabilities")),
        "input_schema": in_schema,
        "output_schema": out_schema,
        "config": cfg,
        "sop": sop,
    }


def _synthesize_sop(description: str, *, file_write: bool, display_name: str = "") -> str:
    """Last-resort SOP grounded in the user description (not empty boilerplate)."""
    desc = (description or "").strip()
    title = (display_name or "本技能").strip()
    # Prefer numbered requirement lines from user text
    bullets = re.findall(
        r"(?:(?:^|[;；。\n：:])\s*)?(?:\d+[)）.、]|[-*•])\s*([^\n;；]{6,160})",
        desc,
    )
    lines = [
        "# 概述",
        "",
        f"## 目标",
        f"{title}：{desc[:280]}" if desc else f"完成 {title} 并返回结构化结果。",
        "",
        "## 何时使用 / 何时不用",
        f"- ✅ 用户需要：{title}",
        "- ❌ 需求与描述约束冲突时（如要求联网而描述禁止联网）",
        "",
        "## 工作流程（SOP）",
    ]
    if bullets:
        for i, b in enumerate(bullets[:6], 1):
            lines.append(f"{i}. {b.strip().rstrip('。')}。")
        n = len(bullets[:6]) + 1
        lines.append(f"{n}. 组装 output_schema，并生成与之一致的 markdown 摘要。")
        if file_write:
            lines.append(f"{n + 1}. 确认文件已写出且路径可访问；遵守离线/不编造约束。")
    else:
        lines.extend(
            [
                "1. 校验输入：确认必填字段齐全；缺参则追问，不猜测。",
                "2. 按描述执行核心处理，仅使用用户提供的信息。",
                "3. 组装输出：填写 output_schema 各字段，并生成与之一致的 markdown。",
            ]
        )
        if file_write:
            lines.append("4. 落盘：写出目标文件并返回绝对路径与元信息。")
            lines.append("5. 约束：默认离线；不编造用户未提供的事实。")
        else:
            lines.append("4. 约束：遵守描述中的禁止事项（如不联网、不编造）。")
    lines.extend(
        [
            "",
            "## 验收清单（Checklist）",
            "- [ ] 输入已校验",
            "- [ ] 输出含 markdown 且与结构化字段一致",
            "- [ ] 未编造用户未提供的事实",
        ]
    )
    if file_write:
        lines.append("- [ ] 返回了可访问的文件路径")
    if _OFFLINE_RE.search(desc):
        lines.append("- [ ] 未联网检索素材")
    return "\n".join(lines) + "\n"


async def generate_skill_autofill(
    *,
    name: str,
    description: str,
    refine_hint: str = "",
    skills_catalog: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate Skill frontmatter + SOP from name/description via LLM."""
    name = str(name or "").strip()
    description = str(description or "").strip()
    refine_hint = str(refine_hint or "").strip()
    if not name or not description:
        raise ValueError("name and description are required")

    seed_name = name
    seed_desc = description
    if refine_hint:
        description = f"{description}\n\n【补强要求】{refine_hint}"

    catalog = skills_catalog if skills_catalog is not None else "(无)"
    if skills_catalog is None:
        try:
            from core.api.routers.workspace_agents import _scan_skills_direct

            entries = _scan_skills_direct()
            if entries:
                catalog = "\n".join(entries[:50])
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    from core.api.core_facade import (  # P0-A2: via CoreFacade
        _async_prompt_resolve,
        best_model_for_purpose,
        create_selected_adapter,
        sys_llm_generate,  # noqa: context-assembly-ok
    )

    async def _once(desc_for_llm: str) -> Dict[str, Any]:
        prompt = await _async_prompt_resolve(
            "skill-auto-fill",
            skill_name=seed_name,
            description=desc_for_llm,
            skills_catalog=catalog,
        )
        model_name = best_model_for_purpose("skill_creation")
        model = create_selected_adapter(model_name=model_name)
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("skill-auto-fill-system-role")},
            {"role": "user", "content": prompt},
        ]
        resp = await sys_llm_generate(model, messages)  # noqa: context-assembly-ok
        text = str(resp.content if hasattr(resp, "content") else resp)
        fm, sop = _parse_skill_md(text)
        if not isinstance(fm, dict) or not fm:
            fm = {"name": seed_name, "display_name": seed_name, "description": seed_desc}
        draft = {
            "name": fm.get("name", seed_name),
            "display_name": fm.get("display_name", seed_name),
            "description": fm.get("description", seed_desc),
            "category": fm.get("category", "general"),
            "version": fm.get("version", "1.0.0"),
            "skill_kind": fm.get("skill_kind", "rule"),
            "invocation_mode": fm.get("invocation_mode") or "user",
            "auto_trigger_allowed": fm.get("auto_trigger_allowed"),
            "permissions": fm.get("permissions", []) or [],
            "trigger_conditions": fm.get("trigger_conditions", []) or [],
            "capabilities": fm.get("capabilities", []) or [],
            "input_schema": fm.get("input_schema", {}) or {},
            "output_schema": fm.get("output_schema", {}) or {},
            "config": fm.get("config") if isinstance(fm.get("config"), dict) else {},
            "sop": sop or fm.get("sop_body", "") or "",
        }
        return _enrich_draft(draft, seed_name=seed_name, seed_desc=seed_desc)

    draft = await _once(description)
    gaps = _completeness_gaps(draft, seed_desc)
    if gaps and not refine_hint:
        hint = (
            "请补全以下缺失项并重新输出完整 SKILL.md（YAML frontmatter + Markdown SOP）：\n- "
            + "\n- ".join(gaps)
        )
        try:
            draft2 = await _once(f"{seed_desc}\n\n【补强要求】{hint}")
            gaps2 = _completeness_gaps(draft2, seed_desc)
            # Prefer richer draft
            if len(gaps2) < len(gaps) or len(str(draft2.get("sop") or "")) > len(str(draft.get("sop") or "")):
                draft = draft2
                gaps = gaps2
        except Exception as e:
            logging.warning("skill autofill refine retry failed: %s", e, exc_info=True)

    if gaps:
        draft["autofill_gaps"] = gaps
    return draft
