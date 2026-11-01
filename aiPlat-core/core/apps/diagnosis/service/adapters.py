"""Read-only evidence adapters (aiPlat / Pi / FDE / Evaluation / Ontology) + fixture pack."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_LOG = logging.getLogger(__name__)

_FIXTURE_ROOT_CANDIDATES = (
    Path(__file__).resolve().parents[5] / "packages" / "aiplat-diagnosis" / "fixtures",
    Path(__file__).resolve().parents[4] / "packages" / "aiplat-diagnosis" / "fixtures",
)

_ADAPTER_MODES = {
    "aiplat": "read_only",
    "pi": "read_only",
    "fde": "read_only",
    "evaluation": "read_only",
    "ontology": "read_only",
}


def fixture_root() -> Path:
    for p in _FIXTURE_ROOT_CANDIDATES:
        if p.is_dir():
            return p
    cwd = Path.cwd() / "packages" / "aiplat-diagnosis" / "fixtures"
    return cwd


def resolve_fixture_id(subject_ref: str) -> Optional[str]:
    s = (subject_ref or "").strip()
    if not s:
        return None
    for prefix in ("fixture:", "dx.fixture:", "case:"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    if s.startswith("dx."):
        return s
    root = fixture_root()
    if (root / s).is_dir():
        return s
    return None


def load_fixture(case_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    d = fixture_root() / case_id
    if not d.is_dir():
        raise FileNotFoundError(f"fixture_not_found:{case_id}")
    evidence = json.loads((d / "evidence.json").read_text(encoding="utf-8"))
    expected = json.loads((d / "expected.json").read_text(encoding="utf-8"))
    return evidence, expected


def read_evaluation_refs(
    *,
    subject_ref: str,
    baseline_ref: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """C2: deeper Evaluation adapter — CoreFacade read-only snapshot (no writes)."""
    captured = "1970-01-01T00:00:00+00:00"
    meta: Dict[str, Any] = {
        "adapter": "evaluation",
        "baseline_ref": baseline_ref,
        "path": "core_facade.eval_g2a_status",
    }
    try:
        from core.api.core_facade import eval_g2a_status

        st = eval_g2a_status(tenant_id="eval-v1") or {}
        meta.update(
            {
                "locked": bool(st.get("locked") or st.get("v0_locked")),
                "accuracy_claim": bool(st.get("accuracy_claim")),
                "gate_claim": bool(st.get("gate_claim")),
                "status_keys": sorted(list(st.keys()))[:12],
            }
        )
        freshness = "fresh" if st else "unknown"
    except Exception as e:  # noqa: BLE001 — adapter must not fail collect
        _LOG.warning("diagnosis evaluation adapter failed: %s", e)
        meta["error"] = type(e).__name__
        freshness = "unknown"
    return [
        {
            "id": "e-eval-live",
            "source": "evaluation",
            "kind": "eval_report",
            "ref": f"evaluation://g2a/{subject_ref}",
            "captured_at": captured,
            "freshness": freshness,
            "meta": meta,
        }
    ]


def read_ontology_refs(*, subject_ref: str) -> List[Dict[str, Any]]:
    """C2: Ontology adapter — healthz/domain count only (read_only)."""
    captured = "1970-01-01T00:00:00+00:00"
    meta: Dict[str, Any] = {
        "adapter": "ontology",
        "path": "core_facade.ontology_healthz_payload",
        "mode": "read_only",
    }
    try:
        from core.api.core_facade import ontology_healthz_payload

        hz = ontology_healthz_payload(mode="read_only") or {}
        meta.update(
            {
                "status": hz.get("status"),
                "domains": hz.get("domains"),
                "version": hz.get("version"),
            }
        )
        freshness = "fresh" if hz else "unknown"
    except Exception as e:  # noqa: BLE001
        _LOG.warning("diagnosis ontology adapter failed: %s", e)
        meta["error"] = type(e).__name__
        freshness = "unknown"
    return [
        {
            "id": "e-ontology-health",
            "source": "ontology",
            "kind": "ontology_health",
            "ref": f"ontology://healthz/{subject_ref}",
            "captured_at": captured,
            "freshness": freshness,
            "meta": meta,
        }
    ]


def collect_from_fixture(case_id: str) -> Dict[str, Any]:
    evidence_doc, expected = load_fixture(case_id)
    refs = list(evidence_doc.get("evidence") or [])
    return {
        "source": "fixture",
        "fixture_id": case_id,
        "evidence": refs,
        "payload": evidence_doc.get("payload") or {},
        "expected": expected,
        "adapters": dict(_ADAPTER_MODES),
    }


def collect_live_stubs(
    *,
    scenario: str,
    subject_ref: str,
    baseline_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """Read-only refs when no fixture pack match — never invents root cause."""
    captured = "1970-01-01T00:00:00+00:00"
    refs: List[Dict[str, Any]] = [
        {
            "id": "e-aiplat-subject",
            "source": "aiplat",
            "kind": "run",
            "ref": f"aiplat://subject/{subject_ref}",
            "captured_at": captured,
            "freshness": "unknown",
            "meta": {"adapter": "aiplat", "note": "live collect stub; no source write"},
        },
        {
            "id": "e-pi-health",
            "source": "pi",
            "kind": "healthz",
            "ref": "pi://healthz",
            "captured_at": captured,
            "freshness": "unknown",
            "meta": {"adapter": "pi"},
        },
        {
            "id": "e-fde",
            "source": "fde",
            "kind": "fde_evidence",
            "ref": f"fde://subject/{subject_ref}",
            "captured_at": captured,
            "freshness": "unknown",
            "meta": {"adapter": "fde"},
        },
    ]
    # C2: prefer live Evaluation / Ontology snapshots over static stubs
    refs.extend(
        read_evaluation_refs(subject_ref=subject_ref, baseline_ref=baseline_ref)
    )
    refs.extend(read_ontology_refs(subject_ref=subject_ref))
    return {
        "source": "live_stub",
        "fixture_id": None,
        "evidence": refs,
        "payload": {
            "note": "adapters returned refs only; insufficient for confirmed root cause",
            "scenario": scenario,
        },
        "expected": {
            "gold_root_cause": "insufficient_evidence",
            "expect_unknown": True,
            "expect_stale": False,
        },
        "adapters": dict(_ADAPTER_MODES),
    }


def collect_evidence(
    *,
    scenario: str,
    subject_ref: str,
    baseline_ref: Optional[str] = None,
) -> Dict[str, Any]:
    fid = resolve_fixture_id(subject_ref)
    if fid:
        return collect_from_fixture(fid)
    return collect_live_stubs(
        scenario=scenario, subject_ref=subject_ref, baseline_ref=baseline_ref
    )
