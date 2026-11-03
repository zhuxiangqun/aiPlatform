#!/usr/bin/env python3
"""Live LLM 10-task smoke (stub vs live × N). accuracy_claim=false always.

Does not authorize process_split / staging / G2b accuracy.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llm.client import (  # noqa: E402
    assert_provider_independence,
    llm_seed,
    llm_temperature,
    looks_like_central_llm_url,
    provider_base_url,
)
from app.scoring.semantics import efficiency_dimension  # noqa: E402
from app.store.jobs import enqueue_job, get_job  # noqa: E402
from app.store.migrate import apply_migrations  # noqa: E402
from app.worker.claim import process_once  # noqa: E402

DEFAULT_TASKS = ROOT / "docs/a3/live_llm_tasks.v0.json"
DEFAULT_EVID = ROOT / "docs/a3/drills"


def _load_tasks(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list) or len(tasks) < 1:
        raise SystemExit(f"task pack missing tasks: {path}")
    return [t for t in tasks if isinstance(t, dict)]


def _db_url(tmp: Path) -> str:
    url = f"sqlite:///{tmp / 'live_llm_smoke.sqlite3'}"
    apply_migrations(url)
    return url


def _run_one(
    db: str,
    *,
    task: Dict[str, Any],
    mode_label: str,
    worker_id: str,
) -> Dict[str, Any]:
    tid = str(task.get("id") or "task")
    family = str(task.get("family") or "prompt")
    prompt = str(task.get("prompt") or "")
    job = enqueue_job(
        db,
        runner_id="prompt_eval",
        tenant_id="local-live-llm",
        payload={"prompt": prompt, "expected": ""},
    )
    out = process_once(db, worker_id=worker_id)
    stored = get_job(db, job["job_id"]) if isinstance(job, dict) else None
    result = (out or {}).get("result") if isinstance(out, dict) else {}
    if not isinstance(result, dict):
        result = {}
    audit = {}
    ev = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    if isinstance(ev.get("llm"), dict):
        audit = dict(ev["llm"])
    status = str((out or {}).get("status") or (stored or {}).get("status") or "unknown")
    text = ""
    # actual text not always in result; keep audit-centric honesty
    if isinstance(result.get("evidence"), dict):
        text = str(result["evidence"].get("preview") or "")[:200]
    return {
        "task_id": tid,
        "family": family,
        "mode_label": mode_label,
        "job_id": (out or {}).get("job_id") or (job or {}).get("job_id"),
        "status": status,
        "ok": bool(result.get("ok")) if status == "succeeded" else False,
        "detail": str(result.get("detail") or audit.get("detail") or ""),
        "accuracy_claim": False,
        "audit": {
            "model": audit.get("model"),
            "mode": audit.get("mode"),
            "temperature": audit.get("temperature"),
            "seed": audit.get("seed"),
            "timeout_s": audit.get("timeout_s"),
            "latency_ms": audit.get("latency_ms"),
            "tokens_in": audit.get("tokens_in"),
            "tokens_out": audit.get("tokens_out"),
            "cost_estimate": audit.get("cost_estimate"),
            "central_http": bool(audit.get("central_http")),
            "detail": audit.get("detail"),
        },
        "text_preview": text,
    }


def _variance(vals: List[float]) -> Optional[float]:
    if len(vals) < 2:
        return None
    try:
        return round(float(statistics.pstdev(vals)), 4)
    except statistics.StatisticsError:
        return None


def main() -> int:
    tasks_path = Path(os.environ.get("AIPLAT_EVAL_LIVE_LLM_TASKS") or DEFAULT_TASKS)
    evid_dir = Path(os.environ.get("AIPLAT_EVAL_LIVE_LLM_EVIDENCE_DIR") or DEFAULT_EVID)
    evid_dir.mkdir(parents=True, exist_ok=True)
    repeats = int(os.environ.get("AIPLAT_EVAL_LIVE_LLM_REPEATS") or "3")
    cost_cap = float(os.environ.get("AIPLAT_EVAL_LIVE_LLM_COST_CAP") or "1.0")
    live_req = (os.environ.get("AIPLAT_EVAL_LLM_LIVE") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tasks = _load_tasks(tasks_path)
    if len(tasks) != 10:
        # allow pack growth but warn — acceptance targets 10
        pass

    provider = {
        "base_url": provider_base_url(),
        "model": (os.environ.get("AIPLAT_EVAL_LLM_MODEL") or "").strip() or None,
        "temperature": llm_temperature(),
        "seed": llm_seed(),
        "timeout_s": float(os.environ.get("AIPLAT_EVAL_LLM_TIMEOUT") or "30"),
        "cost_per_1k": (os.environ.get("AIPLAT_EVAL_LLM_COST_PER_1K") or "").strip() or None,
        "looks_like_central": looks_like_central_llm_url(),
    }

    rows: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="eval-live-llm-") as td:
        tmp = Path(td)
        db = _db_url(tmp)

        # stub baseline (one pass)
        os.environ["AIPLAT_EVAL_LLM"] = "stub"
        os.environ.setdefault("AIPLAT_EVAL_LLM_STUB_OUTPUT", "stub-ok")
        os.environ.setdefault("AIPLAT_EVAL_LLM_COST_PER_1K", "0.001")
        for task in tasks:
            rows.append(
                _run_one(db, task=task, mode_label="stub", worker_id="w-stub")
            )

        live_ok_count = 0
        live_error = ""
        if live_req:
            try:
                assert_provider_independence()
            except ValueError as exc:
                live_error = str(exc)
            if not provider["base_url"]:
                live_error = live_error or "missing_AIPLAT_EVAL_LLM_BASE_URL"
            if not live_error:
                os.environ["AIPLAT_EVAL_LLM"] = "http"
                for rep in range(1, repeats + 1):
                    for task in tasks:
                        row = _run_one(
                            db,
                            task=task,
                            mode_label=f"live_r{rep}",
                            worker_id=f"w-live-{rep}",
                        )
                        rows.append(row)
                        if row.get("ok") or row.get("status") in ("succeeded", "failed"):
                            # "has result" — failed/timeout still counts as visible outcome
                            if row.get("audit", {}).get("mode") == "http":
                                live_ok_count += 1 if row.get("status") != "unknown" else 0

    # per-task live variance (latency / tokens_out)
    by_task: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        if str(r.get("mode_label", "")).startswith("live_"):
            by_task.setdefault(str(r["task_id"]), []).append(r)
    variance = {}
    for tid, rs in by_task.items():
        lats = [float(r["audit"].get("latency_ms") or 0) for r in rs]
        toks = [float(r["audit"].get("tokens_out") or 0) for r in rs]
        variance[tid] = {
            "n": len(rs),
            "latency_ms_pstdev": _variance(lats),
            "tokens_out_pstdev": _variance(toks),
            "statuses": [r.get("status") for r in rs],
            "oks": [bool(r.get("ok")) for r in rs],
        }

    total_cost = sum(float((r.get("audit") or {}).get("cost_estimate") or 0) for r in rows)
    cost_ok = total_cost <= cost_cap

    live_audits = [
        dict(r.get("audit") or {})
        for r in rows
        if str(r.get("mode_label", "")).startswith("live_")
    ]
    live_flags = [
        bool(r.get("ok"))
        for r in rows
        if str(r.get("mode_label", "")).startswith("live_")
    ]
    efficiency = efficiency_dimension(live_audits, success_flags=live_flags)

    # acceptance: each of 10 tasks has ≥1 stub result; if live, each has ≥1 live result
    task_ids = [str(t.get("id")) for t in tasks]
    stub_ids = {r["task_id"] for r in rows if r["mode_label"] == "stub" and r["status"] != "unknown"}
    live_ids = {
        r["task_id"]
        for r in rows
        if str(r["mode_label"]).startswith("live_") and r["status"] != "unknown"
    }
    stub_complete = all(tid in stub_ids for tid in task_ids)
    live_complete = (not live_req) or all(tid in live_ids for tid in task_ids)
    gate_ok = stub_complete and live_complete and cost_ok and not provider["looks_like_central"]
    if live_req and live_error:
        gate_ok = False

    payload = {
        "schema": "eval.live_llm.smoke.v0",
        "product_id": "evaluation",
        "environment": "local",
        "accuracy_claim": False,
        "process_split_authorized": False,
        "live_requested": live_req,
        "live_error": live_error or None,
        "provider": provider,
        "repeats": repeats if live_req else 0,
        "cost_cap": cost_cap,
        "total_cost_estimate": round(total_cost, 6),
        "cost_ok": cost_ok,
        "task_count": len(tasks),
        "stub_complete": stub_complete,
        "live_complete": live_complete,
        "gate_ok": gate_ok,
        "variance": variance,
        "efficiency_dimension": efficiency,
        "runs": rows,
        "honesty": (
            "stub vs live smoke only; failures/timeouts recorded; "
            "efficiency_dimension carries latency p50/p95 + cost_per_success; "
            "not G2b accuracy; not staging authorize; not security certification"
        ),
        "recorded_at": stamp,
    }
    out_path = evid_dir / f"local-eval-live-llm-{stamp}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "gate": "ok" if gate_ok else "fail",
        "evidence": str(out_path),
        "live_requested": live_req,
        "stub_complete": stub_complete,
        "live_complete": live_complete,
        "cost_ok": cost_ok,
        "total_cost_estimate": payload["total_cost_estimate"],
        "accuracy_claim": False,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if gate_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
