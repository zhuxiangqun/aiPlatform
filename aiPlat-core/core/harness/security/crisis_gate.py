"""

Crisis Gate — enforces crisis safety policy at the syscall boundary.



Inherits the PolicyGate pattern. Checks user messages before LLM

processing. In BLOCK mode, stops the syscall and requires HITL approval.



Usage (integrated in sys_llm_generate / sys_skill_call):

    from core.harness.security.crisis_gate import CrisisGate, CrisisGateDecision



    gate = get_crisis_gate()

    result = gate.check(message, session_id="s1")

    if result.decision == CrisisGateDecision.ESCALATE:

        raise CrisisEscalation(result)

"""



from __future__ import annotations



import os

import logging

from dataclasses import dataclass, field

from enum import Enum

from typing import List, Optional



from core.harness.security.crisis_detector import (

    CrisisDetector,

    CrisisMode,

    CrisisResult,

    CrisisSeverity,

    CrisisEscalation,

    get_crisis_detector,

)



_log = logging.getLogger("aiplat.crisis_gate")





class CrisisGateDecision(str, Enum):

    ALLOW = "allow"

    WARN = "warn"

    FLAG = "flag"

    BLOCK = "block"

    ESCALATE = "escalate"





@dataclass

class CrisisGateResult:

    decision: CrisisGateDecision = CrisisGateDecision.ALLOW

    crisis_result: Optional[CrisisResult] = None

    reason: str = ""

    session_id: str = ""



    def to_dict(self) -> dict:

        return {

            "decision": self.decision.value,

            "reason": self.reason,

            "session_id": self.session_id,

            "crisis": self.crisis_result.to_dict() if self.crisis_result else None,

        }





class CrisisGate:

    """Enforces crisis detection policy at the syscall boundary."""



    def __init__(self, mode: Optional[CrisisMode] = None):

        self.mode = mode or CrisisMode(os.getenv("AIPLAT_CRISIS_MODE", "warn"))

        self._detector = get_crisis_detector()

        self._escalated_sessions: set = set()



    def check(self, text: str, session_id: str = "", user_id: str = "") -> CrisisGateResult:

        if not text or not text.strip():

            return CrisisGateResult(session_id=session_id)



        result = self._detector.detect(text, session_id=session_id)



        if not result.is_crisis:

            return CrisisGateResult(

                decision=CrisisGateDecision.ALLOW,

                crisis_result=result,

                reason="No crisis detected",

                session_id=session_id,

            )



        decision = self._map_decision(result)



        gate_result = CrisisGateResult(

            decision=decision,

            crisis_result=result,

            reason=f"Crisis detected: severity={result.severity.value}, signals={len(result.signals)}",

            session_id=session_id,

        )



        if decision in (CrisisGateDecision.BLOCK, CrisisGateDecision.ESCALATE):

            self._escalated_sessions.add(session_id)

            _log.warning(

                "Crisis gate %s: session=%s, severity=%s, signals=%d, user=%s",

                decision.value, session_id, result.severity.value, len(result.signals), user_id,

            )

            self._audit_crisis(result, session_id, user_id)



        return gate_result



    def _audit_crisis(self, result: CrisisResult, session_id: str, user_id: str) -> None:

        import asyncio as _asyncio

        async def _log():

            try:

                from core.services.execution_store import get_execution_store

                store = get_execution_store()

                await store.add_audit_log(

                    action="safety_crisis_detected",

                    status=result.severity.value,

                    actor_id=user_id,

                    resource_type="session",

                    resource_id=session_id,

                    detail={

                        "severity": result.severity.value,

                        "signal_count": len(result.signals),

                        "action": result.recommended_action[:200],

                        "rule_ids": [s.rule_id for s in result.signals[:10]],

                    },

                )

            except Exception:

                logging.getLogger(__name__).debug('_log failed', exc_info=True)
        try:
            _asyncio.get_running_loop()
            _asyncio.ensure_future(_log())
        except RuntimeError:
            # No running event loop (e.g. sync pytest on Python 3.11) —
            # run the audit synchronously so crisis escalation is never lost.
            try:
                import asyncio as _a2
                _a2.run(_log())
            except Exception:
                logging.getLogger(__name__).debug('_audit_crisis sync fallback failed', exc_info=True)



    def _map_decision(self, result: CrisisResult) -> CrisisGateDecision:

        if self.mode == CrisisMode.SILENT:

            return CrisisGateDecision.ALLOW

        if self.mode == CrisisMode.WARN:

            if result.severity >= CrisisSeverity.HIGH:

                return CrisisGateDecision.FLAG

            return CrisisGateDecision.WARN

        # BLOCK mode

        if result.severity == CrisisSeverity.CRITICAL:

            return CrisisGateDecision.ESCALATE

        if result.severity == CrisisSeverity.HIGH:

            return CrisisGateDecision.BLOCK

        if result.severity == CrisisSeverity.MEDIUM:

            return CrisisGateDecision.FLAG

        return CrisisGateDecision.WARN



    def is_escalated(self, session_id: str) -> bool:

        return session_id in self._escalated_sessions



    def clear_session(self, session_id: str):

        self._escalated_sessions.discard(session_id)





_crisis_gate: Optional[CrisisGate] = None





def get_crisis_gate() -> CrisisGate:

    global _crisis_gate

    if _crisis_gate is None:

        _crisis_gate = CrisisGate()

    return _crisis_gate

