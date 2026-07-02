"""
Crisis Detector — conversation crisis detection for AI safety.

Detects self-harm, suicide, violence, and emergency signals in user messages.
Operates at the syscall boundary (sys_llm_generate / sys_skill_call entry).

Detection modes:
  WARN  — log + flag, continue processing (default)
  BLOCK — reject + HITL approval required
  SILENT — log only, for testing

Usage:
    from core.harness.security.crisis_detector import CrisisDetector, get_crisis_detector

    detector = get_crisis_detector()
    result = detector.detect(user_message, session_id="s1")
    if result.is_crisis:
        raise CrisisEscalation(result)
"""

from __future__ import annotations

import os
import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

_log = logging.getLogger("aiplat.crisis_detector")


class CrisisSeverity(str, Enum):
    NONE = "none"
    LOW = "low"           # distress / anxiety
    MEDIUM = "medium"     # violence / abuse
    HIGH = "high"         # self-harm / suicide
    CRITICAL = "critical" # immediate life threat


class CrisisMode(str, Enum):
    WARN = "warn"
    BLOCK = "block"
    SILENT = "silent"


@dataclass
class CrisisSignal:
    rule_id: str
    severity: CrisisSeverity
    pattern_matched: str
    context_snippet: str = ""


@dataclass
class CrisisResult:
    is_crisis: bool = False
    signals: List[CrisisSignal] = field(default_factory=list)
    severity: CrisisSeverity = CrisisSeverity.NONE
    escalation_required: bool = False
    recommended_action: str = ""

    def to_dict(self) -> dict:
        return {
            "is_crisis": self.is_crisis,
            "severity": self.severity.value,
            "escalation_required": self.escalation_required,
            "recommended_action": self.recommended_action,
            "signals": [
                {"rule_id": s.rule_id, "severity": s.severity.value, "pattern_matched": s.pattern_matched}
                for s in self.signals
            ],
            "signal_count": len(self.signals),
        }


CRISIS_RULES = [
    # HIGH: self-harm / suicide
    {
        "id": "crisis_self_harm_explicit",
        "severity": CrisisSeverity.HIGH,
        "patterns": [
            r"(?i)(kill|hurt|harm)\s*(myself|me)",
            r"(?i)want\s+to\s+(die|end\s+it\s+all|disappear)",
            r"(?i)(suicide|suicidal|self.?harm|self.?injur)",
            r"(?i)can'?t\s+(go\s+on|take\s+it\s+anymore|live\s+like\s+this)",
            r"(?i)(ending|taking)\s+my\s+(life|own\s+life)",
            r"(?i)no\s+reason\s+to\s+(live|go\s+on|exist)",
            r"(?i)(better\s+off|everyone\s+would\s+be\s+better)\s+(dead|without\s+me)",
            r"(?i)(goodbye|farewell)\s+(cruel\s+)?world",
            r"(?i)(我|我想|我要)\s*(自杀|死|结束生命|不想活)",
            r"(?i)活.*(没意思|没意义|没希望|不下去)",
        ],
    },
    # MEDIUM: violence / abuse
    {
        "id": "crisis_violence",
        "severity": CrisisSeverity.MEDIUM,
        "patterns": [
            r"(?i)going\s+to\s+(kill|shoot|stab|murder|attack)",
            r"(?i)(mass\s+(shooting|murder|killing)|active\s+shooter)",
            r"(?i)(bomb|explosive|weapon)\s+(threat|attack|plan)",
            r"(?i)going\s+to\s+(hurt|harm)\s+(someone|people|them)",
            r"(?i)(torture|abuse|assault)\s+(someone|a\s+person|people)",
        ],
    },
    # LOW: distress / anxiety
    {
        "id": "crisis_distress",
        "severity": CrisisSeverity.LOW,
        "patterns": [
            r"(?i)(completely|totally|absolutely)\s+(hopeless|helpless|worthless)",
            r"(?i)nobody\s+(cares|understands|loves)\s+me",
            r"(?i)can'?t\s+(cope|handle\s+this|deal\s+with\s+it)\s+anymore",
            r"(?i)(constant|never.?ending|overwhelming)\s+(pain|suffering|anxiety)",
        ],
    },
    # CRITICAL: immediate emergency
    {
        "id": "crisis_immediate",
        "severity": CrisisSeverity.CRITICAL,
        "patterns": [
            r"(?i)(about\s+to|going\s+to)\s+(kill\s+myself|end\s+my\s+life|jump|overdose)",
            r"(?i)(right\s+now|immediately|this\s+moment)\s+(killing|hurting)",
            r"(?i)(held\s+hostage|hostage\s+situation|armed\s+and\s+dangerous)",
        ],
    },
]

