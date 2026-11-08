"""Agent exam — run a built-in eval set against a chosen workspace agent.

Honesty: engineering scores only; accuracy_claim stays false.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence

from core.harness.evaluation.eval_runner import (
    EvalRunner,
    _resolve_exam_agent_info,
    list_eval_sets,
    load_eval_set,
    persist_runtime_eval,
    serialize_eval_result,
)
from core.harness.evaluation.eval_types import EvalSet, EvalTask


_FACT_GOLD_KEYS = (
    "expected_answer",
    "expected_facts",
    "must_cite",
    "citations",
    "reference",
    "must_contain",  # builtin papers use this as lexical gold
)


def list_exam_sets() -> List[Dict[str, Any]]:
    """List runnable exam papers (eval sets on disk)."""
    return list_eval_sets()


def _exam_code_revision() -> str:
    """Best-effort code/build revision for report reproduction."""
    for env in ("AIPLAT_GIT_SHA", "GIT_COMMIT", "GITHUB_SHA", "COMMIT_SHA"):
        v = (os.getenv(env) or "").strip()
        if v:
            return v[:40]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        sha = (out.stdout or "").strip()
        if out.returncode == 0 and sha:
            return sha[:40]
    except Exception:  # noqa: BLE001 — optional repro stamp
        pass
    return ""


def _bind_set_to_agent(evalset: EvalSet, agent_id: str) -> EvalSet:
    aid = (agent_id or "").strip()
    if not aid:
        raise ValueError("agent_id required")
    tasks = [replace(t, agent_id=aid) for t in evalset.tasks]
    return replace(evalset, tasks=tasks)


def _norm_text(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()


def _as_str_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v.strip() else []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if x is not None and str(x).strip()]
    return [str(v)]


def _task_has_fact_gold(task: EvalTask) -> bool:
    sc = getattr(task, "success_criteria", None) or {}
    return isinstance(sc, dict) and any(k in sc for k in _FACT_GOLD_KEYS)


def compute_exam_fact_support(
    evalset: EvalSet,
    task_results: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Lexical fact-gold support rate from evidence/reasoning vs success_criteria.

    Checks expected_facts / expected_answer / must_cite|citations|reference /
    must_contain as substring matches (engineering, not semantic NLI).
    sufficiency still false.
    """
    by_id: Dict[str, Dict[str, Any]] = {}
    for tr in task_results or []:
        if isinstance(tr, dict) and tr.get("task_id"):
            by_id[str(tr.get("task_id"))] = tr

    details: List[Dict[str, Any]] = []
    used_must_contain = False
    used_fact_fields = False
    for t in evalset.tasks or []:
        if not _task_has_fact_gold(t):
            continue
        sc = t.success_criteria if isinstance(t.success_criteria, dict) else {}
        checks: List[str] = []
        fact_bits = _as_str_list(sc.get("expected_facts"))
        checks.extend(fact_bits)
        ans = sc.get("expected_answer")
        if ans is not None and str(ans).strip():
            checks.append(str(ans))
            used_fact_fields = True
        if fact_bits:
            used_fact_fields = True
        for key in ("must_cite", "citations", "reference"):
            cites = _as_str_list(sc.get(key))
            if cites:
                used_fact_fields = True
                checks.extend(cites)
        # Builtin papers: must_contain is the practical lexical gold today.
        must = _as_str_list(sc.get("must_contain"))
        if must:
            used_must_contain = True
            checks.extend(must)
        if not checks:
            continue
        tr = by_id.get(t.task_id) or {}
        blob = _norm_text(
            f"{tr.get('evidence') or ''} {tr.get('reasoning') or ''}"
        )
        hits = 0
        missing: List[str] = []
        for c in checks:
            needle = _norm_text(c)
            if not needle:
                continue
            if needle in blob:
                hits += 1
            else:
                missing.append(c[:80])
        denom = max(1, len([c for c in checks if _norm_text(c)]))
        support = hits / denom
        details.append(
            {
                "task_id": t.task_id,
                "support": round(support, 4),
                "hits": hits,
                "checks": denom,
                "missing": missing[:8],
            }
        )

    if not details:
        return {
            "fact_support_rate": None,
            "fact_support_n": 0,
            "fact_support_details": [],
            "method": "lexical_substring_v0",
            "accuracy_claim": False,
        }
    rate = sum(float(d["support"]) for d in details) / len(details)
    method = "lexical_substring_v0"
    if used_must_contain and not used_fact_fields:
        method = "lexical_must_contain_v0"
    elif used_must_contain and used_fact_fields:
        method = "lexical_fact_and_must_contain_v0"
    return {
        "fact_support_rate": round(rate, 4),
        "fact_support_n": len(details),
        "fact_support_details": details[:50],
        "method": method,
        "accuracy_claim": False,
    }


