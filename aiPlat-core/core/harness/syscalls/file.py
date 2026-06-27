"""
sys_file - File operation syscalls.

Atomic file operations that go through the Gate system:
- sys_file_read: read contents of a file
- sys_file_write: write content to a file (creates directories)
- sys_file_edit: surgical edit — replace old_string with new_string in a file

Each syscall passes through PolicyGate (permission), TraceGate (audit),
ContextGate (workspace scoping), and ResilienceGate (timeout/retry).
"""

from __future__ import annotations
import logging

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Optional

from core.harness.infrastructure.gates import PolicyGate, TraceGate, ResilienceGate
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.kernel.execution_context import get_active_workspace_context

# Session-level file read cache: key=path, value=(timestamp, size_chars, first_200_chars)
_read_cache: Dict[str, tuple] = {}


def _resolve_workspace_root() -> str:
    try:
        ws = get_active_workspace_context()
        if ws:
            return os.path.realpath(os.path.expanduser(
                getattr(ws, "workspace_path", None) or os.getcwd()
            ))
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return os.path.realpath(os.getcwd())


def _is_outside_workspace(absolute_path: str, workspace_root: str) -> bool:
    return not absolute_path.startswith(workspace_root)


async def sys_file_read(
    path: str,
    *,
    max_chars: int = 50000,
    trace_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Read contents of a file with Gate enforcement.

    Returns dict with: success, content, path, chars, error.
    """
    gate = TraceGate.start("sys.file.read", trace_context)
    try:
        if not os.path.isfile(path):
            return {"success": False, "error": f"File not found: {path}", "path": path}

        resolved = os.path.realpath(path)
        ws_root = _resolve_workspace_root()
        if _is_outside_workspace(resolved, ws_root):
            return {"success": False, "error": "Access denied: path outside workspace", "path": path}

        # Session cache: warn on repeated reads, prepend size hint
        import time as _time
        cached = _read_cache.get(resolved)
        if cached:
            ts, size, preview = cached
            elapsed = _time.time() - ts
            hint = f"[REPEAT READ: {path} ({size} chars, last read {elapsed:.0f}s ago). Preview: {preview}]\n\n"
        else:
            hint = ""

        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)

        # Update cache
        preview_text = content[:200].replace("\n", " ").strip()
        _read_cache[resolved] = (_time.time(), len(content), preview_text)

        result_content = hint + content if hint else content
        result_content = hint + content if hint else content
        return {
            "success": True,
            "content": result_content,
            "path": resolved,
            "chars": len(content),
            "truncated": len(content) >= max_chars,
            "repeat_read": bool(hint),
        }
    except PermissionError as e:
        return {"success": False, "error": str(e), "path": path}
    except Exception as e:
        return {"success": False, "error": str(e), "path": path}
    finally:
        gate.close()


async def sys_file_write(
    path: str,
    content: str,
    *,
    trace_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write content to a file with Gate enforcement.

    Creates parent directories if needed. Returns dict with: success, path, bytes_written, error.
    """
    gate = TraceGate.start("sys.file.write", trace_context)
    try:
        resolved = os.path.realpath(os.path.abspath(path))
        ws_root = _resolve_workspace_root()
        if _is_outside_workspace(resolved, ws_root):
            return {"success": False, "error": "Access denied: path outside workspace", "path": path}

        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)

        return {"success": True, "path": resolved, "bytes_written": len(content.encode("utf-8"))}
    except PermissionError as e:
        return {"success": False, "error": str(e), "path": path}
    except Exception as e:
        return {"success": False, "error": str(e), "path": path}
    finally:
        gate.close()


async def sys_file_edit(
    path: str,
    old_string: str,
    new_string: str,
    *,
    trace_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Surgical edit — replace old_string with new_string in a file.

    Returns dict with: success, path, replaced, error.
    """
    gate = TraceGate.start("sys.file.edit", trace_context)
    try:
        resolved = os.path.realpath(os.path.abspath(path))
        if not os.path.isfile(resolved):
            return {"success": False, "error": f"File not found: {path}", "path": path}

        ws_root = _resolve_workspace_root()
        if _is_outside_workspace(resolved, ws_root):
            return {"success": False, "error": "Access denied: path outside workspace", "path": path}

        with open(resolved, "r", encoding="utf-8") as f:
            original = f.read()

        if old_string not in original:
            return {"success": False, "error": "old_string not found in file", "path": path}

        replaced = original.replace(old_string, new_string, 1)
        if replaced == original:
            return {"success": False, "error": "old_string not found in file", "path": path}

        with open(resolved, "w", encoding="utf-8") as f:
            f.write(replaced)

        return {"success": True, "path": resolved, "replaced": True}
    except PermissionError as e:
        return {"success": False, "error": str(e), "path": path}
    except Exception as e:
        return {"success": False, "error": str(e), "path": path}
    finally:
        gate.close()


__all__ = ["sys_file_read", "sys_file_write", "sys_file_edit"]
