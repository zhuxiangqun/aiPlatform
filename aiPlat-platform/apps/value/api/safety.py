"""
Safety router — crisis detection and emotional safety monitoring endpoints.

POST /safety/crisis-check     — Check message for crisis signals
POST /safety/session-check    — Check entire session for crisis
GET  /safety/emotion-state    — Get emotional state for a session
POST /safety/dependency-check — Check over-dependency risk
GET  /safety/flagged-sessions — List safety-flagged sessions
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, Query

router = APIRouter(prefix="/safety", tags=["safety"])


@router.post("/crisis-check", response_model=Dict[str, Any])
async def crisis_check(body: Dict[str, Any]):
    """Check a single message for crisis signals."""
    text = body.get("text", "") or body.get("message", "")
    session_id = body.get("session_id", "")
    if not text:
        return {"error": "text or message is required"}

    try:
        from core.harness.security.crisis_detector import get_crisis_detector
        detector = get_crisis_detector()
        result = detector.detect(text, session_id=session_id)
        return result.to_dict()
    except Exception as e:
        return {"error": str(e)}


@router.post("/session-check", response_model=Dict[str, Any])
async def session_check(body: Dict[str, Any]):
    """Check an entire conversation session for crisis signals."""
    messages = body.get("messages", [])
    session_id = body.get("session_id", "")
    if not messages:
        return {"error": "messages is required"}

    try:
        from core.harness.security.crisis_detector import get_crisis_detector
        detector = get_crisis_detector()
        all_signals = []
        max_severity = "none"
        for msg in messages:
            content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
            result = detector.detect(content, session_id=session_id)
            all_signals.extend(result.signals)
            if result.severity.value != "none":
                current_val = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(max_severity, 0)
                new_val = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(result.severity.value, 0)
                if new_val > current_val:
                    max_severity = result.severity.value

        return {
            "session_id": session_id,
            "is_crisis": len(all_signals) > 0,
            "severity": max_severity,
            "signal_count": len(all_signals),
            "signals": [
                {"rule_id": s.rule_id, "severity": s.severity.value}
                for s in all_signals[:20]
            ],
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/emotion-state", response_model=Dict[str, Any])
async def emotion_state(body: Dict[str, Any]):
    """Get emotional state for a session after tracking."""
    session_id = body.get("session_id", "")
    tenant_id = body.get("tenant_id", "default")
    if not session_id:
        return {"error": "session_id is required"}

    try:
        from core.harness.security.emotion_tracker import get_emotion_tracker
        tracker = get_emotion_tracker()
        state = await tracker.get_state(session_id=session_id, tenant_id=tenant_id)
        if state is None:
            return {"session_id": session_id, "found": False, "message": "No data for this session"}
        return {"found": True, "state": state.to_dict()}
    except Exception as e:
        return {"error": str(e)}


@router.post("/dependency-check", response_model=Dict[str, Any])
async def dependency_check(body: Dict[str, Any]):
    """Check over-dependency risk for a user/session."""
    session_id = body.get("session_id", "")
    tenant_id = body.get("tenant_id", "default")
    if not session_id:
        return {"error": "session_id is required"}

    try:
        from core.harness.security.emotion_tracker import get_emotion_tracker
        tracker = get_emotion_tracker()
        state = await tracker.get_state(session_id=session_id, tenant_id=tenant_id)
        if state is None:
            return {"session_id": session_id, "found": False}

        return {
            "session_id": session_id,
            "tenant_id": tenant_id,
            "dependency_risk": state.dependency_risk,
            "sessions_24h": state.sessions_24h,
            "trend": state.trend,
            "current_tone": state.current_tone.value,
            "recommendation": _dependency_recommendation(state),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/flagged-sessions", response_model=Dict[str, Any])
async def flagged_sessions(tenant_id: str = Query("default")):
    """List all safety-flagged sessions."""
    try:
        from core.harness.security.emotion_tracker import get_emotion_tracker
        tracker = get_emotion_tracker()
        flagged = tracker.get_flagged_sessions(tenant_id=tenant_id)
        return {
            "tenant_id": tenant_id,
            "count": len(flagged),
            "sessions": [s.to_dict() for s in flagged],
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/track-emotion", response_model=Dict[str, Any])
async def track_emotion(body: Dict[str, Any]):
    """Track emotion from a completed conversation session."""
    session_id = body.get("session_id", "")
    messages = body.get("messages", [])
    tenant_id = body.get("tenant_id", "default")
    duration_s = body.get("duration_s", 0)
    if not session_id or not messages:
        return {"error": "session_id and messages are required"}

    try:
        from core.harness.security.emotion_tracker import get_emotion_tracker
        tracker = get_emotion_tracker()
        await tracker.track(
            session_id=session_id,
            messages=messages,
            tenant_id=tenant_id,
            session_duration_s=duration_s,
        )
        state = await tracker.get_state(session_id=session_id, tenant_id=tenant_id)
        return {"tracked": True, "state": state.to_dict() if state else None}
    except Exception as e:
        return {"error": str(e)}


def _dependency_recommendation(state) -> str:
    if state.dependency_risk == "high":
        return "High dependency risk detected. Recommend: session frequency limit, proactive well-being check-in, human review."
    if state.dependency_risk == "medium":
        return "Moderate dependency risk. Monitor session frequency. Consider periodic human check-in."
    return "No dependency concern detected."
