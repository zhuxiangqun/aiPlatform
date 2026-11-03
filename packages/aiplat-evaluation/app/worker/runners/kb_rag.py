"""kb_rag — readonly local retrieval fixture scorer (no KB writes).

Honesty: P1 groundedness/text_quality are engineering scores; accuracy_claim=false.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.scoring.semantics import groundedness_dimension, kb_rag_p1_metrics
from app.worker.runners._common import runner_result


def _hit_texts(hits: List[Any]) -> List[str]:
    texts: List[str] = []
    for h in hits:
        if isinstance(h, dict):
            texts.append(str(h.get("text") or h.get("content") or h.get("snippet") or ""))
        else:
            texts.append(str(h))
    return [t for t in texts if t]


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
        texts = _hit_texts([])
        gdim = groundedness_dimension(actual=query, context="", sources=texts)
        return runner_result(
            runner_id="kb_rag",
            job_id=job_id,
            ok=False,
            metrics=kb_rag_p1_metrics(query=query, hits=[], ok=False),
            groundedness_dimension=gdim,
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
    texts = _hit_texts(hits)
    gdim = groundedness_dimension(
        actual=query, context="\n".join(texts), sources=texts
    )
    return runner_result(
        runner_id="kb_rag",
        job_id=job_id,
        ok=ok,
        metrics=kb_rag_p1_metrics(query=query, hits=hits, ok=ok),
        groundedness_dimension=gdim,
        evidence={"query_len": len(query), "readonly": True},
        detail="" if ok else "expected_ids not covered by hits",
    )
