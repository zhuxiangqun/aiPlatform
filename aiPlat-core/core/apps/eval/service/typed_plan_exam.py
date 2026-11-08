"""Shared Plan-chain exam for typed packs (prompt / workflow / model / dataset).

Object Contract §0.8: versioned ``{type}/*`` JSON + oracle + executable entry.
prompt/workflow/model: lexical oracle; dry fixture stub / live optional LLM.
dataset: deterministic fixture_table asserts (≠ KB retrieval path).
accuracy_claim=false.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

_log = logging.getLogger("aiplat.eval.typed_plan")

_SUPPORTED = frozenset({"prompt", "workflow", "model", "dataset"})

_TARGET_RUNTIME = {
    "prompt": "prompt_execute",
    "workflow": "workspace_execute",
    "model": "model_generate",
    "dataset": "fixture",
}


def _engine_eval_sets_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "engine" / "eval_sets"


def load_typed_set_json(set_id: str, *, object_type: str) -> Dict[str, Any]:
    """Load ``{object_type}/<stem>`` from engine eval_sets."""
    ot = str(object_type or "").strip()
    if ot not in _SUPPORTED:
        raise ValueError(f"unsupported typed plan object_type: {ot!r}")
    sid = str(set_id or "").strip()
    prefix = f"{ot}/"
    if not sid.startswith(prefix):
        raise ValueError(f"{ot} plan sets must be {prefix}*; got {sid!r}")
    stem = sid.split("/", 1)[1].strip()
    if not stem or "/" in stem or ".." in stem:
        raise ValueError(f"invalid set_id: {sid!r}")
    path = _engine_eval_sets_dir() / ot / f"{stem}.json"
    if not path.is_file():
        raise FileNotFoundError(f"{ot} set not found: {sid} ({path})")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"corrupt {ot} set: {sid}")
    return data


def _path_ok(output: str, path: Mapping[str, Any]) -> bool:
    out = (output or "").lower()
    any_kw = path.get("must_contain_any") or path.get("must_contain") or []
    if isinstance(any_kw, list) and any_kw:
        if not any(str(k).lower() in out for k in any_kw if str(k).strip()):
            return False
    must = path.get("must_contain_all") or []
    if isinstance(must, list) and must:
        if not all(str(k).lower() in out for k in must if str(k).strip()):
            return False
    forbid = path.get("must_not_contain") or []
    if isinstance(forbid, list) and forbid:
        if any(str(k).lower() in out for k in forbid if str(k).strip()):
            return False
    return True


def score_lexical_output(
    output: str, criteria: Mapping[str, Any] | None
) -> Dict[str, Any]:
    """Lexical oracle: must_contain / must_not_contain / paths (OR)."""
    crit = criteria if isinstance(criteria, Mapping) else {}
    out = output or ""
    paths = crit.get("paths")
    if isinstance(paths, list) and paths:
        matched = [
            str(p.get("id") or "path")
            for p in paths
            if isinstance(p, Mapping) and _path_ok(out, p)
        ]
        if matched:
            return {
                "status": "pass",
                "summary": f"paths matched={matched}",
                "matched_paths": matched,
            }
        return {
            "status": "fail",
            "summary": "no success path matched",
            "matched_paths": [],
        }

    must = list(crit.get("must_contain") or [])
    must_not = list(crit.get("must_not_contain") or [])
    low = out.lower()
    hits = [k for k in must if str(k).lower() in low]
    bad = [k for k in must_not if str(k).lower() in low]
    if must_not and bad:
        return {
            "status": "fail",
            "summary": f"forbidden hits={bad}",
            "hits": hits,
            "forbidden_hits": bad,
        }
    if must and len(hits) == len(must):
        return {
            "status": "pass",
            "summary": f"must_contain {len(hits)}/{len(must)}",
            "hits": hits,
        }
    if must and hits:
        return {
            "status": "fail",
            "summary": f"partial must_contain {len(hits)}/{len(must)}",
            "hits": hits,
        }
    if must:
        return {
            "status": "fail",
            "summary": f"must_contain 0/{len(must)}",
            "hits": [],
        }
    return {"status": "inconclusive", "summary": "no lexical criteria"}


def dry_stub_output(task: Mapping[str, Any]) -> str:
    """Deterministic fixture reply for dry runs (≠ live subject claim)."""
    cat = str(task.get("category") or "").lower()
    tid = str(task.get("task_id") or "")
    crit = task.get("success_criteria") if isinstance(task.get("success_criteria"), dict) else {}
    if cat in ("missing_info", "missing_vars", "missing_input") or "miss" in tid:
        return "缺少必填输入，请提供后再继续。"
    if cat in ("safety", "high_risk") or "safety" in tid:
        return "无法协助该请求：涉及不安全或越权内容，已拒绝。"
    if cat in ("stage_failure", "error") or "fail" in tid:
        return "阶段失败已捕获，请重试或降级：error_recovery。"
    must = list(crit.get("must_contain") or [])
    if must:
        return " ".join(str(x) for x in must)
    paths = crit.get("paths") if isinstance(crit.get("paths"), list) else []
    for p in paths:
        if not isinstance(p, dict):
            continue
        any_kw = p.get("must_contain_any") or p.get("must_contain") or []
        if isinstance(any_kw, list) and any_kw:
            return str(any_kw[0])
    return str(task.get("user_input") or "")[:500]


async def live_llm_output(user_input: str, *, model_name: str) -> str:
    from core.api.core_facade import create_selected_adapter, sys_llm_generate
    from core.harness.utils.model_injection import best_model_for_purpose

    name = (model_name or "").strip() or best_model_for_purpose("clarify")
    model = create_selected_adapter(model_name=name)
    messages = [{"role": "user", "content": user_input}]
    resp = await sys_llm_generate(model, messages)
    return resp.content if hasattr(resp, "content") else str(resp)


def score_dataset_task(task: Mapping[str, Any]) -> Dict[str, Any]:
    """Deterministic asserts on embedded fixture_table (≠ KB sample eval)."""
    table = task.get("fixture_table") if isinstance(task.get("fixture_table"), dict) else {}
    crit = task.get("success_criteria") if isinstance(task.get("success_criteria"), dict) else {}
    spec = crit.get("dataset_assert") if isinstance(crit.get("dataset_assert"), dict) else {}
    if not spec:
        return {"status": "inconclusive", "summary": "no dataset_assert"}

    columns = [str(c) for c in (table.get("columns") or [])]
    rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    expect_fail = bool(spec.get("expect_fail"))
    problems: List[str] = []

    required = [str(c) for c in (spec.get("required_columns") or [])]
    missing_cols = [c for c in required if c not in columns]
    if missing_cols:
        problems.append(f"missing_columns={missing_cols}")

    min_rows = spec.get("min_rows")
    try:
        min_n = int(min_rows) if min_rows is not None else None
    except (TypeError, ValueError):
        min_n = None
    if min_n is not None and len(rows) < min_n:
        problems.append(f"rows={len(rows)}<min_rows={min_n}")

    allowed = spec.get("column_allowed_values")
    if isinstance(allowed, dict) and columns:
        col_index = {c: i for i, c in enumerate(columns)}
        for col, vals in allowed.items():
            if col not in col_index:
                problems.append(f"allowed_values_col_missing={col}")
                continue
            idx = col_index[col]
            allow_set = {str(v) for v in (vals or [])}
            for r_i, row in enumerate(rows):
                if not isinstance(row, (list, tuple)) or idx >= len(row):
                    problems.append(f"row[{r_i}] missing col={col}")
                    continue
                if str(row[idx]) not in allow_set:
                    problems.append(f"row[{r_i}].{col}={row[idx]!r} not in {sorted(allow_set)}")

    ok = len(problems) == 0
    if expect_fail:
        if ok:
            return {
                "status": "fail",
                "summary": "expect_fail but asserts passed",
                "problems": [],
            }
        return {
            "status": "pass",
            "summary": f"expect_fail observed: {problems[:3]}",
            "problems": problems,
        }
    if ok:
        return {
            "status": "pass",
            "summary": f"dataset_assert ok rows={len(rows)} cols={columns}",
            "problems": [],
        }
    return {
        "status": "fail",
        "summary": "; ".join(problems[:5]) or "dataset_assert failed",
        "problems": problems,
    }


def annotate_typed_plan_runtime(*, object_type: str, live: bool) -> Dict[str, Any]:
    """Actual plane stays fixture; target_runtime + execution_mode record intent."""
    ot = str(object_type or "").strip()
    if ot not in _SUPPORTED:
        raise ValueError(f"unsupported typed plan object_type: {ot!r}")
    target = _TARGET_RUNTIME[ot]
    if ot == "dataset":
        # Dataset exam is always fixture deterministic; live flag ignored for host.
        return {
            "runtime_tier": "fixture",
            "target_runtime": "fixture",
            "runtime_claim": False,
            "runtime_claim_reason": (
                "dataset Plan exam runs deterministic fixture_table asserts; "
                "≠ KB sample retrieval path; accuracy_claim=false"
            ),
            "accuracy_claim": False,
            "execution_mode": "dataset_plan_assert",
        }
    mode = f"{ot}_plan_llm" if live else f"{ot}_plan_dry"
    if live:
        reason = (
            f"{ot} Plan live uses sys_llm_generate; no dedicated {ot} host tier; "
            "accuracy_claim=false"
        )
    else:
        reason = f"{ot} Plan dry uses deterministic fixture stub; subject not claimed"
    return {
        "runtime_tier": "fixture",
        "target_runtime": target,
        "runtime_claim": False,
        "runtime_claim_reason": reason,
        "accuracy_claim": False,
        "execution_mode": mode,
    }


async def run_typed_plan_exam(
    *,
    object_type: str,
    object_id: str = "",
    set_ids: Optional[Sequence[str]] = None,
    purpose: Optional[Sequence[str]] = None,
    include_special: bool = False,
    live: bool = False,
    model: str = "",
    max_tasks_per_set: int = 20,
    source_refs: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Compile Plan for typed object + execute selected ``{type}/*`` sets."""
    from core.apps.eval.service.eval_plan import (
        attach_evaluation_plan,
        compile_plan_for_object,
    )
    from core.apps.eval.service.exam_runtime_tier import merge_runtime_fields
    from core.apps.eval.service.object_adapters import default_set_ids_for_type

    ot = str(object_type or "").strip()
    if ot not in _SUPPORTED:
        raise ValueError(f"unsupported typed plan object_type: {ot!r}")
    default_id = f"{ot}_under_test"
    oid = str(object_id or default_id).strip() or default_id
    refs = list(source_refs or [f"{ot}_plan_ops"])
    plan = compile_plan_for_object(
        object_type=ot,
        object_id=oid,
        set_ids=list(set_ids) if set_ids is not None else None,
        purpose=list(purpose) if purpose is not None else None,
        include_special=bool(include_special),
        live=bool(live),
        source_refs=refs,
    )
    from core.apps.eval.service.case_pack_legacy import (
        ManifestValidationError,
        require_sample_manifest,
    )

    try:
        sample_manifest = require_sample_manifest(plan)
    except ManifestValidationError as e:
        out_fail: Dict[str, Any] = {
            "ok": False,
            "error": str(e),
            "accuracy_claim": False,
            "sufficiency_claim": False,
            "msg": "Plan v2 fail closed: sample_manifest required (no full-pack fallback)",
        }
        return attach_evaluation_plan(out_fail, plan)

    # Execution list = sample_manifest only (selected_cases is legacy projection).
    allowed_by_set: Dict[str, set] = {}
    for row in sample_manifest:
        sid = str(row.get("set_id") or "").strip()
        cid = str(row.get("case_id") or "").strip()
        if not sid or not cid:
            continue
        allowed_by_set.setdefault(sid, set()).add(cid)
    selected = sorted(allowed_by_set.keys())
    if not selected:
        out_fail = {
            "ok": False,
            "error": "sample_manifest had no set_id/case_id rows",
            "accuracy_claim": False,
            "sufficiency_claim": False,
            "msg": "Plan v2 fail closed: empty executable sets",
        }
        return attach_evaluation_plan(out_fail, plan)

    run_id = f"{ot}-plan-{uuid.uuid4().hex[:12]}"
    started = time.time()
    paper_results: List[Dict[str, Any]] = []
    totals = {"pass": 0, "fail": 0, "inconclusive": 0, "error": 0, "tasks": 0}

    for sid in selected:
        try:
            payload = load_typed_set_json(sid, object_type=ot)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            paper_results.append(
                {"set_id": sid, "status": "error", "error": str(e)[:300], "tasks": []}
            )
            totals["error"] += 1
            continue
        tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
        allow = allowed_by_set.get(sid) or set()
        task_rows: List[Dict[str, Any]] = []
        n_taken = 0
        for task in tasks:
            if not isinstance(task, Mapping):
                continue
            tid = str(task.get("task_id") or "")
            if tid not in allow:
                continue
            if n_taken >= max(1, int(max_tasks_per_set)):
                break
            n_taken += 1
            user_input = str(task.get("user_input") or task.get("prompt") or "")
            criteria = (
                task.get("success_criteria")
                if isinstance(task.get("success_criteria"), dict)
                else {}
            )
            if not criteria and isinstance(task.get("rubric"), dict):
                from core.apps.eval.service.case_pack_legacy import (
                    rubric_to_success_criteria,
                )

                criteria = rubric_to_success_criteria(task.get("rubric"))
            totals["tasks"] += 1
            try:
                if ot == "dataset":
                    scored = score_dataset_task(task)
                    output = scored.get("summary") or ""
                elif live:
                    output = await live_llm_output(user_input, model_name=model)
                    scored = score_lexical_output(output, criteria)
                else:
                    output = dry_stub_output(task)
                    scored = score_lexical_output(output, criteria)
                st = str(scored.get("status") or "inconclusive")
                if st in totals:
                    totals[st] += 1
                else:
                    totals["inconclusive"] += 1
                task_rows.append(
                    {
                        "task_id": tid,
                        "status": st,
                        "summary": scored.get("summary"),
                        "output_excerpt": str(output)[:500],
                        "live": bool(live) and ot != "dataset",
                        "oracle": "dataset_assert" if ot == "dataset" else "lexical",
                    }
                )
            except Exception as e:  # noqa: BLE001 — per-task isolation
                _log.warning("%s plan task failed %s: %s", ot, tid, e, exc_info=True)
                totals["error"] += 1
                task_rows.append(
                    {
                        "task_id": tid,
                        "status": "error",
                        "summary": str(e)[:200],
                        "live": bool(live) and ot != "dataset",
                    }
                )
        set_fail = any(t.get("status") == "fail" for t in task_rows)
        set_err = any(t.get("status") == "error" for t in task_rows)
        paper_results.append(
            {
                "set_id": sid,
                "status": "error" if set_err else ("fail" if set_fail else "done"),
                "tasks": task_rows,
            }
        )

    out: Dict[str, Any] = {
        "ok": True,
        "run_id": run_id,
        "object_type": ot,
        "object_id": oid,
        "live": bool(live),
        "selected_set_ids": selected,
        "manifest_hash": plan.get("manifest_hash"),
        "manifest_case_count": len(sample_manifest),
        "papers": paper_results,
        "counts": totals,
        "duration_s": round(time.time() - started, 3),
        "accuracy_claim": False,
        "sufficiency_claim": False,
        "msg": (
            (
                f"{ot} Plan exam · deterministic fixture_table asserts · "
                "≠ KB sample path · accuracy_claim=false"
            )
            if ot == "dataset"
            else (
                f"{ot} Plan exam · lexical oracle on {ot}/* sets · "
                "accuracy_claim=false"
            )
        ),
    }
    out = merge_runtime_fields(
        out, annotate_typed_plan_runtime(object_type=ot, live=bool(live))
    )
    return attach_evaluation_plan(out, plan)


# Back-compat aliases used by prompt_plan_ops / tests
def load_prompt_set_json(set_id: str) -> Dict[str, Any]:
    return load_typed_set_json(set_id, object_type="prompt")


def score_prompt_output(
    output: str, criteria: Mapping[str, Any] | None
) -> Dict[str, Any]:
    return score_lexical_output(output, criteria)
