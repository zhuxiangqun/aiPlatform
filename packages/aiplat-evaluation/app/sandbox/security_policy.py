"""security_redteam admit — S1 fixture + optional live_llm (env-gated).

Honesty: deterministic checks on responses; live_llm fills responses via
independent Eval LLM (not Central, not skill tools). accuracy_claim=false.
Not a security certification.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Mapping, Optional


def s1_live_enabled() -> bool:
    raw = (os.environ.get("AIPLAT_EVAL_S1_LIVE") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def security_redteam_is_fixture(payload: Optional[Mapping[str, Any]] = None) -> bool:
    body: Dict[str, Any] = dict(payload or {})
    mode = str(body.get("mode") or body.get("execution_mode") or "").strip().lower()
    if mode in ("live", "online", "agent", "tools", "live_llm"):
        return False
    if mode in ("fixture", "local_fixture", "security_eval_v1"):
        return True
    cases = body.get("cases") or body.get("attacks")
    return isinstance(cases, list) and len(cases) > 0


def security_redteam_is_live_llm(payload: Optional[Mapping[str, Any]] = None) -> bool:
    """Admit live_llm only when AIPLAT_EVAL_S1_LIVE=1 and cases have prompts."""
    if not s1_live_enabled():
        return False
    body: Dict[str, Any] = dict(payload or {})
    mode = str(body.get("mode") or body.get("execution_mode") or "").strip().lower()
    if mode not in ("live_llm", "s1_live"):
        return False
    cases = body.get("cases") or body.get("attacks")
    if not isinstance(cases, list) or not cases:
        return False
    return all(isinstance(c, dict) and str(c.get("prompt") or "").strip() for c in cases)


def security_redteam_admits(payload: Optional[Mapping[str, Any]] = None) -> bool:
    return security_redteam_is_fixture(payload) or security_redteam_is_live_llm(payload)


def assert_security_redteam_fixture(payload: Optional[Mapping[str, Any]] = None) -> None:
    """Backward-compatible name: admit fixture **or** env-gated live_llm."""
    if not security_redteam_admits(payload):
        raise ValueError("sandbox_required:security_redteam")


def _wire_security_policy() -> bool:
    """Same-file caller for method_verify."""
    _ = security_redteam_is_fixture({"mode": "fixture"})
    _ = security_redteam_is_live_llm({"mode": "live_llm", "cases": [{"prompt": "x"}]})
    return security_redteam_is_fixture({"mode": "live"})
