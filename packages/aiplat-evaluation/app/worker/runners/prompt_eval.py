"""prompt_eval — pure-text scorer; optional LLM via AIPLAT_EVAL_LLM (no Central).

Honesty: default offline deterministic. Live provider is independent HTTP
(OpenAI-compatible). accuracy_claim=false always.
"""
from __future__ import annotations

from typing import Any, Dict

from app.llm.client import complete_text, llm_enabled, llm_mode
from app.worker.runners._common import runner_result


def run_prompt_eval(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    job_id = str(job.get("job_id") or "")
    tenant_id = str(job.get("tenant_id") or "")
    prompt = str(payload.get("prompt") or payload.get("input") or "")
    expected = str(payload.get("expected") or payload.get("expected_text") or "")
    actual = str(payload.get("actual") or payload.get("output") or "")
    audit: Dict[str, Any] = {}

    if not actual and llm_enabled():
        llm = complete_text(
            prompt,
            job_id=job_id,
            tenant_id=tenant_id,
            runner_id="prompt_eval",
            purpose="prompt_eval",
            model=str(payload.get("model") or "") or None,
        )
        audit = dict(llm.get("audit") or {})
        if not llm.get("ok"):
            return runner_result(
                runner_id="prompt_eval",
                job_id=job_id,
                ok=False,
                metrics={"pass": 0.0, "exact_match": 0.0},
                evidence={
                    "prompt_len": len(prompt),
                    "has_actual": False,
                    "llm": audit,
                },
                detail=str(audit.get("detail") or "llm_failed"),
                mode=f"llm_{llm_mode()}",
            )
        actual = str(llm.get("text") or "")

    if not actual and expected:
        return runner_result(
            runner_id="prompt_eval",
            job_id=job_id,
            ok=False,
            metrics={"pass": 0.0, "exact_match": 0.0},
            evidence={"prompt_len": len(prompt), "has_actual": False},
            detail="prompt_eval requires payload.actual (or AIPLAT_EVAL_LLM)",
            mode="local_deterministic",
        )

    exact = 1.0 if (actual == expected and expected != "") else 0.0
    if expected == "" and actual != "":
        exact = 0.0
        ok = bool(actual.strip())
    else:
        ok = exact == 1.0

    mode = "local_deterministic"
    if audit:
        mode = f"llm_{audit.get('mode') or llm_mode()}"

    return runner_result(
        runner_id="prompt_eval",
        job_id=job_id,
        ok=ok,
        metrics={"pass": 1.0 if ok else 0.0, "exact_match": exact},
        evidence={
            "prompt_len": len(prompt),
            "actual_len": len(actual),
            **({"llm": audit} if audit else {}),
        },
        detail="" if ok else "exact_match failed or empty",
        mode=mode,
    )
