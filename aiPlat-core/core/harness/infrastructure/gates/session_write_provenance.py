"""Session write provenance — OpenWorker-inspired (OPE-114 lightweight).

Tracks paths the agent *wrote or downloaded this session*. When a later shell/code
tool executes one of those paths, ApprovalGate escalates to a hard floor: the
reviewer (and a human) cannot see file contents, so "python setup.py" after the
agent just wrote setup.py must not auto-run.

Misses leave behaviour unchanged (fail toward caution when we *do* know).
"""
from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

ORIGIN_WRITTEN = "written"
ORIGIN_DOWNLOADED = "downloaded"

_SCRIPT_SUFFIXES = frozenset(
    {
        ".py",
        ".sh",
        ".bash",
        ".zsh",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".rb",
        ".pl",
        ".php",
        ".ps1",
        ".bat",
        ".cmd",
    }
)

# Interpreters / runners whose next path-like arg is the script being executed.
_EXEC_PREFIXES = frozenset(
    {
        "python",
        "python3",
        "python2",
        "node",
        "nodejs",
        "deno",
        "bun",
        "bash",
        "sh",
        "zsh",
        "dash",
        "ksh",
        "fish",
        "ruby",
        "perl",
        "php",
        "pwsh",
        "powershell",
    }
)


@dataclass
class OriginRecord:
    path: str
    origin: str
    step: int
    at: float = field(default_factory=time.time)


class SessionWriteProvenance:
    """In-process store keyed by session_id (best-effort, not cross-host)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_session: Dict[str, Dict[str, OriginRecord]] = {}
        self._steps: Dict[str, int] = {}

    def _sid(self, session_id: str) -> str:
        return str(session_id or "").strip() or "default"

    def _norm(self, path: str) -> str:
        try:
            return os.path.realpath(os.path.abspath(str(path)))
        except OSError:
            return str(path)

    def record(
        self,
        session_id: str,
        path: str,
        *,
        origin: str = ORIGIN_WRITTEN,
    ) -> None:
        if not path:
            return
        sid = self._sid(session_id)
        norm = self._norm(path)
        with self._lock:
            step = self._steps.get(sid, 0) + 1
            self._steps[sid] = step
            bucket = self._by_session.setdefault(sid, {})
            bucket[norm] = OriginRecord(path=norm, origin=origin, step=step)

    def lookup(self, session_id: str, path: str) -> Optional[OriginRecord]:
        if not path:
            return None
        sid = self._sid(session_id)
        norm = self._norm(path)
        with self._lock:
            return self._by_session.get(sid, {}).get(norm)

    def clear(self, session_id: Optional[str] = None) -> None:
        with self._lock:
            if session_id is None:
                self._by_session.clear()
                self._steps.clear()
            else:
                sid = self._sid(session_id)
                self._by_session.pop(sid, None)
                self._steps.pop(sid, None)

    def known_paths(self, session_id: str) -> Set[str]:
        sid = self._sid(session_id)
        with self._lock:
            return set(self._by_session.get(sid, {}).keys())


_store: Optional[SessionWriteProvenance] = None
_store_lock = threading.Lock()


def get_session_write_provenance() -> SessionWriteProvenance:
    global _store
    with _store_lock:
        if _store is None:
            _store = SessionWriteProvenance()
        return _store


def _reset_session_write_provenance() -> None:
    """Test helper — drop singleton."""
    global _store
    with _store_lock:
        _store = None


def record_session_write(
    path: str,
    *,
    session_id: str = "",
    trace_context: Optional[dict] = None,
    origin: str = ORIGIN_WRITTEN,
) -> None:
    """Best-effort record from sys_file_* / tool wrappers."""
    sid = session_id
    if not sid and isinstance(trace_context, dict):
        sid = str(
            trace_context.get("session_id")
            or trace_context.get("run_id")
            or trace_context.get("_session_id")
            or ""
        )
    if not sid:
        try:
            from core.harness.kernel.execution_context import get_active_request_context

            arq = get_active_request_context()
            if arq is not None:
                sid = str(
                    getattr(arq, "session_id", None)
                    or getattr(arq, "run_id", None)
                    or ""
                )
        except Exception as e:
            import logging

            logging.getLogger(__name__).debug(
                "session_id from request context skipped: %s", e, exc_info=True,
            )
    try:
        get_session_write_provenance().record(sid, path, origin=origin)
    except Exception as e:
        import logging

        logging.getLogger(__name__).debug(
            "record_session_write skipped: %s", e, exc_info=True,
        )


def _tokenize(command: str) -> List[str]:
    try:
        import shlex

        return [t for t in shlex.split(command, posix=True) if t]
    except ValueError:
        return command.split()


def extract_executable_paths(command: str) -> List[str]:
    """Heuristic: script-like tokens and interpreter-following paths."""
    text = str(command or "").strip()
    if not text:
        return []
    toks = _tokenize(text)
    found: List[str] = []
    for i, tok in enumerate(toks):
        bare = tok.rsplit("/", 1)[-1]
        prog = bare.lower()
        # ./script.sh or path with script suffix
        suffix = Path(tok).suffix.lower()
        if suffix in _SCRIPT_SUFFIXES or (tok.startswith("./") and "/" in tok[2:]):
            found.append(tok)
        if prog in _EXEC_PREFIXES and i + 1 < len(toks):
            nxt = toks[i + 1]
            if not nxt.startswith("-"):
                found.append(nxt)
        # bare `script.py` without interpreter
        if re.match(r"^[\w./\\-]+\.(py|sh|js|ts|rb|pl)$", tok):
            found.append(tok)
    # Dedup preserve order
    seen: Set[str] = set()
    out: List[str] = []
    for p in found:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def provenance_forces_hard_floor(
    *,
    session_id: str,
    command: str,
) -> Optional[OriginRecord]:
    """If command executes a path written this session, return that origin."""
    store = get_session_write_provenance()
    for raw in extract_executable_paths(command):
        # Resolve relative to cwd best-effort
        candidates = [raw]
        if not os.path.isabs(raw):
            candidates.append(os.path.abspath(raw))
        for c in candidates:
            rec = store.lookup(session_id, c)
            if rec is not None:
                return rec
    return None
