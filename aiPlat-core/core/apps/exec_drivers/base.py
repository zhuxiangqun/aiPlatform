from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ExecResult:
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

    async def run_code(self, *, language: str, code: str, timeout_s: float) -> ExecResult:
        raise NotImplementedError

    async def health(self) -> Dict[str, object]:
        return {"driver_id": self.driver_id, "ok": True}

