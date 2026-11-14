"""base：模块接口。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ExecResult:
    """ExecResult。"""
    ok: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    error: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)


class ExecDriver:
    """
    Pluggable execution backend.
    """

    driver_id: str = "base"

    def capabilities(self) -> Dict[str, object]:
        """
        Capability matrix for this backend.

        This is intentionally a plain dict so that:
        - it can be returned directly from diagnostics endpoints
        - callers can add/inspect fields without tight coupling
        """
        return {
            "driver_id": self.driver_id,
            "supported_languages": [],
            "isolation": {
                # best-effort hints (not security guarantees)
                "network_isolated": None,
                "filesystem_isolated": None,
                "process_isolated": None,
            },
            "limits": {},
            "config": {"required": False, "env": []},
            "notes": "",
        }

    async def run_code(self, *, language: str, code: str, timeout_s: float) -> ExecResult:
        """run_code。

        Args:
            language: language 参数。
            code: code 参数。
            timeout_s: timeout_s 参数。
        """
        raise NotImplementedError

    async def health(self) -> Dict[str, object]:
        """health。
        """
        return {"driver_id": self.driver_id, "ok": True, "capabilities": self.capabilities()}
