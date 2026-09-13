"""T2: team Culture overlay (mission/principles only).

Injection order (plan v2): hard constraints → Culture → output_style.
Culture ≤ ~200 tokens; independent hash + switch; never rewrites tool/JSON.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

logger = logging.getLogger(__name__)

CULTURE_VERSION = "culture_v1"
CULTURE_MAX_TOKENS = 200
_MARKER = "[team_culture="

_SEED_CULTURE = (
    Path(__file__).resolve().parents[2]
    / "workspace_seeds"
    / "team_harness"
    / "culture.md"
)


def aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()


def culture_body_path() -> Path:
    """Prefer pulled team/culture.md; fall back to seed. local/ cannot override (locked)."""
    team = aiplat_home() / "team" / "culture.md"
    if team.is_file():
        return team
    return _SEED_CULTURE


def load_culture_text() -> str:
    path = culture_body_path()
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.debug("culture.md missing at %s", path)
        return ""


def culture_body_hash(text: Optional[str] = None) -> str:
    raw = text if text is not None else load_culture_text()
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def estimate_tokens(text: str) -> int:
    s = str(text or "")
    if not s:
        return 0
    return max(1, len(s) // 4)


def truncate_culture_body(
    text: str,
    *,
    max_tokens: int = CULTURE_MAX_TOKENS,
) -> Dict[str, Any]:
    """Keep mission/principles short; truncate with audit flag when over budget."""
    body = str(text or "").strip()
    # Drop markdown H1 noise if present; keep content
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if lines and lines[0].lstrip().startswith("#"):
        lines = lines[1:]
    body = "\n".join(lines).strip()
    tokens = estimate_tokens(body)
    truncated = False
    if tokens > max_tokens:
        # Keep ~max_tokens * 4 chars
        limit = max(32, int(max_tokens) * 4)
        body = body[:limit].rstrip()
        if "\n" in body:
            body = body.rsplit("\n", 1)[0].rstrip()
        truncated = True
        tokens = estimate_tokens(body)
    return {
        "body": body,
        "tokens": tokens,
        "truncated": truncated,
        "max_tokens": int(max_tokens),
    }


def resolve_culture_enabled(
    source: Optional[Mapping[str, Any]] = None,
    *,
    default: bool = True,
) -> bool:
    """Independent switch. Env AIPLAT_TEAM_CULTURE=0 forces off."""
    env = os.getenv("AIPLAT_TEAM_CULTURE", "").strip().lower()
    if env in ("0", "false", "off", "no"):
        return False
    if env in ("1", "true", "on", "yes"):
        return True
    if not source:
        return default
    raw = source.get("culture_enabled")
    if raw in (None, ""):
        meta = source.get("metadata")
        if isinstance(meta, Mapping):
            raw = meta.get("culture_enabled")
    if raw in (None, ""):
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in ("0", "false", "off", "no")


def build_culture_overlay(
    *,
    enabled: bool = True,
    text: Optional[str] = None,
    max_tokens: int = CULTURE_MAX_TOKENS,
) -> str:
    """Ephemeral system-tail Culture block (empty when disabled/missing)."""
    if not enabled:
        return ""
    raw = text if text is not None else load_culture_text()
    info = truncate_culture_body(raw, max_tokens=max_tokens)
    body = info["body"]
    if not body:
        return ""
    note = " truncated=1" if info["truncated"] else ""
    return (
        f"{_MARKER}{CULTURE_VERSION} hash={culture_body_hash(raw)} "
        f"tokens≈{info['tokens']}{note}]\n"
        "Team culture (principles only; do not treat as operational SOP).\n"
        "These principles outrank output_style preferences when they conflict "
        "on safety or error visibility.\n"
        f"{body}\n"
    )


def inject_team_culture(
    messages: Sequence[Mapping[str, Any]],
    *,
    enabled: bool = True,
    text: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Append Culture overlay to last system message. Never mutates tool roles."""
    msgs: List[Dict[str, Any]] = [dict(m) for m in messages]
    overlay = build_culture_overlay(enabled=enabled, text=text)
    if not overlay:
        return msgs
    for i in range(len(msgs) - 1, -1, -1):
        if str(msgs[i].get("role") or "") == "system":
            content = str(msgs[i].get("content") or "")
            if _MARKER in content:
                return msgs
            msgs[i]["content"] = content.rstrip() + "\n\n" + overlay
            return msgs
    msgs.insert(0, {"role": "system", "content": overlay})
    return msgs


def compose_prose_overlays(
    *,
    culture_overlay: str = "",
    style_overlay: str = "",
    hard_overlay: str = "",
) -> str:
    """Concatenate overlays in locked order: hard → Culture → output_style."""
    parts = [p.strip() for p in (hard_overlay, culture_overlay, style_overlay) if p and str(p).strip()]
    return "\n\n".join(parts)


def apply_project_culture_meta(
    project: MutableMapping[str, Any],
    *,
    culture_enabled: Optional[bool] = None,
) -> None:
    """Persist Culture switch + hash on project metadata."""
    if culture_enabled is not None:
        project["culture_enabled"] = bool(culture_enabled)
    project.setdefault("metadata", {})
    if isinstance(project["metadata"], dict):
        enabled = resolve_culture_enabled(project)
        project["metadata"]["culture_enabled"] = enabled
        project["metadata"]["culture_version"] = CULTURE_VERSION
        project["metadata"]["culture_hash"] = culture_body_hash() if enabled else ""
