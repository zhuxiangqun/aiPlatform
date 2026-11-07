"""External pull-mode exam — chat HTTP + optional tool-order; accuracy_claim stays false."""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from core.apps.eval.service.agent_exam_ops import (
    _exam_gold_manifest,
    compute_exam_fact_support,
)
from core.apps.eval.service.external_chat_pull import (
    HttpChatPullAdapter,
    probe_target,
    tool_names_to_syscall_events,
)
from core.apps.eval.service.external_targets import (
    external_agent_id,
    get_external_target,
    list_external_targets,
    upsert_external_target,
)
from core.harness.evaluation.eval_metrics import EvalMetricsEngine
from core.harness.evaluation.eval_runner import (
    EvalRunner,
    load_eval_set,
    persist_runtime_eval,
    serialize_eval_result,
)
from core.harness.evaluation.eval_types import MatchMode, SingleTaskResult, TaskResultLevel

HONESTY_TEXT_ONLY = (
    "外部拉模式 · 仅对话文本结果；≠ 本机 live Agent；≠ 轨迹充分。"
)
HONESTY_WITH_TRAJ = (
    "外部拉模式 · 对话文本 + 工具序（IN_ORDER）；≠ 副作用充分 / ≠ 准确率。"
)


def list_targets(workspace_id: str) -> List[Dict[str, Any]]:
    return list_external_targets(workspace_id)


def register_target(workspace_id: str, **kwargs: Any) -> Dict[str, Any]:
    return upsert_external_target(workspace_id, **kwargs)


def _task_expected_tools(task: Any) -> List[str]:
    raw = getattr(task, "expected_tools", None) or []
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


