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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


Message = Dict[str, Any]


@dataclass
class ContextResult:
    messages: List[Message]
    metadata: Dict[str, Any]


class ContextEngine:
    def apply(self, *, messages: List[Message], metadata: Dict[str, Any], repo_root: Optional[str]) -> ContextResult:
        raise NotImplementedError


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

        if str(meta.get("enable_project_context", "")).lower() in ("0", "false", "no"):
            return ContextResult(messages=msgs, metadata=meta)
        if not repo_root:
            return ContextResult(messages=msgs, metadata=meta)

        content, used_path, blocked_reason = self._load_project_context(repo_root)
        if blocked_reason:
            meta["project_context_blocked"] = blocked_reason
            meta["project_context_file"] = used_path
            meta["repo_root"] = str(repo_root)
            return ContextResult(messages=msgs, metadata=meta)

        if content and used_path:
            # Avoid duplication if caller already injected it.
            if not (
                msgs
                and isinstance(msgs[0], dict)
                and msgs[0].get("role") == "system"
                and "# Project Context" in str(msgs[0].get("content", ""))
            ):
                msgs = [{"role": "system", "content": f"# Project Context\n\n{content}"}] + msgs
            meta["project_context_file"] = used_path
            meta["repo_root"] = str(repo_root)
            meta["project_context_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()

        return ContextResult(messages=msgs, metadata=meta)

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

