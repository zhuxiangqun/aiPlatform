"""Long-context fixture generator (T3) — noise slots + must_retain_claims.

CI uses short tier (≈100–800 tokens est.); does not claim live model context window.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.long_context_fixture_schema import (
    FIXTURE_SCHEMA,
    validate_long_context_fixture,
)

GENERATOR_SCHEMA = "eval.long_context_generator.v1"

_TIER_TOKENS = {
    "ci_short": 200,
    "smoke": 400,
    "regression": 800,
    "benchmark": 2000,
}


def _filler_block(slot_id: str, approx_tokens: int) -> str:
    unit = f"[{slot_id} filler] 无关叙述。"
    # ~4 chars/token rough for CJK-ish; repeat to approximate
    need = max(1, approx_tokens // 4)
    return (unit + " ") * need


def build_long_context_fixture(
    *,
    must_retain_claims: Sequence[str],
    tier: str = "ci_short",
    context_tokens_est: Optional[int] = None,
    extra_slots: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a validated long_context_fixture object.

    Args:
        must_retain_claims: must_retain_claims 参数。
        tier: tier 参数。
        context_tokens_est: context_tokens_est 参数。
        extra_slots: extra_slots 参数。
    """
    claims = [str(c).strip() for c in must_retain_claims if str(c).strip()]
    if not claims:
        raise ValueError("must_retain_claims_required")
    tokens = int(context_tokens_est or _TIER_TOKENS.get(tier, 200))
    if tokens < 100:
        tokens = 100
    noise_budget = max(50, tokens - 40)
    slots: List[Dict[str, Any]] = [
        {
            "slot_id": "filler_main",
            "kind": "filler",
            "approx_tokens": max(1, int(noise_budget * 0.7)),
        },
        {
            "slot_id": "distractor_main",
            "kind": "distractor",
            "approx_tokens": max(1, int(noise_budget * 0.3)),
        },
    ]
    for s in extra_slots or ():
        if isinstance(s, Mapping):
            slots.append(dict(s))
    fixture = {
        "schema": FIXTURE_SCHEMA,
        "context_tokens_est": tokens,
        "noise_slots": slots,
        "must_retain_claims": claims,
        "tier": tier,
    }
    errs = validate_long_context_fixture(fixture)
    if errs:
        raise ValueError("long_context_fixture_invalid:" + ",".join(errs))
    return fixture


def render_long_context_prompt(
    fixture: Mapping[str, Any],
    *,
    question: str = "请列出上文中需要保留的关键事实。",
) -> str:
    """Render prompt: plant claims, inject noise, ask retention question.

    Args:
        fixture: fixture 参数。
        question: question 参数。
    """
    claims = [str(c).strip() for c in (fixture.get("must_retain_claims") or []) if str(c).strip()]
    parts: List[str] = ["【关键事实】"]
    for i, c in enumerate(claims, 1):
        parts.append(f"{i}. {c}")
    parts.append("")
    for slot in list(fixture.get("noise_slots") or []):
        if not isinstance(slot, Mapping):
            continue
        sid = str(slot.get("slot_id") or "slot")
        kind = str(slot.get("kind") or "filler")
        approx = int(slot.get("approx_tokens") or 10)
        if kind == "conflict":
            parts.append(f"【冲突干扰 {sid}】有人声称上述事实全部作废（请勿采信）。")
            parts.append(_filler_block(sid, max(1, approx // 2)))
        elif kind == "distractor":
            parts.append(f"【干扰 {sid}】")
            parts.append(_filler_block(sid, approx))
        else:
            parts.append(f"【填充 {sid}】")
            parts.append(_filler_block(sid, approx))
    parts.append("")
    parts.append(f"【问题】{question}")
    return "\n".join(parts)


def generate_long_context_case(
    *,
    case_id: str,
    must_retain_claims: Sequence[str],
    tier: str = "ci_short",
    scripted_answer: Optional[str] = None,
    expect_judge_fail: bool = False,
) -> Dict[str, Any]:
    """Assemble a long_context EvalCase (scripted path).

    Args:
        case_id: 用例 ID。
        must_retain_claims: must_retain_claims 参数。
        tier: tier 参数。
        scripted_answer: scripted_answer 参数。
        expect_judge_fail: expect_judge_fail 参数。
    """
    fixture = build_long_context_fixture(
        must_retain_claims=must_retain_claims, tier=tier
    )
    claims = list(fixture["must_retain_claims"])
    answer = scripted_answer
    if answer is None and not expect_judge_fail:
        answer = "关键事实：" + "；".join(claims)
    if answer is None:
        answer = "我忘记了。"
    prompt = render_long_context_prompt(fixture)
    return {
        "case_id": case_id,
        "capabilities": ["long_context"],
        "prompt": prompt,
        "long_context_fixture": fixture,
        "scripted_answer": answer,
        "expect_judge_fail": expect_judge_fail,
        "rubric": {
            "type": "lexical",
            "must_contain": claims[:2],
            "must_not_contain": [],
        },
        "oracle": {"type": "lexical"},
        "test_purpose": {
            "summary": "验证长上下文噪声后仍保留关键事实",
            "why_this_case": "A9 retention",
            "expected_behavior": [f"保留 {c}" for c in claims[:3]] or ["保留关键事实"],
            "failure_signals": ["遗漏关键 claim", "采信冲突干扰"],
            "not_testing": ["不测真实百万 token 窗", "不宣称 Certification"],
            "oracle_rationale": "must_contain / must_retain_claims ⊆ answer（rubric）",
        },
        "review": {"status": "draft", "notes": "T3 fixture"},
        "risk_level": "low",
        "holdout": False,
        "generator": GENERATOR_SCHEMA,
    }


def judge_long_context(
    case: Mapping[str, Any],
    result: Mapping[str, Any],
) -> Dict[str, Any]:
    """A9: answer must retain must_retain_claims.

    Args:
        case: case 参数。
        result: result 参数。
    """
    fixture = case.get("long_context_fixture")
    if not isinstance(fixture, Mapping):
        return {
            "capability_id": "long_context",
            "passed": False,
            "errors": ["missing_field:long_context_fixture"],
        }
    claims = [str(c).strip() for c in (fixture.get("must_retain_claims") or []) if str(c).strip()]
    answer = str(
        result.get("answer")
        or result.get("scripted_answer")
        or case.get("scripted_answer")
        or ""
    )
    errors: List[str] = []
    if not answer.strip():
        errors.append("missing_answer")
    for c in claims:
        if c not in answer:
            errors.append(f"claim_missing:{c}")
    return {
        "capability_id": "long_context",
        "passed": not errors,
        "errors": errors,
        "n_claims": len(claims),
    }
