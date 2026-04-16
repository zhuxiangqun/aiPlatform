"""
Kernel runtime registry (Phase 3).

Goal:
- Provide a minimal global access point for KernelRuntime so syscalls can access
  runtime dependencies (TraceService, ApprovalManager, ExecutionStore) without
  importing server.py or creating circular imports.
"""

from __future__ import annotations

from typing import Optional, Any

_runtime: Optional[Any] = None


def set_kernel_runtime(runtime: Any) -> None:
    global _runtime
    _runtime = runtime


def get_kernel_runtime() -> Optional[Any]:
    return _runtime