async def run_external_exam(
    *,
    workspace_id: str,
    target_id: str,
    set_id: str,
    live: bool = False,
    max_tasks: int = 0,
    persist: bool = True,
    probe: bool = True,
) -> Dict[str, Any]:
    """Run exam paper against an external http_chat_pull target.

    live=False → validate target + paper (+ optional soft probe); no persist.
    live=True → pull each task, score text + optional IN_ORDER tool sequence, persist as ext:{id}.
    """
    from core.harness.named_workspace.resolve import (
        reset_active_named_workspace,
        resolve_named_workspace,
        set_active_named_workspace,
    )

    wid = (workspace_id or "").strip() or "default"
    tid = (target_id or "").strip()
    sid = (set_id or "").strip()
    if not tid:
        raise ValueError("target_id required")
    if not sid:
        raise ValueError("set_id required")

    nw = resolve_named_workspace(wid, method="POST" if live or persist else "GET")

    target = get_external_target(nw.workspace_id, tid)
    if target is None:
        raise FileNotFoundError(f"external target not found: {tid}")

    raw = load_eval_set(sid)
    if raw is None:
        raise FileNotFoundError(f"eval set not found: {sid}")

    agent_key = external_agent_id(tid)
    tasks = list(raw.tasks or [])
    if max_tasks and max_tasks > 0:
        tasks = tasks[: int(max_tasks)]

    paper_has_tool_gold = any(_task_expected_tools(t) for t in tasks)

    probe_info: Optional[Dict[str, Any]] = None
    if probe:
        probe_info = probe_target(target)

    if not live:
        from core.apps.eval.service.exam_runtime_tier import (
            annotate_external_exam_runtime,
            merge_runtime_fields,
        )

        dry = {
            "ok": True,
            "agent_id": agent_key,
            "target_id": tid,
            "set_id": sid,
            "live": False,
            "accuracy_claim": False,
            "sufficiency_claim": False,
            "mode": "external_http_chat_pull",
            "named_workspace_id": nw.workspace_id,
            "task_count": len(tasks),
            "probe": probe_info,
            "paper_has_tool_gold": paper_has_tool_gold,
            "message": (
                f"Dry-run external exam {sid} → {agent_key}: "
                f"target+paper ok; tasks={len(tasks)}"
                + (
                    f"; probe_ok={probe_info.get('ok')}"
                    if isinstance(probe_info, dict)
                    else ""
                )
            ),
            "honesty": HONESTY_WITH_TRAJ if paper_has_tool_gold else HONESTY_TEXT_ONLY,
        }
        return merge_runtime_fields(dry, annotate_external_exam_runtime(live=False))

    runner = EvalRunner()
    metrics = EvalMetricsEngine()
    adapter = HttpChatPullAdapter()
    results: List[SingleTaskResult] = []
    all_events: List[Dict[str, Any]] = []
    expected_traj: List[str] = []
    any_parsed_traj = False
    traj_task_matches: List[bool] = []

    for task in tasks:
        run_id = f"ext-eval-{uuid.uuid4().hex[:12]}"
        t0 = time.time()
        exp = _task_expected_tools(task)
        if exp:
            expected_traj.extend(exp)
        try:
            pull = adapter.invoke(
                target,
                user_input=str(task.user_input or ""),
                task_id=str(task.task_id or ""),
                set_id=sid,
            )
            output = str(pull.get("output_text") or "")
            names = list(pull.get("tool_names") or [])
            if names:
                any_parsed_traj = True
            events = tool_names_to_syscall_events(names)
            all_events.extend(events)
            if exp:
                tq = metrics.compute_trajectory_quality(
                    events,
                    expected_trajectory=exp,
                    match_mode=MatchMode.IN_ORDER,
                )
                traj_task_matches.append(bool(tq.matched))
            level = runner._determine_level(task, output, "done", 0, events)
            results.append(
                SingleTaskResult(
                    task_id=task.task_id,
                    agent_id=agent_key,
                    run_id=run_id,
                    level=level,
                    reasoning=runner._build_reasoning(level, output, task)
                    + "; mode=external_http_chat_pull"
                    + (f"; tools={names}" if names else ""),
                    evidence=output[:500] if output else "",
                    duration_ms=(time.time() - t0) * 1000,
                    steps=len(names),
                )
            )
        except Exception as e:
            results.append(
                SingleTaskResult(
                    task_id=task.task_id,
                    agent_id=agent_key,
                    run_id=run_id,
                    level=TaskResultLevel.ERROR_FAILURE,
                    reasoning=f"External pull failed: {e}",
                    evidence="",
                    duration_ms=(time.time() - t0) * 1000,
                    steps=0,
                    errors=[{"error": str(e)[:300]}],
                )
            )
            if exp:
                traj_task_matches.append(False)

    result = metrics.compute_all(
        agent_id=agent_key,
        task_results=results,
        syscall_events=all_events,
        eval_set_id=sid,
        expected_tools=list(expected_traj),
        expected_trajectory=list(expected_traj),
    )
    # Force IN_ORDER for external pull (compute_all defaults EXACT_ORDER).
    if expected_traj:
        result.trajectory_quality = metrics.compute_trajectory_quality(
            all_events,
            expected_trajectory=list(expected_traj),
            match_mode=MatchMode.IN_ORDER,
        )

    payload = serialize_eval_result(result)
    payload["accuracy_claim"] = False
    traj_scored = bool(paper_has_tool_gold and any_parsed_traj and expected_traj)
    payload["exam"] = {
        "agent_id": agent_key,
        "target_id": tid,
        "set_id": sid,
        "live": True,
        "task_count": len(tasks),
        "bound_override": False,
        "mode": "external_http_chat_pull",
        "trajectory_match_mode": "in_order" if traj_scored else None,
        "category": getattr(raw, "category", "") or "",
    }
    gold = _exam_gold_manifest(raw)
    gold["tool_gold_applicable"] = bool(paper_has_tool_gold)
    gold["trajectory_scored"] = traj_scored
    gold["trajectory_match_mode"] = "in_order" if traj_scored else None
    if traj_scored and traj_task_matches:
        rate = sum(1 for m in traj_task_matches if m) / max(1, len(traj_task_matches))
        gold["tool_gold_match_rate"] = round(rate, 4)
    elif traj_scored and result.trajectory_quality is not None:
        gold["tool_gold_match_rate"] = 1.0 if result.trajectory_quality.matched else 0.0
    fact = compute_exam_fact_support(
        raw,
        payload.get("task_results") if isinstance(payload.get("task_results"), list) else [],
    )
    if fact.get("fact_support_rate") is not None:
        gold["fact_support_rate"] = fact["fact_support_rate"]
        gold["fact_support_n"] = fact.get("fact_support_n")
        gold["fact_support_method"] = fact.get("method")
        gold["fact_support_details"] = fact.get("fact_support_details")
    payload["gold"] = gold
    payload["category"] = gold.get("category") or payload.get("category")
    payload["external"] = {
        "target_id": tid,
        "kind": "http_chat_pull",
        "workspace_id": nw.workspace_id,
        "trajectory_scored": traj_scored,
    }

    from core.apps.eval.service.agent_attributable_report import build_attributable_report

    attributable = build_attributable_report(
        payload, agent_id=agent_key, set_id=sid, live=True
    )
    payload["attributable_report"] = attributable

    from core.apps.eval.service.exam_runtime_tier import (
        annotate_external_exam_runtime,
        merge_runtime_fields,
    )

    rt = annotate_external_exam_runtime(live=True)
    payload["runtime_tier"] = rt["runtime_tier"]
    payload["runtime_claim"] = rt["runtime_claim"]
    payload["runtime_claim_reason"] = rt["runtime_claim_reason"]

    persisted: Optional[str] = None
    if persist:
        token = set_active_named_workspace(nw)
        try:
            persisted = persist_runtime_eval(agent_key, payload)
        finally:
            reset_active_named_workspace(token)

    honesty = HONESTY_WITH_TRAJ if traj_scored else HONESTY_TEXT_ONLY
    veto = bool((attributable.get("gate") or {}).get("veto"))
    publish = attributable.get("publish") if isinstance(attributable.get("publish"), dict) else {}
    publish_allowed = bool(publish.get("allowed")) if publish else (not veto)
    out = {
        "ok": True,
        "agent_id": agent_key,
        "target_id": tid,
        "set_id": sid,
        "live": True,
        "accuracy_claim": False,
        "sufficiency_claim": False,
        "mode": "external_http_chat_pull",
        "named_workspace_id": nw.workspace_id,
        "composite_score": payload.get("composite_score"),
        "grade": payload.get("grade"),
        "total_tasks": payload.get("total_tasks"),
        "result": payload,
        "attributable_report": attributable,
        "gate_pass": bool((attributable.get("gate") or {}).get("pass")),
        "safety_veto": veto,
        "publish_allowed": publish_allowed,
        "persisted_path": persisted,
        "probe": probe_info,
        "honesty": honesty,
        "message": (
            f"Live external exam {sid} → {agent_key}: "
            f"score={payload.get('composite_score')} ({payload.get('grade')})"
            + (f" · PUBLISH_VETO" if veto else " · PUBLISH_ALLOW_GAPS")
        ),
    }
    out = merge_runtime_fields(out, rt)
    try:
        from core.apps.eval.service.eval_plan import (
            attach_evaluation_plan,
            compile_plan_for_object,
        )

        plan = compile_plan_for_object(
            object_type="api",
            object_id=str(tid),
            set_ids=["api/chat_pull"],
            live=True,
            source_refs=["external_exam_ops"],
        )
        out = attach_evaluation_plan(out, plan)
        if isinstance(attributable, dict):
            attributable.setdefault("evaluation_plan", out.get("evaluation_plan"))
            attributable.setdefault("match_report", out.get("match_report"))
            attributable.setdefault("target_contract", out.get("target_contract"))
    except Exception:  # noqa: BLE001 — plan advisory must not fail external exam
        pass
    return out
