"""
Generic Skill Adapter — auto-detect imported skill type and adapt to aiPlatform.

After a skill is installed from agentskills.io / Claude Code / OpenClaw / etc.,
this module detects the execution pattern and rewrites SKILL.md frontmatter
+ optionally generates handler.py.

Callers:
  - skill_installer._install_from_dir()  — auto-adapt after every import
  - agentskills_parser.convert_agentskills_to_aiplat() — enrich conversion
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Set


# ── Tool name crosswalk: platform tool → aiPlatform equivalent ──

@dataclass
class ToolMapping:
    primary: Optional[str]  # aiPlatform tool/skill name; None = no equivalent
    critical: bool = False  # missing → block skill activation


TOOL_NAME_CROSSWALK: Dict[str, ToolMapping] = {
    # Claude Code
    "WebSearch":       ToolMapping("information_search", critical=True),
    "Bash":            ToolMapping("code_execution",     critical=False),
    "Glob":            ToolMapping("file_glob",          critical=False),
    "Grep":            ToolMapping("code_search",        critical=False),
    "Read":            ToolMapping("file_read",          critical=False),
    "Write":           ToolMapping("file_write",         critical=False),
    "Edit":            ToolMapping("file_edit",          critical=False),
    "ToolSearch":      ToolMapping("tool_search",        critical=False),
    "AskUserQuestion": ToolMapping(None,                 critical=False),
    # Cursor / OpenClaw
    "search":             ToolMapping("information_search", critical=True),
    "run_terminal_cmd":   ToolMapping("code_execution",     critical=False),
    "grep_search":        ToolMapping("code_search",        critical=False),
    "read_file":          ToolMapping("file_read",          critical=False),
    "write_file":         ToolMapping("file_write",         critical=False),
}

# Tool names in SOP body that indicate tool_composition pattern
_TOOL_REF_PATTERN = re.compile(
    r'\b(WebSearch|Bash|Glob|Grep|Read|Write|Edit|ToolSearch|'
    r'AskUserQuestion|search|run_terminal_cmd|grep_search|read_file|write_file)\b'
)


# ── Pattern detection ──

class SkillPattern(Enum):
    PRE_ADAPTED = auto()        # handler.py exists
    SCRIPT_BASED = auto()       # scripts/ dir with .py files
    TOOL_COMPOSITION = auto()   # SOP references external platform tools
    PURE_PROMPT = auto()        # only SKILL.md, no scripts, no tool refs
    AGENT_CONFIG = auto()       # agents/ dir with .yaml/.md


@dataclass
class SkillProfile:
    pattern: SkillPattern
    has_scripts: bool = False
    has_agent_config: bool = False
    detected_tools: Set[str] = None
    main_script: Optional[str] = None  # path to main executable in scripts/


def detect_pattern(skill_dir: str | Path) -> SkillProfile:
    """Scan a skill directory and return its detected pattern."""
    root = Path(skill_dir)
    if not root.is_dir():
        return SkillProfile(SkillPattern.PURE_PROMPT)

    # Check pre-adapted
    if (root / "handler.py").exists():
        return SkillProfile(SkillPattern.PRE_ADAPTED, has_scripts=bool(
            list((root / "scripts").glob("*.py")) if (root / "scripts").is_dir() else []))

    # Check script-based
    scripts_dir = root / "scripts"
    if not (scripts_dir.is_dir() and bool(list(scripts_dir.glob("*.py")))):
        # Fallback: check nested skills/<name>/scripts/ (Path B zip import artifact)
        nested = root / "skills" / root.name / "scripts"
        if nested.is_dir() and bool(list(nested.glob("*.py"))):
            scripts_dir = nested
    has_scripts = scripts_dir.is_dir() and bool(list(scripts_dir.glob("*.py")))
    if has_scripts:
        main_script = None
        py_files = list(scripts_dir.glob("*.py"))
        # Heuristic: pick the main script by naming convention or size
        for candidate in ["main.py", "run.py", "index.py", "app.py"]:
            if (scripts_dir / candidate).exists():
                main_script = candidate
                break
        if not main_script and py_files:
            # Pick script matching skill directory name
            name_parts = root.name.lower().replace("-", "").replace("_", "")
            for pf in py_files:
                if name_parts in pf.name.lower().replace("-", "").replace("_", ""):
                    main_script = pf.name
                    break
        if not main_script and py_files:
            main_script = py_files[0].name

        return SkillProfile(SkillPattern.SCRIPT_BASED, has_scripts=True,
                           main_script=str(scripts_dir / main_script))

    # Check agent config
    agents_dir = root / "agents"
    has_agent_config = agents_dir.is_dir() and bool(
        list(agents_dir.glob("*.yaml")) + list(agents_dir.glob("*.yml")) + list(agents_dir.glob("*.json")))
    if has_agent_config:
        return SkillProfile(SkillPattern.AGENT_CONFIG, has_agent_config=True)

    # Check tool composition — scan SKILL.md body for tool references
    skill_md = root / "SKILL.md"
    detected_tools: Set[str] = set()
    if skill_md.exists():
        content = skill_md.read_text(encoding="utf-8", errors="replace")
        body = content
        # Strip YAML frontmatter to avoid matching tools in metadata
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                body = parts[2]
        detected_tools = set(_TOOL_REF_PATTERN.findall(body))
    if detected_tools:
        return SkillProfile(SkillPattern.TOOL_COMPOSITION, detected_tools=detected_tools)

    return SkillProfile(SkillPattern.PURE_PROMPT)


# ── Auto-adapter ──

def adapt_skill(dst_dir: str | Path) -> Dict[str, any]:
    """Auto-adapt a skill after installation. Returns summary dict."""
    root = Path(dst_dir)
    if not root.is_dir():
        return {"adapted": False, "reason": "dir_not_found"}

    profile = detect_pattern(root)

    if profile.pattern == SkillPattern.PRE_ADAPTED:
        return {"adapted": False, "reason": "already_adapted", "pattern": "pre_adapted"}

    if profile.pattern == SkillPattern.SCRIPT_BASED:
        return _adapt_script_based(root, profile)

    if profile.pattern == SkillPattern.TOOL_COMPOSITION:
        return _adapt_tool_composition(root, profile)

    if profile.pattern == SkillPattern.AGENT_CONFIG:
        return _adapt_agent_config(root, profile)

    # PURE_PROMPT — just enrich frontmatter
    return _adapt_pure_prompt(root, profile)


def _adapt_script_based(root: Path, profile: SkillProfile) -> dict:
    """Generate handler.py + rewrite SKILL.md for script-based skills."""
    skill_name = root.name
    main_script = profile.main_script or "scripts/main.py"
    script_rel = str(Path(main_script).relative_to(root)) if Path(main_script).is_absolute() else main_script

    # Generate handler.py
    handler_code = f'''"""Auto-generated handler for {skill_name} — wraps {script_rel}."""
import subprocess, sys, json, time
from pathlib import Path

async def execute(params: dict) -> dict:
    topic = params.get("query", params.get("topic", ""))
    script = Path(__file__).parent / "{script_rel}"
    if not topic:
        return {{"error": "query or topic parameter required"}}
    try:
        start = time.time()
        result = subprocess.run(
            [sys.executable, str(script), topic, "--emit=compact"],
            capture_output=True, text=True, timeout=300,
            cwd=str(Path(__file__).parent),
        )
        elapsed = time.time() - start
        # Emit engine stage events via ActiveTraceContext (set by sys_skill_call)
        try:
            from core.harness.kernel.execution_context import emit_trace_event
            emit_trace_event("skill", "{skill_name}", "completed",
                             args={{"topic": topic}}, duration_ms=elapsed * 1000)
            if result.stderr:
                # Parse engine progress from stderr if available
                for line in result.stderr.split(chr(10))[:20]:
                    if "Processing" in line:
                        emit_trace_event("tool", "process", "completed",
                                         args={{"detail": line[:200]}})
        except Exception:
            pass
        return {{"topic": topic, "output": result.stdout, "stderr": result.stderr[:500],
                 "success": result.returncode == 0}}
    except subprocess.TimeoutExpired:
        return {{"topic": topic, "error": "execution timed out after 300s"}}
'''
    (root / "handler.py").write_text(handler_code, encoding="utf-8")

    # Enrich SKILL.md frontmatter — preserve original body
    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        # No SKILL.md — create minimal one with original body
        body = f"Auto-generated skill for {skill_name}.\nScript: {script_rel}"
        new_md = _build_enriched_skill_md(skill_name, desc, body, script_rel, root)
        skill_md.write_text(new_md, encoding="utf-8")
        return {"adapted": True, "pattern": "script_based", "actions": ["generated_handler_py", "created_skill_md"]}

    existing = skill_md.read_text(encoding="utf-8", errors="replace")
    body = ""

    # Parse existing frontmatter to extract description + body
    if existing.startswith("---"):
        parts = existing.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml
                fm = yaml.safe_load(parts[1]) or {}
                desc = str(fm.get("description", fm.get("name", skill_name)))[:200]
                # Preserve upstream version if present
                if fm.get("version"):
                    v = str(fm.get("version", "1.0.0"))
                    version = v
                if fm.get("license"):
                    pass
            except Exception:
                pass
            body = parts[2]

    if not body:
        body = existing  # no frontmatter, use whole file as body

    # Build enriched frontmatter + preserve body
    new_md = _build_enriched_skill_md(skill_name, desc, body, script_rel, root)
    skill_md.write_text(new_md, encoding="utf-8")

    return {"adapted": True, "pattern": "script_based", "actions": ["generated_handler_py", "enriched_skill_md"]}


def _build_enriched_skill_md(skill_name: str, desc: str, body: str,
                               script_rel: str, root: Optional[Path] = None) -> str:
    """Build enriched SKILL.md frontmatter while preserving original body."""
    import json as _json

    # ── Category inference ──
    category = _infer_category(skill_name, desc, body)

    # ── Permissions inference ──
    permissions, effects = _infer_permissions(body, root)

    # ── Capabilities ──
    capabilities = _infer_capabilities(skill_name, desc, body)

    # ── Trigger keywords ──
    trigger_keywords = _infer_trigger_keywords(skill_name, desc)

    # ── Build frontmatter ──
    lines = [
        "---",
        f"name: {skill_name}",
        f"description: {desc[:500]}",
        "execution_type: handler",
        "execution_mode: inline",
        f"category: {category}",
        "version: 1.0.0",
        "status: draft",
        "protected: false",
        "",
        f"permissions: {_json.dumps(permissions, ensure_ascii=False)}",
        f"capabilities: {_json.dumps(capabilities, ensure_ascii=False)}",
        f"trigger_keywords: {_json.dumps(trigger_keywords, ensure_ascii=False)}",
        f"input_schema:",
        f"  query:",
        f"    type: string",
        f"    required: true",
        f"    description: 查询主题或话题",
        f"output_schema:",
        f"  output:",
        f"    type: string",
        f"    description: 搜索引擎的原始输出",
        f"  stderr:",
        f"    type: string",
        f"    description: 执行过程中的诊断输出",
        "",
        f"effects:",
        f"  - type: read",
        f"    resources: [filesystem:~/.aiplat, filesystem:~/Documents]",
        f"    idempotent: true",
    ]
    if effects.get("write"):
        lines.append(f"  - type: write")
        lines.append(f"    resources: [filesystem:~/Documents/Last30Days]")
        lines.append(f"    idempotent: false")
    if effects.get("execute"):
        lines.append(f"  - type: execute")
        lines.append(f"    resources: [process:python3]")
        lines.append(f"    idempotent: true")
        lines.append(f"    rollback_available: false")

    lines.append("")
    lines.append("---")
    if body.strip():
        lines.append("")
        lines.append(body.strip())

    return "\n".join(lines) + "\n"


# ── Inference helpers ──

def _infer_category(name: str, desc: str, body: str) -> str:
    """Guess category from name, description, and body content."""
    combined = f"{name} {desc[:200]} {body[:500]}".lower()
    if any(k in combined for k in ("search", "检索", "查找", "查询", "research", "reddit", "twitter", "x ", "youtube")):
        return "retrieval"
    if any(k in combined for k in ("code", "代码", "generate", "生成", "write")):
        return "generation"
    if any(k in combined for k in ("doc", "文档", "pdf", "parse", "解析", "ingest", "import")):
        return "document"
    if any(k in combined for k in ("analysis", "分析", "insight", "洞察")):
        return "analysis"
    if any(k in combined for k in ()):
        return "analysis"
    return "general"


def _infer_permissions(body: str, root: Optional[Path] = None) -> tuple:
    """Infer required permissions and effects from script behavior."""
    permissions = []
    effects = {"read": True}

    # Detect from source code in scripts/ directory
    if root and (root / "scripts").is_dir():
        scripts_text = ""
        for sf in sorted((root / "scripts").rglob("*.py"))[:15]:
            try:
                scripts_text += sf.read_text(encoding="utf-8", errors="replace")[:200]
            except Exception:
                pass
        combined = f"{body[:500]} {scripts_text}"
    else:
        combined = body[:1000]

    if any(k in combined for k in ("requests.", "urllib", "http.client", "httpx", "api.", "reddit.com",
                                     "github.com", "x.com", "twitter", "youtube", "scrapecreators")):
        permissions.append("network:outbound")
        effects["read"] = True

    if any(k in combined for k in ("save", "write", "open(", "json.dump", "yaml.dump", "store", "persist")):
        effects["write"] = True

    if any(k in combined for k in ("subprocess", "os.system", "Popen", "shutil")):
        effects["execute"] = True

    return permissions, effects


def _infer_capabilities(name: str, desc: str, body: str) -> list:
    """Infer capability labels from skill content."""
    combined = f"{name} {desc[:200]} {body[:500]}".lower()
    caps = []
    if any(k in combined for k in ("search", "检索", "查找", "query", "research")):
        caps.append("multi_source_search")
    if any(k in combined for k in ("platform", "cross-platform", "跨平台", "multi_platform", "multi-source")):
        caps.append("cross_platform_research")
    if any(k in combined for k in ("30", "last", "recent", "today", "week", "month")):
        caps.append("time_ranged_analysis")
    if any(k in combined for k in ("prompt", "code", "generate", "生成")):
        caps.append("content_generation")
    if any(k in combined for k in ("compare", "vs", "versus", "对比", "比较")):
        caps.append("comparative_analysis")
    return caps or ["data_processing"]


def _infer_trigger_keywords(name: str, desc: str) -> list:
    """Extract trigger keywords from name and description."""
    keywords = []
    # From name
    parts = name.replace("-", " ").replace("_", " ").split()
    for p in parts[:5]:
        if len(p) > 1 and p.lower() not in ("skill", "tool", "agent"):
            keywords.append(p.lower())
    # From description
    desc_lower = desc.lower()
    for kw in ("search", "research", "检索", "搜索", "查找", "查询", "trend", "趋势",
               "generate", "analyze"):
        if kw in desc_lower and kw not in keywords:
            keywords.append(kw)
    return keywords[:8]


def _adapt_tool_composition(root: Path, profile: SkillProfile) -> dict:
    """Inject tool mappings into SKILL.md frontmatter for tool-composition skills."""
    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        return {"adapted": False, "reason": "no_skill_md"}

    content = skill_md.read_text(encoding="utf-8", errors="replace")
    mapped = {}
    missing = []

    for tool in (profile.detected_tools or set()):
        mapping = TOOL_NAME_CROSSWALK.get(tool)
        if mapping and mapping.primary:
            mapped[tool] = mapping.primary
        else:
            missing.append(tool)

    if not mapped and not missing:
        return {"adapted": False, "reason": "no_tools_mapped"}

    # Inject into frontmatter
    try:
        import yaml
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {"adapted": False, "reason": "no_frontmatter"}

        fm = yaml.safe_load(parts[1]) or {}
        fm["execution_type"] = "prompt"
        fm["_auto_adapted"] = True
        fm["tools"] = list(mapped.values())

        if missing:
            critical_missing = [t for t in missing
                              if TOOL_NAME_CROSSWALK.get(t, ToolMapping(None)).critical]
            fm["missing_capabilities"] = missing
            if critical_missing:
                fm["status"] = "draft"
                fm["block_reason"] = f"missing critical tools: {', '.join(critical_missing)}"

        new_fm = yaml.dump(dict(fm), allow_unicode=True, sort_keys=False).strip()
        new_content = f"---\n{new_fm}\n---\n{parts[2]}"
        skill_md.write_text(new_content, encoding="utf-8")

    except Exception:
        return {"adapted": False, "reason": "frontmatter_parse_failed"}

    return {
        "adapted": True, "pattern": "tool_composition",
        "actions": ["injected_tools", "marked_missing" if missing else ""],
        "tools_mapped": mapped, "tools_missing": missing,
    }


def _adapt_agent_config(root: Path, profile: SkillProfile) -> dict:
    """Promote agent config files into SKILL.md metadata."""
    # For now, mark as draft and note agent config presence
    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        # Create minimal SKILL.md from agent config
        agents_dir = root / "agents"
        agent_files = list(agents_dir.glob("*.yaml")) + list(agents_dir.glob("*.yml"))
        name = root.name
        desc = name
        if agent_files:
            try:
                import yaml
                cfg = yaml.safe_load(agent_files[0].read_text(encoding="utf-8")) or {}
                name = cfg.get("name", name)
                desc = cfg.get("description", desc)
            except Exception:
                pass
        skill_md.write_text(f"""---
name: {name}
description: {desc}
execution_type: prompt
execution_mode: inline
category: general
status: draft
_auto_adapted: true
_has_agent_config: true
---
""", encoding="utf-8")

    return {"adapted": True, "pattern": "agent_config", "actions": ["promoted_agent_config"]}


def _adapt_pure_prompt(root: Path, profile: SkillProfile) -> dict:
    """Enrich frontmatter without changing SOP body."""
    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        return {"adapted": False, "reason": "no_skill_md"}

    content = skill_md.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {"adapted": False, "reason": "no_frontmatter"}

        fm = yaml.safe_load(parts[1]) or {}
        fm.setdefault("execution_type", "prompt")
        fm.setdefault("category", "general")
        fm.setdefault("_auto_adapted", True)
        new_fm = yaml.dump(dict(fm), allow_unicode=True, sort_keys=False).strip()
        new_content = f"---\n{new_fm}\n---\n{parts[2]}"
        skill_md.write_text(new_content, encoding="utf-8")

    except Exception:
        return {"adapted": False, "reason": "frontmatter_parse_failed"}

    return {"adapted": True, "pattern": "pure_prompt", "actions": ["enriched_frontmatter"]}
