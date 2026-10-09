"""IDE bypass capture — Cursor / Claude Code → Team Brain (no parallel store).

Hooks / CLI POST a thin payload; we only deliver into existing shared_memory /
optional session wiki. Failures stay as medium-confidence learnings (core must
not import platform experience_feedback).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_\u4e00-\u9fff]+")


def _slug(text: str, limit: int = 60) -> str:
    s = _SLUG_RE.sub("_", (text or "").strip())[:limit].strip("_")
    return s or "untitled"


def ingest_ide_capture(
    prompt: str,
    result: str = "",
    *,
    tools: Optional[Sequence[str]] = None,
    success: bool = True,
    tags: Optional[Sequence[str]] = None,
    source: str = "ide",
    session_id: str = "",
    write_wiki: bool = False,
) -> Dict[str, Any]:
    """Deliver one IDE/agent turn into Team Brain (+ optional session wiki).

    Production callers: CoreFacade.ingest_ide_capture, POST /memory/ide-capture,
    scripts/ide_capture.py, SESSION_END wiki worker (via write_session_wiki).
    """
    prompt = (prompt or "").strip()
    result = (result or "").strip()
    if not prompt and not result:
        return {"ok": False, "reason": "empty_payload"}

    tool_list: List[str] = [str(t) for t in (tools or []) if str(t).strip()][:20]
    tag_list: List[str] = [str(t) for t in (tags or []) if str(t).strip()][:12]
    src = (source or "ide").strip() or "ide"
    title = (prompt[:80] if prompt else result[:80]) or f"{src}-capture"
    tool_blob = ",".join(tool_list) if tool_list else "-"
    tag_blob = ",".join(tag_list) if tag_list else ""
    summary_parts = [
        f"result={result[:500]}" if result else "result=(empty)",
        f"tools={tool_blob}",
    ]
    if tag_blob:
        summary_parts.append(f"tags={tag_blob}")
    if session_id:
        summary_parts.append(f"session={session_id}")
    summary = "; ".join(summary_parts)

    out: Dict[str, Any] = {
        "ok": True,
        "success": bool(success),
        "source": src,
        "session_id": session_id or "",
    }

    try:
        from core.harness.memory.team_brain import publish_manual_solution
        from core.harness.memory.shared_memory import record_learning

        if success:
            learning = publish_manual_solution(
                title=title,
                summary=summary[:800],
                source_agent=f"ide:{src}",
                keywords=list(dict.fromkeys(tool_list + tag_list + _slug(prompt).split("_")[:6])),
                confidence="high",
            )
            out["action"] = "team_brain"
            out["learning"] = learning
        else:
            key = f"team_solution:ide_fail:{_slug(title)}"
            learning = record_learning(
                key=key,
                value=summary[:800],
                source_agent=f"ide:{src}",
                source_session=session_id or "",
                confidence="medium",
            )
            out["action"] = "shared_learning_fail"
            out["learning"] = learning.to_dict() if hasattr(learning, "to_dict") else {"key": key}
    except Exception as e:
        logger.warning("ingest_ide_capture publish failed: %s", e, exc_info=True)
        return {"ok": False, "reason": str(e)[:200]}

    if write_wiki and success:
        try:
            from core.harness.memory.session_wiki import write_session_wiki_page

            wiki = write_session_wiki_page(
                title=title,
                summary=f"{prompt}\n\n{result}"[:4000] if prompt else result[:4000],
                session_id=session_id,
                tags=["ide-capture", src] + tag_list,
                source=src,
            )
            out["wiki"] = wiki
        except Exception as e:
            logger.debug("session wiki from ide capture skipped: %s", e, exc_info=True)
            out["wiki"] = {"ok": False, "reason": str(e)[:150]}

    return out
