"""
compat.py — Backward-compatibility + evaluation + playground routes.

Evaluation and playground endpoints are fully implemented.
Repairs/workbench stubs delegate to existing handlers.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Query, Request

logger = logging.getLogger("aiplat.compat")

router = APIRouter(tags=["compat"])


# ════════════════════════════════════════════════════════════
# Evaluation — LearningManager + eval_results disk store
# ════════════════════════════════════════════════════════════

async def _get_learning_manager():
    from core.learning.manager import LearningManager
    return LearningManager()


def _score_payload(
    agent_id: str,
    results: List[Dict[str, Any]],
    *,
    set_id: str = "",
) -> Dict[str, Any]:
    """Shape expected by EvalDashboard (legacy_7dim; accuracy_claim false)."""
    want = (set_id or "").strip()
    if not results:
        return {
            "agent_id": agent_id,
            "set_id": want or None,
            "latest_score": None,
            "grade": "",
            "eval_time": None,
            "total_evals": 0,
            "has_data": False,
            "accuracy_claim": False,
            "note": (
                f"no eval_results for set={want} — run live exam on this paper"
                if want
                else "no eval_results yet — run scripts/eval.sh or enable AIPLAT_ENABLE_AUTO_EVAL"
            ),
        }
    latest = results[0]
    dim_keys = (
        "task_completion",
        "tool_quality",
        "trajectory",
        "text_quality",
        "step_efficiency",
        "error_recovery",
        "safety",
        "content_safety",
        "refusal",
        "cost",
    )
    dimensions = {k: latest[k] for k in dim_keys if isinstance(latest.get(k), dict)}
    from core.apps.eval.service.agent_attributable_report import build_attributable_report

    attributable = latest.get("attributable_report")
    if not isinstance(attributable, dict):
        attributable = build_attributable_report(latest, agent_id=agent_id)
    return {
        "agent_id": agent_id,
        "latest_score": latest.get("composite_score"),
        "grade": latest.get("grade") or "",
        "eval_time": latest.get("eval_time"),
        "total_evals": len(results),
        "total_tasks": latest.get("total_tasks"),
        "dimensions": dimensions or None,
        "has_data": True,
        "accuracy_claim": False,
        "scoring": latest.get("scoring"),
        "attributable_report": attributable,
        "gate_pass": bool((attributable.get("gate") or {}).get("pass")),
        "safety_veto": bool((attributable.get("gate") or {}).get("veto")),
        "publish_allowed": bool((attributable.get("publish") or {}).get("allowed")),
        "sufficiency_claim": False,
    }


@router.get("/evaluation/overview")
async def compat_evaluation_overview():
    """Evaluation dashboard overview — learning artifacts + disk eval_results agents."""
    try:
        mgr = await _get_learning_manager()
        overview = await mgr.get_overview()
    except Exception as e:
        logger.debug("evaluation overview failed", exc_info=True)
        overview = {"status": "error", "message": str(e)[:200]}

    agents: List[Dict[str, Any]] = []
    eval_sets = 0
    try:
        from core.harness.evaluation.eval_runner import (
            list_agents_with_eval_results,
            list_eval_sets,
        )

        agents = list_agents_with_eval_results(limit=100)
        eval_sets = len(list_eval_sets())
    except Exception:
        logger.debug("evaluation overview disk agents failed", exc_info=True)

    total_evals = sum(int(a.get("evals_count") or 0) for a in agents)
    return {
        "status": "ok",
        **(overview if isinstance(overview, dict) else {}),
        "agents": agents,
        "agents_evaluated": len(agents),
        "total_evals": total_evals,
        "eval_sets": eval_sets,
        "accuracy_claim": False,
    }


@router.get("/evaluation/agents/{agent_id}/score")
async def compat_evaluation_agent_score(
    agent_id: str,
    request: Request,
    set_id: str = Query("", description="Optional filter by eval_set_id"),
):
    """Latest AgentEvalResult from workspace eval_results (empty ≠ 404)."""
    from core.harness.evaluation.eval_runner import load_agent_eval_results
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    want = (set_id or "").strip()
    with named_workspace_scope(request, method="GET", require_local=True) as nw:
        results = load_agent_eval_results(agent_id, limit=50 if not want else 200)
        if want:
            results = [
                r
                for r in results
                if str(r.get("eval_set_id") or r.get("set_id") or "").strip() == want
            ]
        out = _score_payload(agent_id, results, set_id=want)
        out.update(workspace_meta(nw))
        return out


@router.get("/evaluation/agents/{agent_id}/attributable-report")
async def compat_evaluation_agent_attributable_report(
    agent_id: str,
    request: Request,
    limit: int = Query(5, ge=1, le=20),
    set_id: str = Query("", description="Scope to this exam set; empty = latest any set"),
):
    """Task / tools / safety-veto / cost attributable report (accuracy_claim=false)."""
    from core.api.core_facade import eval_agent_attributable_report
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    with named_workspace_scope(request, method="GET", require_local=True) as nw:
        out = eval_agent_attributable_report(
            agent_id=agent_id, limit=limit, set_id=(set_id or "").strip()
        )
        if isinstance(out, dict):
            out.update(workspace_meta(nw))
        return out


@router.get("/evaluation/agents/{agent_id}/history")
async def compat_evaluation_agent_history(
    agent_id: str,
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    set_id: str = Query("", description="Optional filter by eval_set_id"),
):
    """Eval history for dashboard trend chart (empty list when none)."""
    from core.harness.evaluation.eval_runner import load_agent_eval_results
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    want = (set_id or "").strip()
    with named_workspace_scope(request, method="GET", require_local=True) as nw:
        fetch_n = max(limit * 10, 50) if want else limit
        results = load_agent_eval_results(agent_id, limit=fetch_n)
        if want:
            results = [
                r
                for r in results
                if str(r.get("eval_set_id") or r.get("set_id") or "").strip() == want
            ][:limit]
        else:
            results = results[:limit]
        history = [
            {
                "eval_time": r.get("eval_time"),
                "composite_score": r.get("composite_score"),
                "grade": r.get("grade") or "",
                "eval_set_id": r.get("eval_set_id") or "",
                "total_tasks": r.get("total_tasks") or 0,
            }
            for r in results
        ]
        out = {
            "agent_id": agent_id,
            "set_id": want or None,
            "history": history,
            "count": len(history),
            "accuracy_claim": False,
        }
        out.update(workspace_meta(nw))
        return out


@router.get("/evaluation/sets")
async def compat_evaluation_list_sets():
    """List exam papers (built-in eval sets) for Agent 从零开考."""
    from core.api.core_facade import eval_list_exam_sets

    items = eval_list_exam_sets()
    return {
        "items": items,
        "total": len(items),
        "accuracy_claim": False,
    }


@router.post("/evaluation/match-cases")
async def compat_evaluation_match_cases(body: Dict[str, Any]):
    """Object-contract P0: advisory MatchReport for agent vs set applicability.

    Body: {agent_id, set_ids?, capabilities?, tools?, permissions?, roles?, eval_profile?}
    Does not execute agents.
    """
    from core.api.core_facade import eval_match_cases_for_agent_target

    agent_id = str((body or {}).get("agent_id") or "").strip()
    if not agent_id:
        return {"ok": False, "error": "agent_id required", "accuracy_claim": False}
    set_ids = (body or {}).get("set_ids")
    if set_ids is not None and not isinstance(set_ids, list):
        return {"ok": False, "error": "set_ids must be a list", "accuracy_claim": False}
    profile = (body or {}).get("eval_profile")
    if profile is not None and not isinstance(profile, dict):
        return {"ok": False, "error": "eval_profile must be an object", "accuracy_claim": False}
    try:
        return eval_match_cases_for_agent_target(
            agent_id=agent_id,
            set_ids=set_ids,
            capabilities=(body or {}).get("capabilities"),
            tools=(body or {}).get("tools"),
            permissions=(body or {}).get("permissions"),
            roles=(body or {}).get("roles"),
            eval_profile=profile,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("evaluation match-cases failed", exc_info=True)
        return {"ok": False, "error": str(e)[:300], "accuracy_claim": False}


@router.post("/evaluation/compile-plan")
async def compat_evaluation_compile_plan(body: Dict[str, Any]):
    """Object-contract P2/P3: compile Evaluation Plan for agent/skill/api/generated_app/….

    Body: {agent_id|object_id, object_type?, set_ids?, purpose?, include_special?, …}
    For agent without eval_profile/capabilities, server derives hints from skills/tools.
    """
    from core.api.core_facade import eval_compile_evaluation_plan

    agent_id = str((body or {}).get("agent_id") or "").strip()
    object_id = str((body or {}).get("object_id") or "").strip()
    if not agent_id and not object_id:
        return {
            "ok": False,
            "error": "object_id or agent_id required",
            "accuracy_claim": False,
        }
    set_ids = (body or {}).get("set_ids")
    purpose = (body or {}).get("purpose")
    if set_ids is not None and not isinstance(set_ids, list):
        return {"ok": False, "error": "set_ids must be a list", "accuracy_claim": False}
    if purpose is not None and not isinstance(purpose, list):
        return {"ok": False, "error": "purpose must be a list", "accuracy_claim": False}
    profile = (body or {}).get("eval_profile")
    if profile is not None and not isinstance(profile, dict):
        return {"ok": False, "error": "eval_profile must be an object", "accuracy_claim": False}
    object_type = str((body or {}).get("object_type") or "agent").strip() or "agent"
    capabilities = (body or {}).get("capabilities")
    # Auto-resolve agent profile when caller did not supply capabilities/profile.
    if (
        object_type == "agent"
        and agent_id
        and not profile
        and not capabilities
    ):
        try:
            from core.apps.eval.service.eval_profile_resolve import resolve_agent_eval_profile

            profile = await resolve_agent_eval_profile(agent_id)
        except FileNotFoundError as e:
            # Do not silently compile an empty Plan for a missing agent — UI would
            # show wrong N/A counts while the picker still lists the id.
            return {
                "ok": False,
                "error": str(e),
                "accuracy_claim": False,
            }
        except Exception as e:  # noqa: BLE001 — unexpected resolve errors
            logger.debug("resolve_agent_eval_profile failed: %s", e)
            return {
                "ok": False,
                "error": f"resolve_agent_eval_profile failed: {e}"[:300],
                "accuracy_claim": False,
            }
    try:
        return eval_compile_evaluation_plan(
            agent_id=agent_id,
            object_id=object_id,
            object_type=object_type,
            set_ids=set_ids,
            purpose=purpose,
            include_special=bool((body or {}).get("include_special")),
            live=bool((body or {}).get("live")),
            capabilities=capabilities,
            tools=(body or {}).get("tools"),
            permissions=(body or {}).get("permissions"),
            roles=(body or {}).get("roles"),
            eval_profile=profile,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("evaluation compile-plan failed", exc_info=True)
        return {"ok": False, "error": str(e)[:300], "accuracy_claim": False}


@router.post("/evaluation/resolve-eval-profile")
async def compat_evaluation_resolve_eval_profile(body: Dict[str, Any]):
    """Resolve Agent eval_profile (explicit config or derived skill/tool hints)."""
    from core.apps.eval.service.eval_profile_resolve import resolve_agent_eval_profile

    agent_id = str((body or {}).get("agent_id") or "").strip()
    if not agent_id:
        return {"ok": False, "error": "agent_id required", "accuracy_claim": False}
    try:
        profile = await resolve_agent_eval_profile(agent_id)
        return {
            "ok": True,
            "agent_id": agent_id,
            "eval_profile": profile,
            "accuracy_claim": False,
            "sufficiency_claim": False,
            "honesty": (
                "explicit config.eval_profile wins; else derived_hints from skills/tools "
                "substrings — not a certified capability declaration"
            ),
        }
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("resolve-eval-profile failed", exc_info=True)
        return {"ok": False, "error": str(e)[:300], "accuracy_claim": False}


@router.post("/evaluation/exam")
async def compat_evaluation_exam(body: Dict[str, Any], request: Request):
    """从零开考：选 agent + 试卷 → dry-run 或 live 执行并落分。

    Body: {agent_id, set_id, live?: bool, max_tasks?: int}
    Write: requires X-Aiplat-Workspace-Id (no silent default).
    """
    from fastapi import HTTPException

    from core.api.core_facade import eval_run_agent_exam
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    agent_id = str((body or {}).get("agent_id") or "").strip()
    set_id = str((body or {}).get("set_id") or "").strip()
    live = bool((body or {}).get("live"))
    max_tasks = int((body or {}).get("max_tasks") or 0)
    if not agent_id or not set_id:
        return {
            "ok": False,
            "error": "agent_id and set_id required",
            "accuracy_claim": False,
        }
    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = await eval_run_agent_exam(
                agent_id=agent_id,
                set_id=set_id,
                live=live,
                max_tasks=max_tasks,
                persist=True,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, dict) else {"error": str(e.detail)}
        return {
            "ok": False,
            "error": detail.get("error") or "workspace_error",
            "message": detail.get("message") or str(e.detail),
            "accuracy_claim": False,
        }
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("evaluation exam failed", exc_info=True)
        return {
            "ok": False,
            "error": str(e)[:300],
            "accuracy_claim": False,
        }
    except BaseException as e:
        # CancelledError (BaseException) must not become Starlette "No response returned".
        if type(e).__name__ == "CancelledError":
            logger.warning("evaluation exam cancelled", exc_info=True)
            return {
                "ok": False,
                "error": "exam_cancelled",
                "message": "评测任务被取消，请重试正式评测",
                "accuracy_claim": False,
            }
        raise


@router.get("/evaluation/external-targets")
async def compat_evaluation_list_external_targets(request: Request):
    """List external http_chat_pull targets for the selected named workspace."""
    from fastapi import HTTPException

    from core.api.core_facade import eval_list_external_targets
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="GET", require_local=True) as nw:
            out = eval_list_external_targets(workspace_id=nw.workspace_id)
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, dict) else {"error": str(e.detail)}
        return {
            "ok": False,
            "error": detail.get("error") or "workspace_error",
            "message": detail.get("message") or str(e.detail),
            "items": [],
            "accuracy_claim": False,
        }


@router.post("/evaluation/external-targets")
async def compat_evaluation_upsert_external_target(body: Dict[str, Any], request: Request):
    """Register external chat-pull target. Write requires X-Aiplat-Workspace-Id."""
    from fastapi import HTTPException

    from core.api.core_facade import eval_upsert_external_target
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_upsert_external_target(
                workspace_id=nw.workspace_id,
                target_id=str((body or {}).get("target_id") or "").strip(),
                label=str((body or {}).get("label") or "").strip(),
                base_url=str((body or {}).get("base_url") or "").strip(),
                path=str((body or {}).get("path") or "/v1/chat").strip() or "/v1/chat",
                auth_header_name=str((body or {}).get("auth_header_name") or "").strip(),
                auth_secret_env=str((body or {}).get("auth_secret_env") or "").strip(),
                timeout_ms=int((body or {}).get("timeout_ms") or 30_000),
                response_mode=str((body or {}).get("response_mode") or "aiplat_v0").strip(),
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, dict) else {"error": str(e.detail)}
        return {
            "ok": False,
            "error": detail.get("error") or "workspace_error",
            "message": detail.get("message") or str(e.detail),
            "accuracy_claim": False,
        }
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("external target upsert failed", exc_info=True)
        return {"ok": False, "error": str(e)[:300], "accuracy_claim": False}


@router.post("/evaluation/external-exam")
async def compat_evaluation_external_exam(body: Dict[str, Any], request: Request):
    """External pull-mode exam: target_id + set_id → dry-run or live score.

    Body: {target_id, set_id, live?: bool, max_tasks?: int}
    Write: requires X-Aiplat-Workspace-Id.
    """
    from fastapi import HTTPException

    from core.api.core_facade import eval_run_external_exam
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    target_id = str((body or {}).get("target_id") or "").strip()
    set_id = str((body or {}).get("set_id") or "").strip()
    live = bool((body or {}).get("live"))
    max_tasks = int((body or {}).get("max_tasks") or 0)
    if not target_id or not set_id:
        return {
            "ok": False,
            "error": "target_id and set_id required",
            "accuracy_claim": False,
        }
    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = await eval_run_external_exam(
                workspace_id=nw.workspace_id,
                target_id=target_id,
                set_id=set_id,
                live=live,
                max_tasks=max_tasks,
                persist=True,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, dict) else {"error": str(e.detail)}
        return {
            "ok": False,
            "error": detail.get("error") or "workspace_error",
            "message": detail.get("message") or str(e.detail),
            "accuracy_claim": False,
        }
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("external exam failed", exc_info=True)
        return {
            "ok": False,
            "error": str(e)[:300],
            "accuracy_claim": False,
        }


@router.post("/evaluation/generated-app-pi-smoke")
async def compat_evaluation_generated_app_pi_smoke(body: Dict[str, Any]):
    """Generated-app Pi delivery smoke: sample/project/path → offline or live pi CLI.

    Body: {source?: sample|project|path, project_id?, app_home?, live?: bool, model?, timeout_s?}
    """
    from core.api.core_facade import eval_run_generated_app_pi_smoke

    source = str((body or {}).get("source") or "sample").strip() or "sample"
    project_id = str((body or {}).get("project_id") or "").strip()
    app_home = str((body or {}).get("app_home") or "").strip()
    live = bool((body or {}).get("live"))
    model = str((body or {}).get("model") or "").strip()
    try:
        timeout_s = float((body or {}).get("timeout_s") or 90.0)
    except (TypeError, ValueError):
        timeout_s = 90.0
    try:
        return eval_run_generated_app_pi_smoke(
            source=source,
            project_id=project_id,
            app_home=app_home,
            live=live,
            model=model,
            timeout_s=timeout_s,
        )
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("generated-app pi smoke failed", exc_info=True)
        return {
            "ok": False,
            "error": str(e)[:300],
            "accuracy_claim": False,
        }


async def _typed_plan_exam_compat(
    *,
    object_type: str,
    body: Dict[str, Any],
    default_object_id: str,
    runner,
):
    set_ids = (body or {}).get("set_ids")
    purpose = (body or {}).get("purpose")
    if set_ids is not None and not isinstance(set_ids, list):
        return {"ok": False, "error": "set_ids must be a list", "accuracy_claim": False}
    if purpose is not None and not isinstance(purpose, list):
        return {"ok": False, "error": "purpose must be a list", "accuracy_claim": False}
    try:
        max_tasks = int((body or {}).get("max_tasks_per_set") or 20)
    except (TypeError, ValueError):
        max_tasks = 20
    try:
        return await runner(
            object_id=str((body or {}).get("object_id") or default_object_id).strip(),
            set_ids=set_ids,
            purpose=purpose,
            include_special=bool((body or {}).get("include_special")),
            live=bool((body or {}).get("live")),
            model=str((body or {}).get("model") or "").strip(),
            max_tasks_per_set=max_tasks,
        )
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("%s-plan-exam failed", object_type, exc_info=True)
        return {"ok": False, "error": str(e)[:300], "accuracy_claim": False}


@router.post("/evaluation/prompt-plan-exam")
async def compat_evaluation_prompt_plan_exam(body: Dict[str, Any]):
    """Prompt Plan-chain exam (≠ page/DB prompt_eval)."""
    from core.api.core_facade import eval_run_prompt_plan_exam

    return await _typed_plan_exam_compat(
        object_type="prompt",
        body=body or {},
        default_object_id="prompt_under_test",
        runner=eval_run_prompt_plan_exam,
    )


@router.post("/evaluation/workflow-plan-exam")
async def compat_evaluation_workflow_plan_exam(body: Dict[str, Any]):
    """Workflow Plan-chain exam: workflow/* lexical oracle."""
    from core.api.core_facade import eval_run_workflow_plan_exam

    return await _typed_plan_exam_compat(
        object_type="workflow",
        body=body or {},
        default_object_id="workflow_under_test",
        runner=eval_run_workflow_plan_exam,
    )


@router.post("/evaluation/model-plan-exam")
async def compat_evaluation_model_plan_exam(body: Dict[str, Any]):
    """Model Plan-chain exam: model/* lexical oracle (≠ model leaderboard)."""
    from core.api.core_facade import eval_run_model_plan_exam

    return await _typed_plan_exam_compat(
        object_type="model",
        body=body or {},
        default_object_id="model_under_test",
        runner=eval_run_model_plan_exam,
    )


@router.post("/evaluation/dataset-plan-exam")
async def compat_evaluation_dataset_plan_exam(body: Dict[str, Any]):
    """Dataset Plan-chain exam: fixture_table asserts (≠ KB sample path)."""
    from core.api.core_facade import eval_run_dataset_plan_exam

    return await _typed_plan_exam_compat(
        object_type="dataset",
        body=body or {},
        default_object_id="dataset_under_test",
        runner=eval_run_dataset_plan_exam,
    )


@router.post("/evaluation/system-plan-exam")
async def compat_evaluation_system_plan_exam(body: Dict[str, Any]):
    """System combination exam: typed parts + runtime_parts (§10.1).

    Body: {object_id?, parts?: [{object_type, object_id?, set_ids?}], live?, model?, max_tasks_per_set?}
    Default parts: prompt/workflow/model/dataset basic dry packs.
    """
    from core.api.core_facade import eval_run_system_plan_exam

    parts = (body or {}).get("parts")
    if parts is not None and not isinstance(parts, list):
        return {"ok": False, "error": "parts must be a list", "accuracy_claim": False}
    try:
        max_tasks = int((body or {}).get("max_tasks_per_set") or 20)
    except (TypeError, ValueError):
        max_tasks = 20
    try:
        return await eval_run_system_plan_exam(
            object_id=str((body or {}).get("object_id") or "system_under_test").strip(),
            parts=parts,
            live=bool((body or {}).get("live")),
            model=str((body or {}).get("model") or "").strip(),
            max_tasks_per_set=max_tasks,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("system-plan-exam failed", exc_info=True)
        return {"ok": False, "error": str(e)[:300], "accuracy_claim": False}


@router.post("/evaluation/claims-gate")
async def compat_evaluation_claims_gate(body: Dict[str, Any]):
    """L5 scope-bound claims gate (eval.claims_gate.v1).

    Body: {evidence: {...scope fields...}, explicit_authorize?: bool}
    Never auto-publishes certification; fixture/dry/incomplete → not eligible.
    """
    from core.api.core_facade import eval_evaluate_l5_claims_gate

    evidence = (body or {}).get("evidence")
    if evidence is None:
        evidence = body or {}
    if not isinstance(evidence, dict):
        return {"ok": False, "error": "evidence must be an object", "accuracy_claim": False}
    # Strip control keys if whole body was passed as evidence
    ev = {
        k: v
        for k, v in evidence.items()
        if k not in ("explicit_authorize", "evidence")
    }
    try:
        report = eval_evaluate_l5_claims_gate(
            evidence=ev,
            explicit_authorize=bool((body or {}).get("explicit_authorize")),
        )
        report["ok"] = True
        return report
    except Exception as e:
        logger.debug("claims-gate failed", exc_info=True)
        return {"ok": False, "error": str(e)[:300], "accuracy_claim": False}


def _case_pack_http_error(exc: BaseException) -> Dict[str, Any]:
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
        return {
            "ok": False,
            "error": detail.get("error") or "workspace_error",
            "message": detail.get("message") or str(exc.detail),
            "accuracy_claim": False,
        }
    return {
        "ok": False,
        "error": str(exc)[:300],
        "accuracy_claim": False,
    }


@router.post("/evaluation/case-packs/draft")
async def compat_evaluation_case_pack_draft(body: Dict[str, Any], request: Request):
    """P1.0/P1.3: template|cases → workspace draft pack (claim_eligible=false)."""
    from core.api.core_facade import eval_publish_draft_case_pack
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_publish_draft_case_pack(
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                template=(body or {}).get("template"),
                variants=(body or {}).get("variants"),
                cases=(body or {}).get("cases"),
                workspace_id=nw.workspace_id,
                caller_workspace_id=nw.workspace_id,
                object_types=(body or {}).get("object_types"),
                kind=str((body or {}).get("kind") or "curated"),
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs draft failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/enqueue-review")
async def compat_evaluation_case_pack_enqueue_review(
    body: Dict[str, Any], request: Request
):
    """P1.1/P1.3: draft|rejected → in_review."""
    from core.api.core_facade import eval_enqueue_case_pack_review
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_enqueue_case_pack_review(
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                workspace_id=nw.workspace_id,
                caller_workspace_id=nw.workspace_id,
                notes=str((body or {}).get("notes") or ""),
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs enqueue-review failed", exc_info=True)
        return _case_pack_http_error(e)


@router.get("/evaluation/case-packs/review-queue")
async def compat_evaluation_case_pack_review_queue(
    request: Request,
    statuses: str = Query(""),
):
    """P1.1/P1.3: list workspace draft/in_review packs. statuses=comma list optional."""
    from core.api.core_facade import eval_list_case_pack_review_queue
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    status_list = [s.strip() for s in (statuses or "").split(",") if s.strip()] or None
    try:
        with named_workspace_scope(request, method="GET", require_local=True) as nw:
            out = eval_list_case_pack_review_queue(
                workspace_id=nw.workspace_id,
                caller_workspace_id=nw.workspace_id,
                statuses=status_list,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs review-queue failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/review")
async def compat_evaluation_case_pack_review(body: Dict[str, Any], request: Request):
    """P1.1/P1.3: approve→reviewed / reject→rejected. Never freezes."""
    from core.api.core_facade import eval_submit_case_pack_review
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_submit_case_pack_review(
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                workspace_id=nw.workspace_id,
                decision=str((body or {}).get("decision") or "").strip(),
                reviewer=str((body or {}).get("reviewer") or ""),
                notes=str((body or {}).get("notes") or ""),
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs review failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/freeze")
async def compat_evaluation_case_pack_freeze(body: Dict[str, Any], request: Request):
    """P1.2/P1.3: reviewed → kind=frozen; claim_eligible stays false."""
    from core.api.core_facade import eval_freeze_workspace_case_pack
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_freeze_workspace_case_pack(
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                workspace_id=nw.workspace_id,
                caller_workspace_id=nw.workspace_id,
                frozen_by=str((body or {}).get("frozen_by") or ""),
                notes=str((body or {}).get("notes") or ""),
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs freeze failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/promote-agent-capability")
async def compat_evaluation_promote_agent_capability(body: Dict[str, Any], request: Request):
    """P1 closeout: seed bank → draft → approve → freeze (claim_eligible=false)."""
    from core.api.core_facade import eval_promote_agent_capability_bank
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_promote_agent_capability_bank(
                workspace_id=nw.workspace_id,
                caller_workspace_id=nw.workspace_id,
                reviewer=str((body or {}).get("reviewer") or ""),
                frozen_by=str((body or {}).get("frozen_by") or ""),
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                notes=str((body or {}).get("notes") or ""),
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("promote-agent-capability failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/promote-subject-capability")
async def compat_evaluation_promote_subject_capability(body: Dict[str, Any], request: Request):
    """Subject seed bank → purpose_ok → freeze (claim_eligible=false)."""
    from core.api.core_facade import (
        eval_promote_all_subject_capability_banks,
        eval_promote_subject_capability_bank,
    )
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    kind = str((body or {}).get("subject_kind") or "").strip()
    all_subjects = bool((body or {}).get("all")) or kind in ("*", "all")
    if not all_subjects and not kind:
        return {
            "ok": False,
            "error": "subject_kind required (or all=true)",
            "claim_eligible": False,
            "accuracy_claim": False,
        }
    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            reviewer = str((body or {}).get("reviewer") or "")
            frozen_by = str((body or {}).get("frozen_by") or "")
            notes = str((body or {}).get("notes") or "")
            if all_subjects:
                out = eval_promote_all_subject_capability_banks(
                    workspace_id=nw.workspace_id,
                    caller_workspace_id=nw.workspace_id,
                    reviewer=reviewer,
                    frozen_by=frozen_by,
                    notes=notes,
                )
            else:
                out = eval_promote_subject_capability_bank(
                    subject_kind=kind,
                    workspace_id=nw.workspace_id,
                    caller_workspace_id=nw.workspace_id,
                    reviewer=reviewer,
                    frozen_by=frozen_by,
                    pack_id=str((body or {}).get("pack_id") or "").strip(),
                    version=str((body or {}).get("version") or "").strip(),
                    notes=notes,
                )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("promote-subject-capability failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/stamp-subject-seed-purpose-ok")
async def compat_evaluation_stamp_subject_seed_purpose_ok(body: Dict[str, Any]):
    """Stamp purpose_ok into Subject seed cases/*.json (no freeze; claim closed)."""
    from core.api.core_facade import (
        eval_stamp_all_subject_seed_purpose_ok,
        eval_stamp_subject_seed_purpose_ok,
    )

    kind = str((body or {}).get("subject_kind") or "").strip()
    reviewer = str((body or {}).get("reviewer") or "owner").strip() or "owner"
    all_subjects = bool((body or {}).get("all"))
    try:
        if all_subjects or kind in ("*", "all"):
            return eval_stamp_all_subject_seed_purpose_ok(reviewer=reviewer)
        if not kind:
            return {
                "ok": False,
                "error": "subject_kind required (or all=true)",
                "claim_eligible": False,
                "accuracy_claim": False,
            }
        return eval_stamp_subject_seed_purpose_ok(
            subject_kind=kind, reviewer=reviewer
        )
    except Exception as e:
        logger.debug("stamp-subject-seed-purpose-ok failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/freeze-subject-seed-pack-meta")
async def compat_evaluation_freeze_subject_seed_pack_meta(body: Dict[str, Any]):
    """Freeze Subject seed pack.meta.json after purpose_ok (claim closed)."""
    from core.api.core_facade import (
        eval_freeze_all_subject_seed_pack_meta,
        eval_freeze_subject_seed_pack_meta,
    )

    kind = str((body or {}).get("subject_kind") or "").strip()
    reviewer = str((body or {}).get("reviewer") or "owner").strip() or "owner"
    all_subjects = bool((body or {}).get("all"))
    try:
        if all_subjects or kind in ("*", "all"):
            return eval_freeze_all_subject_seed_pack_meta(reviewer=reviewer)
        if not kind:
            return {
                "ok": False,
                "error": "subject_kind required (or all=true)",
                "claim_eligible": False,
                "accuracy_claim": False,
            }
        return eval_freeze_subject_seed_pack_meta(
            subject_kind=kind, reviewer=reviewer
        )
    except Exception as e:
        logger.debug("freeze-subject-seed-pack-meta failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/compile-suite-profile")
async def compat_evaluation_compile_suite_profile(body: Dict[str, Any]):
    """P2/P4: Suite Profile quotas → Plan v2 sample_manifest (claim closed)."""
    from core.api.core_facade import eval_compile_plan_from_suite_profile

    profile = (body or {}).get("profile")
    profile_id = str((body or {}).get("profile_id") or "").strip()
    if profile is not None and not isinstance(profile, dict):
        return {"ok": False, "error": "profile must be an object", "accuracy_claim": False}
    try:
        return eval_compile_plan_from_suite_profile(
            profile=profile if isinstance(profile, dict) else None,
            profile_id=profile_id,
            object_id=str((body or {}).get("object_id") or "agent.capability.target"),
            object_version=str((body or {}).get("object_version") or "0.1.0"),
        )
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("compile-suite-profile failed", exc_info=True)
        return {"ok": False, "error": str(e)[:300], "accuracy_claim": False}


@router.post("/evaluation/case-packs/run-suite-profile")
async def compat_evaluation_run_suite_profile(request: Request, body: Dict[str, Any]):
    """Post-P4: execute only sample_manifest from Suite Profile Plan (claim closed)."""
    from core.api.core_facade import eval_run_suite_profile_exam

    profile = (body or {}).get("profile")
    if profile is not None and not isinstance(profile, dict):
        return {"ok": False, "error": "profile must be an object", "accuracy_claim": False}
    wid = str((body or {}).get("workspace_id") or "").strip()
    if not wid:
        wid = str(request.headers.get("X-Aiplat-Workspace-Id") or "").strip()
    if not wid:
        wid = str(request.query_params.get("workspace_id") or "").strip()
    try:
        return await eval_run_suite_profile_exam(
            profile_id=str((body or {}).get("profile_id") or "agent.regression.v1"),
            profile=profile if isinstance(profile, dict) else None,
            live=bool((body or {}).get("live")),
            model=str((body or {}).get("model") or ""),
            run_key=str((body or {}).get("run_key") or ""),
            object_id=str((body or {}).get("object_id") or "agent.capability.target"),
            object_version=str((body or {}).get("object_version") or "0.1.0"),
            max_cases=int((body or {}).get("max_cases") or 0),
            workspace_id=wid,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("run-suite-profile failed", exc_info=True)
        return {"ok": False, "error": str(e)[:300], "accuracy_claim": False}


@router.post("/evaluation/case-packs/capability-heatmap")
async def compat_evaluation_capability_heatmap(body: Dict[str, Any]):
    """§8.4 capability coverage heatmap (claim closed)."""
    from core.api.core_facade import eval_capability_heatmap

    profile = (body or {}).get("profile")
    exam = (body or {}).get("exam")
    if profile is not None and not isinstance(profile, dict):
        return {"ok": False, "error": "profile must be an object", "accuracy_claim": False}
    if exam is not None and not isinstance(exam, dict):
        return {"ok": False, "error": "exam must be an object", "accuracy_claim": False}
    try:
        return eval_capability_heatmap(
            profile_id=str((body or {}).get("profile_id") or ""),
            profile=profile if isinstance(profile, dict) else None,
            exam=exam if isinstance(exam, dict) else None,
            subject_kind=str((body or {}).get("subject_kind") or ""),
        )
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("capability-heatmap failed", exc_info=True)
        return {"ok": False, "error": str(e)[:300], "accuracy_claim": False}


@router.post("/evaluation/case-packs/certification-readiness")
async def compat_evaluation_certification_readiness(body: Dict[str, Any]):
    """P5 pre-gate: §8.5 relative completeness; never unlocks certification/claim."""
    from core.api.core_facade import eval_certification_readiness

    profile = (body or {}).get("profile")
    if profile is not None and not isinstance(profile, dict):
        return {"ok": False, "error": "profile must be an object", "accuracy_claim": False}
    judge_agreement = (body or {}).get("judge_agreement")
    if judge_agreement is not None and not isinstance(judge_agreement, dict):
        return {
            "ok": False,
            "error": "judge_agreement must be an object",
            "accuracy_claim": False,
        }
    thr_raw = (body or {}).get("judge_threshold", 0.8)
    try:
        thr = float(thr_raw)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "error": "judge_threshold must be float",
            "accuracy_claim": False,
        }
    try:
        return eval_certification_readiness(
            profile_id=str((body or {}).get("profile_id") or "agent.benchmark.v1"),
            profile=profile if isinstance(profile, dict) else None,
            subject_kind=str((body or {}).get("subject_kind") or ""),
            pack_kind=str((body or {}).get("pack_kind") or ""),
            pack_status=str((body or {}).get("pack_status") or ""),
            judge_agreement=judge_agreement
            if isinstance(judge_agreement, dict)
            else None,
            judge_threshold=thr,
            compile_plan=bool((body or {}).get("compile_plan", True)),
        )
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("certification-readiness failed", exc_info=True)
        return {"ok": False, "error": str(e)[:300], "accuracy_claim": False}


@router.get("/evaluation/case-packs/suite-profiles")
async def compat_evaluation_suite_profiles():
    """List built-in Suite Profiles (smoke / regression / benchmark)."""
    from core.api.core_facade import eval_list_suite_profiles

    profiles = eval_list_suite_profiles()
    return {
        "ok": True,
        "profiles": profiles,
        "claim_eligible": False,
        "accuracy_claim": False,
    }


@router.post("/evaluation/case-packs/benchmark-readiness")
async def compat_evaluation_benchmark_readiness(body: Dict[str, Any]):
    """P4: benchmark coverage + holdout compile disclosure (claim closed)."""
    from core.api.core_facade import eval_benchmark_readiness

    profile = (body or {}).get("profile")
    if profile is not None and not isinstance(profile, dict):
        return {"ok": False, "error": "profile must be an object", "accuracy_claim": False}
    min_raw = (body or {}).get("min_per_capability")
    min_n = None
    if min_raw is not None and str(min_raw).strip() != "":
        try:
            min_n = int(min_raw)
        except (TypeError, ValueError):
            return {
                "ok": False,
                "error": "min_per_capability must be int",
                "accuracy_claim": False,
            }
    compile_plan = bool((body or {}).get("compile_plan", True))
    try:
        return eval_benchmark_readiness(
            min_per_capability=min_n,
            compile_plan=compile_plan,
            profile_id=str((body or {}).get("profile_id") or ""),
            profile=profile if isinstance(profile, dict) else None,
            subject_kind=str((body or {}).get("subject_kind") or ""),
        )
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("benchmark-readiness failed", exc_info=True)
        return {"ok": False, "error": str(e)[:300], "accuracy_claim": False}


@router.post("/evaluation/case-packs/judge-calibration-gate")
async def compat_evaluation_judge_calibration_gate(
    body: Dict[str, Any], request: Request
):
    """P4: engineering agreement gate — always report_only / claim=false."""
    from core.api.core_facade import eval_judge_calibration_gate
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    ticket_id = str((body or {}).get("ticket_id") or "").strip()
    thr_raw = (body or {}).get("threshold", 0.8)
    try:
        thr = float(thr_raw)
    except (TypeError, ValueError):
        return {"ok": False, "error": "threshold must be float", "accuracy_claim": False}
    ratings = (body or {}).get("ratings")
    if ratings is not None and not isinstance(ratings, list):
        return {"ok": False, "error": "ratings must be a list", "accuracy_claim": False}
    try:
        if ticket_id:
            with named_workspace_scope(request, method="POST", require_local=True) as nw:
                out = eval_judge_calibration_gate(
                    workspace_id=nw.workspace_id,
                    ticket_id=ticket_id,
                    threshold=thr,
                    caller_workspace_id=nw.workspace_id,
                )
                if isinstance(out, dict):
                    out.update(workspace_meta(nw))
                return out
        return eval_judge_calibration_gate(threshold=thr, ratings=ratings)
    except Exception as e:
        logger.debug("judge-calibration-gate failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/open-capability-judge-calibration")
async def compat_evaluation_open_capability_judge_calibration(
    body: Dict[str, Any], request: Request
):
    """P4: open judge ticket sampling capability bank cases."""
    from core.api.core_facade import eval_open_capability_judge_calibration
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            profile = (body or {}).get("profile")
            if profile is not None and not isinstance(profile, dict):
                return {
                    "ok": False,
                    "error": "profile must be an object",
                    "accuracy_claim": False,
                }
            out = eval_open_capability_judge_calibration(
                workspace_id=nw.workspace_id,
                caller_workspace_id=nw.workspace_id,
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                sample_n=int((body or {}).get("sample_n") or 8),
                notes=str((body or {}).get("notes") or ""),
                profile_id=str((body or {}).get("profile_id") or "").strip(),
                profile=profile if isinstance(profile, dict) else None,
                subject_kind=str((body or {}).get("subject_kind") or "").strip(),
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("open-capability-judge-calibration failed", exc_info=True)
        return _case_pack_http_error(e)


@router.get("/evaluation/case-packs/seed-cases", response_model=Dict[str, Any])
async def compat_evaluation_seed_cases(capability_id: str = ""):
    """Read-only browse of repo seed capability cases."""
    from core.api.core_facade import eval_list_seed_capability_cases

    try:
        return eval_list_seed_capability_cases(capability_id=capability_id)
    except Exception as e:
        logger.debug("seed-cases list failed", exc_info=True)
        return _case_pack_http_error(e)


@router.get("/evaluation/case-packs/seed-cases/{case_id}", response_model=Dict[str, Any])
async def compat_evaluation_seed_case_get(case_id: str):
    from core.api.core_facade import eval_get_seed_capability_case

    try:
        return eval_get_seed_capability_case(case_id=case_id)
    except Exception as e:
        logger.debug("seed-case get failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/editor/open", response_model=Dict[str, Any])
async def compat_evaluation_case_editor_open(body: Dict[str, Any], request: Request):
    """Open editable workspace draft (from seeds or bump frozen)."""
    from core.api.core_facade import eval_open_capability_bank_editor
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_open_capability_bank_editor(
                workspace_id=nw.workspace_id,
                caller_workspace_id=nw.workspace_id,
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                bump_if_frozen=bool((body or {}).get("bump_if_frozen", True)),
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-editor open failed", exc_info=True)
        return _case_pack_http_error(e)


@router.get("/evaluation/case-packs/editor/cases", response_model=Dict[str, Any])
async def compat_evaluation_case_editor_list(
    request: Request,
    pack_id: str = "agent.capability",
    version: str = "0.1.0",
    capability_id: str = "",
):
    from core.api.core_facade import eval_list_workspace_pack_cases
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="GET", require_local=True) as nw:
            out = eval_list_workspace_pack_cases(
                workspace_id=nw.workspace_id,
                caller_workspace_id=nw.workspace_id,
                pack_id=pack_id,
                version=version,
                capability_id=capability_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-editor list failed", exc_info=True)
        return _case_pack_http_error(e)


@router.get("/evaluation/case-packs/editor/cases/{case_id}", response_model=Dict[str, Any])
async def compat_evaluation_case_editor_get(
    case_id: str,
    request: Request,
    pack_id: str = "agent.capability",
    version: str = "0.1.0",
):
    from core.api.core_facade import eval_get_workspace_pack_case
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="GET", require_local=True) as nw:
            out = eval_get_workspace_pack_case(
                workspace_id=nw.workspace_id,
                caller_workspace_id=nw.workspace_id,
                case_id=case_id,
                pack_id=pack_id,
                version=version,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-editor get failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/editor/upsert", response_model=Dict[str, Any])
async def compat_evaluation_case_editor_upsert(body: Dict[str, Any], request: Request):
    from core.api.core_facade import eval_upsert_workspace_pack_case
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    case = (body or {}).get("case")
    if not isinstance(case, dict):
        return {
            "ok": False,
            "error": "case object required",
            "accuracy_claim": False,
        }
    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_upsert_workspace_pack_case(
                workspace_id=nw.workspace_id,
                caller_workspace_id=nw.workspace_id,
                case=case,
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-editor upsert failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/editor/delete", response_model=Dict[str, Any])
async def compat_evaluation_case_editor_delete(body: Dict[str, Any], request: Request):
    from core.api.core_facade import eval_delete_workspace_pack_case
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_delete_workspace_pack_case(
                workspace_id=nw.workspace_id,
                caller_workspace_id=nw.workspace_id,
                case_id=str((body or {}).get("case_id") or "").strip(),
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-editor delete failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/capability-coverage")
async def compat_evaluation_capability_coverage(body: Dict[str, Any]):
    """P3: capability gap inventory vs profile quotas or min_per_capability."""
    from core.api.core_facade import (
        eval_agent_regression_profile,
        eval_analyze_capability_coverage,
    )

    profile = (body or {}).get("profile")
    profile_id = str((body or {}).get("profile_id") or "").strip()
    subject_kind = str((body or {}).get("subject_kind") or "").strip()
    if profile is None and profile_id in ("", "agent.regression.v1") and not subject_kind:
        profile = eval_agent_regression_profile()
    min_raw = (body or {}).get("min_per_capability")
    min_n = None
    if min_raw is not None and str(min_raw).strip() != "":
        try:
            min_n = int(min_raw)
        except (TypeError, ValueError):
            return {
                "ok": False,
                "error": "min_per_capability must be int",
                "accuracy_claim": False,
            }
    try:
        return eval_analyze_capability_coverage(
            profile=profile if isinstance(profile, dict) else None,
            profile_id=profile_id,
            subject_kind=subject_kind,
            min_per_capability=min_n,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e), "accuracy_claim": False}
    except Exception as e:
        logger.debug("capability-coverage failed", exc_info=True)
        return {"ok": False, "error": str(e)[:300], "accuracy_claim": False}


@router.post("/evaluation/case-packs/coverage-fill")
async def compat_evaluation_coverage_fill(body: Dict[str, Any], request: Request):
    """P3: coverage-driven fill — dry by default; apply=true expands draft pack."""
    from core.api.core_facade import (
        eval_agent_regression_profile,
        eval_fill_capability_coverage,
    )
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    profile = (body or {}).get("profile")
    profile_id = str((body or {}).get("profile_id") or "").strip()
    subject_kind = str((body or {}).get("subject_kind") or "").strip()
    if profile is None and profile_id in ("", "agent.regression.v1") and not subject_kind:
        profile = eval_agent_regression_profile()
    min_raw = (body or {}).get("min_per_capability")
    min_n = None
    if min_raw is not None and str(min_raw).strip() != "":
        try:
            min_n = int(min_raw)
        except (TypeError, ValueError):
            return {
                "ok": False,
                "error": "min_per_capability must be int",
                "accuracy_claim": False,
            }
    apply = bool((body or {}).get("apply"))
    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_fill_capability_coverage(
                workspace_id=nw.workspace_id,
                caller_workspace_id=nw.workspace_id,
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                profile=profile if isinstance(profile, dict) else None,
                profile_id=profile_id,
                subject_kind=subject_kind,
                min_per_capability=min_n,
                method=str((body or {}).get("method") or "mutation"),
                seed=str((body or {}).get("seed") or "7"),
                ops=(body or {}).get("ops")
                if isinstance((body or {}).get("ops"), list)
                else None,
                apply=apply,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("coverage-fill failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/expand")
async def compat_evaluation_case_pack_expand(body: Dict[str, Any], request: Request):
    """P1.4: append cases into non-frozen draft/in_review/rejected pack."""
    from core.api.core_facade import eval_expand_draft_case_pack
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_expand_draft_case_pack(
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                workspace_id=nw.workspace_id,
                cases=(body or {}).get("cases"),
                template=(body or {}).get("template"),
                variants=(body or {}).get("variants"),
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs expand failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/bump")
async def compat_evaluation_case_pack_bump(body: Dict[str, Any], request: Request):
    """P1.4: version++ → new draft curated (source frozen untouched)."""
    from core.api.core_facade import eval_bump_case_pack_version
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_bump_case_pack_version(
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                from_version=str(
                    (body or {}).get("from_version")
                    or (body or {}).get("version")
                    or ""
                ).strip(),
                workspace_id=nw.workspace_id,
                to_version=str((body or {}).get("to_version") or "").strip(),
                extra_cases=(body or {}).get("extra_cases") or (body or {}).get("cases"),
                template=(body or {}).get("template"),
                variants=(body or {}).get("variants"),
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs bump failed", exc_info=True)
        return _case_pack_http_error(e)


@router.get("/evaluation/case-packs/coverage")
async def compat_evaluation_case_pack_coverage(request: Request):
    """P1.4: workspace pack coverage inventory (not accuracy)."""
    from core.api.core_facade import eval_summarize_case_pack_coverage
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="GET", require_local=True) as nw:
            out = eval_summarize_case_pack_coverage(
                workspace_id=nw.workspace_id,
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs coverage failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/holdout")
async def compat_evaluation_case_pack_holdout(body: Dict[str, Any], request: Request):
    """P2.0: mark holdout flags on non-frozen pack."""
    from core.api.core_facade import eval_mark_case_pack_holdout
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_mark_case_pack_holdout(
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                workspace_id=nw.workspace_id,
                case_ids=(body or {}).get("case_ids"),
                ratio=float((body or {}).get("ratio") or 0.0),
                seed=str((body or {}).get("seed") or "0"),
                holdout=bool((body or {}).get("holdout", True)),
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs holdout failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/mutate")
async def compat_evaluation_case_pack_mutate(body: Dict[str, Any], request: Request):
    """P2.0: deterministic mutations → kind=generated draft (claim closed)."""
    from core.api.core_facade import eval_publish_mutation_case_pack
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    seeds = (body or {}).get("seed_cases") or (body or {}).get("cases") or []
    if not isinstance(seeds, list):
        return {"ok": False, "error": "seed_cases must be a list", "accuracy_claim": False}
    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_publish_mutation_case_pack(
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                workspace_id=nw.workspace_id,
                seed_cases=seeds,
                ops=(body or {}).get("ops"),
                seed=str((body or {}).get("seed") or "0"),
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs mutate failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/from-trace")
async def compat_evaluation_case_pack_from_trace(
    body: Dict[str, Any], request: Request
):
    """P2.0: trace dicts → kind=trace draft (claim closed)."""
    from core.api.core_facade import eval_publish_trace_case_pack
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    traces = (body or {}).get("traces") or []
    if not isinstance(traces, list):
        return {"ok": False, "error": "traces must be a list", "accuracy_claim": False}
    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_publish_trace_case_pack(
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                workspace_id=nw.workspace_id,
                traces=traces,
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs from-trace failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/llm-candidates")
async def compat_evaluation_case_pack_llm_candidates(
    body: Dict[str, Any], request: Request
):
    """P3.0: LLM/stub candidates → kind=generated draft (claim closed)."""
    from core.api.core_facade import eval_publish_llm_candidate_case_pack
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    theme = str((body or {}).get("theme") or "").strip()
    if not theme:
        return {"ok": False, "error": "theme required", "accuracy_claim": False}
    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = await eval_publish_llm_candidate_case_pack(
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                workspace_id=nw.workspace_id,
                theme=theme,
                n=int((body or {}).get("n") or 3),
                category=str((body or {}).get("category") or "normal"),
                seed=str((body or {}).get("seed") or "0"),
                model_name=str((body or {}).get("model_name") or ""),
                dry=bool((body or {}).get("dry", True)),
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs llm-candidates failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/propose-difficulty")
async def compat_evaluation_case_pack_propose_difficulty(
    body: Dict[str, Any], request: Request
):
    """P3.0: heuristic difficulty (optional persist; not calibrated)."""
    from core.api.core_facade import eval_propose_case_pack_difficulty
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_propose_case_pack_difficulty(
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                workspace_id=nw.workspace_id,
                persist=bool((body or {}).get("persist", False)),
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs propose-difficulty failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/judge-calibration-ticket")
async def compat_evaluation_case_pack_judge_calibration_ticket(
    body: Dict[str, Any], request: Request
):
    """P3.1: open + persist judge calibration ticket (no claim unlock)."""
    from core.api.core_facade import eval_open_judge_calibration_ticket
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_open_judge_calibration_ticket(
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                workspace_id=nw.workspace_id,
                sample_case_ids=(body or {}).get("sample_case_ids"),
                notes=str((body or {}).get("notes") or ""),
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs judge-calibration-ticket failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/calibrate-difficulty")
async def compat_evaluation_case_pack_calibrate_difficulty(
    body: Dict[str, Any], request: Request
):
    """P3.1: human difficulty labels → pack (engineering; claim closed)."""
    from core.api.core_facade import eval_calibrate_case_pack_difficulty
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    labels = (body or {}).get("labels") or []
    if not isinstance(labels, list):
        return {"ok": False, "error": "labels must be a list", "accuracy_claim": False}
    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_calibrate_case_pack_difficulty(
                pack_id=str((body or {}).get("pack_id") or "").strip(),
                version=str((body or {}).get("version") or "").strip(),
                workspace_id=nw.workspace_id,
                labels=labels,
                rater=str((body or {}).get("rater") or ""),
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs calibrate-difficulty failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/judge-calibration-ratings")
async def compat_evaluation_case_pack_judge_calibration_ratings(
    body: Dict[str, Any], request: Request
):
    """P3.1: append judge ratings + agreement."""
    from core.api.core_facade import eval_record_judge_calibration_ratings
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    ratings = (body or {}).get("ratings") or []
    if not isinstance(ratings, list):
        return {"ok": False, "error": "ratings must be a list", "accuracy_claim": False}
    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_record_judge_calibration_ratings(
                workspace_id=nw.workspace_id,
                ticket_id=str((body or {}).get("ticket_id") or "").strip(),
                ratings=ratings,
                rater=str((body or {}).get("rater") or ""),
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs judge-calibration-ratings failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/case-packs/judge-calibration-close")
async def compat_evaluation_case_pack_judge_calibration_close(
    body: Dict[str, Any], request: Request
):
    """P3.1: close judge ticket (engineering calibrated; claim closed)."""
    from core.api.core_facade import eval_close_judge_calibration_ticket
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="POST", require_local=True) as nw:
            out = eval_close_judge_calibration_ticket(
                workspace_id=nw.workspace_id,
                ticket_id=str((body or {}).get("ticket_id") or "").strip(),
                notes=str((body or {}).get("notes") or ""),
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs judge-calibration-close failed", exc_info=True)
        return _case_pack_http_error(e)


@router.get("/evaluation/case-packs/judge-calibration-ticket/{ticket_id}")
async def compat_evaluation_case_pack_judge_calibration_get(
    ticket_id: str, request: Request
):
    """P3.1: load persisted judge ticket."""
    from core.api.core_facade import eval_get_judge_calibration_ticket
    from core.harness.named_workspace.http_bind import named_workspace_scope, workspace_meta

    try:
        with named_workspace_scope(request, method="GET", require_local=True) as nw:
            out = eval_get_judge_calibration_ticket(
                workspace_id=nw.workspace_id,
                ticket_id=str(ticket_id or "").strip(),
                caller_workspace_id=nw.workspace_id,
            )
            if isinstance(out, dict):
                out.update(workspace_meta(nw))
            return out
    except Exception as e:
        logger.debug("case-packs judge-calibration-get failed", exc_info=True)
        return _case_pack_http_error(e)


@router.post("/evaluation/policy")
async def compat_evaluation_policy_set(body: Dict[str, Any]):
    """Create or update an evaluation policy artifact."""
    try:
        mgr = await _get_learning_manager()
        artifact = await mgr.create_artifact(
            kind="evaluation_policy",
            target_type=body.get("target_type", "policy"),
            target_id=body.get("target_id", "default"),
            version=str(int(__import__("time").time())),
            payload=body.get("policy", body),
            status="published",
        )
        return {"status": "ok", "artifact_id": artifact.artifact_id, "policy": body.get("policy", body)}
    except Exception as e:
        logger.debug("evaluation policy creation failed", exc_info=True)
        return {"status": "error", "message": str(e)[:200]}


@router.get("/evaluation/policy/latest")
async def compat_evaluation_policy_latest():
    """Get the latest evaluation policy."""
    try:
        mgr = await _get_learning_manager()
        artifacts = await mgr.list_artifacts(
            kind="evaluation_policy",
            status="published",
            limit=1,
        )
        if artifacts:
            return {"status": "ok", "policy": artifacts[0].get("payload", {}).get("policy", artifacts[0])}
        return {"status": "ok", "message": "No evaluation policy configured yet."}
    except Exception as e:
        logger.debug("evaluation policy fetch failed", exc_info=True)
        return {"status": "error", "message": str(e)[:200]}


@router.post("/scopes/{scope_id}/evaluation/policy")
async def compat_scoped_evaluation_policy_set(scope_id: str, body: Dict[str, Any]):
    """Create/update scoped evaluation policy."""
    try:
        mgr = await _get_learning_manager()
        artifact = await mgr.create_artifact(
            kind="evaluation_policy",
            target_type="policy",
            target_id=f"scope:{scope_id}",
            version=str(int(__import__("time").time())),
            payload={"scope_id": scope_id, "policy": body.get("policy", body)},
            status="published",
        )
        return {"status": "ok", "artifact_id": artifact.artifact_id, "scope_id": scope_id}
    except Exception as e:
        logger.debug("scoped policy creation failed", exc_info=True)
        return {"status": "error", "message": str(e)[:200]}


@router.get("/scopes/{scope_id}/evaluation/policy/latest")
async def compat_scoped_evaluation_policy_latest(scope_id: str):
    """Get latest scoped evaluation policy."""
    try:
        mgr = await _get_learning_manager()
        artifacts = await mgr.list_artifacts(
            kind="evaluation_policy",
            target_id=f"scope:{scope_id}",
            status="published",
            limit=1,
        )
        if artifacts:
            return {"status": "ok", "scope_id": scope_id, "policy": artifacts[0].get("payload", {}).get("policy", artifacts[0])}
        return {"status": "ok", "scope_id": scope_id, "message": "No policy yet."}
    except Exception as e:
        logger.debug("scoped policy fetch failed", exc_info=True)
        return {"status": "error", "message": str(e)[:200]}


# ════════════════════════════════════════════════════════════
# Diagnostics playground — powered by infra ModelManager + LLM
# ════════════════════════════════════════════════════════════

def _list_models() -> list[dict]:
    """List installed models + market catalog for playground comparison."""
    result = []
    installed_names = set()

    # 1. Installed models (local Ollama + configured API)
    try:
        from infra.management.model.manager import ModelManager as InfraModelManager
        mgr = InfraModelManager()
        models = mgr.select_by_purpose_list("chat")
        for m in models:
            name = m if isinstance(m, str) else getattr(m, "name", str(m))
            installed_names.add(name)
            result.append({
                "name": name, "available": True,
                "category": "installed",
            })
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    # 2. Market catalog — popular models user can add
    _CATALOG = [
        {"name": "claude-sonnet-4-20250514", "provider": "Anthropic", "context": "200K", "strength": "复杂推理、代码生成、长上下文"},
        {"name": "claude-3.5-haiku", "provider": "Anthropic", "context": "200K", "strength": "快速轻量、成本低"},
        {"name": "gpt-4o", "provider": "OpenAI", "context": "128K", "strength": "多模态、通用能力强"},
        {"name": "gpt-4o-mini", "provider": "OpenAI", "context": "128K", "strength": "高性价比、快速响应"},
        {"name": "gemini-2.5-flash", "provider": "Google", "context": "1M", "strength": "超长上下文、多模态"},
        {"name": "gemini-2.5-pro", "provider": "Google", "context": "1M", "strength": "最强推理、超长上下文"},
        {"name": "llama-4-maverick", "provider": "Meta", "context": "128K", "strength": "开源旗舰、多语言"},
        {"name": "llama-4-scout", "provider": "Meta", "context": "10M", "strength": "开源超长上下文"},
        {"name": "mixtral-8x22b", "provider": "Mistral", "context": "64K", "strength": "开源MoE、函数调用"},
        {"name": "mistral-large", "provider": "Mistral", "context": "128K", "strength": "多语言、代码能力"},
        {"name": "qwen-max", "provider": "Alibaba", "context": "128K", "strength": "中文能力强、性价比"},
        {"name": "glm-4-plus", "provider": "Zhipu", "context": "128K", "strength": "中文理解、长文本"},
    ]
    for cat in _CATALOG:
        if cat["name"] not in installed_names:
            result.append({**cat, "available": False, "category": "catalog"})

    # Also add installed models as reference
    for r in result:
        if r.get("available") and not r.get("provider"):
            # Local model — guess provider from name
            name = r["name"]
            if "qwen" in name.lower():
                r["provider"] = "Alibaba (Ollama)"
                r["strength"] = "本地运行、数据安全"
            elif "gemma" in name.lower():
                r["provider"] = "Google (Ollama)"
                r["strength"] = "本地运行、轻量高效"
            elif "minicpm" in name.lower():
                r["provider"] = "OpenBMB (Ollama)"
                r["strength"] = "本地运行、多模态"
            elif "deepseek" in name.lower():
                r["provider"] = "DeepSeek"
                r["strength"] = "高性价比、推理能力强"

    return result


@router.get("/diagnostics/playground/models")
async def compat_playground_models():
    """List available models for the diagnostics playground."""
    models = _list_models()
    return {"models": models, "count": len(models)}


@router.post("/diagnostics/playground/chat")
async def compat_playground_chat(body: Dict[str, Any]):
    """Chat with a specified model via the playground."""
    prompt = body.get("prompt", "") or body.get("message", "")
    model_id = body.get("model", "")

    if not prompt:
        return {"reply": "", "error": "No prompt provided"}

    try:
        messages = [{"role": "user", "content": prompt}]

        if model_id:
            from core.api.core_facade import create_selected_adapter  # P0-A2: 经 CoreFacade
            adapter = create_selected_adapter("chat", model_id=model_id)
        else:
            from core.api.core_facade import create_selected_adapter  # P0-A2: 经 CoreFacade
            adapter = create_selected_adapter("chat")

        result = adapter.generate(messages)
        return {"reply": result, "model": model_id or "default", "status": "ok"}
    except Exception as e:
        logger.debug("playground chat failed", exc_info=True)
        return {"reply": f"Model call failed: {str(e)[:200]}", "status": "error"}


@router.post("/diagnostics/playground/compare")
async def compat_playground_compare(body: Dict[str, Any]):
    """Compare outputs from multiple models (installed + market with api_key).
    
    Body: {
        prompt: str,
        models: [{name: str, api_key?: str, api_base?: str}]
    }
    """
    prompt = body.get("prompt", "")
    model_list = body.get("models") or []
    # Backward compat: model_a/model_b
    if not model_list:
        ma = body.get("model_a", "")
        mb = body.get("model_b", "")
        model_list = [{"name": m} for m in (ma, mb) if m]

    if not prompt:
        return {"results": [], "error": "No prompt provided"}

    # Preload installed model names for routing
    installed_names = set()
    try:
        from infra.management.model.manager import ModelManager as InfraModelManager
        mgr = InfraModelManager()
        for m in mgr.select_by_purpose_list("chat"):
            installed_names.add(m if isinstance(m, str) else getattr(m, "name", str(m)))
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    import time as _time, asyncio as _aio
    messages = [{"role": "user", "content": prompt}]

    async def _call_model(model_name: str, api_key: str = "", api_base: str = ""):
        start = _time.time()
        try:
            if model_name in installed_names:
                # Installed model — use system adapter
                from core.api.core_facade import create_selected_adapter  # P0-A2: 经 CoreFacade
                adapter = create_selected_adapter("chat", model_name=model_name)
                reply = adapter.generate(messages)
            elif api_key:
                # Market model — create temp adapter with provided config
                from core.adapters.llm.base import create_adapter
                provider_map = {
                    "gpt": "openai", "claude": "anthropic", "gemini": "google",
                    "llama": "openai_compatible", "mixtral": "openai_compatible",
                    "mistral": "openai_compatible", "qwen": "openai_compatible",
                    "glm": "openai_compatible",
                }
                provider = "openai_compatible"
                for k, v in provider_map.items():
                    if k in model_name.lower():
                        provider = v
                        break
                # Determine base URL
                if not api_base:
                    _base_map = {
                        "openai": "https://api.openai.com/v1",
                        "openai_compatible": api_base,  # will be set below
                    }
                adapter = create_adapter(
                    provider=provider,
                    api_key=api_key,
                    model=model_name,
                    base_url=api_base or None,
                )
                reply = adapter.generate(messages)
            else:
                raise ValueError("未配置 API key — 请在模型名称旁输入密钥")

            latency_ms = int((_time.time() - start) * 1000)
            return {
                "model": model_name, "content": reply, "status": "success",
                "latency_ms": latency_ms,
            }
        except Exception as e:
            latency_ms = int((_time.time() - start) * 1000)
            return {
                "model": model_name, "status": "error",
                "error": str(e)[:300], "latency_ms": latency_ms,
            }

    # Run all models in parallel
    tasks = [
        _call_model(m.get("name", m) if isinstance(m, dict) else m,
                     api_key=m.get("api_key", "") if isinstance(m, dict) else "",
                     api_base=m.get("api_base", "") if isinstance(m, dict) else "")
        for m in model_list
    ]
    results = await _aio.gather(*tasks, return_exceptions=True)
    clean = []
    for r in results:
        if isinstance(r, Exception):
            clean.append({"model": "?", "status": "error", "error": str(r)[:200]})
        else:
            clean.append(r)

    return {"results": clean, "status": "ok"}


# ════════════════════════════════════════════════════════════
# Repairs stub — delegates to GET handler
# ════════════════════════════════════════════════════════════

@router.get("/diagnostics/repairs-latest")
async def compat_repairs_get(request: Request):
    """GET repairs-latest — returns cached/empty result (repairs module migrated out)."""
    return {"needs_diagnostics": False, "repairs": [], "status": "delegated"}


@router.post("/diagnostics/repairs-latest")
async def compat_repairs_post(request: Request, body: Dict[str, Any] = None):
    """POST trigger for repairs → delegates to GET handler."""
    try:
        from core.api.routers.repairs import get_repairs_latest
        return await get_repairs_latest()
    except ImportError:
        return {"needs_diagnostics": False, "repairs": [], "status": "delegated"}


# ════════════════════════════════════════════════════════════
# Workbench FDE dashboard — POST alias
# ════════════════════════════════════════════════════════════

@router.post("/workbench/fde-dashboard")
async def compat_workbench_fde_dashboard_post():
    """POST alias for workbench FDE dashboard."""
    return {"pending_decisions": 0, "signal_alerts": 0, "status": "ok"}
