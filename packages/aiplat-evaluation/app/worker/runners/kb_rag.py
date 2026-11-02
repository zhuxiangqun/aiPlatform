"""kb_rag — readonly local retrieval fixture scorer (no KB writes)."""
from __future__ import annotations

from typing import Any, Dict, List

from app.worker.runners._common import runner_result


def run_kb_rag(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    job_id = str(job.get("job_id") or "")
    query = str(payload.get("query") or "")
    hits: List[Any] = []
    if isinstance(payload.get("hits"), list):
        hits = payload["hits"]
    elif isinstance(payload.get("docs"), list):
        hits = payload["docs"]
    # Fail closed without fixture hits — do not invent retrieval.
    if not hits:
        return runner_result(
            runner_id="kb_rag",
            job_id=job_id,
            ok=False,
            metrics={"pass": 0.0, "hit_count": 0},
            evidence={"query_len": len(query)},
            detail="kb_rag requires payload.hits (readonly fixture); no live KB write",
        )
    expected_ids = payload.get("expected_ids")
    if isinstance(expected_ids, list) and expected_ids:
        got = []
        for h in hits:
            if isinstance(h, dict) and h.get("id") is not None:
                got.append(h.get("id"))
            elif isinstance(h, str):
                got.append(h)
        ok = all(eid in got for eid in expected_ids)
    else:
        ok = len(hits) > 0
    return runner_result(
        runner_id="kb_rag",
        job_id=job_id,
        ok=ok,
        metrics={"pass": 1.0 if ok else 0.0, "hit_count": len(hits)},
        evidence={"query_len": len(query), "readonly": True},
        detail="" if ok else "expected_ids not covered by hits",
    )
