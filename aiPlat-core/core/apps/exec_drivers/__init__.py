"""
Exec Drivers (P1-1).

Provide pluggable execution backends for running code/scripts:
- local: subprocess on host
- docker: isolated container execution (no network by default)
"""

from .base import ExecDriver, ExecResult
from .registry import get_exec_backend, get_exec_driver, list_exec_backends, healthcheck_backends

__all__ = [
    "ExecDriver",
    "ExecResult",
    "get_exec_backend",
    "get_exec_driver",
    "list_exec_backends",
    "healthcheck_backends",
]

