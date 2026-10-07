"""Hot-reload platform_consultant AGENT.md + constitution card by mtime.

Avoids requiring a gunicorn restart when editing ~/.aiplat/agents/.../AGENT.md
or consultant_constitution.md during consultant iteration.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Tuple

logger = logging.getLogger("aiplat.consultant_reload")

_AGENT_MTIME: Dict[str, float] = {}
_CONST_MTIME: float = -1.0
_CONST_TEXT: str = ""


def _aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def agent_md_path(agent_id: str = "platform_consultant") -> Path:
    return _aiplat_home() / "agents" / agent_id / "AGENT.md"


def constitution_path() -> Path:
    return Path(__file__).resolve().parent / "consultant_constitution.md"


def parse_agent_system_prompt(raw: str) -> str:
    """Extract config.system_prompt (or top-level system_prompt) from AGENT.md."""
    text = (raw or "").strip()
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    try:
        import yaml

        fm = yaml.safe_load(parts[1]) or {}
    except Exception:
        logger.debug("AGENT.md frontmatter parse failed", exc_info=True)
        return ""
    if not isinstance(fm, dict):
        return ""
    cfg = fm.get("config") if isinstance(fm.get("config"), dict) else {}
    sp = str((cfg or {}).get("system_prompt") or fm.get("system_prompt") or "").strip()
    return sp


def read_agent_system_prompt(agent_id: str = "platform_consultant") -> Tuple[str, float]:
    """Return (system_prompt, mtime). Empty prompt / 0.0 mtime if missing."""
    path = agent_md_path(agent_id)
    try:
        st = path.stat()
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return "", 0.0
    return parse_agent_system_prompt(raw), float(st.st_mtime)


def apply_system_prompt(agent: Any, prompt: str) -> bool:
    """Write prompt into ConversationalAgent conv + config.metadata."""
    sp = (prompt or "").strip()
    if not sp or agent is None:
        return False
    applied = False
    conv = getattr(agent, "_conv_config", None)
    if conv is not None:
        try:
            conv.system_prompt = sp
            applied = True
        except Exception:
            logger.debug("set conv.system_prompt failed", exc_info=True)
    cfg = getattr(agent, "_config", None)
    if cfg is not None:
        md = getattr(cfg, "metadata", None)
        if isinstance(md, dict):
            md["system_prompt"] = sp
            applied = True
        elif md is None:
            try:
                cfg.metadata = {"system_prompt": sp}
                applied = True
            except Exception:
                logger.debug("set config.metadata failed", exc_info=True)
    return applied


def refresh_consultant_prompt(
    agent: Any,
    *,
    agent_id: str = "platform_consultant",
    force: bool = False,
) -> bool:
    """Reload AGENT.md system_prompt when mtime changes. Returns True if applied."""
    path = agent_md_path(agent_id)
    try:
        mtime = float(path.stat().st_mtime)
    except OSError:
        return False
    prev = _AGENT_MTIME.get(agent_id)
    if not force and prev is not None and prev == mtime:
        return False
    prompt, _ = read_agent_system_prompt(agent_id)
    if not prompt:
        _AGENT_MTIME[agent_id] = mtime
        return False
    ok = apply_system_prompt(agent, prompt)
    if ok:
        _AGENT_MTIME[agent_id] = mtime
        logger.info("consultant AGENT.md reloaded id=%s mtime=%s", agent_id, mtime)
        # Drop derived caches so the next turn rebuilds brief/CAPABILITIES excerpts.
        # Keep mtime tracker (reset_reload=False) — we just recorded a fresh stamp.
        try:
            from core.harness.digital_human.consultant_knowledge import (
                clear_knowledge_caches,
            )

            clear_knowledge_caches(reset_reload=False)
        except Exception:
            logger.debug("clear knowledge caches after reload failed", exc_info=True)
    return ok


def load_constitution_fresh(*, max_chars: int = 2200) -> str:
    """mtime-aware constitution load (replaces forever lru_cache for iteration)."""
    global _CONST_MTIME, _CONST_TEXT
    path = constitution_path()
    try:
        mtime = float(path.stat().st_mtime)
        if mtime == _CONST_MTIME and _CONST_TEXT:
            return _CONST_TEXT
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.debug("constitution card missing", exc_info=True)
        _CONST_MTIME = -1.0
        _CONST_TEXT = ""
        return ""
    if not raw:
        _CONST_MTIME = mtime
        _CONST_TEXT = ""
        return ""
    body = raw[:max_chars].rstrip()
    text = (
        "平台心智卡（稳定规则；名单/数量/本页审核以简报为准，勿用本卡覆盖实况）:\n"
        + body
    )
    _CONST_MTIME = mtime
    _CONST_TEXT = text
    return text


def clear_reload_cache() -> None:
    """Test helper."""
    global _CONST_MTIME, _CONST_TEXT
    _AGENT_MTIME.clear()
    _CONST_MTIME = -1.0
    _CONST_TEXT = ""
