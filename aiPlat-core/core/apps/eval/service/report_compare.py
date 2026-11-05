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


def _scoring_module_path(name: str) -> Path:
    return (
        _repo_root()
        / "packages"
        / "aiplat-evaluation"
        / "app"
        / "scoring"
        / name
    )


def _load_scoring_module(filename: str, mod_name: str) -> ModuleType:
    path = _scoring_module_path(filename)
    if not path.is_file():
        raise FileNotFoundError(f"missing scoring module: {path}")
    # Package modules import `app.*`; ensure package root is on sys.path.
    import sys

    pkg_root = str(_repo_root() / "packages" / "aiplat-evaluation")
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_compare_module() -> ModuleType:
    return _load_scoring_module("report_compare.py", "aiplat_eval_report_compare")


def stamp_eval_report_metrics(
    metrics: Optional[Mapping[str, Any]] = None,
    *,
    scoring: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Delegate to package ensure_report_scoring (P1b stamp)."""
    mod = _load_scoring_module("report_stamp.py", "aiplat_eval_report_stamp")
    return mod.ensure_report_scoring(metrics, scoring=scoring)


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
    _ = stamp_eval_report_metrics({"exact_match": 1.0})
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
