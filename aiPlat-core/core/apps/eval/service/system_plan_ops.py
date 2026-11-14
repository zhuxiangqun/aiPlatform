"""System combination Plan exam (Object Contract §0.8 P3 / §10.1).

Runs configured typed sub-exams and archives ``runtime_parts[]``.
Heterogeneous actual tiers must not collapse to a representative host tier
(``summarize_runtime_parts`` → mixed + claim=false).

≠ single-object Agent/Skill exam. accuracy_claim=false.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence

_log = logging.getLogger("aiplat.eval.system_plan")

_DEFAULT_PARTS: tuple = (
    {"object_type": "prompt", "set_ids": ["prompt/basic"]},
    {"object_type": "workflow", "set_ids": ["workflow/basic"]},
    {"object_type": "model", "set_ids": ["model/basic"]},
    {"object_type": "dataset", "set_ids": ["dataset/basic"]},
)

_TYPED = frozenset({"prompt", "workflow", "model", "dataset"})


def _normalize_parts(
    parts: Optional[Sequence[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    raw = list(parts) if parts is not None else [dict(p) for p in _DEFAULT_PARTS]
    out: List[Dict[str, Any]] = []
    for i, p in enumerate(raw):
        if not isinstance(p, Mapping):
            continue
        ot = str(p.get("object_type") or "").strip()
        if ot not in _TYPED:
            raise ValueError(
                f"system part[{i}] object_type must be one of {sorted(_TYPED)}; got {ot!r}"
            )
        sid = str(p.get("object_id") or f"{ot}_part").strip() or f"{ot}_part"
        set_ids = p.get("set_ids")
        if set_ids is not None and not isinstance(set_ids, (list, tuple)):
            raise ValueError(f"system part[{i}] set_ids must be a list")
        out.append(
            {
                "object_type": ot,
                "object_id": sid,
                "set_ids": list(set_ids) if set_ids is not None else None,
                "include_special": bool(p.get("include_special")),
                "purpose": list(p.get("purpose") or []) or None,
            }
        )
    if not out:
        raise ValueError("system plan requires at least one typed part")
    return out


async def run_system_plan_exam(
    *,
    object_id: str = "system_under_test",
    parts: Optional[Sequence[Mapping[str, Any]]] = None,
    live: bool = False,
    model: str = "",
    max_tasks_per_set: int = 20,
) -> Dict[str, Any]:
    """Execute typed sub-exams and aggregate runtime_parts + system Plan stamp.

    Args:
        object_id: object 标识。
        parts: parts 参数。
        live: 是否 live（非 fixture）路径。
        model: 模型名。
        max_tasks_per_set: max_tasks_per_set 参数。
    """
    from core.apps.eval.service.eval_plan import (
        attach_evaluation_plan,
        compile_plan_for_object,
    )
    from core.apps.eval.service.exam_runtime_tier import merge_runtime_fields
    from core.apps.eval.service.typed_plan_exam import run_typed_plan_exam

    oid = str(object_id or "system_under_test").strip() or "system_under_test"
    norm_parts = _normalize_parts(parts)
    started = time.time()
    run_id = f"system-plan-{uuid.uuid4().hex[:12]}"

    # System Plan: contract-only (no system/* packs); parts carry case truth.
    plan = compile_plan_for_object(
        object_type="system",
        object_id=oid,
        set_ids=[],
        purpose=["behavior", "regression"],
        include_special=False,
        live=bool(live),
        source_refs=["system_plan_ops"],
    )

    sub_results: List[Dict[str, Any]] = []
    runtime_parts: List[Dict[str, Any]] = []
    totals = {
        "parts": 0,
        "parts_ok": 0,
        "parts_fail": 0,
        "parts_error": 0,
        "tasks": 0,
        "pass": 0,
        "fail": 0,
        "inconclusive": 0,
        "error": 0,
    }

    for spec in norm_parts:
        totals["parts"] += 1
        ot = spec["object_type"]
        sub_id = f"{ot}:{spec['object_id']}"
        try:
            sub = await run_typed_plan_exam(
                object_type=ot,
                object_id=str(spec["object_id"]),
                set_ids=spec.get("set_ids"),
                purpose=spec.get("purpose"),
                include_special=bool(spec.get("include_special")),
                live=bool(live) and ot != "dataset",
                model=model,
                max_tasks_per_set=max_tasks_per_set,
                source_refs=["system_plan_ops", f"{ot}_plan_ops"],
            )
        except Exception as e:  # noqa: BLE001 — isolate parts
            _log.warning("system part %s failed: %s", sub_id, e, exc_info=True)
            totals["parts_error"] += 1
            totals["error"] += 1
            err_row = {
                "ok": False,
                "object_type": ot,
                "object_id": spec["object_id"],
                "error": str(e)[:300],
                "runtime_tier": "fixture",
                "target_runtime": "fixture",
                "runtime_claim": False,
            }
            sub_results.append(err_row)
            runtime_parts.append(
                {
                    "sub_id": sub_id,
                    "runtime_tier": "fixture",
                    "target_runtime": "fixture",
                    "runtime_claim": False,
                    "execution_mode": f"{ot}_plan_error",
                    "result": {"ok": False, "error": str(e)[:200]},
                }
            )
            continue

        counts = sub.get("counts") if isinstance(sub.get("counts"), dict) else {}
        for k in ("tasks", "pass", "fail", "inconclusive", "error"):
            try:
                totals[k] += int(counts.get(k) or 0)
            except (TypeError, ValueError) as e:
                _log.debug("system_plan count skip %s=%r: %s", k, counts.get(k), e)
        papers = sub.get("papers") if isinstance(sub.get("papers"), list) else []
        part_bad = any(
            isinstance(p, dict) and p.get("status") in ("fail", "error") for p in papers
        ) or not bool(sub.get("ok", True))
        if part_bad:
            totals["parts_fail"] += 1
        else:
            totals["parts_ok"] += 1

        tier = str(sub.get("runtime_tier") or "fixture")
        target = str(sub.get("target_runtime") or tier)
        runtime_parts.append(
            {
                "sub_id": sub_id,
                "runtime_tier": tier,
                "target_runtime": target,
                "runtime_claim": bool(sub.get("runtime_claim")),
                "execution_mode": sub.get("execution_mode"),
                "result": {
                    "ok": bool(sub.get("ok")),
                    "run_id": sub.get("run_id"),
                    "counts": counts,
                    "selected_set_ids": sub.get("selected_set_ids"),
                },
            }
        )
        # Keep payload lean for top-level response
        sub_results.append(
            {
                "ok": bool(sub.get("ok")),
                "object_type": ot,
                "object_id": spec["object_id"],
                "run_id": sub.get("run_id"),
                "selected_set_ids": sub.get("selected_set_ids"),
                "counts": counts,
                "runtime_tier": tier,
                "target_runtime": target,
                "execution_mode": sub.get("execution_mode"),
                "papers": papers,
            }
        )

    out: Dict[str, Any] = {
        "ok": totals["parts_error"] == 0 and totals["parts_fail"] == 0,
        "run_id": run_id,
        "object_type": "system",
        "object_id": oid,
        "live": bool(live),
        "parts": sub_results,
        "counts": totals,
        "duration_s": round(time.time() - started, 3),
        "accuracy_claim": False,
        "sufficiency_claim": False,
        "msg": (
            "system Plan exam · composed typed parts · runtime_parts archived · "
            "heterogeneous tiers → mixed · ≠ single-object exam · accuracy_claim=false"
        ),
        "runtime_parts": runtime_parts,
    }
    # summarize_runtime_parts via merge_runtime_fields
    out = merge_runtime_fields(out, {"runtime_parts": runtime_parts})
    out = attach_evaluation_plan(out, plan)
    # Preserve parts list after attach
    out["parts"] = sub_results
    out["runtime_parts"] = runtime_parts
    return out
