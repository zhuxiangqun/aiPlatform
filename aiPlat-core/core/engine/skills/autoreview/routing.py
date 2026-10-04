"""Autoreview mode routing — decide single vs panel from params + diff.

Default ``panel=auto``: elevate to multi-engine panel when the change looks
security-sensitive or the caller already asked for security/architecture focus.
Explicit ``panel=true|false`` always wins.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Optional, Sequence

# Path / content cues (skill-local heuristics; not business agent names).
_PATH_SECURITY_RE = re.compile(
    r"(?i)("
    r"auth|oauth|jwt|session|cookie|csrf|xss|password|passwd|secret|credential|"
    r"crypto|encrypt|decrypt|permission|rbac|acl|firewall|sanitize|injection|"
    r"login|signup|token|apikey|api[_-]?key|private[_-]?key"
    r")"
)
_CONTENT_SECURITY_RE = re.compile(
    r"(?i)("
    r"innerHTML|dangerouslySetInnerHTML|eval\s*\(|new\s+Function\s*\(|"
    r"pickle\.loads|subprocess\.[a-z_]+\([^)]*shell\s*=\s*True|"
    r"password\s*=\s*['\"]|api[_-]?key\s*=\s*['\"]sk-|"
    r"Authorization:\s*Bearer|child_process|exec\s*\(|"
    r"SELECT\s+.+\s+FROM|DROP\s+TABLE|UNION\s+SELECT"
    r")"
)

_DEEP_LINE_THRESHOLD = int(os.getenv("AIPLAT_AUTOREVIEW_DEEP_LINES", "500") or "500")


@dataclass(frozen=True)
class ReviewRouting:
    use_panel: bool
    focus: str
    mode: str  # single | quick | deep (report.mode uses single when not panel)
    preset_name: str
    reason: str


def _truthy_panel(raw: Any) -> Optional[bool]:
    """True/False for explicit; None means auto."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in ("auto", "default", "smart"):
        return None
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return None


def diff_security_score(*, files: Sequence[str], content: str) -> int:
    """0 = clean; higher = more security-relevant signals."""
    score = 0
    for f in files or []:
        if _PATH_SECURITY_RE.search(str(f) or ""):
            score += 2
    text = str(content or "")
    # Cap content scan for cost
    blob = text[:80000]
    hits = _CONTENT_SECURITY_RE.findall(blob)
    score += min(6, len(hits))
    return score


def resolve_review_routing(
    *,
    panel: Any = None,
    focus: str = "comprehensive",
    mode: str = "quick",
    preset: str = "",
    files: Optional[Sequence[str]] = None,
    content: str = "",
    total_lines: int = 0,
) -> ReviewRouting:
    """Choose single vs panel (+ focus/mode/preset) from caller intent + diff."""
    focus_n = (focus or "comprehensive").strip().lower() or "comprehensive"
    mode_n = (mode or "quick").strip().lower() or "quick"
    if mode_n not in ("quick", "deep"):
        mode_n = "quick"
    preset_n = (preset or "").strip() or ""
    explicit = _truthy_panel(panel)
    # Default when unset: auto (overridable via env)
    if panel is None or panel == "":
        default = (os.getenv("AIPLAT_AUTOREVIEW_PANEL_DEFAULT", "auto") or "auto").strip().lower()
        if default in ("0", "false", "no", "off", "single"):
            explicit = False
        elif default in ("1", "true", "yes", "on", "panel"):
            explicit = True
        else:
            explicit = None

    sec_score = diff_security_score(files=files or [], content=content)
    large = int(total_lines or 0) >= _DEEP_LINE_THRESHOLD

    # Explicit off → always single
    if explicit is False:
        return ReviewRouting(
            use_panel=False,
            focus=focus_n,
            mode="single",
            preset_name=preset_n or "code_review",
            reason="panel=false",
        )

    # Explicit on → panel; elevate focus if needed
    if explicit is True:
        foc = focus_n if focus_n in ("security", "architecture") else "security"
        preset_use = preset_n or ("architecture" if foc == "architecture" else "security")
        mode_use = "deep" if mode_n == "deep" or large else "quick"
        return ReviewRouting(
            use_panel=True,
            focus=foc,
            mode=mode_use,
            preset_name=preset_use,
            reason="panel=true" + ("; elevated_focus=security" if foc != focus_n else ""),
        )

    # ── auto ──
    if focus_n == "security":
        mode_use = "deep" if mode_n == "deep" or large else "quick"
        return ReviewRouting(
            use_panel=True,
            focus="security",
            mode=mode_use,
            preset_name=preset_n or "security",
            reason="auto:focus=security" + (";deep_lines" if large and mode_n != "deep" else ""),
        )

    if focus_n == "architecture":
        mode_use = "deep" if mode_n == "deep" or large else "quick"
        return ReviewRouting(
            use_panel=True,
            focus="architecture",
            mode=mode_use,
            preset_name=preset_n or "architecture",
            reason="auto:focus=architecture",
        )

    # comprehensive / style / performance — panel only when diff looks sensitive
    if sec_score >= 2:
        mode_use = "deep" if large or mode_n == "deep" else "quick"
        return ReviewRouting(
            use_panel=True,
            focus="security",
            mode=mode_use,
            preset_name=preset_n or "security",
            reason=f"auto:security_signals={sec_score}" + (";deep_lines" if large else ""),
        )

    return ReviewRouting(
        use_panel=False,
        focus=focus_n,
        mode="single",
        preset_name=preset_n or "code_review",
        reason="auto:single_default",
    )
