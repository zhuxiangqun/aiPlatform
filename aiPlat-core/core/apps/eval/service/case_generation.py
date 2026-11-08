"""P2.0 Case generation — deterministic mutation + trace→case + holdout flags.

No LLM. L3 kinds (generated/trace) are claim_eligible=false forever.
Does not open accuracy_claim.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.case_factory import (
    CaseFactoryError,
    dedupe_cases_by_hash,
    validate_case_dict,
)
from core.apps.eval.service.case_pack_legacy import task_dict_to_case

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
