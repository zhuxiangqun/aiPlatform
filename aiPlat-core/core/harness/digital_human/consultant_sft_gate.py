"""小朱 sft_promote 最小 holdout/结构门（批准前）。

复用「冻结夹具 + 诚实锁」思路（对齐 evo regression），不做生产流量评测、
不改 best_model_for_purpose、不宣称适配器可上线。

非目标：不跑真实模型推理；不自动绑 purpose。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.utils.paths import get_aiplat_home

# 冻结版本；用例变更必须升版
DH_SFT_HOLDOUT_VERSION = "dh_sft_holdout_v1"


def _skip_gate_enabled() -> bool:
    return (os.getenv("AIPLAT_DH_SFT_PROMOTE_SKIP_GATE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def default_consultant_holdout_cases() -> List[Dict[str, Any]]:
    """顾问冻结 holdout：心智种子题（结构完整性，非模型打分）。

    Returns:
        case 列表；每条须有非空 q/a。
    """
    try:
        from core.harness.digital_human.trajectory_collector import _SEED_QA
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for i, pair in enumerate(_SEED_QA or []):
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        q, a = str(pair[0] or "").strip(), str(pair[1] or "").strip()
        out.append(
            {
                "case_id": f"seed.{i}",
                "q": q,
                "a": a,
                "require_nonempty": True,
            }
        )
    return out


def _approved_seed_cases(limit: int = 20) -> List[Dict[str, Any]]:
    path = Path(get_aiplat_home()) / "digital_human" / "approved_seed_qa.jsonl"
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            q = str(obj.get("q") or "").strip()
            a = str(obj.get("a") or "").strip()
            rows.append(
                {
                    "case_id": f"approved.{len(rows)}",
                    "q": q,
                    "a": a,
                    "require_nonempty": True,
                }
            )
            if len(rows) >= limit:
                break
    except OSError:
        return []
    return rows


def _check_case(case: Dict[str, Any]) -> Dict[str, Any]:
    cid = str(case.get("case_id") or "?")
    q = str(case.get("q") or "").strip()
    a = str(case.get("a") or "").strip()
    ok = True
    reason = "ok"
    if case.get("require_nonempty") and (not q or not a):
        ok = False
        reason = "empty_qa"
    return {"case_id": cid, "ok": ok, "reason": reason}


def evaluate_sft_promote_gate(
    *,
    proposal: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """对 sft_promote 提案跑最小结构/holdout 门。

    Args:
        proposal: 完整提案（优先）。
        payload: 若无 proposal 则直接用载荷。

    Returns:
        passed / cases / 诚实字段；``production_model_changed`` 恒 false；
        ``feeds_production_routing`` 恒 false。
    """
    prop = proposal if isinstance(proposal, dict) else {}
    pl = dict(payload or prop.get("payload") or {})
    job_id = str(pl.get("job_id") or "").strip()
    cases = default_consultant_holdout_cases() + _approved_seed_cases()
    results = [_check_case(c) for c in cases]
    failed = [r for r in results if not r.get("ok")]

    checks: List[Dict[str, Any]] = []
    if not job_id:
        checks.append({"id": "job_id", "ok": False, "reason": "missing_job_id"})
    else:
        checks.append({"id": "job_id", "ok": True, "reason": "ok"})

    if not cases:
        checks.append({"id": "holdout_fixture", "ok": False, "reason": "empty_holdout"})
    elif failed:
        checks.append(
            {
                "id": "holdout_fixture",
                "ok": False,
                "reason": f"failed_cases:{len(failed)}",
            }
        )
    else:
        checks.append(
            {
                "id": "holdout_fixture",
                "ok": True,
                "reason": "ok",
                "n_cases": len(cases),
                "dataset_version": DH_SFT_HOLDOUT_VERSION,
            }
        )

    # 样本数：载荷声明或跳过（无导出时不硬拦，靠 job_id+holdout）
    sample_count = pl.get("sample_count")
    if sample_count is not None:
        try:
            n = int(sample_count)
        except (TypeError, ValueError):
            n = -1
        min_n = 1
        try:
            from core.harness.digital_human.consultant_sft_loop import _min_samples

            min_n = _min_samples()
        except Exception:
            min_n = 10
        checks.append(
            {
                "id": "sample_count",
                "ok": n >= min_n,
                "reason": "ok" if n >= min_n else f"need>={min_n} got={n}",
            }
        )

    skipped = _skip_gate_enabled()
    structural_ok = all(c.get("ok") for c in checks)
    passed = True if skipped else structural_ok

    return {
        "ok": True,
        "passed": passed,
        "skipped": skipped,
        "dataset_version": DH_SFT_HOLDOUT_VERSION,
        "job_id": job_id,
        "checks": checks,
        "case_results": results,
        "n_cases": len(cases),
        "n_failed": len(failed),
        "production_model_changed": False,
        "feeds_production_routing": False,
        "production_sample": False,
        "note": (
            "skip_gate_env"
            if skipped
            else (
                "holdout_structure_ok; still human /infra/finetune to bind"
                if passed
                else "eval_gate_failed; APPROVED without APPLIED"
            )
        ),
    }
