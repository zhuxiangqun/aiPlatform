"""
_trace.py — Phase 46: Lightweight syscall entry tracing.

Adds `trace_syscall_entry("sys_xxx")` at each syscall entry point.
When AIPLAT_SYSCALL_TRACE=true, writes a JSONL line with:
  {syscall, timestamp, caller_module}

Used for runtime verification: "which consumers are actually calling
through the syscall layer, and which are bypassing it?"
"""

import json
import os
import time
import inspect as _inspect

_TRACE_ENABLED = os.getenv("AIPLAT_SYSCALL_TRACE", "false").lower() in ("1", "true", "yes")
_TRACE_FILE = os.path.expanduser("~/.aiplat/traces/syscall_calls.jsonl")


def trace_syscall_entry(name: str) -> None:
    if not _TRACE_ENABLED:
        return
    try:
        caller = _inspect.stack()[2]
        caller_module = caller.filename.replace(os.path.expanduser("~"), "~")
    except Exception:
        caller_module = "unknown"

    entry = {
        "syscall": name,
        "timestamp": time.time(),
        "caller": caller_module,
    }
    os.makedirs(os.path.dirname(_TRACE_FILE), exist_ok=True)
    with open(_TRACE_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
