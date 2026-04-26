from __future__ import annotations

import time
from typing import Any, Dict, List

from core.apps.skills.base import BaseSkill
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult
from core.harness.kernel.runtime import get_kernel_runtime
from core.utils.ids import new_prefixed_id


class SkillEvalQualitySkill(BaseSkill):
    """
    Skill Quality Evaluation (Skeleton)

    Execute target_skill on a set of quality_cases and grade results with simple rules.
    Stores results into ExecutionStore skill_eval_* tables (reusing skill_eval_results rows).
    """

    def __init__(self):
        cfg = SkillConfig(
            name="skill_eval_quality",
            description="运行 Skill 的执行质量评测（Quality Eval 骨架），基于规则生成 checklist 与评分，并写入评测结果。",
            input_schema={
                "suite_id": {"type": "string", "description": "评测套件 ID"},
                "max_cases": {"type": "integer", "description": "最多评测条数", "default": 50},
            },
            output_schema={
                "run_id": {"type": "string"},
                "suite_id": {"type": "string"},
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

    def _grade(self, *, expected: Dict[str, Any], success: bool, output: Any, error: str | None) -> Dict[str, Any]:
        checklist: List[Dict[str, Any]] = []

        exp_success = expected.get("success")
        if isinstance(exp_success, bool):
            ok = bool(success) == exp_success
            checklist.append({"text": f"成功标志应为 {exp_success}", "status": "passed" if ok else "failed", "note": error or ""})

        req_keys = expected.get("require_keys")
        if isinstance(req_keys, list):
            ok = isinstance(output, dict) and all(str(k) in output for k in req_keys if isinstance(k, str))
            checklist.append({"text": f"输出包含必需字段：{[k for k in req_keys if isinstance(k,str)][:10]}", "status": "passed" if ok else "failed"})

        bullets_min = expected.get("bullets_min")
        if bullets_min is not None:
            try:
                n = int(bullets_min)
            except Exception:
                n = None
            if n is not None:
                ok = isinstance(output, dict) and isinstance(output.get("bullets"), list) and len(output.get("bullets")) >= n
                checklist.append({"text": f"bullets 数量 >= {n}", "status": "passed" if ok else "failed"})

        contains = expected.get("contains")
        if isinstance(contains, list):
            hay = ""
            try:
                if isinstance(output, dict):
                    if isinstance(output.get("title"), str):
                        hay += output.get("title") + "\n"
                    if isinstance(output.get("short_summary"), str):
                        hay += output.get("short_summary") + "\n"
                    if isinstance(output.get("bullets"), list):
                        hay += "\n".join([str(x) for x in output.get("bullets")[:20]])
                else:
                    hay = str(output)
            except Exception:
                hay = ""
            for s in [x for x in contains if isinstance(x, str) and x.strip()][:10]:
                ok = s in hay
                checklist.append({"text": f"输出包含文本片段：{s[:60]}", "status": "passed" if ok else "failed"})

        passed = sum(1 for c in checklist if c.get("status") == "passed")
        total = len(checklist) if checklist else 0
        score = float(passed) / float(total) if total > 0 else (1.0 if success else 0.0)
        return {"checklist": checklist, "passed": passed, "total": total, "score": score}

    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        if store is None:
            return SkillResult(success=False, error="ExecutionStore not initialized")

        run_id = str(getattr(context, "session_id", None) or "") or new_prefixed_id("evalrun")
        suite_id = str((params or {}).get("suite_id") or "").strip()
        max_cases = int((params or {}).get("max_cases") or 50)
        if not suite_id:
            return SkillResult(success=False, error="missing_suite_id")

        suite = await store.get_skill_eval_suite(suite_id=suite_id)
        if not suite:
            return SkillResult(success=False, error="suite_not_found")

        cfg = suite.get("config") if isinstance(suite.get("config"), dict) else {}
        target_skill_id = str(suite.get("target_skill_id") or cfg.get("target_skill_id") or "").strip()
        if not target_skill_id:
            return SkillResult(success=False, error="missing_target_skill_id")

        cases = cfg.get("quality_cases") if isinstance(cfg.get("quality_cases"), list) else []
        cases = [c for c in cases if isinstance(c, dict)]
        cases = cases[: max_cases]

        await store.upsert_skill_eval_run(
            run_id=run_id,
            suite_id=suite_id,
            tenant_id=str(cfg.get("tenant_id") or "") or None,
            mode="quality",
            status="running",
            metrics=None,
            error=None,
        )

        ok_cnt = 0
        total = 0
        failures: List[Dict[str, Any]] = []

        for idx, c in enumerate(cases):
            total += 1
            inp = c.get("input") if isinstance(c.get("input"), dict) else {}
            expected = c.get("expected") if isinstance(c.get("expected"), dict) else {}
            case_name = str(c.get("name") or f"case_{idx}")

            # Execute target skill
            exec_id = new_prefixed_id("evalcase")
            try:
                exec_res = await rt.skill_manager.execute_skill(
                    skill_id=target_skill_id,
                    input_data=inp,
                    context={"user_id": getattr(context, "user_id", None) or "system", "tenant_id": cfg.get("tenant_id"), "timeout": 60},
                    execution_id=str(exec_id),
                )
                # SkillManager returns SkillExecution dataclass in most paths; keep dict fallback for compatibility.
                if isinstance(exec_res, dict):
                    st0 = str(exec_res.get("status") or "").strip().lower()
                    err = exec_res.get("error")
                    output = exec_res.get("output_data")
                else:
                    st0 = str(getattr(exec_res, "status", "") or "").strip().lower()
                    err = getattr(exec_res, "error", None)
                    output = getattr(exec_res, "output_data", None)
                # treat completed with no error as success
                success = (st0 in {"success", "completed"}) and not err
            except Exception as e:
                success = False
                output = None
                err = str(e)

            grade = self._grade(expected=expected, success=success, output=output, error=err)
            ok = bool(grade.get("score", 0.0) >= 0.999)  # skeleton: require all checks to pass
            if ok:
                ok_cnt += 1
            else:
                failures.append({"name": case_name, "score": grade.get("score"), "error": err})

            # Reuse skill_eval_results row: put grading payload into candidates_json
            await store.add_skill_eval_result(
                run_id=run_id,
                query_index=int(idx),
                query_text=case_name,
                expected=str(expected),
                selected_kind="quality",
                selected_skill_id=str(target_skill_id),
                selected_score=float(grade.get("score") or 0.0),
                candidates={"input": inp, "output": output, "grade": grade, "error": err, "exec_id": exec_id},
                ok=bool(ok),
            )

        metrics = {
            "target_skill_id": target_skill_id,
            "counts": {"passed": ok_cnt, "failed": int(total - ok_cnt), "total": total},
            "pass_rate": float(ok_cnt) / float(total) if total > 0 else None,
            "failures": failures[:20],
        }

        await store.upsert_skill_eval_run(
            run_id=run_id,
            suite_id=suite_id,
            tenant_id=str(cfg.get("tenant_id") or "") or None,
            mode="quality",
            status="completed",
            metrics=metrics,
            error=None,
        )

        return SkillResult(success=True, output={"run_id": run_id, "suite_id": suite_id, "metrics": metrics})
