"""
ContextEngine (Roadmap-1, Phase 1: minimal).

Purpose:
- Centralize "context assembly" logic (project context files, retrieval, compaction).
- Provide a stable extension point so future phases can add:
  - token budgeting + compression
  - RAG retrieval from knowledge base
  - cached summaries
  - observability

This initial version only handles "project context files" (AGENTS.md / AIPLAT.md).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import os


Message = Dict[str, Any]


@dataclass
class ContextResult:
    messages: List[Message]
    metadata: Dict[str, Any]
    status: Dict[str, Any] = field(default_factory=dict)
    workspace_context_hash: Optional[str] = None


class ContextEngine:
    def apply(self, *, messages: List[Message], metadata: Dict[str, Any], repo_root: Optional[str]) -> ContextResult:
        raise NotImplementedError

    def should_compact(self, *, messages: List[Message], metadata: Dict[str, Any]) -> bool:
        return False

    def compact(self, *, messages: List[Message], metadata: Dict[str, Any]) -> ContextResult:
        return ContextResult(messages=list(messages or []), metadata=dict(metadata or {}))

    def get_status(self, *, messages: List[Message], metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {}


class DefaultContextEngine(ContextEngine):
    _INJECTION_PATTERNS = [
        (re.compile(r"ignore\\s+(previous|all|above|prior)\\s+instructions", re.I), "prompt_injection"),
        (re.compile(r"do\\s+not\\s+tell\\s+the\\s+user", re.I), "deception_hide"),
        (re.compile(r"system\\s+prompt\\s+override", re.I), "sys_prompt_override"),
    ]
    _INVISIBLE_CHARS = {
        "\u200b",
        "\u200c",
        "\u200d",
        "\u2060",
        "\ufeff",
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
    }
    _MAX_CONTEXT_CHARS = 20_000

    def __init__(self) -> None:
        # naive cache: {repo_root: (mtime, content, path)}
        self._cache: Dict[str, Tuple[float, str, str]] = {}
        self._cache_max = 16

    def apply(self, *, messages: List[Message], metadata: Dict[str, Any], repo_root: Optional[str]) -> ContextResult:
        msgs = list(messages or [])
        meta = dict(metadata or {})

        # Project context is optional; even when absent, we still allow:
        # - session search injection
        # - deterministic compaction
        if str(meta.get("enable_project_context", "")).lower() not in ("0", "false", "no") and repo_root:
            content, used_path, blocked_reason = self._load_project_context(repo_root)
            if blocked_reason:
                meta["project_context_blocked"] = blocked_reason
                meta["project_context_file"] = used_path
                meta["repo_root"] = str(repo_root)
            elif content and used_path:
                # Avoid duplication if caller already injected it.
                if not (
                    msgs
                    and isinstance(msgs[0], dict)
                    and msgs[0].get("role") == "system"
                    and "# Project Context" in str(msgs[0].get("content", ""))
                ):
                    msgs = [
                        {
                            "role": "system",
                            "content": f"# Project Context\n\n{content}",
                            "metadata": {"layer": "stable", "kind": "project_context"},
                        }
                    ] + msgs
                meta["project_context_file"] = used_path
                meta["repo_root"] = str(repo_root)
                meta["project_context_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Roadmap-4 (P0): optional session search injection (cross-session memory).
        session_sha = None
        if os.getenv("AIPLAT_ENABLE_SESSION_SEARCH", "false").lower() in ("1", "true", "yes", "y"):
            try:
                from core.harness.kernel.execution_context import get_active_request_context
                from core.harness.kernel.runtime import get_kernel_runtime

                rctx = get_active_request_context()
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                if rctx and store:
                    q = self._extract_last_user_query(msgs)
                    if q:
                        items = self._search_session_messages_sync(
                            db_path=getattr(getattr(store, "_config", None), "db_path", None),
                            query=q,
                            user_id=rctx.user_id,
                            limit=3,
                        )
                        if items:
                            ids = [str(x.get("id")) for x in items if x.get("id")]
                            session_sha = hashlib.sha256(("|".join(ids)).encode("utf-8")).hexdigest()
                            meta["session_search_hits"] = len(items)
                            meta["session_search_ids"] = ids
                            # Inject as system message (ephemeral overlay)
                            snippet_lines = []
                            for it in items:
                                sid = it.get("session_id")
                                role = it.get("role")
                                c = str(it.get("content") or "")
                                snippet_lines.append(f"- ({sid}/{role}) {c}")
                            inject = {
                                "role": "system",
                                "content": "# Session Search\n\n" + "\n".join(snippet_lines),
                                "metadata": {"layer": "ephemeral", "kind": "session_search"},
                            }
                            # Put after project context if present, else as first system message.
                            if msgs and msgs[0].get("role") == "system" and "# Project Context" in str(msgs[0].get("content", "")):
                                msgs = [msgs[0], inject] + msgs[1:]
                            else:
                                msgs = [inject] + msgs
            except Exception:
                session_sha = None

        # Optional compaction (deterministic, non-LLM).
        if self.should_compact(messages=msgs, metadata=meta):
            cr = self.compact(messages=msgs, metadata=meta)
            msgs, meta = cr.messages, cr.metadata

        return self._finalize(msgs, meta, project_sha=meta.get("project_context_sha256"), session_sha=session_sha)

    def _finalize(
        self,
        msgs: List[Message],
        meta: Dict[str, Any],
        *,
        project_sha: Optional[str],
        session_sha: Optional[str],
    ) -> ContextResult:
        # Roadmap-1: provide a stable hash for prompt caching.
        base = f"proj:{project_sha or ''}|sess:{session_sha or ''}"
        w_hash = hashlib.sha256(base.encode("utf-8")).hexdigest()
        meta.setdefault("workspace_context_hash", w_hash)
        status = self.get_status(messages=msgs, metadata=meta)
        return ContextResult(messages=msgs, metadata=meta, status=status, workspace_context_hash=w_hash)

    def _extract_last_user_query(self, msgs: List[Message]) -> Optional[str]:
        for m in reversed(msgs or []):
            if isinstance(m, dict) and m.get("role") == "user":
                t = str(m.get("content") or "").strip()
                return t if t else None
        return None

    def _search_session_messages_sync(self, *, db_path: Optional[str], query: str, user_id: str, limit: int) -> List[Dict[str, Any]]:
        """
        Best-effort session search (sync, SQLite).
        We keep ContextEngine synchronous; avoid awaiting ExecutionStore methods.
        """
        if not db_path or not query:
            return []
        try:
            import sqlite3

            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                q = str(query or "").strip()
                uid = str(user_id or "system")
                # Prefer FTS; fallback to LIKE.
                try:
                    q_fts = q.replace('"', '""')
                    rows = conn.execute(
                        """
                        SELECT id,user_id,session_id,role,content FROM memory_messages_fts
                        WHERE memory_messages_fts MATCH ?
                          AND user_id = ?
                        LIMIT ?;
                        """,
                        (q_fts, uid, int(limit)),
                    ).fetchall()
                    return [
                        {
                            "id": r["id"],
                            "user_id": r["user_id"],
                            "session_id": r["session_id"],
                            "role": r["role"],
                            "content": str(r["content"] or "")[:200],
                            "score": 1.0,
                        }
                        for r in rows
                    ]
                except Exception:
                    pass
                like = f"%{q}%"
                rows = conn.execute(
                    """
                    SELECT id,user_id,session_id,role,content FROM memory_messages
                    WHERE user_id = ? AND content LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?;
                    """,
                    (uid, like, int(limit)),
                ).fetchall()
                return [
                    {
                        "id": r["id"],
                        "user_id": r["user_id"],
                        "session_id": r["session_id"],
                        "role": r["role"],
                        "content": str(r["content"] or "")[:200],
                        "score": 1.0,
                    }
                    for r in rows
                ]
            finally:
                conn.close()
        except Exception:
            return []

    def _estimate_tokens(self, msgs: List[Message]) -> int:
        total_chars = 0
        for m in msgs or []:
            try:
                total_chars += len(str(m.get("content") or ""))
            except Exception:
                pass
        return int(total_chars / 4) + 1

    def should_compact(self, *, messages: List[Message], metadata: Dict[str, Any]) -> bool:
        try:
            token_limit = int(os.getenv("AIPLAT_CONTEXT_TOKEN_LIMIT", "24000") or "24000")
            max_messages = int(os.getenv("AIPLAT_CONTEXT_MAX_MESSAGES", "120") or "120")
        except Exception:
            token_limit, max_messages = 24000, 120
        est = self._estimate_tokens(messages)
        return est > token_limit or len(messages or []) > max_messages

    def compact(self, *, messages: List[Message], metadata: Dict[str, Any]) -> ContextResult:
        """
        Deterministic compaction (no LLM):
        - Keep leading system messages
        - Keep last K messages
        - Summarize the middle as a system note
        """
        meta = dict(metadata or {})
        msgs = list(messages or [])
        try:
            keep_last = int(os.getenv("AIPLAT_CONTEXT_KEEP_LAST", "30") or "30")
        except Exception:
            keep_last = 30
        # Split head system messages
        head: List[Message] = []
        i = 0
        while i < len(msgs) and isinstance(msgs[i], dict) and msgs[i].get("role") == "system":
            head.append(msgs[i])
            i += 1
        tail = msgs[max(i, len(msgs) - keep_last) :]
        middle = msgs[i : max(i, len(msgs) - keep_last)]
        if middle:
            lines = []
            for m in middle[-10:]:
                role = m.get("role")
                c = str(m.get("content") or "")
                c = c.replace("\n", " ").strip()
                if len(c) > 120:
                    c = c[:117] + "..."
                lines.append(f"- {role}: {c}")
            summary = {
                "role": "system",
                "content": "# Context Summary\n\n[TRUNCATED {} messages]\n{}".format(len(middle), "\n".join(lines)),
            }
            msgs2 = head + [summary] + tail
        else:
            msgs2 = head + tail
        meta["context_compacted"] = True
        meta["context_compaction_keep_last"] = keep_last
        meta["context_compaction_truncated"] = len(middle)
        return ContextResult(messages=msgs2, metadata=meta)

    def get_status(self, *, messages: List[Message], metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "message_count": len(messages or []),
            "estimated_tokens": self._estimate_tokens(messages),
            "project_context_file": metadata.get("project_context_file"),
            "project_context_blocked": metadata.get("project_context_blocked"),
            "workspace_context_hash": metadata.get("workspace_context_hash"),
            "context_compacted": bool(metadata.get("context_compacted")),
        }

    def _load_project_context(self, repo_root: str) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Load project context from repo root (best-effort).

        Search order (first hit wins):
        - AGENTS.md
        - AIPLAT.md
        - .aiplat.md

        Returns: (content, used_path, blocked_reason)
        """
        root = Path(str(repo_root)).expanduser()
        candidates = [root / "AGENTS.md", root / "AIPLAT.md", root / ".aiplat.md"]
        for p in candidates:
            try:
                if not p.is_file():
                    continue
                mtime = p.stat().st_mtime
                cache_key = f"{root}:{p.name}"
                if cache_key in self._cache:
                    cached_mtime, cached_content, cached_path = self._cache[cache_key]
                    if cached_mtime == mtime:
                        return cached_content, cached_path, None

                text = p.read_text(encoding="utf-8", errors="replace").strip()
                if not text:
                    continue
                text, blocked = self._scan_project_context(text)
                if blocked:
                    return "", str(p), blocked
                if len(text) > self._MAX_CONTEXT_CHARS:
                    text = text[: self._MAX_CONTEXT_CHARS] + "\n\n[TRUNCATED]"

                self._cache[cache_key] = (mtime, text, str(p))
                if len(self._cache) > self._cache_max:
                    # drop oldest entry
                    try:
                        oldest = sorted(self._cache.items(), key=lambda kv: kv[1][0])[0][0]
                        self._cache.pop(oldest, None)
                    except Exception:
                        self._cache = dict(list(self._cache.items())[-self._cache_max :])
                return text, str(p), None
            except Exception:
                continue
        return "", None, None

    def _scan_project_context(self, content: str) -> Tuple[str, Optional[str]]:
        findings: List[str] = []
        for ch in self._INVISIBLE_CHARS:
            if ch in content:
                findings.append(f"invisible_unicode_U+{ord(ch):04X}")
        for pat, reason in self._INJECTION_PATTERNS:
            if pat.search(content):
                findings.append(reason)
        if findings:
            # Block injection-like content: do not feed into LLM.
            return "", ",".join(findings)
        return content, None
