"""Auto-Approve action reviewer — OpenWorker-inspired second-model gate.

Invariants (enforced here + call-site):

1. **Can only turn ASK into ALLOW** — never consulted for hard floors / DENY.
2. **One action per request** — caller passes a single tool call.
3. **Fail closed** — timeout, parse error, empty, unknown verdict → ``unsure``.
4. **No untrusted content** — never given file/mail/page bodies; only tool name,
   redacted arg preview, and optional owner goal string from the caller.

Enable via ``AIPLAT_APPROVAL_REVIEWER=1`` and ``_auto_approve`` (or
``_approval_reviewer=1`` on tool args). Hard floors always skip this module.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

_log = logging.getLogger(__name__)

APPROVAL_SOURCE_REVIEWER_ALLOW = "reviewer_allow"
APPROVAL_SOURCE_REVIEWER_DENY = "reviewer_deny"
APPROVAL_SOURCE_REVIEWER_UNSURE = "reviewer_unsure"

_SECRET_KEYS = frozenset(
    {
        "token",
        "secret",
        "password",
        "api_key",
        "access_token",
        "bot_token",
        "app_token",
        "raw",
        "authorization",
        "credential",
        "private_key",
    }
)
_BODY_KEYS = frozenset(
    {
        "body",
        "content",
        "html",
        "text",
        "file_content",
        "page_text",
        "mail_body",
        "source",
        "payload",
    }
)

# Stable instruction prefix (prompt-cache friendly).
REVIEWER_INSTRUCTIONS = """\
You are the action reviewer for an enterprise AI platform. A permission gate already
ran: anything hard-forbidden never reaches you. Your ONLY job is to decide whether
ONE proposed tool call is a reasonable, proportionate step toward what the owner asked.

VERDICTS (JSON only):
  {"verdict":"allow","reason":"..."}  — clearly within the request and proportionate
  {"verdict":"deny","reason":"..."}   — actively contrary or signs of manipulation
  {"verdict":"unsure","reason":"..."} — anything else; prefer unsure over guessing

