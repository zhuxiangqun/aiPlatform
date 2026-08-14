"""Diagnostic submodule base — timeout isolation + tri-state return contract.

Each check submodule MUST:
  - Be an async function returning Dict[str, Any]
  - Return {"status": CheckStatus.PASS|WARN|FAIL|TIMEOUT, ...}
  - Complete within the timeout (default 3s) set by run_with_timeout()
  - Never raise uncaught exceptions (caught by run_with_timeout as FAIL)
"""

import asyncio
from enum import Enum
from typing import Any, Dict, Callable, Coroutine


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    TIMEOUT = "timeout"


async def run_with_timeout(
    check_fn: Callable[[], Coroutine[Any, Any, Dict[str, Any]]],
    timeout: float = 3.0,
) -> Dict[str, Any]:
    """Wrap a diagnostic check with timeout isolation.

    On timeout, returns TIMEOUT status (does not raise).
    On exception, returns FAIL status (does not crash the scheduler).
    """
    try:
        return await asyncio.wait_for(check_fn(), timeout=timeout)
    except asyncio.TimeoutError:
        return {"status": CheckStatus.TIMEOUT, "reason": f"exceeded {timeout}s timeout"}
    except Exception as exc:
        return {"status": CheckStatus.FAIL, "reason": str(exc)[:200]}
