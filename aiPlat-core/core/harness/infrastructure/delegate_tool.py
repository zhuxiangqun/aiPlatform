"""
DelegateTool — sub-agent delegation with resource isolation.

Extends SubagentCoordinator with per-task resource budgets and
structured output requirements. Provides the "delegate" syscall
that Agent can use to fan out work to sub-agents.

hermes-agent parity: tools/delegate_tool.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class DelegateConfig:
    """Configuration for a sub-agent delegation."""
    subagent_name: str
    task: str
    max_tokens: int = 4096
    timeout_s: float = 300.0
    isolate_context: bool = True
    max_output_chars: int = 800
    retry_on_failure: bool = True
    max_retries: int = 2
    priority: int = 0


@dataclass
class DelegateResult:
    """Result of a sub-agent delegation."""
    subagent_name: str
    success: bool
    output: str
    error: Optional[str] = None
    duration_ms: float = 0.0
    token_used: int = 0
    retries: int = 0


@dataclass
class DelegateStats:
    """Aggregate statistics for delegations."""
    total_delegations: int = 0
    successful: int = 0
    failed: int = 0
    total_duration_ms: float = 0.0
    total_tokens: int = 0
    by_subagent: Dict[str, Dict[str, int]] = field(default_factory=dict)


# ── Delegate Manager ─────────────────────────────────────────────────────────

class DelegateManager:
    """
    Orchestrates sub-agent delegation with resource budgets and retries.

    Wraps SubagentCoordinator to add:
    - Per-task token budgets
    - Timeout enforcement
    - Retry with backoff
    - Result summarization (§5.26: max 800 chars)
    - Delegation statistics

    Usage:
        mgr = DelegateManager()
        result = await mgr.delegate(DelegateConfig(
            subagent_name="code_reviewer",
            task="Review auth.py for security issues",
            timeout_s=120,
        ))
    """

    def __init__(self):
        self._stats = DelegateStats()
        self._active_delegations: Dict[str, int] = {}  # subagent_name → active_count
        self._max_concurrent: int = 5
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._disabled: bool = os.getenv("AIPLAT_DELEGATE_DISABLED", "false").lower() in ("1", "true", "yes")

    async def delegate(self, config: DelegateConfig) -> DelegateResult:
        """
        Delegate a task to a sub-agent with full lifecycle management.
        """
        if self._disabled:
            return DelegateResult(
                subagent_name=config.subagent_name,
                success=False,
                output="",
                error="sub-agent delegation is disabled (AIPLAT_DELEGATE_DISABLED=true)",
            )

        start = time.time()
        self._stats.total_delegations += 1
        self._stats.by_subagent.setdefault(config.subagent_name, {"total": 0, "success": 0, "failure": 0})
        self._stats.by_subagent[config.subagent_name]["total"] += 1

        async with self._semaphore:
            last_error: Optional[str] = None
            for attempt in range(1 + config.max_retries):
                try:
                    result = await asyncio.wait_for(
                        self._execute_delegation(config),
                        timeout=config.timeout_s,
                    )
                    result.retries = attempt
                    result.duration_ms = (time.time() - start) * 1000

                    self._stats.successful += 1
                    self._stats.total_duration_ms += result.duration_ms
                    self._stats.total_tokens += result.token_used
                    self._stats.by_subagent[config.subagent_name]["success"] += 1

                    return result
                except asyncio.TimeoutError:
                    last_error = f"timeout after {config.timeout_s}s"
                    logger.warning("DelegateManager: %s timeout (attempt %d/%d)",
                                   config.subagent_name, attempt + 1, 1 + config.max_retries)
                except Exception as e:
                    last_error = str(e)[:200]
                    logger.warning("DelegateManager: %s failed (attempt %d/%d): %s",
                                   config.subagent_name, attempt + 1, 1 + config.max_retries, last_error)
                if attempt < config.max_retries:
                    await asyncio.sleep(2 ** attempt)

            # All retries exhausted
            self._stats.failed += 1
            self._stats.by_subagent[config.subagent_name]["failure"] += 1
            return DelegateResult(
                subagent_name=config.subagent_name,
                success=False,
                output="",
                error=last_error or "unknown error",
                duration_ms=(time.time() - start) * 1000,
                retries=config.max_retries,
            )

    async def delegate_parallel(self, configs: List[DelegateConfig]) -> List[DelegateResult]:
        """Execute multiple delegations in parallel (FanOut pattern)."""
        tasks = [self.delegate(cfg) for cfg in configs]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def delegate_sequential(self, configs: List[DelegateConfig]) -> List[DelegateResult]:
        """Execute multiple delegations sequentially (Pipeline pattern)."""
        results: List[DelegateResult] = []
        for cfg in configs:
            results.append(await self.delegate(cfg))
        return results

    async def delegate_coordinated(self, configs: List[DelegateConfig],
                                   aggregator_task: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute delegation in coordinated mode: parallel sub-agents + optional aggregation.

        Returns: { "results": [...], "aggregated_output": "..." }
        """
        results = await self.delegate_parallel(configs)
        successful = [r for r in results if r.success]
        aggregated = ""
        if aggregator_task and successful:
            # Combine all sub-agent outputs
            combined = "\n\n".join(
                f"### {r.subagent_name}\n{r.output}"
                for r in successful
            )
            aggregated = combined
        return {
            "results": [{
                "subagent": r.subagent_name,
                "success": r.success,
                "output": r.output[:500],
                "error": r.error,
            } for r in results],
            "aggregated_output": aggregated[:2000] if aggregated else "",
            "total_success": len(successful),
            "total_failed": len([r for r in results if not r.success]),
        }

    async def _execute_delegation(self, config: DelegateConfig) -> DelegateResult:
        """Execute a single delegation via SubagentCoordinator."""
        try:
            from core.harness.integration import get_subagent_coordinator  # P0-A1: DI 解析
            coordinator = get_subagent_coordinator()

            result = await coordinator.execute_single(
                subagent_name=config.subagent_name,
                task=config.task,
                isolate_context=config.isolate_context,
                max_tokens=config.max_tokens,
            )
            # Summarize output per §5.26
            output = str(result.get("output", "")) if isinstance(result, dict) else str(result)
            if len(output) > config.max_output_chars:
                output = output[:config.max_output_chars] + f"\n... [{len(output) - config.max_output_chars} more chars truncated]"

            return DelegateResult(
                subagent_name=config.subagent_name,
                success=bool(result.get("success", True)) if isinstance(result, dict) else True,
                output=output,
                token_used=result.get("token_used", 0) if isinstance(result, dict) else 0,
            )
        except ImportError:
            return DelegateResult(
                subagent_name=config.subagent_name,
                success=False,
                output="",
                error="SubagentCoordinator not available",
            )

    def get_stats(self) -> Dict[str, Any]:
        """Return delegation statistics."""
        return {
            "total": self._stats.total_delegations,
            "successful": self._stats.successful,
            "failed": self._stats.failed,
            "success_rate": round(
                self._stats.successful / max(self._stats.total_delegations, 1), 3
            ),
            "total_duration_ms": self._stats.total_duration_ms,
            "total_tokens": self._stats.total_tokens,
            "by_subagent": self._stats.by_subagent,
            "active": self._active_delegations,
            "max_concurrent": self._max_concurrent,
        }

    def reset_stats(self):
        """Reset delegation statistics."""
        self._stats = DelegateStats()


# ── Global Singleton ──────────────────────────────────────────────────────────

_delegate_manager: Optional[DelegateManager] = None


def get_delegate_manager() -> DelegateManager:
    """Get or create the global DelegateManager singleton."""
    global _delegate_manager
    if _delegate_manager is None:
        _delegate_manager = DelegateManager()
    return _delegate_manager


def reset_delegate_manager():
    """Reset the global singleton (for testing)."""
    global _delegate_manager
    _delegate_manager = None
