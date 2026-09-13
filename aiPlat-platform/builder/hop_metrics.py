"""Factory skill-hop metrics (Phase C W5).

Append-only JSONL per project under AIPLAT_HOME/builder/hop_metrics/{project_id}.jsonl
Feeds promotion_gate evaluate_run_through (N≥20 / success_rate / failed_stage).
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

_VALID_STAGES = frozenset({
    "planning",
    "tool_selection",
    "tool_execution",
    "response_synthesis",
    "verification",
    "",  # success may omit
})


def _metrics_dir() -> Path:
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    d = Path(home) / "builder" / "hop_metrics"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(project_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(project_id or "unknown"))
    return _metrics_dir() / f"{safe}.jsonl"


def record_hop(
    project_id: str,
    *,
    skill: str,
    agent: str = "",
    ok: bool,
    failed_stage: str = "",
    error: str = "",
    mode: str = "",
    latency_ms: float = 0.0,
) -> None:
    """Append one hop outcome. best-effort, never raises."""
    try:
        stage = str(failed_stage or "")
        if not ok and stage and stage not in _VALID_STAGES:
            stage = "tool_execution"
        if not ok and not stage:
            # 无 failed_stage 的失败：标记后仍写入，聚合时计入 failures_missing_stage
            stage = ""
        rec = {
            "ts": time.time(),
            "project_id": project_id,
            "skill": skill,
            "agent": agent,
            "ok": bool(ok),
            "failed_stage": stage,
            "error": str(error or "")[:300],
            "mode": mode,
            "latency_ms": float(latency_ms or 0),
        }
        with open(_path_for(project_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass  # noqa: cleanup-best-effort


def load_hops(project_id: str, limit: int = 5000) -> List[Dict[str, Any]]:
    path = _path_for(project_id)
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        if limit and len(rows) > limit:
            rows = rows[-limit:]
    except Exception:
        return []
    return rows


def aggregate_hops(project_id: str) -> Dict[str, Any]:
    """Return n_runs, success_rate, failures_missing_stage, by_failed_stage, by_skill."""
    rows = load_hops(project_id)
    n = len(rows)
    if n == 0:
        return {
            "n_runs": 0,
            "success_count": 0,
            "success_rate": 0.0,
            "failures_missing_stage": 0,
            "by_failed_stage": {},
            "by_skill": {},
            "effective_n": 0,
            "effective_success_rate": 0.0,
        }
    ok_n = sum(1 for r in rows if r.get("ok"))
    fail_rows = [r for r in rows if not r.get("ok")]
    missing = sum(1 for r in fail_rows if not r.get("failed_stage"))
    # 有效样本：成功 + 带 failed_stage 的失败（无 stage 的失败剔除出成功率分母）
    effective = [r for r in rows if r.get("ok") or r.get("failed_stage")]
    eff_n = len(effective)
    eff_ok = sum(1 for r in effective if r.get("ok"))
    by_stage = Counter(str(r.get("failed_stage") or "?") for r in fail_rows)
    by_skill: Dict[str, Dict[str, int]] = {}
    for r in rows:
        sk = str(r.get("skill") or "?")
        bucket = by_skill.setdefault(sk, {"ok": 0, "fail": 0})
        if r.get("ok"):
            bucket["ok"] += 1
        else:
            bucket["fail"] += 1
    return {
        "n_runs": n,
        "success_count": ok_n,
        "success_rate": (ok_n / n) if n else 0.0,
        "failures_missing_stage": missing,
        "by_failed_stage": dict(by_stage),
        "by_skill": by_skill,
        "effective_n": eff_n,
        "effective_success_rate": (eff_ok / eff_n) if eff_n else 0.0,
    }


def evaluate_project_run_through(
    project_id: str,
    *,
    conformance_green: bool = False,
    real_tests_green: bool = False,
    physical_evidence: bool = False,
    policy_gate_closed: bool = True,
    mature: bool = False,
) -> Dict[str, Any]:
    """Combine hop aggregate + promotion_gate.evaluate_run_through."""
    import importlib.util as _iu

    _pg_path = Path(__file__).resolve().parent / "promotion_gate.py"
    _spec = _iu.spec_from_file_location("promotion_gate_hop", _pg_path)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"cannot load {_pg_path}")
    _pg = _iu.module_from_spec(_spec)
    _spec.loader.exec_module(_pg)
    evaluate_run_through = _pg.evaluate_run_through
    load_promotion_gate = _pg.load_promotion_gate

    agg = aggregate_hops(project_id)
    # 用 effective_*：无 failed_stage 的失败不计入成功率（与契约一致）
    result = evaluate_run_through(
        n_runs=int(agg["effective_n"]),
        success_rate=float(agg["effective_success_rate"]),
        failures_missing_stage=int(agg["failures_missing_stage"]),
        conformance_green=conformance_green,
        real_tests_green=real_tests_green,
        physical_evidence=physical_evidence,
        policy_gate_closed=policy_gate_closed,
        mature=mature,
    )
    result["hops"] = agg
    result["policy"] = load_promotion_gate().get("external_message", "")
    result["project_id"] = project_id
    return result