RECOMMENDED_ACTIONS = {
    CrisisSeverity.CRITICAL: "IMMEDIATE_ESCALATE: Contact emergency services (110/120) and human operator",
    CrisisSeverity.HIGH: "ESCALATE: Flag for human review. Provide crisis hotline: 北京心理危机干预热线 010-82951332 · Lifeline 988",
    CrisisSeverity.MEDIUM: "FLAG: Mark for human review within 24h. Do not block message.",
    CrisisSeverity.LOW: "WARN: Log for trend analysis. Continue normally.",
    CrisisSeverity.NONE: "",
}


class CrisisEscalation(Exception):
    def __init__(self, result: CrisisResult):
        self.result = result
        super().__init__(f"Crisis detected: severity={result.severity.value}, signals={len(result.signals)}")


class CrisisDetector:
    """Pattern-based crisis detection with optional LLM verification."""

    def __init__(self, mode: Optional[CrisisMode] = None):
        self.mode = mode or CrisisMode(os.getenv("AIPLAT_CRISIS_MODE", "warn"))
        self._compiled = [(r["id"], r["severity"], [re.compile(p) for p in r["patterns"]]) for r in CRISIS_RULES]

    def detect(self, text: str, session_id: str = "", enable_llm: bool = False) -> CrisisResult:
        if not text or not text.strip():
            return CrisisResult()

        signals: List[CrisisSignal] = []
        for rule_id, severity, patterns in self._compiled:
            for rx in patterns:
                match = rx.search(text)
                if match:
                    start = max(0, match.start() - 30)
                    end = min(len(text), match.end() + 30)
                    signals.append(CrisisSignal(
                        rule_id=rule_id,
                        severity=severity,
                        pattern_matched=match.group(),
                        context_snippet=text[start:end],
                    ))
                    break

        if not signals:
            return CrisisResult()

        max_sev = max(s.severity for s in signals)
        is_crisis = max_sev != CrisisSeverity.NONE
        escalate = max_sev in (CrisisSeverity.HIGH, CrisisSeverity.CRITICAL)

        if self.mode == CrisisMode.SILENT:
            _log.debug("Crisis detected (silent mode): severity=%s, signals=%d, session=%s",
                       max_sev.value, len(signals), session_id)
        elif is_crisis:
            _log.warning("Crisis detected: severity=%s, signals=%d, session=%s, mode=%s",
                        max_sev.value, len(signals), session_id, self.mode.value)

        return CrisisResult(
            is_crisis=is_crisis,
            signals=signals,
            severity=max_sev,
            escalation_required=escalate and self.mode == CrisisMode.BLOCK,
            recommended_action=RECOMMENDED_ACTIONS.get(max_sev, ""),
        )

    def detect_quick(self, text: str) -> bool:
        result = self.detect(text)
        return result.is_crisis and result.severity in (CrisisSeverity.HIGH, CrisisSeverity.CRITICAL)


_crisis_detector: Optional[CrisisDetector] = None


def get_crisis_detector() -> CrisisDetector:
    global _crisis_detector
    if _crisis_detector is None:
        _crisis_detector = CrisisDetector()
    return _crisis_detector
