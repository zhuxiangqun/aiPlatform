"""Case generation — mutation/trace/holdout (P2) + LLM candidates (P3.0).

L3 kinds (generated/trace) are claim_eligible=false forever.
LLM path uses best_model_for_purpose → create_selected_adapter → sys_llm_generate.
Does not open accuracy_claim.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.case_factory import (
    CaseFactoryError,
    dedupe_cases_by_hash,
    validate_case_dict,
)
from core.apps.eval.service.case_pack_legacy import task_dict_to_case

LlmGenerateFn = Callable[[str], Awaitable[str]]

VALID_MUTATIONS = frozenset(
    {"append_noise", "drop_punctuation", "case_swap", "prefix_typo"}
)


class CaseGenerationError(ValueError):
    """Mutation / trace / holdout generation failure."""


def _stable_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}:{salt}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _mutate_prompt(prompt: str, *, op: str, seed: str, index: int) -> str:
    text = str(prompt or "")
    if op == "append_noise":
        n = _stable_int(seed, f"noise-{index}") % 1000
        return f"{text} [noise:{n}]"
    if op == "drop_punctuation":
        return re.sub(r"[^\w\s\u4e00-\u9fff]", "", text, flags=re.UNICODE)
    if op == "case_swap":
        return "".join(ch.swapcase() if ch.isalpha() else ch for ch in text)
    if op == "prefix_typo":
        return f"typo{_stable_int(seed, f'typo-{index}') % 10} {text}"
    raise CaseGenerationError(f"unknown mutation op={op!r}")


def mutate_cases(
    seeds: Sequence[Mapping[str, Any]],
    *,
    ops: Optional[Sequence[str]] = None,
    seed: str = "0",
    id_prefix: str = "mut",
) -> List[Dict[str, Any]]:
    """Deterministic mutations of seed cases (no LLM). kind provenance=mutation."""
    op_list = [str(o).strip() for o in (ops or ["append_noise"])]
    if not op_list:
        raise CaseGenerationError("ops required")
    for op in op_list:
        if op not in VALID_MUTATIONS:
            raise CaseGenerationError(
                f"unsupported mutation {op!r}; allowed={sorted(VALID_MUTATIONS)}"
            )
    out: List[Dict[str, Any]] = []
    sid = str(seed or "0")
    for i, raw in enumerate(seeds):
        if not isinstance(raw, Mapping):
            raise CaseGenerationError(f"seed[{i}] must be object")
        base = task_dict_to_case(raw, set_id=str(raw.get("set_id") or ""))
        for op in op_list:
            merged = dict(base)
            new_prompt = _mutate_prompt(base.get("prompt") or "", op=op, seed=sid, index=i)
            stem = str(base.get("case_id") or f"seed{i}")
            merged["case_id"] = f"{id_prefix}-{stem}-{op}-{i+1:03d}"
            merged["prompt"] = new_prompt
            merged["user_input"] = new_prompt
            tags = list(merged.get("tags") or [])
            if "mutation" not in tags:
                tags.append("mutation")
            if op not in tags:
                tags.append(op)
            merged["tags"] = tags
            prov = dict(merged.get("provenance") or {})
            prov.update(
                {
                    "generator": "case_mutation",
                    "generator_version": "1",
                    "seed": sid,
                    "mutation_op": op,
                    "parent_case_id": base.get("case_id"),
                }
            )
            merged["provenance"] = prov
            merged["review"] = {"status": "draft", "notes": f"mutation:{op}"}
            # L3 discovery — never claim
            merged["holdout"] = bool(merged.get("holdout") or False)
            try:
                validate_case_dict(merged)
            except CaseFactoryError as e:
                raise CaseGenerationError(str(e)) from e
            out.append(merged)
    return dedupe_cases_by_hash(out)


def cases_from_trace(
    trace: Mapping[str, Any],
    *,
    case_id: str = "",
    category: str = "normal",
) -> List[Dict[str, Any]]:
    """Build draft case(s) from a chat/tool trace dict (no LLM).

    Expected keys (flexible): messages[{role,content}], tool_calls[{name}],
    or prompt / user_input directly.
    """
    if not isinstance(trace, Mapping):
        raise CaseGenerationError("trace must be object")
    prompt = str(trace.get("prompt") or trace.get("user_input") or "").strip()
    if not prompt:
        for msg in trace.get("messages") or []:
            if not isinstance(msg, Mapping):
                continue
            if str(msg.get("role") or "").lower() in ("user", "human"):
                prompt = str(msg.get("content") or "").strip()
                if prompt:
                    break
    if not prompt:
        raise CaseGenerationError("trace missing user prompt/messages")

    tools: List[str] = []
    for tc in trace.get("tool_calls") or []:
        if isinstance(tc, Mapping) and tc.get("name"):
            tools.append(str(tc["name"]))
    for msg in trace.get("messages") or []:
        if not isinstance(msg, Mapping):
            continue
        for tc in msg.get("tool_calls") or []:
            if isinstance(tc, Mapping) and tc.get("name"):
                tools.append(str(tc["name"]))

    cid = str(case_id or trace.get("case_id") or "").strip()
    if not cid:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]
        cid = f"trace-{digest}"

    rubric = trace.get("rubric")
    if not isinstance(rubric, Mapping):
        must = trace.get("must_contain")
        rubric = {
            "type": "lexical",
            "must_contain": list(must) if isinstance(must, list) else [],
        }

    case = task_dict_to_case(
        {
            "case_id": cid,
            "prompt": prompt,
            "rubric": rubric,
            "category": str(category or "normal"),
            "tags": ["trace", str(category or "normal")],
            "expected_tools": tools,
            "holdout": bool(trace.get("holdout") or False),
            "difficulty": str(trace.get("difficulty") or "medium"),
            "risk_level": str(trace.get("risk_level") or "low"),
        }
    )
    case["provenance"] = {
        "generator": "case_trace",
        "generator_version": "1",
        "seed": trace.get("seed"),
        "trace_id": trace.get("trace_id") or trace.get("run_id"),
    }
    case["review"] = {"status": "draft", "notes": "from_trace"}
    try:
        validate_case_dict(case)
    except CaseFactoryError as e:
        raise CaseGenerationError(str(e)) from e
    return [case]


def apply_holdout_flags(
    cases: Sequence[Mapping[str, Any]],
    *,
    case_ids: Optional[Sequence[str]] = None,
    holdout: bool = True,
    ratio: float = 0.0,
    seed: str = "0",
) -> List[Dict[str, Any]]:
    """Set holdout flags. Explicit case_ids win; else deterministic ratio split."""
    rows = [dict(c) for c in cases]
    if not rows:
        return []
    want = {str(x).strip() for x in (case_ids or []) if str(x).strip()}
    if want:
        for c in rows:
            if str(c.get("case_id") or "") in want:
                c["holdout"] = bool(holdout)
        return rows
    r = float(ratio or 0.0)
    if r <= 0:
        raise CaseGenerationError("case_ids or positive ratio required")
    if r > 1:
        raise CaseGenerationError("ratio must be <= 1")
    # stable order by case_id then pick first k
    ordered = sorted(rows, key=lambda c: str(c.get("case_id") or ""))
    k = max(1, int(round(len(ordered) * r))) if ordered else 0
    # mix with seed for which end
    flip = _stable_int(str(seed), "holdout") % 2 == 1
    chosen = set()
    pool = list(reversed(ordered)) if flip else list(ordered)
    for c in pool[:k]:
        chosen.add(str(c.get("case_id") or ""))
    for c in rows:
        if str(c.get("case_id") or "") in chosen:
            c["holdout"] = bool(holdout)
    return rows


def partition_holdout(
    cases: Sequence[Mapping[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Split cases into eval vs holdout lists (by holdout flag)."""
    eval_cases: List[Dict[str, Any]] = []
    holdout_cases: List[Dict[str, Any]] = []
    for c in cases:
        row = dict(c)
        if bool(row.get("holdout")):
            holdout_cases.append(row)
        else:
            eval_cases.append(row)
    return {
        "eval": eval_cases,
        "holdout": holdout_cases,
        "n_eval": len(eval_cases),
        "n_holdout": len(holdout_cases),
    }


