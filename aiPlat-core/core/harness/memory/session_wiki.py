"""Session → Wiki worker — short coding-session pages (reuse wiki_engine).

Does not synthesize via KnowledgeSynthesizer (too heavy). Mirrors the thin
pipeline pattern in `_save_pipeline_knowledge_to_wiki`.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_SAFE_TITLE = re.compile(r"[^a-zA-Z0-9_\u4e00-\u9fff/\-]+")


def _safe_segment(text: str, limit: int = 48) -> str:
    s = _SAFE_TITLE.sub("_", (text or "").strip())[:limit].strip("_/-")
    return s or "session"


def write_session_wiki_page(
    title: str,
    summary: str,
    *,
    session_id: str = "",
    tags: Optional[Sequence[str]] = None,
    source: str = "session",
    collection_id: str = "default",
) -> Dict[str, Any]:
    """Write a short draft wiki page for a finished coding / IDE session.

    Production callers: ide_capture.ingest_ide_capture(write_wiki=True),
    session_wiki_worker_hook (SESSION_END), CoreFacade.write_session_wiki.
    """
    summary = (summary or "").strip()
    if len(summary) < 40:
        return {"ok": False, "reason": "summary_too_short"}

    sid = _safe_segment(session_id or time.strftime("%Y%m%d-%H%M%S", time.gmtime()))
    topic = _safe_segment(title or "coding-session")
    page_title = f"session/{sid}/{topic}"
    tag_list: List[str] = ["session-summary", str(source or "session")]
    for t in tags or []:
        t = str(t).strip()
        if t and t not in tag_list:
            tag_list.append(t)

    body = (
        f"# {title or topic}\n\n"
        f"- source: `{source}`\n"
        f"- session_id: `{session_id or sid}`\n"
        f"- written_at: `{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}`\n\n"
        f"## Summary\n\n{summary[:5000]}\n"
    )

    try:
        from core.harness.knowledge.wiki_engine import write_page

        path = write_page(
            title=page_title,
            body=body,
            category="topics",
            tags=tag_list[:16],
            collection_id=collection_id or "default",
            status="draft",
            skip_validation=True,
            summary=(summary[:200] if summary else ""),
        )
        return {"ok": True, "title": page_title, "path": str(path), "tags": tag_list}
    except Exception as e:
        logger.warning("write_session_wiki_page failed: %s", e, exc_info=True)
        return {"ok": False, "reason": str(e)[:200]}


def session_wiki_enabled() -> bool:
    """Opt-in via AIPLAT_SESSION_WIKI (default off — avoid noisy pages)."""
    return os.getenv("AIPLAT_SESSION_WIKI", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )


async def session_wiki_worker_hook(context: Any) -> Dict[str, Any]:
    """SESSION_END hook: if enabled + success summary present → short wiki page.

    Registered from hook_manager.get_default_hooks().
    """
    if not session_wiki_enabled():
        return {"continue": True, "session_wiki": "disabled"}

    state = getattr(context, "state", None) or {}
    if not isinstance(state, dict):
        state = {}

    success = state.get("success")
    if success is False:
        return {"continue": True, "session_wiki": "skipped_failure"}

    summary = (
        str(state.get("final_answer") or "")
        or str(state.get("summary") or "")
        or str(state.get("description") or "")
        or str(state.get("result") or "")
    ).strip()
    session_id = str(
        state.get("session_id") or state.get("run_id") or getattr(context, "session_id", "") or ""
    )
    title = str(state.get("task") or state.get("description") or session_id or "agent-session")
    agent_id = str(state.get("agent_id") or getattr(context, "agent_id", "") or "agent")

    result = write_session_wiki_page(
        title=title[:120],
        summary=summary,
        session_id=session_id,
        tags=["agent-session", agent_id],
        source="session_end",
    )
    return {"continue": True, "session_wiki": result}
