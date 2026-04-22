"""
Exec Drivers (P1-1).

Provide pluggable execution backends for running code/scripts:
- local: subprocess on host
- docker: isolated container execution (no network by default)
"""

from .base import ExecDriver, ExecResult

__all__ = [
    "ExecDriver",
    "ExecResult",
]
