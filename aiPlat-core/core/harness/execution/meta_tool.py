"""Code meta-tool preference — Turing-complete escape hatch (Harness first-class).

Article alignment: fixed tool lists are closed; when the task is deterministic
(arithmetic / dates / parse / transform) or no bound tool fits, prefer the
sandbox ``code`` / ``code_execution`` tool over LLM guesswork.

Does NOT invent agent_id branches. Production callers:
  - ReActLoop._build_tools_desc (hint + pin)
  - ReActLoop._ensure_meta_tool_bound (opt-in auto-bind)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)

# ToolConfig.name is ``code``; some gates/docs still say code_execution.
META_TOOL_ALIASES: Tuple[str, ...] = ("code", "code_execution")

# (pattern, reason_tag) — deterministic / compute-heavy intents
# CJK intent tokens via unicode escapes (§78b: no literal CJK in execution/).
_INTENT_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(
        r"(?i)(\bcalculate\b|\barithmetic\b|\bsum\b|\baverage\b|\bmean\b|"
        r"\bpercentile\b|\bstddev\b|\bfactorial\b|\bmodulo\b|"
        + "\u8ba1\u7b97|\u6c42\u548c|\u5e73\u5747\u503c|\u7b97\u672f|\u767e\u5206\u6bd4)"
    ), "arithmetic"),
    (re.compile(
        r"(?i)(\btimezone\b|\butc\b|\bisodate\b|\bstrptime\b|\btimedelta\b|"
        r"\bcalendar\b|\bepoch\b|"
        + "\u65f6\u533a|\u65e5\u671f\u8ba1\u7b97|\u65f6\u95f4\u5dee|\u65f6\u95f4\u6233)"
    ), "datetime"),
    (re.compile(
        r"(?i)(\bparse\s+json\b|\bjson\.loads\b|\bcsv\b|\bregex\b|\bre\.match\b|"
        r"\bchecksum\b|\bhashlib\b|\bbase64\b|\buuid\b|"
        + "\u89e3\u6790json|\u6821\u9a8c\u548c|\u54c8\u5e0c|\u6b63\u5219\u63d0\u53d6)"
    ), "parse_transform"),
    (re.compile(
        r"(?i)(\bno\s+tool\b|\bno\s+skill\b|\bwrite\s+a\s+(script|program)\b|"
        r"\bexecute\s+code\b|\brun\s+python\b|"
        + "\u6ca1\u6709\u5408\u9002\u7684\u5de5\u5177|\u73b0\u573a\u5199\u4ee3\u7801|"
        + "\u7528\u4ee3\u7801\u6267\u884c)"
    ), "escape_hatch"),
)


def meta_tool_enabled(context: Optional[Dict[str, Any]] = None) -> bool:
    """Master switch. Context ``_prefer_code_meta_tool`` overrides env."""
    ctx = context if isinstance(context, dict) else {}
    if "_prefer_code_meta_tool" in ctx:
        return bool(ctx.get("_prefer_code_meta_tool"))
    return os.getenv("AIPLAT_META_TOOL_CODE", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def meta_tool_auto_bind_enabled(context: Optional[Dict[str, Any]] = None) -> bool:
    """Bind CodeExecutionTool when missing.

    Default ``auto``: on in AIPLAT_PROFILE=production, off in dev (PolicyGate surface).
    Explicit true/false still wins.
    """
    ctx = context if isinstance(context, dict) else {}
    if "_meta_tool_auto_bind" in ctx:
        return bool(ctx.get("_meta_tool_auto_bind"))
    raw = (os.getenv("AIPLAT_META_TOOL_AUTO_BIND") or "auto").strip().lower()
    if raw in ("1", "true", "yes", "y", "on"):
        return True
    if raw in ("0", "false", "no", "n", "off"):
        return False
    # auto
    return (os.getenv("AIPLAT_PROFILE") or "").strip().lower() == "production"


def detect_meta_tool_intent(task: str) -> Optional[str]:
    """Return reason tag if task should prefer code meta-tool; else None."""
    text = (task or "").strip()
    if len(text) < 4:
        return None
    for pat, tag in _INTENT_PATTERNS:
        if pat.search(text):
            return tag
    return None


def resolve_meta_tool_name(available: Sequence[str]) -> Optional[str]:
    """Pick the bound meta-tool name present in ``available``."""
    names = {str(n).strip() for n in available if str(n).strip()}
    for alias in META_TOOL_ALIASES:
        if alias in names:
            return alias
    return None


def tool_names_from_tools(tools: Sequence[Any]) -> List[str]:
    out: List[str] = []
    for t in tools or []:
        n = getattr(t, "name", None) or getattr(getattr(t, "config", None), "name", None)
        if n:
            out.append(str(n))
    return out


def meta_tool_pin_names(
    available: Sequence[str],
    *,
    task: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> Set[str]:
    """Names to pin in tool ordering (always_include) when intent matches."""
    if not meta_tool_enabled(context):
        return set()
    intent = detect_meta_tool_intent(task)
    # Also pin when caller explicitly requested preference without regex hit
    ctx = context if isinstance(context, dict) else {}
    force = bool(ctx.get("_force_code_meta_tool"))
    if not intent and not force:
        return set()
    name = resolve_meta_tool_name(available)
    return {name} if name else set()


def build_meta_tool_hint(
    task: str,
    available: Sequence[str],
    *,
    context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Ephemeral overlay hint — does not reorder tools (prompt-cache safe)."""
    if not meta_tool_enabled(context):
        return None
    intent = detect_meta_tool_intent(task)
    ctx = context if isinstance(context, dict) else {}
    if not intent and not ctx.get("_force_code_meta_tool"):
        return None
    name = resolve_meta_tool_name(available)
    if not name:
        if meta_tool_auto_bind_enabled(context):
            return (
                f"[META TOOL] Deterministic/{intent or 'compute'} step — "
                "code sandbox will be auto-bound; prefer tool `code` over guessing."
            )
        return (
            f"[META TOOL] Deterministic/{intent or 'compute'} step detected — "
            "bind/use tool `code` (sandbox) instead of LLM arithmetic or invented APIs."
        )
    return (
        f"[META TOOL] Prefer `{name}` for {intent or 'compute'} "
        "(unique non-probabilistic engine). Do not approximate with prose."
    )


