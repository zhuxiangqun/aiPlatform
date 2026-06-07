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
    has_scripts = scripts_dir.is_dir() and bool(list(scripts_dir.glob("*.py")))
    if has_scripts:
        main_script = None
        py_files = list(scripts_dir.glob("*.py"))
        # Heuristic: pick the largest or most "main"-looking script
        for candidate in ["last30days.py", "main.py", "run.py", "index.py", "app.py"]:
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
import subprocess, sys, json
from pathlib import Path

async def execute(params: dict) -> dict:
    topic = params.get("query", params.get("topic", ""))
    script = Path(__file__).parent / "{script_rel}"
    if not topic:
        return {{"error": "query or topic parameter required"}}
    try:
        result = subprocess.run(
            [sys.executable, str(script), topic, "--emit=compact"],
            capture_output=True, text=True, timeout=300,
            cwd=str(Path(__file__).parent),
        )
        return {{"topic": topic, "output": result.stdout, "stderr": result.stderr[:500]}}
    except subprocess.TimeoutExpired:
        return {{"topic": topic, "error": "execution timed out after 300s"}}
'''
    (root / "handler.py").write_text(handler_code, encoding="utf-8")

    # Rewrite SKILL.md
    skill_md = root / "SKILL.md"
    existing = ""
    if skill_md.exists():
        existing = skill_md.read_text(encoding="utf-8", errors="replace")

    # Extract description from existing frontmatter
    desc = skill_name
    if existing.startswith("---"):
        parts = existing.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml
                fm = yaml.safe_load(parts[1]) or {}
                desc = str(fm.get("description", fm.get("name", skill_name)))[:200]
            except Exception:
                pass

    new_skill_md = f"""---
name: {skill_name}
description: {desc}
execution_type: handler
execution_mode: inline
category: general
version: 1.0.0
status: draft
input_schema:
  query:
    type: string
    required: true
    description: 查询主题
output_schema:
  output:
    type: string
    description: 搜索引擎的原始输出
---
## SOP

本 skill 通过 handler.py 包装 `{script_rel}` 执行。
Agent 通过 sys_skill_call("{skill_name}", {{query: "topic"}}) 调用。
"""
    skill_md.write_text(new_skill_md, encoding="utf-8")

    return {"adapted": True, "pattern": "script_based", "actions": ["generated_handler_py", "rewrote_skill_md"]}


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