def _exam_gold_manifest(evalset: EvalSet) -> Dict[str, Any]:
    """Count gold/criteria fields on the paper — for attributable grounding slice."""
    with_tools = 0
    with_criteria = 0
    with_fact = 0
    for t in evalset.tasks or []:
        if getattr(t, "expected_tools", None):
            with_tools += 1
        sc = getattr(t, "success_criteria", None) or {}
        if isinstance(sc, dict) and sc:
            with_criteria += 1
            if any(k in sc for k in _FACT_GOLD_KEYS):
                with_fact += 1
    return {
        "task_count": len(evalset.tasks or []),
        "tasks_with_expected_tools": with_tools,
        "tasks_with_success_criteria": with_criteria,
        "tasks_with_fact_gold": with_fact,
        "set_id": getattr(evalset, "set_id", "") or "",
        "category": getattr(evalset, "category", "") or "",
    }


def _attach_task_criteria(payload: Dict[str, Any], bound: Any) -> None:
    """Join paper success_criteria onto serialized task_results for probe evidence."""
    by_id = {}
    for t in getattr(bound, "tasks", None) or []:
        tid = str(getattr(t, "task_id", "") or "")
        if tid:
            by_id[tid] = t
    rows = payload.get("task_results")
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        t = by_id.get(str(row.get("task_id") or ""))
        if t is None:
            continue
        sc = getattr(t, "success_criteria", None) or {}
        if isinstance(sc, dict) and sc and not row.get("success_criteria"):
            row["success_criteria"] = sc
        risk = getattr(t, "risk_level", None)
        if risk and not row.get("risk_level"):
            row["risk_level"] = str(risk)
        if not row.get("response") and row.get("evidence"):
            row["response"] = str(row.get("evidence") or "")[:500]


def _resolve_exam_model_stamp(mdl: Any) -> Dict[str, Any]:
    """Stamp configured model; if auto, try purpose resolution for repro honesty."""
    raw = str(mdl or "").strip() or "未采集"
    out: Dict[str, Any] = {
        "model": raw,
        "model_configured": raw,
        "model_resolved": None,
        "reproduction_limits": [],
    }
    if raw.lower() in ("auto", "best", ""):
        out["reproduction_limits"].append(
            f"模型配置={raw or '空'}：复测需对齐实际解析模型名/版本"
        )
        try:
            from core.harness.utils.model_injection import best_model_for_purpose

            resolved = best_model_for_purpose("skill_execution") or best_model_for_purpose("chat")
            if resolved and str(resolved).strip().lower() not in ("auto", "best"):
                out["model_resolved"] = str(resolved)
                out["model"] = f"{raw}→{resolved}"
            else:
                out["model"] = f"{raw}（未解析到实际模型名 — 复现限制）"
        except Exception:  # noqa: BLE001
            out["model"] = f"{raw}（未解析到实际模型名 — 复现限制）"
    return out