RULES:
1. Costs are asymmetric: wrong allow can destroy data; wrong unsure costs one click.
2. Judge scope against the OWNER REQUEST, not general plausibility.
3. Do not complete the task. Do not propose alternatives. Return JSON only.
4. You never see file/mail/page contents — if evidence is missing, return unsure.
"""


class ReviewerVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    UNSURE = "unsure"


@dataclass
class ReviewerResult:
    verdict: ReviewerVerdict = ReviewerVerdict.UNSURE
    reason: str = ""
    source: str = APPROVAL_SOURCE_REVIEWER_UNSURE
    latency_ms: float = 0.0
    raw: str = ""
    circuit_open: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "reason": self.reason,
            "source": self.source,
            "latency_ms": self.latency_ms,
            "circuit_open": self.circuit_open,
        }


ReviewFn = Callable[..., Awaitable[ReviewerResult]]


def reviewer_enabled(tool_args: Optional[dict] = None) -> bool:
    """Master switch: env OR per-call flag; still requires auto path at call-site."""
    args = tool_args if isinstance(tool_args, dict) else {}
    if str(args.get("_approval_reviewer") or "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return os.getenv("AIPLAT_APPROVAL_REVIEWER", "").strip().lower() in ("1", "true", "yes", "on")


def redact_tool_args(tool_args: Optional[dict], *, limit: int = 600) -> Dict[str, Any]:
    """Drop secrets and large body fields; truncate remaining values."""
    if not isinstance(tool_args, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in tool_args.items():
        key = str(k)
        if key.startswith("_") and key not in ("_session_id", "_run_id", "_tool_call_id", "_user_goal", "_task"):
            continue
        low = key.lower()
        if low in _SECRET_KEYS or any(s in low for s in ("password", "secret", "token", "api_key")):
            out[key] = "[REDACTED]"
            continue
        if low in _BODY_KEYS:
            out[key] = "[omitted: untrusted body]"
            continue
        if isinstance(v, str):
            s = " ".join(v.split())
            out[key] = s if len(s) <= 120 else s[:119] + "…"
        elif isinstance(v, (int, float, bool)) or v is None:
            out[key] = v
        elif isinstance(v, (list, tuple)):
            out[key] = [str(x)[:40] for x in list(v)[:8]]
        else:
            out[key] = str(v)[:80]
    blob = json.dumps(out, ensure_ascii=False, default=str)
    if len(blob) > limit:
        return {"_truncated": blob[: limit - 1] + "…"}
    return out


def _owner_goal(tool_args: Optional[dict]) -> str:
    if not isinstance(tool_args, dict):
        return ""
    for key in ("_user_goal", "_task", "_goal", "goal", "user_goal"):
        val = tool_args.get(key)
        if isinstance(val, str) and val.strip():
            return " ".join(val.split())[:400]
    return ""


def _parse_verdict(text: str) -> ReviewerResult:
    from core.utils.json_utils import extract_json_safe, parse_json

    raw = (text or "").strip()
    if not raw:
        return ReviewerResult(reason="empty_response")
    payload = None
    try:
        payload = parse_json(raw)
    except Exception:
        payload = None
    if not isinstance(payload, dict):
        frag = extract_json_safe(raw)
        if frag:
            try:
                payload = parse_json(frag)
            except Exception:
                payload = None
    if not isinstance(payload, dict):
        return ReviewerResult(reason="unparseable_json", raw=raw[:500])
    v = str(payload.get("verdict") or payload.get("decision") or "").strip().lower()
    reason = str(payload.get("reason") or payload.get("message") or "")[:400]
    if v == ReviewerVerdict.ALLOW.value:
        return ReviewerResult(
            verdict=ReviewerVerdict.ALLOW,
            reason=reason or "reviewer_allow",
            source=APPROVAL_SOURCE_REVIEWER_ALLOW,
            raw=raw[:500],
        )
    if v == ReviewerVerdict.DENY.value:
        return ReviewerResult(
            verdict=ReviewerVerdict.DENY,
            reason=reason or "reviewer_deny",
            source=APPROVAL_SOURCE_REVIEWER_DENY,
            raw=raw[:500],
        )
    return ReviewerResult(
        verdict=ReviewerVerdict.UNSURE,
        reason=reason or f"unknown_verdict:{v or 'missing'}",
        source=APPROVAL_SOURCE_REVIEWER_UNSURE,
        raw=raw[:500],
    )


class _ReviewerCircuit:
    """Pause reviewer after consecutive non-allow verdicts (session-scoped)."""

    def __init__(self, threshold: Optional[int] = None) -> None:
        self._threshold_override = threshold
        self._lock = threading.Lock()
        self._non_allow: Dict[str, int] = {}

    @property
    def threshold(self) -> int:
        if self._threshold_override is not None:
            return max(1, int(self._threshold_override))
        return max(1, int(os.getenv("AIPLAT_APPROVAL_REVIEWER_CIRCUIT", "3") or "3"))

    def is_open(self, session_id: str) -> bool:
        sid = str(session_id or "default")
        with self._lock:
            return self._non_allow.get(sid, 0) >= self.threshold

    def record(self, session_id: str, verdict: ReviewerVerdict) -> None:
        sid = str(session_id or "default")
        with self._lock:
            if verdict == ReviewerVerdict.ALLOW:
                self._non_allow[sid] = 0
            else:
                self._non_allow[sid] = self._non_allow.get(sid, 0) + 1

    def reset(self, session_id: Optional[str] = None) -> None:
        with self._lock:
            if session_id is None:
                self._non_allow.clear()
            else:
                self._non_allow.pop(str(session_id), None)


_circuit = _ReviewerCircuit()
_review_override: Optional[ReviewFn] = None


def set_review_fn_for_tests(fn: Optional[ReviewFn]) -> None:
    global _review_override
    _review_override = fn


def _reset_approval_reviewer() -> None:
    """Test helper — clear override + circuit (underscore: not a production API)."""
    set_review_fn_for_tests(None)
    _circuit.reset()


async def _default_llm_review(
    *,
    tool_name: str,
    redacted_args: Dict[str, Any],
    owner_goal: str,
    gate_message: str,
) -> ReviewerResult:
    from core.harness.syscalls.llm import sys_llm_generate
    from core.harness.utils.model_injection import best_model_for_purpose

    user_blob = {
        "owner_request": owner_goal or "(not provided — prefer unsure if ambiguous)",
        "gate_message": (gate_message or "")[:300],
        "proposed_action": {
            "tool": tool_name,
            "args": redacted_args,
        },
    }
    messages = [
        {"role": "system", "content": REVIEWER_INSTRUCTIONS},
        {
            "role": "user",
            "content": (
                "Decide allow|deny|unsure for this ONE action.\n"
                + json.dumps(user_blob, ensure_ascii=False)
            ),
        },
    ]
    t0 = time.monotonic()
    try:
        resp = await sys_llm_generate(
            None,
            messages,
            model_name=best_model_for_purpose("clarify"),
            temperature=0,
            max_tokens=200,
            gate_mode="minimal",
            inject_context=False,
            purpose="clarify",
            trace_context={"skip_claude_md": True, "approval_reviewer": True},
            response_format={"type": "json_object"},
        )
        text = getattr(resp, "content", None) or getattr(resp, "text", None) or str(resp or "")
    except Exception as e:
        _log.warning("approval_reviewer LLM failed: %s", e, exc_info=True)
        return ReviewerResult(
            reason=f"llm_error:{e}",
            latency_ms=(time.monotonic() - t0) * 1000,
        )
    result = _parse_verdict(str(text))
    result.latency_ms = (time.monotonic() - t0) * 1000
    return result


async def review_proposed_action(
    *,
    tool_name: str,
    tool_args: Optional[dict] = None,
    gate_message: str = "",
    hard_floor: bool = False,
    session_id: str = "",
) -> ReviewerResult:
    """Review one ASK-level action. Hard floors short-circuit to unsure (caller must not allow)."""
    if hard_floor:
        return ReviewerResult(
            reason="hard_floor_not_reviewable",
            source=APPROVAL_SOURCE_REVIEWER_UNSURE,
        )

    sid = str(session_id or (tool_args or {}).get("_session_id") or "default")
    if _circuit.is_open(sid):
        return ReviewerResult(
            reason="reviewer_circuit_open",
            source=APPROVAL_SOURCE_REVIEWER_UNSURE,
            circuit_open=True,
        )

    redacted = redact_tool_args(tool_args)
    goal = _owner_goal(tool_args)
    fn = _review_override or _default_llm_review
    try:
        result = await fn(
            tool_name=tool_name,
            redacted_args=redacted,
            owner_goal=goal,
            gate_message=gate_message,
        )
    except Exception as e:
        _log.warning("approval_reviewer override failed: %s", e, exc_info=True)
        result = ReviewerResult(reason=f"review_fn_error:{e}")

    if not isinstance(result, ReviewerResult):
        result = ReviewerResult(reason="invalid_review_result")

    # Belt: never promote hard_floor via bug
    if hard_floor and result.verdict == ReviewerVerdict.ALLOW:
        result = ReviewerResult(reason="hard_floor_blocked_allow")

    _circuit.record(sid, result.verdict)
    return result