def _extract_json_array(text: str) -> List[Any]:
    raw = str(text or "").strip()
    if not raw:
        raise CaseGenerationError("empty LLM response")
    # fenced ```json ... ```
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[")
        end = raw.rfind("]")
        if start < 0 or end <= start:
            raise CaseGenerationError("LLM response is not a JSON array")
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as e:
            raise CaseGenerationError(f"LLM JSON parse failed: {e}") from e
    if not isinstance(parsed, list):
        raise CaseGenerationError("LLM JSON root must be array")
    return parsed


def stub_llm_candidate_json(
    *,
    theme: str,
    n: int = 3,
    category: str = "normal",
    seed: str = "0",
) -> str:
    """Deterministic stub JSON for dry/tests (no network)."""
    rows = []
    for i in range(max(1, int(n))):
        tag = _stable_int(seed, f"llm-{i}") % 10000
        rows.append(
            {
                "case_id": f"llm-{seed}-{i+1:03d}",
                "prompt": f"{theme} — candidate {i+1} (tag={tag})",
                "rubric": {"type": "lexical", "must_contain": [str(theme)[:24] or "ok"]},
                "category": category,
                "difficulty": "medium",
            }
        )
    return json.dumps(rows, ensure_ascii=False)


async def generate_llm_candidate_cases(
    *,
    theme: str,
    n: int = 3,
    category: str = "normal",
    seed: str = "0",
    model_name: str = "",
    dry: bool = False,
    llm_generate_fn: Optional[LlmGenerateFn] = None,
) -> List[Dict[str, Any]]:
    """Ask LLM (or stub) for candidate cases; validate + provenance=case_llm.

    Always L3 discovery material — never claim_eligible.
    """
    theme_s = str(theme or "").strip()
    if not theme_s:
        raise CaseGenerationError("theme required")
    count = max(1, min(int(n or 3), 20))
    sid = str(seed or "0")

    if dry and llm_generate_fn is None:
        text = stub_llm_candidate_json(
            theme=theme_s, n=count, category=category, seed=sid
        )
    elif llm_generate_fn is not None:
        prompt = (
            "Return ONLY a JSON array of eval cases. Each object needs "
            "case_id, prompt, rubric{type,must_contain}, category. "
            f"Theme={theme_s!r} n={count} seed={sid} category={category}."
        )
        text = await llm_generate_fn(prompt)
    else:
        from core.api.core_facade import create_selected_adapter, sys_llm_generate
        from core.harness.utils.model_injection import best_model_for_purpose

        name = (model_name or "").strip() or best_model_for_purpose("clarify")
        model = create_selected_adapter(model_name=name)
        prompt = (
            "You generate evaluation cases for an AI agent exam. "
            "Return ONLY a JSON array (no markdown prose). Each item: "
            '{"case_id":"...","prompt":"...","rubric":{"type":"lexical",'
            '"must_contain":["..."]},"category":"...","difficulty":"easy|medium|hard"}. '
            f"Theme: {theme_s}. Produce exactly {count} items. Seed={sid}."
        )
        resp = await sys_llm_generate(
            model,
            [{"role": "user", "content": prompt}],
            trace_context={
                "skip_claude_md": True,
                "source": "case_llm_candidates",
            },
        )
        text = getattr(resp, "content", None) or str(resp)

    parsed = _extract_json_array(text)
    out: List[Dict[str, Any]] = []
    for i, item in enumerate(parsed[:count]):
        if not isinstance(item, Mapping):
            raise CaseGenerationError(f"candidate[{i}] must be object")
        merged = dict(item)
        if not merged.get("case_id"):
            merged["case_id"] = f"llm-{sid}-{i+1:03d}"
        if not merged.get("category"):
            merged["category"] = category
        if not merged.get("rubric"):
            merged["rubric"] = {
                "type": "lexical",
                "must_contain": [theme_s[:24]],
            }
        case = task_dict_to_case(merged, set_id="")
        tags = list(case.get("tags") or [])
        if "llm_candidate" not in tags:
            tags.append("llm_candidate")
        case["tags"] = tags
        case["provenance"] = {
            "generator": "case_llm",
            "generator_version": "1",
            "seed": sid,
            "theme": theme_s,
            "dry": bool(dry and llm_generate_fn is None),
        }
        case["review"] = {"status": "draft", "notes": "llm_candidate"}
        try:
            validate_case_dict(case)
        except CaseFactoryError as e:
            raise CaseGenerationError(str(e)) from e
        out.append(case)
    if not out:
        raise CaseGenerationError("no valid LLM candidates")
    return dedupe_cases_by_hash(out)


def propose_difficulty(
    cases: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Heuristic difficulty labels (not calibrated; claim closed)."""
    out: List[Dict[str, Any]] = []
    for c in cases:
        prompt = str(c.get("prompt") or "")
        tools = c.get("expected_tools") if isinstance(c.get("expected_tools"), list) else []
        steps = c.get("expected_steps") if isinstance(c.get("expected_steps"), list) else []
        score = len(prompt) + 40 * len(tools) + 20 * len(steps)
        if bool(c.get("holdout")):
            score += 15
        if score < 80:
            diff = "easy"
        elif score < 200:
            diff = "medium"
        else:
            diff = "hard"
        row = dict(c)
        row["difficulty"] = diff
        row["difficulty_proposal"] = {
            "method": "heuristic_v1",
            "score": score,
            "calibrated": False,
            "accuracy_claim": False,
        }
        out.append(row)
    return out


def build_judge_calibration_ticket(
    *,
    pack_id: str,
    version: str,
    sample_case_ids: Optional[Sequence[str]] = None,
    notes: str = "",
) -> Dict[str, Any]:
    """Open a work-order style ticket for judge calibration (no claim)."""
    pid = str(pack_id or "").strip()
    ver = str(version or "").strip()
    if not pid or not ver:
        raise CaseGenerationError("pack_id and version required")
    ids = [str(x).strip() for x in (sample_case_ids or []) if str(x).strip()]
    return {
        "ok": True,
        "ticket_kind": "judge_calibration",
        "schema": "eval.judge_calibration_ticket.v1",
        "pack_id": pid,
        "version": ver,
        "sample_case_ids": ids,
        "status": "open",
        "notes": str(notes or ""),
        "calibrated": False,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": "ticket only — does not calibrate or unlock claims",
    }
