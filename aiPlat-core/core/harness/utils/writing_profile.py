"""Concise handoff writing profile (STE-inspired, not full ASD-STE100).

Config-driven prose constraints for errors / handoff / HITL / Agent↔Agent text.
Never rewrites API param names, error strings, or code symbols (term whitelist).
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

PROFILE_OFF = "off"
PROFILE_CONCISE = "concise_v1"
PROFILE_VERSION = "concise_v1"

# Unapproved → approved (lowercase keys). Applied only outside protected spans.
_PHRASE_REPLACEMENTS: Tuple[Tuple[str, str], ...] = (
    (r"\bprior to\b", "before"),
    (r"\bin order to\b", "to"),
    (r"\bcommence\b", "start"),
    (r"\butilize\b", "use"),
    (r"\butilises?\b", "use"),
    (r"\bensures?\b", "make sure"),
    (r"\breplenish\b", "fill"),
    (r"\bapproximately\b", "about"),
    (r"\bimperative that\b", "required that"),
)

# Protect: backticks, fenced code, ALL_CAPS tokens (ERROR_CODE), dotted.idents, snake_case
_PROTECT = re.compile(
    r"(`[^`]+`)"
    r"|(```[\s\S]*?```)"
    r"|(\b[A-Z][A-Z0-9_]{2,}\b)"
    r"|(\b[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+\b)"
    r"|(\b[a-z][a-z0-9_]{2,}\b(?=\s*=))"
)


def resolve_writing_profile(
    source: Optional[Mapping[str, Any]] = None,
    *,
    default: str = PROFILE_OFF,
) -> str:
    """Resolve writing_profile from project/state/env.

    Priority: source.writing_profile → metadata → _writing_profile →
    AIPLAT_WRITING_PROFILE → default.
    """
    raw = None
    if source:
        raw = source.get("writing_profile")
        if raw in (None, ""):
            meta = source.get("metadata")
            if isinstance(meta, Mapping):
                raw = meta.get("writing_profile")
        if raw in (None, ""):
            raw = source.get("_writing_profile")
    if raw in (None, ""):
        raw = os.getenv("AIPLAT_WRITING_PROFILE", "").strip() or default
    style = str(raw or default).strip().lower()
    if style in (PROFILE_OFF, "none", "disabled"):
        return PROFILE_OFF
    if style in (PROFILE_CONCISE, "concise", "ste80", "ste", "default"):
        return PROFILE_CONCISE
    return default if default in (PROFILE_OFF, PROFILE_CONCISE) else PROFILE_OFF


def build_writing_overlay(
    profile: str,
    *,
    term_whitelist: Optional[Sequence[str]] = None,
) -> str:
    """Ephemeral system-tail overlay (append-only; prompt-cache safe)."""
    if resolve_writing_profile({"writing_profile": profile}) != PROFILE_CONCISE:
        return ""
    extra = ""
    wl = [str(t).strip() for t in (term_whitelist or []) if str(t).strip()]
    if wl:
        shown = ", ".join(wl[:24])
        extra = f" Term whitelist (never rewrite): {shown}.\n"
    return (
        f"[writing_profile={PROFILE_CONCISE} version={PROFILE_VERSION}]\n"
        "Use concise handoff style (~80% STE spirit, not full ASD-STE100):\n"
        "- One word, one meaning; short active sentences; imperative for steps.\n"
        "- Procedural sentence ≤20 words; descriptive ≤25; one instruction per sentence.\n"
        "- No progressive/perfect tense; no passive in procedures.\n"
        "- NEVER rewrite API param names, error strings, code symbols, or JSON keys.\n"
        "- Keep fenced code and backtick identifiers verbatim.\n"
        f"{extra}"
    )


def _protect_spans(text: str) -> Tuple[str, Dict[str, str]]:
    """Replace protected spans with placeholders."""
    mapping: Dict[str, str] = {}
    counter = 0

    def _sub(m: re.Match[str]) -> str:
        nonlocal counter
        key = f"\x00W{counter}\x00"
        counter += 1
        mapping[key] = m.group(0)
        return key

    return _PROTECT.sub(_sub, text), mapping


def _restore_spans(text: str, mapping: Mapping[str, str]) -> str:
    out = text
    for key, val in mapping.items():
        out = out.replace(key, val)
    return out


def apply_concise_prose(
    text: str,
    *,
    profile: str = PROFILE_CONCISE,
    protect: Optional[Sequence[str]] = None,
) -> str:
    """Deterministic concise rewrite; skips when profile is off.

    Protects backtick/code/ALL_CAPS/dotted idents plus optional ``protect`` terms.
    Never rewrites protected spans (API names, error strings, symbols).
    """
    if resolve_writing_profile({"writing_profile": profile}) != PROFILE_CONCISE:
        return str(text or "")
    s = str(text or "")
    if not s.strip():
        return s

    # Extra protect terms (longest first)
    extras = sorted(
        {str(t) for t in (protect or []) if str(t).strip()},
        key=len,
        reverse=True,
    )
    extra_map: Dict[str, str] = {}
    for i, term in enumerate(extras):
        if term and term in s:
            key = f"\x00E{i}\x00"
            extra_map[key] = term
            s = s.replace(term, key)

    s, mapping = _protect_spans(s)
    mapping = {**mapping, **extra_map}

    for pat, repl in _PHRASE_REPLACEMENTS:
        s = re.sub(pat, repl, s, flags=re.IGNORECASE)

    # Soften common filler openers
    s = re.sub(r"^(Please\s+|Kindly\s+)", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s{2,}", " ", s).strip()

    return _restore_spans(s, mapping)


def apply_error_message(
    message: str,
    *,
    profile: str = PROFILE_CONCISE,
    protect: Optional[Sequence[str]] = None,
) -> str:
    """Concise wrapper for operator-facing errors; keeps diagnostic tokens intact."""
    return apply_concise_prose(message, profile=profile, protect=protect)


def apply_handoff_fields(
    fields: Mapping[str, Any],
    *,
    profile: str = PROFILE_CONCISE,
    protect: Optional[Sequence[str]] = None,
    keys: Sequence[str] = ("summary", "verify", "next"),
) -> Dict[str, Any]:
    """Apply concise prose to selected handoff string fields only."""
    out = dict(fields)
    if resolve_writing_profile({"writing_profile": profile}) != PROFILE_CONCISE:
        return out
    for k in keys:
        v = out.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = apply_concise_prose(v, profile=profile, protect=protect)
    return out


def apply_project_writing_meta(
    project: MutableMapping[str, Any],
    *,
    writing_profile: Optional[str] = None,
) -> None:
    """Persist writing_profile on project dict."""
    if writing_profile is not None:
        project["writing_profile"] = resolve_writing_profile(
            {"writing_profile": writing_profile}
        )
    project.setdefault("metadata", {})
    if isinstance(project["metadata"], dict):
        project["metadata"]["writing_profile"] = project.get(
            "writing_profile", PROFILE_OFF
        )
        project["metadata"]["writing_profile_version"] = PROFILE_VERSION
