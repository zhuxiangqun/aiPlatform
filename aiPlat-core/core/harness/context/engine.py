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
import json
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
        (re.compile(r"ignore\s+(previous|all|above|prior)\s+instructions", re.I), "prompt_injection"),
        (re.compile(r"do\s+not\s+tell\s+the\s+user", re.I), "deception_hide"),
        (re.compile(r"system\s+prompt\s+override", re.I), "sys_prompt_override"),
        # common exfil / jailbreak wording
        (re.compile(r"(exfiltrate|leak|steal)\\s+(secrets?|keys?|tokens?)", re.I), "exfiltration_attempt"),
        (re.compile(r"(upload|send)\\s+.*(to|into)\\s+https?://", re.I), "url_exfiltration"),
        (re.compile(r"BEGIN\\s+PRIVATE\\s+KEY", re.I), "embedded_private_key"),
        (re.compile(r"api[_-]?key\\s*[:=]", re.I), "secret_mention"),
        # encoding/obfuscation hints
        (re.compile(r"base64\\s*[:=]|-----BEGIN", re.I), "encoding_or_pem"),
        (re.compile(r"\\b[a-f0-9]{32,}\\b", re.I), "suspicious_hex_blob"),
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
        status: Dict[str, Any] = {
            "context_engine": "default_v1",
            "project_context": {"enabled": False, "injected": False},
            "session_search": {"enabled": False, "injected": False, "hits": 0},
            "compaction": {"applied": False},
            "budgets": {"max_context_chars": int(self._MAX_CONTEXT_CHARS)},
        }

        # Project context is optional; even when absent, we still allow:
        # - session search injection
        # - deterministic compaction
        if str(meta.get("enable_project_context", "")).lower() not in ("0", "false", "no") and repo_root:
            status["project_context"]["enabled"] = True
            content, used_path, decision = self._load_project_context(repo_root)
            if isinstance(decision, dict) and decision.get("action") in {"block", "approval_required"}:
                meta["project_context_blocked"] = ",".join(decision.get("findings") or []) if decision.get("findings") else decision.get("action")
                meta["project_context_block_policy"] = decision.get("action")
                if decision.get("approval_request_id"):
                    meta["project_context_approval_request_id"] = decision.get("approval_request_id")
                meta["project_context_file"] = used_path
                meta["repo_root"] = str(repo_root)
                status["project_context"].update(
                    {
                        "injected": False,
                        "file": used_path,
                        "blocked": True,
                        "blocked_policy": decision.get("action"),
                        "findings": decision.get("findings") or [],
                    }
                )
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
                status["project_context"].update(
                    {
                        "injected": True,
                        "file": used_path,
                        "sha256": meta.get("project_context_sha256"),
                        "chars": len(content),
                    }
                )
                if isinstance(decision, dict) and decision.get("action") == "warn":
                    meta["project_context_warn"] = decision.get("findings") or []
                    status["project_context"]["warn_findings"] = decision.get("findings") or []
                if isinstance(decision, dict) and decision.get("action") == "truncate":
                    meta["project_context_truncated"] = True
                    status["project_context"]["truncated"] = True

        # Roadmap-4 (P0): optional session search injection (cross-session memory).
        session_sha = None
        if os.getenv("AIPLAT_ENABLE_SESSION_SEARCH", "false").lower() in ("1", "true", "yes", "y"):
            status["session_search"]["enabled"] = True
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
                            status["session_search"].update(
                                {"injected": True, "hits": int(len(items)), "sha256": session_sha, "ids": ids}
                            )
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
                status["session_search"]["error"] = "failed"

        # Optional compaction (deterministic, non-LLM).
        reasons: List[str] = []
        try:
            token_limit = int(os.getenv("AIPLAT_CONTEXT_TOKEN_LIMIT", "24000") or "24000")
            max_messages = int(os.getenv("AIPLAT_CONTEXT_MAX_MESSAGES", "120") or "120")
            char_limit = int(os.getenv("AIPLAT_CONTEXT_CHAR_LIMIT", "80000") or "80000")
        except Exception:
            token_limit, max_messages, char_limit = 24000, 120, 80000
        try:
            est_tokens = self._estimate_tokens(msgs)
            est_chars = self._estimate_chars(msgs)
            if est_tokens > token_limit:
                reasons.append("token_limit")
            if len(msgs) > max_messages:
                reasons.append("max_messages")
            if est_chars > char_limit:
                reasons.append("char_limit")
            status["compaction"].update(
                {
                    "limits": {"token_limit": token_limit, "max_messages": max_messages, "char_limit": char_limit},
                    "observed": {"tokens_est": est_tokens, "chars": est_chars, "messages": len(msgs)},
                    "reasons": reasons,
                }
            )
        except Exception:
            pass

        if reasons and self.should_compact(messages=msgs, metadata=meta):
            cr = self.compact(messages=msgs, metadata=meta)
            msgs, meta = cr.messages, cr.metadata
            status["compaction"]["applied"] = True
            if isinstance(meta.get("context_compaction"), dict):
                status["compaction"].update(meta.get("context_compaction") or {})

        status["budgets"]["messages"] = len(msgs)
        try:
            status["budgets"]["system_chars"] = sum(
                len(str(m.get("content") or "")) for m in msgs if isinstance(m, dict) and m.get("role") == "system"
            )
        except Exception:
            pass
        try:
            total_chars = sum(len(str(m.get("content") or "")) for m in msgs if isinstance(m, dict))
            status["budgets"]["total_chars"] = int(total_chars)
            # naive token estimate (keeps deps minimal): ~4 chars/token for English-like text
            status["budgets"]["token_estimate"] = int(total_chars // 4) if total_chars else 0
        except Exception:
            pass

        fin = self._finalize(msgs, meta, project_sha=meta.get("project_context_sha256"), session_sha=session_sha)
        # attach status produced during apply
        fin.status = status
        return fin

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

    def _estimate_chars(self, msgs: List[Message]) -> int:
        total_chars = 0
        for m in msgs or []:
            try:
                total_chars += len(str(m.get("content") or ""))
            except Exception:
                pass
        return int(total_chars)

    def _hash_messages(self, msgs: List[Message]) -> str:
        """
        Stable-ish hash for observability (not for security).
        """
        try:
            parts: List[str] = []
            for m in msgs or []:
                if not isinstance(m, dict):
                    continue
                role = str(m.get("role") or "")
                content = str(m.get("content") or "")
                parts.append(f"{role}:{content}")
            return hashlib.sha256(("\n---\n".join(parts)).encode("utf-8")).hexdigest()
        except Exception:
            return ""

    def should_compact(self, *, messages: List[Message], metadata: Dict[str, Any]) -> bool:
        try:
            token_limit = int(os.getenv("AIPLAT_CONTEXT_TOKEN_LIMIT", "24000") or "24000")
            max_messages = int(os.getenv("AIPLAT_CONTEXT_MAX_MESSAGES", "120") or "120")
            char_limit = int(os.getenv("AIPLAT_CONTEXT_CHAR_LIMIT", "80000") or "80000")
        except Exception:
            token_limit, max_messages, char_limit = 24000, 120, 80000
        est = self._estimate_tokens(messages)
        ch = self._estimate_chars(messages)
        return est > token_limit or len(messages or []) > max_messages or ch > char_limit

    def compact(self, *, messages: List[Message], metadata: Dict[str, Any]) -> ContextResult:
        """
        Deterministic compaction (no LLM):
        - Keep leading system messages
        - Keep last K messages
        - Summarize the middle as a system note (hash + truncated snippets)
        - If too many system messages, summarize excess system messages as a single note
        - Emit compaction stats for observability (before/after hash, chars, tokens, drops)
        """
        meta = dict(metadata or {})
        msgs = list(messages or [])

        try:
            keep_last = int(os.getenv("AIPLAT_CONTEXT_KEEP_LAST", "30") or "30")
        except Exception:
            keep_last = 30
        try:
            keep_system = int(os.getenv("AIPLAT_CONTEXT_KEEP_SYSTEM", "6") or "6")
        except Exception:
            keep_system = 6
        try:
            summary_max_chars = int(os.getenv("AIPLAT_CONTEXT_SUMMARY_MAX_CHARS", "2000") or "2000")
        except Exception:
            summary_max_chars = 2000

        before_hash = self._hash_messages(msgs)
        before_chars = self._estimate_chars(msgs)
        before_tokens = self._estimate_tokens(msgs)

        # Split head system messages
        head: List[Message] = []
        i = 0
        while i < len(msgs) and isinstance(msgs[i], dict) and msgs[i].get("role") == "system":
            head.append(msgs[i])
            i += 1

        # Summarize excess system messages (keep first keep_system)
        head_kept = head[:keep_system]
        head_dropped = head[keep_system:]
        sys_summary_msg: Optional[Message] = None
        if head_dropped:
            lines: List[str] = []
            for m in head_dropped[-10:]:
                c = str(m.get("content") or "")
                c = c.replace("\n", " ").strip()
                if len(c) > 120:
                    c = c[:117] + "..."
                lines.append(f"- system: {c}")
            sys_blob = "\n".join(lines)
            sys_summary_msg = {
                "role": "system",
                "content": "# System Messages Summary\n\n[TRUNCATED {} system messages]\n{}".format(len(head_dropped), sys_blob),
                "metadata": {"layer": "stable", "kind": "system_summary"},
            }

        tail = msgs[max(i, len(msgs) - keep_last) :]
        middle = msgs[i : max(i, len(msgs) - keep_last)]

        summary_msg: Optional[Message] = None
        if middle:
            lines: List[str] = []
            for m in middle[-10:]:
                role = m.get("role")
                c = str(m.get("content") or "")
                c = c.replace("\n", " ").strip()
                if len(c) > 120:
                    c = c[:117] + "..."
                lines.append(f"- {role}: {c}")
            dropped_hash = self._hash_messages(middle)
            content = "# Context Summary\n\n[TRUNCATED {} messages]\n[dropped_sha256:{}]\n{}".format(
                len(middle), dropped_hash[:16], "\n".join(lines)
            )
            if len(content) > summary_max_chars:
                content = content[:summary_max_chars] + "\n…[TRUNCATED]"
            summary_msg = {"role": "system", "content": content, "metadata": {"layer": "ephemeral", "kind": "context_summary"}}

        msgs2: List[Message] = []
        msgs2.extend(head_kept)
        if sys_summary_msg:
            msgs2.append(sys_summary_msg)
        if summary_msg:
            msgs2.append(summary_msg)
        msgs2.extend(tail)

        after_hash = self._hash_messages(msgs2)
        after_chars = self._estimate_chars(msgs2)
        after_tokens = self._estimate_tokens(msgs2)

        meta["context_compacted"] = True
        meta["context_compaction_keep_last"] = keep_last
        meta["context_compaction_truncated"] = len(middle)
        meta["context_compaction"] = {
            "before": {"hash": before_hash, "chars": before_chars, "tokens_est": before_tokens, "messages": len(msgs)},
            "after": {"hash": after_hash, "chars": after_chars, "tokens_est": after_tokens, "messages": len(msgs2)},
            "dropped": {"system": len(head_dropped), "middle": len(middle)},
            "keep": {"system": keep_system, "last": keep_last},
            "summary_max_chars": summary_max_chars,
        }
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

    def _load_project_context(self, repo_root: str) -> Tuple[str, Optional[str], Dict[str, Any]]:
        """
        Load project context from repo root (best-effort).

        Search order (first hit wins):
        - AGENTS.md
        - AIPLAT.md
        - .aiplat.md

        Returns: (content, used_path, decision)
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
                text, decision = self._scan_project_context(text, path=str(p), repo_root=str(root))
                if decision.get("action") in {"block", "approval_required"}:
                    return "", str(p), decision
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
                return text, str(p), decision
            except Exception:
                continue
        return "", None, {"action": "none", "findings": []}

    def _scan_project_context(self, content: str, *, path: str, repo_root: str) -> Tuple[str, Dict[str, Any]]:
        """
        Scan project context file for injection-like content.
        Policy via env AIPLAT_PROJECT_CONTEXT_POLICY:
          - block (default): drop content
          - warn: keep content but record findings
          - truncate: redact suspicious patterns, keep rest
          - approval_required: create approval request (best-effort) and drop content
        """
        policy = os.getenv("AIPLAT_PROJECT_CONTEXT_POLICY", "block").strip().lower() or "block"
        if policy not in {"block", "warn", "truncate", "approval_required"}:
            policy = "block"

        findings: List[str] = []
        for ch in self._INVISIBLE_CHARS:
            if ch in content:
                findings.append(f"invisible_unicode_U+{ord(ch):04X}")
        matched_patterns: List[Tuple[re.Pattern, str]] = []
        for pat, reason in self._INJECTION_PATTERNS:
            try:
                if pat.search(content):
                    findings.append(reason)
                    matched_patterns.append((pat, reason))
            except Exception:
                continue

        decision: Dict[str, Any] = {"action": "none", "findings": findings, "policy": policy, "path": path}
        if not findings:
            return content, decision

        # audit event (best-effort)
        try:
            from core.harness.kernel.runtime import get_kernel_runtime
            from core.harness.kernel.execution_context import get_active_release_context

            rt = get_kernel_runtime()
            store = getattr(rt, "execution_store", None) if rt else None
            ar = get_active_release_context()
            if store is not None:
                store_evt: Dict[str, Any] = {
                    "kind": "context",
                    "name": "project_context_scan",
                    "status": policy if policy != "approval_required" else "approval_required",
                    "error": ",".join(findings),
                    "error_code": "CONTEXT_INJECTION",
                    "args": {"path": path, "repo_root": repo_root, "findings": findings},
                    "target_type": ar.target_type if ar else None,
                    "target_id": ar.target_id if ar else None,
                }
                # ContextEngine is sync; insert directly to sqlite (best-effort) to avoid awaiting.
                try:
                    import sqlite3
                    import uuid
                    import time

                    db_path = getattr(getattr(store, "_config", None), "db_path", None)
                    if db_path:
                        conn = sqlite3.connect(str(db_path))
                        try:
                            conn.execute(
                                """
                                INSERT INTO syscall_events(
                                  id, trace_id, span_id, run_id, kind, name, status, start_time, end_time, duration_ms,
                                  args_json, result_json, error, error_code, target_type, target_id, user_id, session_id,
                                  approval_request_id, created_at
                                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
                                """,
                                (
                                    str(uuid.uuid4()),
                                    None,
                                    None,
                                    None,
                                    store_evt.get("kind"),
                                    store_evt.get("name"),
                                    store_evt.get("status"),
                                    None,
                                    None,
                                    None,
                                    json.dumps(store_evt.get("args") or {}, ensure_ascii=False),
                                    json.dumps(store_evt.get("result") or {}, ensure_ascii=False),
                                    store_evt.get("error"),
                                    store_evt.get("error_code"),
                                    store_evt.get("target_type"),
                                    store_evt.get("target_id"),
                                    store_evt.get("user_id"),
                                    store_evt.get("session_id"),
                                    store_evt.get("approval_request_id"),
                                    float(time.time()),
                                ),
                            )
                            conn.commit()
                        finally:
                            conn.close()
                except Exception:
                    pass
        except Exception:
            pass

        if policy == "warn":
            decision["action"] = "warn"
            return content, decision

        if policy == "truncate":
            # Redact suspicious patterns line-by-line.
            redacted = content
            for pat, _reason in matched_patterns:
                try:
                    redacted = pat.sub("[REDACTED]", redacted)
                except Exception:
                    pass
            decision["action"] = "truncate"
            return redacted, decision

        if policy == "approval_required":
            decision["action"] = "approval_required"
            # Create approval request (best effort).
            try:
                from core.harness.infrastructure.approval.manager import ApprovalManager, ApprovalContext
                from core.harness.kernel.runtime import get_kernel_runtime

                rt = get_kernel_runtime()
                store = getattr(rt, "execution_store", None) if rt else None
                mgr = getattr(rt, "approval_manager", None) if rt else None
                if mgr is None and store is not None:
                    mgr = ApprovalManager(execution_store=store)
                if mgr is not None:
                    ctx = ApprovalContext(
                        user_id="system",
                        operation="project_context_injection",
                        details=f"Project context blocked; findings={findings}; path={path}",
                        amount=None,
                        batch_size=None,
                        is_first_time=True,
                        metadata={"repo_root": repo_root, "path": path, "findings": findings},
                    )
                    req = mgr.create_request(ctx)  # type: ignore[arg-type]
                    decision["approval_request_id"] = getattr(req, "request_id", None) if req else None
            except Exception:
                pass
            return "", decision

        # default: block
        decision["action"] = "block"
        return "", decision
