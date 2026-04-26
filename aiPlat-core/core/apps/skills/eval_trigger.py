from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from core.apps.skills.base import BaseSkill
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.routing.skill_routing import compute_skill_candidates


class SkillEvalTriggerSkill(BaseSkill):
    """
    Skill Trigger Evaluation (MVP)

    Runs an offline/heuristic Trigger Eval for a target skill against a suite of positive/negative queries.
    Stores results into ExecutionStore skill_eval_* tables.
    """

    def __init__(self):
        cfg = SkillConfig(
            name="skill_eval_trigger",
            description="运行 Skill 的触发评测（Trigger Eval），输出准确率/误触发/漏触发等指标，并写入评测结果。",
            input_schema={
                "suite_id": {"type": "string", "description": "评测套件 ID"},
                "mode": {"type": "string", "description": "heuristic|live（MVP 默认 heuristic）", "default": "heuristic"},
                "max_cases": {"type": "integer", "description": "最多评测条数（正负例合计）", "default": 200},
                # Testing/ops-only: allow injecting a tiny skill catalog to make eval deterministic.
                "skills_override": {"type": "array", "description": "可选：覆盖技能目录（用于测试/离线）"},
            },
            output_schema={
                "run_id": {"type": "string"},
                "suite_id": {"type": "string"},
                "mode": {"type": "string"},
                "metrics": {"type": "object"},
            },
            metadata={
                "category": "ops",
                "version": "1.0.0",
                "tags": ["ops", "evaluation"],
                "skill_kind": "executable",
                "permissions": ["execute"],
                "requires_approval": False,
                "risk_level": "low",
            },
        )
        super().__init__(cfg)

    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        if store is None:
            return SkillResult(success=False, error="ExecutionStore not initialized")

        run_id = str(getattr(context, "session_id", None) or "") or f"eval_{int(time.time()*1000)}"
        suite_id = str((params or {}).get("suite_id") or "").strip()
        mode = str((params or {}).get("mode") or "heuristic").strip().lower()
        max_cases = int((params or {}).get("max_cases") or 200)

        if not suite_id:
            return SkillResult(success=False, error="missing_suite_id")

        suite = await store.get_skill_eval_suite(suite_id=suite_id)
        if not suite:
            return SkillResult(success=False, error="suite_not_found")

        cfg = suite.get("config") if isinstance(suite.get("config"), dict) else {}
        target_skill_id = str(suite.get("target_skill_id") or cfg.get("target_skill_id") or "").strip()
        if not target_skill_id:
            return SkillResult(success=False, error="missing_target_skill_id")

        pos = cfg.get("positive_queries") if isinstance(cfg.get("positive_queries"), list) else []
        neg = cfg.get("negative_queries") if isinstance(cfg.get("negative_queries"), list) else []
        pos = [str(x) for x in pos if isinstance(x, str) and x.strip()]
        neg = [str(x) for x in neg if isinstance(x, str) and x.strip()]
        cases: List[Dict[str, Any]] = []
        for q in pos:
            cases.append({"expected": "positive", "query": q})
        for q in neg:
            cases.append({"expected": "negative", "query": q})
        cases = cases[: max_cases]
        score_threshold = float(cfg.get("score_threshold") or cfg.get("live_threshold") or 0.12)

        # Build a skill catalog (heuristic routing). Prefer override for deterministic tests.
        skills_override = params.get("skills_override") if isinstance(params.get("skills_override"), list) else None
        catalog: List[Dict[str, Any]] = []
        if isinstance(skills_override, list) and skills_override:
            for s in skills_override[:500]:
                if isinstance(s, dict):
                    catalog.append(s)
        else:
            # Scan runtime managers (engine + workspace)
            try:
                skills: List[Dict[str, Any]] = []

                async def _scan_mgr(mgr: Any, scope: str) -> None:
                    if mgr is None:
                        return
                    try:
                        items = await mgr.list_skills(None, None, 800, 0)
                    except Exception:
                        items = []
                    for s in items or []:
                        try:
                            meta = getattr(s, "metadata", None)
                            meta = meta if isinstance(meta, dict) else {}
                            skills.append(
                                {
                                    "skill_id": str(getattr(s, "id", "") or ""),
                                    "name": str(getattr(s, "name", "") or ""),
                                    "description": str(getattr(s, "description", "") or ""),
                                    "scope": scope,
                                    "skill_kind": str(meta.get("skill_kind") or "rule"),
                                    "trigger_conditions": meta.get("trigger_conditions") or meta.get("trigger_keywords") or [],
                                    "keywords": meta.get("keywords") if isinstance(meta.get("keywords"), dict) else {},
                                }
                            )
                        except Exception:
                            continue

                await _scan_mgr(getattr(rt, "workspace_skill_manager", None), "workspace")
                await _scan_mgr(getattr(rt, "skill_manager", None), "engine")
                catalog = skills
            except Exception:
                catalog = []

        # Create eval run record
        await store.upsert_skill_eval_run(
            run_id=run_id,
            suite_id=suite_id,
            tenant_id=str((cfg.get("tenant_id") or "") or "") or None,
            mode=mode,
            status="running",
            metrics=None,
            error=None,
        )

        tp = fp = tn = fn = 0
        false_pos = []
        false_neg = []

        async def _emit_routing_events(*, query_text: str, idx0: int, selected_kind: str, selected_name: str, candidates_top: List[Dict[str, Any]]) -> None:
            """Best-effort: emit routing_decision + skill_candidates_snapshot for 'live' eval."""
            try:
                rid = f"rtd_eval_{run_id}_{idx0}"
                end_ts = time.time()
                qx = str(query_text or "").strip()
                # routing_decision
                await store.add_syscall_event(
                    {
                        "trace_id": None,
                        "run_id": str(run_id),
                        "tenant_id": str((cfg.get("tenant_id") or "") or "") or None,
                        "kind": "routing",
                        "name": "routing_decision",
                        "status": "decision",
                        "start_time": end_ts,
                        "end_time": end_ts,
                        "duration_ms": 0.0,
                        "args": {
                            "routing_decision_id": rid,
                            "step_count": 0,
                            "selected_kind": str(selected_kind),
                            "selected_name": str(selected_name or ""),
                            "selected_skill_id": str(selected_name or "") if str(selected_kind) == "skill" else "",
                            "coding_policy_profile": "off",
                            "query_excerpt": qx[:220],
                        },
                        "created_at": end_ts,
                    }
                )
                # candidates snapshot
                await store.add_syscall_event(
                    {
                        "trace_id": None,
                        "run_id": str(run_id),
                        "tenant_id": str((cfg.get("tenant_id") or "") or "") or None,
                        "kind": "routing",
                        "name": "skill_candidates_snapshot",
                        "status": "snapshot",
                        "start_time": end_ts,
                        "end_time": end_ts,
                        "duration_ms": 0.0,
                        "args": {
                            "routing_decision_id": rid,
                            "step_count": 0,
                            "selected_kind": str(selected_kind),
                            "selected_name": str(selected_name or ""),
                            "coding_policy_profile": "off",
                            "query_excerpt": qx[:220],
                            "candidates": candidates_top[:8],
                        },
                        "created_at": end_ts,
                    }
                )
            except Exception:
                return

        for idx, c in enumerate(cases):
            q = c.get("query") or ""
            expected = c.get("expected")
            selected_kind = "none"
            selected_skill_id = ""
            selected_score = 0.0
            candidates_payload = []

            top = compute_skill_candidates(query_text=str(q), skills=catalog, top_k=8)
            # Enrich with permission hints (best-effort)
            candidates_payload = []
            for t in top:
                perm = None
                exec_perm = None
                try:
                    from core.apps.tools.skill_tools import resolve_skill_permission, resolve_executable_skill_permission

                    perm = resolve_skill_permission(t.name)
                    # lookup kind from catalog if available
                    kind0 = None
                    for s in catalog:
                        if str(s.get("skill_id") or "") == str(t.skill_id) or str(s.get("name") or "") == str(t.name):
                            kind0 = str(s.get("skill_kind") or "")
                            break
                    if str(kind0 or "").strip().lower() == "executable":
                        exec_perm = resolve_executable_skill_permission(t.name)
                except Exception:
                    perm = None
                    exec_perm = None
                candidates_payload.append(
                    {"skill_id": t.skill_id, "name": t.name, "scope": t.scope, "score": t.score, "overlap": t.overlap, "perm": perm, "exec_perm": exec_perm}
                )

            if mode == "live":
                # True-live (M1): still heuristic selection, but now emits routing syscalls using the
                # same event schema as runtime (routing_decision + skill_candidates_snapshot).
                if top and float(top[0].score) >= float(score_threshold):
                    selected_kind = "skill"
                    selected_skill_id = top[0].skill_id
                    selected_score = float(top[0].score)
                else:
                    selected_kind = "no_action"
                    selected_skill_id = ""
                    selected_score = float(top[0].score) if top else 0.0
                await _emit_routing_events(
                    query_text=str(q),
                    idx0=int(idx),
                    selected_kind=str(selected_kind),
                    selected_name=str(selected_skill_id or ""),
                    candidates_top=candidates_payload,
                )
            else:
                # heuristic: always select top-1 if any
                if top:
                    selected_kind = "skill"
                    selected_skill_id = top[0].skill_id
                    selected_score = float(top[0].score)

            ok = False
            if expected == "positive":
                ok = (selected_skill_id == target_skill_id)
                if ok:
                    tp += 1
                else:
                    fn += 1
                    false_neg.append({"query": q, "selected": selected_skill_id, "top": candidates_payload[:3]})
            else:
                ok = (selected_skill_id != target_skill_id)
                if ok:
                    tn += 1
                else:
                    fp += 1
                    false_pos.append({"query": q, "selected": selected_skill_id, "top": candidates_payload[:3]})

            await store.add_skill_eval_result(
                run_id=run_id,
                query_index=int(idx),
                query_text=str(q),
                expected=str(expected),
                selected_kind=str(selected_kind),
                selected_skill_id=str(selected_skill_id),
                selected_score=float(selected_score),
                candidates=candidates_payload,
                ok=bool(ok),
            )

        precision = float(tp) / float(tp + fp) if (tp + fp) > 0 else None
        recall = float(tp) / float(tp + fn) if (tp + fn) > 0 else None
        f1 = None
        if precision is not None and recall is not None and (precision + recall) > 0:
            f1 = 2.0 * precision * recall / (precision + recall)

        metrics = {
            "target_skill_id": target_skill_id,
            "score_threshold": score_threshold,
            "counts": {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "total": len(cases)},
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "false_positives": false_pos[:20],
            "false_negatives": false_neg[:20],
        }

        await store.upsert_skill_eval_run(
            run_id=run_id,
            suite_id=suite_id,
            tenant_id=str((cfg.get("tenant_id") or "") or "") or None,
            mode=mode,
            status="completed",
            metrics=metrics,
            error=None,
        )

        return SkillResult(success=True, output={"run_id": run_id, "suite_id": suite_id, "mode": mode, "metrics": metrics})