def apply_meta_tool_config(
    context: Dict[str, Any],
    meta_tool: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge PipelineStageConfig / AGENT.md ``meta_tool`` into loop context flags.

    Returns the same context dict (mutated). Empty overlay is a no-op.
    """
    ctx = context if isinstance(context, dict) else {}
    ov = meta_tool if isinstance(meta_tool, dict) else {}
    if not ov:
        return ctx
    if "enabled" in ov:
        ctx["_prefer_code_meta_tool"] = bool(ov.get("enabled"))
    if "auto_bind" in ov:
        ctx["_meta_tool_auto_bind"] = bool(ov.get("auto_bind"))
    if "force" in ov:
        ctx["_force_code_meta_tool"] = bool(ov.get("force"))
    return ctx


def ensure_code_meta_tool(
    tools: List[Any],
    *,
    task: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> List[Any]:
    """Optionally append CodeExecutionTool when missing and auto-bind is on.

    Returns a new list (or the same list if unchanged). Marks context when bound.
    """
    if not meta_tool_enabled(context) or not meta_tool_auto_bind_enabled(context):
        return list(tools or [])
    intent = detect_meta_tool_intent(task)
    ctx = context if isinstance(context, dict) else None
    if not intent and not (ctx and ctx.get("_force_code_meta_tool")):
        return list(tools or [])
    names = tool_names_from_tools(tools)
    if resolve_meta_tool_name(names):
        return list(tools or [])
    try:
        from core.apps.tools.code import CodeExecutionTool

        new_list = list(tools or [])
        new_list.append(CodeExecutionTool())
        if ctx is not None:
            ctx["_meta_tool_auto_bound"] = True
            ctx["_meta_tool_intent"] = intent or "force"
        return new_list
    except Exception as e:
        logger.debug("meta_tool auto-bind skipped: %s", e, exc_info=True)
        return list(tools or [])
