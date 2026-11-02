"""skill_suite — fixture-only scorer (no live tools / no agent loop).

Honesty: requires docker sandbox admit + fixture payload; accuracy_claim=false.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.sandbox.docker_exec import run_in_docker
from app.sandbox.policy import sandbox_admits, sandbox_backend
from app.sandbox.skill_policy import assert_skill_suite_fixture
from app.worker.runners._common import runner_result


def run_skill_suite(job: Dict[str, Any]) -> Dict[str, Any]:
    rid = "skill_suite"
    job_id = str(job.get("job_id") or "")
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    if not sandbox_admits(rid, payload=payload):
        raise ValueError(f"sandbox_required:{rid}")
    assert_skill_suite_fixture(payload)

    # Optional wrap: prove docker path with allowlisted true (not skill tools).
    wrap = run_in_docker(["true"])
    if not wrap.get("ok"):
        return runner_result(
            runner_id=rid,
            job_id=job_id,
            ok=False,
            metrics={"pass": 0.0, "cases": 0.0},
            evidence={"sandbox": wrap.get("audit") or {}, "fixture": True},
            detail=str((wrap.get("audit") or {}).get("detail") or "docker_wrap_failed"),
            mode="skill_fixture",
        )

    cases: List[Any] = list(payload.get("cases") or [])
    results = payload.get("results")
    if not isinstance(results, list):
        results = []
    passed = 0
    for i, case in enumerate(cases):
        expected = True
        if isinstance(case, dict) and "expected_ok" in case:
            expected = bool(case.get("expected_ok"))
        actual = True
        if i < len(results):
            r = results[i]
            if isinstance(r, dict):
                actual = bool(r.get("ok", r.get("passed", False)))
            else:
                actual = bool(r)
        elif isinstance(case, dict) and "actual_ok" in case:
            actual = bool(case.get("actual_ok"))
        else:
            # No result supplied → fail closed for that case
            actual = False
        if actual == expected:
            passed += 1

    total = len(cases)
    ok = total == 0 or passed == total
    ratio = 1.0 if total == 0 else (passed / float(total))
    return runner_result(
        runner_id=rid,
        job_id=job_id,
        ok=ok,
        metrics={"pass": ratio, "cases": float(total), "passed": float(passed)},
        evidence={
            "fixture": True,
            "tools_executed": False,
            "sandbox_backend": sandbox_backend(),
            "docker_wrap": wrap.get("audit") or {},
            "suite_id": str(payload.get("suite_id") or ""),
        },
        detail="" if ok else f"fixture cases failed passed={passed}/{total}",
        mode="skill_fixture",
    )