async def run_agent_exam(
    *,
    agent_id: str,
    set_id: str,
    live: bool = False,
    max_tasks: int = 0,
    persist: bool = True,
) -> Dict[str, Any]:
    """Run exam paper ``set_id`` with all tasks bound to ``agent_id``.

    live=False → dry_run (validate only, no agent execution).
    live=True → execute agent and optionally persist to eval_results.
    """
    aid = (agent_id or "").strip()
    sid = (set_id or "").strip()
    if not aid:
        raise ValueError("agent_id required")
    if not sid:
        raise ValueError("set_id required")

    raw = load_eval_set(sid)
    if raw is None:
        raise FileNotFoundError(f"eval set not found: {sid}")

    bound = _bind_set_to_agent(raw, aid)

    # Plan v2: sample_manifest is the sole execution list (nail 2).
    from core.apps.eval.service.case_pack_legacy import (
        ManifestValidationError,
        require_sample_manifest,
        verify_manifest_case_hashes,
    )

    plan: Optional[Dict[str, Any]] = None
    try:
        from core.apps.eval.service.eval_plan import compile_plan_for_object
        from core.apps.eval.service.eval_profile_resolve import resolve_agent_eval_profile

        profile = await resolve_agent_eval_profile(aid)
        plan = compile_plan_for_object(
            object_type="agent",
            object_id=aid,
            set_ids=[sid],
            purpose=list(
                profile.get("eval_purpose") or ["behavior", "regression", "safety"]
            ),
            include_special=True,  # user picked this paper explicitly
            live=bool(live),
            eval_profile=profile,
            source_refs=["agent_exam"],
        )
        manifest = require_sample_manifest(plan)
        verify_manifest_case_hashes(manifest)
        allow = {
            str(row.get("case_id") or "")
            for row in manifest
            if str(row.get("set_id") or "") == sid or not row.get("set_id")
        }
        allow.discard("")
        if allow:
            bound.tasks = [t for t in (bound.tasks or []) if t.task_id in allow]
        if not bound.tasks:
            raise ManifestValidationError(
                f"sample_manifest for {sid!r} matched zero tasks — fail closed"
            )
    except ManifestValidationError:
        raise
    except Exception:  # noqa: BLE001 — advisory compile must not block dry exam path
        plan = None

    runner = EvalRunner()
    result = await runner.run_eval_set(
        bound,
        max_tasks=int(max_tasks or 0),
        dry_run=not bool(live),
    )

    payload = serialize_eval_result(result)
    payload["accuracy_claim"] = False
    cat = getattr(bound, "category", "") or ""
    payload["exam"] = {
        "agent_id": aid,
        "set_id": sid,
        "live": bool(live),
        "task_count": len(bound.tasks),
        "bound_override": True,
        "category": cat,
    }
    # Hint memory_horizon slice: multi_turn papers share a session across tasks.
    blob = f"{sid} {cat}".lower()
    if any(k in blob for k in ("multi_turn", "multi-turn", "memory", "horizon")):
        payload["turns"] = max(2, len(bound.tasks or []))
        payload["category"] = cat or payload.get("category") or "multi_turn"
    gold = _exam_gold_manifest(bound)
    # Tool-gold match proxy from trajectory when paper declares expected_tools.
    traj = payload.get("trajectory") if isinstance(payload.get("trajectory"), dict) else {}
    if gold.get("tasks_with_expected_tools") and traj.get("matched") is True:
        gold["tool_gold_match_rate"] = 1.0
    elif gold.get("tasks_with_expected_tools") and traj.get("matched") is False:
        gold["tool_gold_match_rate"] = 0.0
    # Fact-gold lexical support from evidence/reasoning vs success_criteria.
    fact = compute_exam_fact_support(
        bound,
        payload.get("task_results") if isinstance(payload.get("task_results"), list) else [],
    )
    if fact.get("fact_support_rate") is not None:
        gold["fact_support_rate"] = fact["fact_support_rate"]
        gold["fact_support_n"] = fact.get("fact_support_n")
        gold["fact_support_method"] = fact.get("method")
        gold["fact_support_details"] = fact.get("fact_support_details")
    payload["gold"] = gold
    payload["category"] = gold.get("category") or payload.get("category")
    _attach_task_criteria(payload, bound)

    import uuid as _uuid

    # Reproduction stamps (model/version/revision best-effort).
    payload.setdefault("run_id", f"exam-{_uuid.uuid4().hex[:12]}")
    payload.setdefault("total_tasks", len(bound.tasks or []))
    rev = _exam_code_revision()
    if rev:
        payload.setdefault("code_revision", rev)
    try:
        info = await _resolve_exam_agent_info(aid)
        cfg = getattr(info, "config", None) or {}
        if not isinstance(cfg, dict):
            cfg = {}
        mdl = cfg.get("model") or cfg.get("llm_model") or getattr(info, "model", None)
        stamp = _resolve_exam_model_stamp(mdl)
        payload.setdefault("model", stamp["model"])
        payload.setdefault("model_configured", stamp["model_configured"])
        if stamp.get("model_resolved"):
            payload.setdefault("model_resolved", stamp["model_resolved"])
        if stamp.get("reproduction_limits"):
            prev = payload.get("reproduction_limits")
            if isinstance(prev, list):
                payload["reproduction_limits"] = list(dict.fromkeys([*prev, *stamp["reproduction_limits"]]))
            else:
                payload["reproduction_limits"] = list(stamp["reproduction_limits"])
        params = cfg.get("model_params") or cfg.get("llm_params") or cfg.get("generation_params")
        if isinstance(params, dict) and params:
            payload.setdefault("model_params", params)
        elif params:
            payload.setdefault("model_params", str(params))
        else:
            payload.setdefault("model_params", "未采集（复现限制）")
        ver = getattr(info, "version", None)
        if ver:
            payload.setdefault("agent_version", str(ver))
        skills = getattr(info, "skills", None) or []
        if skills:
            payload.setdefault(
                "agent_skills",
                [str(s) for s in list(skills)[:24]],
            )
    except Exception:  # noqa: BLE001 — repro enrichment must not fail exam
        pass

    from core.apps.eval.service.agent_attributable_report import build_attributable_report

    attributable = build_attributable_report(
        payload, agent_id=aid, set_id=sid, live=bool(live)
    )
    payload["attributable_report"] = attributable

    from core.apps.eval.service.exam_runtime_tier import (
        annotate_agent_exam_runtime,
        merge_runtime_fields,
    )

    rt = annotate_agent_exam_runtime(live=bool(live))
    payload["runtime_tier"] = rt["runtime_tier"]
    payload["runtime_claim"] = rt["runtime_claim"]
    payload["runtime_claim_reason"] = rt["runtime_claim_reason"]

    # Object-contract: attach Plan/MatchReport (reuse pre-run compile when present).
    try:
        from core.apps.eval.service.eval_plan import attach_evaluation_plan
        from core.apps.eval.service.eval_profile_resolve import resolve_agent_eval_profile

        if plan is None:
            from core.apps.eval.service.eval_plan import compile_plan_for_object

            profile = await resolve_agent_eval_profile(aid)
            plan = compile_plan_for_object(
                object_type="agent",
                object_id=aid,
                set_ids=[sid],
                purpose=list(
                    profile.get("eval_purpose")
                    or ["behavior", "regression", "safety"]
                ),
                include_special=True,
                live=bool(live),
                eval_profile=profile,
                source_refs=["agent_exam"],
            )
        else:
            profile = {"profile_source": plan.get("eval_profile_source")}
        stamped = attach_evaluation_plan({"ok": True}, plan)
        payload["target_contract"] = stamped.get("target_contract")
        payload["match_report"] = stamped.get("match_report")
        payload["evaluation_plan"] = stamped.get("evaluation_plan")
        payload["plan_id"] = stamped.get("plan_id")
        payload["manifest_hash"] = (plan or {}).get("manifest_hash")
        payload["eval_profile_source"] = (
            profile.get("profile_source") if isinstance(profile, dict) else None
        ) or plan.get("eval_profile_source")
    except Exception:  # noqa: BLE001 — contract advisory must not fail exam
        payload.setdefault(
            "match_report",
            {"schema": "eval.match_report.v1", "phase": "p0_advisory", "error": "attach_failed"},
        )

    # Keep repro + runtime on attributable so UI/formal report can read one blob.
    for k in (
        "run_id",
        "model",
        "model_configured",
        "model_resolved",
        "model_params",
        "reproduction_limits",
        "agent_version",
        "agent_skills",
        "code_revision",
        "eval_time",
        "runtime_tier",
        "runtime_claim",
        "runtime_claim_reason",
        "target_contract",
        "match_report",
        "evaluation_plan",
        "plan_id",
        "eval_profile_source",
    ):
        if payload.get(k) is not None and attributable.get(k) is None:
            attributable[k] = payload.get(k)

    persisted: Optional[str] = None
    if live and persist:
        persisted = persist_runtime_eval(aid, payload)

    veto = bool((attributable.get("gate") or {}).get("veto"))
    publish = attributable.get("publish") if isinstance(attributable.get("publish"), dict) else {}
    publish_allowed = bool(publish.get("allowed")) if publish else (not veto)
    out = {
        "ok": True,
        "agent_id": aid,
        "set_id": sid,
        "live": bool(live),
        "accuracy_claim": False,
        "sufficiency_claim": False,
        "composite_score": payload.get("composite_score"),
        "grade": payload.get("grade"),
        "total_tasks": payload.get("total_tasks"),
        "run_id": payload.get("run_id"),
        "model": payload.get("model"),
        "agent_version": payload.get("agent_version"),
        "code_revision": payload.get("code_revision"),
        "result": payload,
        "attributable_report": attributable,
        "gate_pass": bool((attributable.get("gate") or {}).get("pass")),
        "safety_veto": veto,
        "publish_allowed": publish_allowed,
        "persisted_path": persisted,
        "target_contract": payload.get("target_contract"),
        "match_report": payload.get("match_report"),
        "evaluation_plan": payload.get("evaluation_plan"),
        "plan_id": payload.get("plan_id"),
        "eval_profile_source": payload.get("eval_profile_source"),
        "message": (
            f"{'Live' if live else 'Dry-run'} exam {sid} → {aid}: "
            f"score={payload.get('composite_score')} ({payload.get('grade')})"
            + (f" · PUBLISH_VETO" if veto else " · PUBLISH_ALLOW_GAPS")
            + (
                f" · profile={payload.get('eval_profile_source')}"
                if payload.get("eval_profile_source")
                else ""
            )
        ),
    }
    return merge_runtime_fields(out, rt)


