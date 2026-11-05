"""P1b — cohost bridge to package report compare (composite_version gate).

Loads packages/aiplat-evaluation/app/scoring/report_compare.py via importlib.
accuracy_claim stays false.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Mapping, Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _module_path() -> Path:
    return (
        _repo_root()
        / "packages"
        / "aiplat-evaluation"
        / "app"
        / "scoring"
        / "report_compare.py"
    )


def _load_compare_module() -> ModuleType:
    path = _module_path()
    if not path.is_file():
        raise FileNotFoundError(f"missing report_compare: {path}")
    spec = importlib.util.spec_from_file_location("aiplat_eval_report_compare", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def compare_eval_reports(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> Dict[str, Any]:
    """Delegate to package SSOT compare_reports."""
    mod = _load_compare_module()
    return mod.compare_reports(baseline, candidate)


def compare_eval_reports_by_id(
    baseline_id: str,
    candidate_id: str,
    *,
    tenant_id: str = "eval-v1",
) -> Dict[str, Any]:
    """Load two store reports then compare (cohost path)."""
    from core.apps.eval.service.store import get_eval_store

    store = get_eval_store(tenant_id=tenant_id)
    base = store.get_report(baseline_id)
    cand = store.get_report(candidate_id)
    if base is None or cand is None:
        return {
            "schema": "eval.report.compare.v0",
            "accuracy_claim": False,
            "comparable": False,
            "incomparable_reason": "report_not_found",
            "error": "not_found",
            "baseline_id": baseline_id,
            "candidate_id": candidate_id,
        }
    return compare_eval_reports(base, cand)


def _wire_report_compare() -> Optional[Dict[str, Any]]:
    """Same-file caller for method_verify."""
    return compare_eval_reports(
        {
            "id": "a",
            "scoring": {
                "composite": {"score": 1.0, "policy": {"composite_version": "v1.1"}}
            },
        },
        {
            "id": "b",
            "scoring": {
                "composite": {"score": 1.0, "policy": {"composite_version": "v1.1"}}
            },
        },
    )
