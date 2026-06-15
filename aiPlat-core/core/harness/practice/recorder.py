"""
Praxis Recorder — session-level execution recording for replay and analysis.

Inspired by ROSClaw's rosclaw-practice: records every syscall, decision point,
and state change during Agent execution into a replayable trace artifact.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class PraxisStep:
    """A single step in a practice recording."""
    seq: int
    kind: str                    # "llm" | "tool" | "skill" | "decision" | "state"
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    status: str = "unknown"      # "running" | "completed" | "failed" | "rejected"
    input: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    context_snapshot: Dict[str, Any] = field(default_factory=dict)  # tokens, budget, state keys
    error: Optional[str] = None


@dataclass
class PraxisSession:
    """A complete practice recording session."""
    session_id: str
    run_id: str
    agent_id: str = ""
    task: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    steps: List[PraxisStep] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "recording"


class PraxisRecorder:
    """
    Session-level execution recorder.
    
    Usage in loop.py:
      recorder = PraxisRecorder(session_id=..., run_id=...)
      recorder.start()
      recorder.record_step(PraxisStep(seq=1, kind="llm", ...))
      recorder.finish()
    """

    def __init__(self, *, session_id: str = "", run_id: str = "", agent_id: str = ""):
        self._session = PraxisSession(
            session_id=session_id or f"praxis-{int(time.time())}",
            run_id=run_id,
            agent_id=agent_id,
        )
        self._active = False

    def start(self) -> None:
        self._active = True
        self._session.status = "recording"
        log.debug("Praxis recording started: %s", self._session.session_id)

    def record_step(self, step: PraxisStep) -> None:
        if not self._active:
            return
        self._session.steps.append(step)
        if len(self._session.steps) % 10 == 0:
            log.debug("Praxis: %d steps recorded", len(self._session.steps))

    def record_llm(
        self, seq: int, *, prompt: str = "", response: str = "",
        input_tokens: int = 0, output_tokens: int = 0,
        duration_ms: float = 0.0, status: str = "unknown", error: str = "",
    ) -> None:
        self.record_step(PraxisStep(
            seq=seq, kind="llm", status=status, duration_ms=duration_ms,
            input={"prompt": prompt[:500], "input_tokens": input_tokens},
            output={"response": response[:500], "output_tokens": output_tokens},
            error=error or None,
        ))

    def record_tool(
        self, seq: int, *, tool_name: str = "", tool_args: Dict = None,
        tool_result: Any = None, duration_ms: float = 0.0,
        status: str = "unknown", error: str = "",
    ) -> None:
        self.record_step(PraxisStep(
            seq=seq, kind="tool", status=status, duration_ms=duration_ms,
            input={"tool": tool_name, "args": str(tool_args or {})[:500]},
            output={"result": str(tool_result)[:500]},
            error=error or None,
        ))

    def finish(self, status: str = "completed") -> PraxisSession:
        self._active = False
        self._session.finished_at = time.time()
        self._session.status = status
        duration = self._session.finished_at - self._session.started_at
        log.info("Praxis recording finished: %s (%d steps, %.1fs)",
                 self._session.session_id, len(self._session.steps), duration)
        return self._session

    @property
    def session(self) -> PraxisSession:
        return self._session

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dict for storage."""
        return {
            "session_id": self._session.session_id,
            "run_id": self._session.run_id,
            "agent_id": self._session.agent_id,
            "task": self._session.task,
            "started_at": self._session.started_at,
            "finished_at": self._session.finished_at,
            "status": self._session.status,
            "step_count": len(self._session.steps),
            "metadata": self._session.metadata,
            "steps": [
                {
                    "seq": s.seq,
                    "kind": s.kind,
                    "timestamp": s.timestamp,
                    "duration_ms": s.duration_ms,
                    "status": s.status,
                    "input": s.input,
                    "output": s.output,
                    "error": s.error,
                }
                for s in self._session.steps
            ],
        }


__all__ = ["PraxisRecorder", "PraxisSession", "PraxisStep"]