def match_cases_for_agent_target(
    *,
    agent_id: str,
    set_ids: Optional[Sequence[str]] = None,
    capabilities: Optional[Sequence[str]] = None,
    tools: Optional[Sequence[str]] = None,
    permissions: Optional[Sequence[str]] = None,
    roles: Optional[Sequence[str]] = None,
    eval_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """P0: explainable MatchReport for agent + set_ids (advisory; no execute)."""
    from core.apps.eval.service.case_match import match_eval_sets_for_target
    from core.apps.eval.service.target_contract import build_agent_target_contract

    aid = (agent_id or "").strip()
    if not aid:
        raise ValueError("agent_id required")
    ids = list(set_ids or [])
    if not ids:
        ids = [
            "default/normal",
            "default/missing_info",
            "default/tool_failure",
            "default/high_risk",
            "default/noise",
            "default/multi_turn",
        ]
    contract = build_agent_target_contract(
        object_id=aid,
        capabilities=capabilities,
        tools=tools,
        permissions=permissions,
        roles=roles,
        eval_profile=eval_profile,
        source_refs=["match_cases_for_agent_target"],
    )
    report = match_eval_sets_for_target(contract, ids)
    return {
        "ok": True,
        "accuracy_claim": False,
        "sufficiency_claim": False,
        "target_contract": contract,
        "match_report": report,
    }
