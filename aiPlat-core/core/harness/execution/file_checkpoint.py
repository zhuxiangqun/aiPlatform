"""
FileCheckpoint — filesystem-level "physical safety net" (Hermes Layer 1).

Captures the *content* of a file right before a mutating syscall (write/edit)
overwrites it, so a corrupted or wrongly-edited file can be restored to its
pre-mutation state. This complements ExecutionSnapshot (which captures pipeline
*state*) by covering the actual workspace files.

Design (aligned with the Hermes checkpoint philosophy):
  - Auto-triggered before dangerous operations (file write/edit).
  - Lightweight: content-hash dedup — identical consecutive versions are not
    re-stored; large files are skipped.
  - Bounded retention: newest N checkpoints per path.
  - Best-effort: checkpoint failures never block the underlying write.

Storage: ~/.aiplat/file_checkpoints/{session_id}/{checkpoint_id}.{header.json,content}
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.file_checkpoint")

CHECKPOINT_ROOT = os.path.expanduser("~/.aiplat/file_checkpoints")
MAX_FILE_BYTES = 1_048_576          # 1 MB — skip larger files (Hermes: large files auto-skipped)
MAX_CHECKPOINTS_PER_PATH = 50       # bounded retention per file path


def _enabled() -> bool:
    return os.getenv("AIPLAT_FILE_CHECKPOINT_ENABLED", "true").lower() not in ("0", "false", "no")


def _sanitize_session(session_id: str) -> str:
    s = (session_id or "default").strip() or "default"
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def _session_dir(session_id: str) -> str:
    path = os.path.join(CHECKPOINT_ROOT, _sanitize_session(session_id))
    os.makedirs(path, exist_ok=True)
    return path


def _path_key(abs_path: str) -> str:
    return hashlib.sha256(abs_path.encode()).hexdigest()[:12]


@dataclass
class FileCheckpoint:
    checkpoint_id: str
    session_id: str
    path: str                # absolute original path
    content_hash: str
    size: int
    reason: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def checkpoint_file(
    path: str,
    *,
    session_id: str = "",
    reason: str = "",
) -> Optional[str]:
    """Back up the current content of an existing file. Returns checkpoint_id or None.

    No-op (returns None) when: disabled, file missing, too large, or unchanged
    since the last checkpoint (content-hash dedup). Never raises.
    """
    if not _enabled():
        return None
    try:
        abs_path = os.path.realpath(os.path.abspath(path))
        if not os.path.isfile(abs_path):
            return None
        size = os.path.getsize(abs_path)
        if size > MAX_FILE_BYTES:
            logger.debug("file_checkpoint: skip large file (%d bytes): %s", size, abs_path)
            return None

        with open(abs_path, "rb") as f:
            raw = f.read()
        content_hash = hashlib.sha256(raw).hexdigest()

        sess = session_id or "default"
        dstdir = _session_dir(sess)
        pkey = _path_key(abs_path)

        # Dedup: if the newest checkpoint for this path has the same hash, skip.
        existing = _list_headers(dstdir, path_key=pkey)
        if existing and existing[0].get("content_hash") == content_hash:
            return None

        ts = time.time()
        cid = hashlib.sha256(f"{abs_path}:{content_hash}:{ts}".encode()).hexdigest()[:16]
        base = os.path.join(dstdir, f"{pkey}.{cid}")

        with open(base + ".content", "wb") as f:
            f.write(raw)
        snap = FileCheckpoint(
            checkpoint_id=cid, session_id=sess, path=abs_path,
            content_hash=content_hash, size=size, reason=reason, timestamp=ts,
        )
        with open(base + ".header.json", "w", encoding="utf-8") as f:
            json.dump(snap.to_dict(), f, ensure_ascii=False, indent=2)

        _prune_path(dstdir, pkey, max_keep=MAX_CHECKPOINTS_PER_PATH)
        logger.info("[file_checkpoint] saved id=%s path=%s reason=%s", cid, abs_path, reason)
        return cid
    except Exception as e:
        logger.debug("file_checkpoint: failed for %s: %s", path, e)
        return None


def _list_headers(dstdir: str, *, path_key: str = "") -> List[Dict[str, Any]]:
    if not os.path.isdir(dstdir):
        return []
    out = []
    prefix = f"{path_key}." if path_key else ""
    for fname in os.listdir(dstdir):
        if not fname.endswith(".header.json"):
            continue
        if prefix and not fname.startswith(prefix):
            continue
        try:
            with open(os.path.join(dstdir, fname), "r", encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            continue
    out.sort(key=lambda h: h.get("timestamp", 0), reverse=True)
    return out


def list_file_checkpoints(*, session_id: str = "", path: str = "") -> List[Dict[str, Any]]:
    """List file checkpoints for a session (newest first), optionally filtered by path."""
    dstdir = _session_dir(session_id or "default")
    pkey = _path_key(os.path.realpath(os.path.abspath(path))) if path else ""
    headers = _list_headers(dstdir, path_key=pkey)
    for h in headers:
        h["age_seconds"] = round(time.time() - h.get("timestamp", 0), 1)
    return headers


def _find_header(checkpoint_id: str, session_id: str) -> Optional[Dict[str, Any]]:
    dstdir = _session_dir(session_id or "default")
    for h in _list_headers(dstdir):
        if h.get("checkpoint_id") == checkpoint_id:
            return h
    return None


def get_file_checkpoint(checkpoint_id: str, session_id: str = "") -> Optional[Dict[str, Any]]:
    """Return a checkpoint header + its stored content (decoded best-effort)."""
    header = _find_header(checkpoint_id, session_id)
    if header is None:
        return None
    dstdir = _session_dir(session_id or "default")
    pkey = _path_key(header["path"])
    content_path = os.path.join(dstdir, f"{pkey}.{checkpoint_id}.content")
    content = None
    if os.path.isfile(content_path):
        try:
            with open(content_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            content = None
    return {**header, "content": content}


def restore_file_checkpoint(checkpoint_id: str, session_id: str = "") -> Dict[str, Any]:
    """Restore a file to the content captured in the given checkpoint.

    Writes the stored bytes back to the original path. Returns a result dict.
    """
    header = _find_header(checkpoint_id, session_id)
    if header is None:
        return {"success": False, "error": "checkpoint_not_found", "checkpoint_id": checkpoint_id}
    dstdir = _session_dir(session_id or "default")
    pkey = _path_key(header["path"])
    content_path = os.path.join(dstdir, f"{pkey}.{checkpoint_id}.content")
    if not os.path.isfile(content_path):
        return {"success": False, "error": "checkpoint_content_missing", "checkpoint_id": checkpoint_id}
    try:
        with open(content_path, "rb") as f:
            raw = f.read()
        target = header["path"]
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(raw)
        logger.info("[file_checkpoint] restored id=%s path=%s", checkpoint_id, target)
        return {"success": True, "checkpoint_id": checkpoint_id, "path": target,
                "bytes_restored": len(raw)}
    except Exception as e:
        return {"success": False, "error": str(e), "checkpoint_id": checkpoint_id}


def _prune_path(dstdir: str, path_key: str, max_keep: int = 50) -> None:
    headers = _list_headers(dstdir, path_key=path_key)
    for old in headers[max_keep:]:
        cid = old.get("checkpoint_id", "")
        for ext in (".header.json", ".content"):
            p = os.path.join(dstdir, f"{path_key}.{cid}{ext}")
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass  # noqa: cleanup-best-effort


__all__ = [
    "FileCheckpoint",
    "checkpoint_file",
    "list_file_checkpoints",
    "get_file_checkpoint",
    "restore_file_checkpoint",
    "CHECKPOINT_ROOT",
    "MAX_FILE_BYTES",
]

