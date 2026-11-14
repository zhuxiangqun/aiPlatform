"""EVAL G2b pack status (facilitation).

Reads committed task pack + optional evidence aggregates under
packages/aiplat-evaluation/docs/a3/. Dual-human labels for 31–100 stay pending
until humans return sheets; UI/API only report facts.

Scheme A honesty:
- Product-level ``accuracy_claim`` is always false (not platform certification).
- ``scoped_accuracy_claim`` is true only when attestation accept_accuracy_claim=true
  AND the accuracy aggregate was closed with --claim-ready (scoped G2b only).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PRODUCT_CLAIM_REFUSE = "产品级 accuracy 未认证；仅 G2b scoped"


def _repo_root() -> Path:
    # aiPlat-core/core/apps/eval/service/g2b.py → workspace root
    return Path(__file__).resolve().parents[5]


def _pack_path() -> Path:
    return (
        _repo_root()
        / "packages"
        / "aiplat-evaluation"
        / "docs"
        / "a3"
        / "g2b_tasks.v0.json"
    )


def _evidence_dir() -> Path:
    return (
        _repo_root()
        / "packages"
        / "aiplat-evaluation"
        / "docs"
        / "a3"
        / "evidence"
    )


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _aggregate_scoped_flag(aggregate: Dict[str, Any]) -> bool:
    """Read scoped claim from aggregate; never treat product accuracy_claim as scoped.

    Args:
        aggregate: g2b_accuracy_aggregate JSON object.

    Returns:
        True when ``scoped_accuracy_claim`` is explicitly true.
    """
    return aggregate.get("scoped_accuracy_claim") is True


def _scoped_accuracy_claim(
    att: Optional[Dict[str, Any]] = None,
    acc: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
    """True only with owner accept + aggregate scoped_accuracy_claim from --claim-ready.

    Args:
        att: Optional attestation dict override.
        acc: Optional accuracy aggregate dict override.

    Returns:
        (scoped_claim, attestation, aggregate).
    """
    ev = _evidence_dir()
    attestation = att if att is not None else (_read_json(ev / "g2b_accuracy_claim_attestation.v1.json") or {})
    aggregate = acc if acc is not None else (_read_json(ev / "g2b_accuracy_aggregate.v1.json") or {})
    claim = (
        attestation.get("accept_accuracy_claim") is True
        and bool(str(attestation.get("product_owner") or "").strip())
        and _aggregate_scoped_flag(aggregate)
    )
    return bool(claim), attestation, aggregate


def g2b_pack_status(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """Facilitator-facing pack readiness (local files; scoped claim from evidence).

    Args:
        tenant_id: 租户 ID。
    """
    pack_path = _pack_path()
    pack = _read_json(pack_path) or {}
    tasks = pack.get("tasks") if isinstance(pack.get("tasks"), list) else []
    target_n = int(pack.get("target_n") or 0) or len(tasks)
    task_n = len(tasks)

    ev = _evidence_dir()
    kappa = _read_json(ev / "g2b_kappa_aggregate.v1.json") or {}
    claim, _att, acc = _scoped_accuracy_claim()

    kappa_n = len(kappa.get("task_ids") or []) if isinstance(kappa.get("task_ids"), list) else 0
    if not kappa_n and isinstance(kappa.get("n"), (int, float)):
        kappa_n = int(kappa["n"])
    acc_n = int(acc.get("n") or 0) if isinstance(acc.get("n"), (int, float)) else 0

    closeout_n = max(kappa_n, acc_n)
    pending_dual = max(0, target_n - closeout_n)
    pack_ready = task_n >= target_n and target_n > 0
    dual_human_complete = pending_dual == 0 and closeout_n >= target_n

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "schema": str(pack.get("schema") or "eval.g2b.task_pack.v0"),
        "pack_path": str(pack_path) if pack_path.is_file() else None,
        "task_count": task_n,
        "target_n": target_n,
        "pack_ready": pack_ready,
        "closeout_n": closeout_n,
        "kappa_n": kappa_n,
        "accuracy_aggregate_n": acc_n,
        "pending_dual_human": pending_dual,
        "dual_human_complete": dual_human_complete,
        "kappa_kind": kappa.get("kappa_kind") or "inter_annotator",
        # Aggregate uses inter_annotator_kappa; accept legacy "kappa" key too.
        "kappa": kappa.get("inter_annotator_kappa", kappa.get("kappa")),
        "accuracy_claim": False,
        "scoped_accuracy_claim": claim,
        "not_accuracy_certification": True,
        "claim_refuse_reason": _PRODUCT_CLAIM_REFUSE,
        "note": (
            (
                "G2b dual-human closeout complete; scoped_accuracy_claim=true "
                "(owner attestation + aggregate --claim-ready). "
                "product accuracy_claim=false; ≠ security cert / process_split / staging."
            )
            if dual_human_complete and claim
            else (
                (
                    "G2b dual-human closeout complete (n=closeout); "
                    "scoped observed pass_rate only; scoped_accuracy_claim stays false "
                    "until owner accept + --claim-ready aggregate; product accuracy_claim=false."
                )
                if dual_human_complete
                else (
                    "G2b pack status is facilitation-only. Pack n=100 ≠ closeout; "
                    "dual-human labels for unfinished ids still required; "
                    "product accuracy_claim=false; scoped_accuracy_claim=false."
                )
            )
        ),
        "runbook": "packages/aiplat-evaluation/docs/a3/G2B_N100.md",
        "families": _family_counts(tasks),
    }


def _family_counts(tasks: list) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for t in tasks:
        if not isinstance(t, dict):
            continue
        fam = str(t.get("family") or "unknown")
        out[fam] = out.get(fam, 0) + 1
    return out


# Protocol thresholds (eval L5 / G2b closeout docs) — disclosure only.
G2B_WILSON_LOWER_THRESHOLD = 0.70
G2B_PASS_RATE_TARGET = 0.80
L5_DEFAULT_MIN_SAMPLE_N = 100


def g2b_claim_unlock_checklist(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """AND-gates for scoped G2b accuracy_claim; claim mirrors attestation+aggregate.

    Args:
        tenant_id: 租户 ID。
    """
    status = g2b_pack_status(tenant_id=tenant_id)
    claim, att, acc = _scoped_accuracy_claim()
    arena = _read_json(_repo_root() / ".aiplat" / "eval_trust" / "arena_send_ready_v0.json") or {}
    next_rung = _read_json(_repo_root() / ".aiplat" / "eval_trust" / "next_rung_manifest.json") or {}
    arena_rung = next_rung.get("arena") if isinstance(next_rung.get("arena"), dict) else {}

    pass_rate = acc.get("pass_rate")
    wilson = acc.get("wilson_ci95") if isinstance(acc.get("wilson_ci95"), list) else []
    wilson_lo = float(wilson[0]) if len(wilson) >= 1 and wilson[0] is not None else None
    n = int(acc.get("n") or 0)
    gates = {
        "dual_human_complete": bool(status.get("dual_human_complete")),
        "section4_pass_rate_met": pass_rate is not None
        and float(pass_rate) >= G2B_PASS_RATE_TARGET,
        "section4_wilson_lo_met": wilson_lo is not None
        and wilson_lo >= G2B_WILSON_LOWER_THRESHOLD,
        "sample_n_met": n >= L5_DEFAULT_MIN_SAMPLE_N,
        "owner_accept_accuracy_claim": att.get("accept_accuracy_claim") is True,
        "arena_send_ready": bool(arena.get("send_ready") or arena_rung.get("send_ready")),
        "arena_qa_overall_pass": bool(
            arena_rung.get("qa_overall_pass") or arena.get("qa_overall_pass")
        ),
        "staging_evidence": False,
        "external_audit": False,
    }
    scoped_keys = (
        "dual_human_complete",
        "section4_pass_rate_met",
        "section4_wilson_lo_met",
        "sample_n_met",
        "owner_accept_accuracy_claim",
    )
    broader_keys = (
        "arena_send_ready",
        "arena_qa_overall_pass",
        "staging_evidence",
        "external_audit",
    )
    g2b_scoped_blockers = [k for k in scoped_keys if not gates[k]]
    broader_trust_blockers = [k for k in broader_keys if not gates[k]]
    return {
        "schema": "eval.g2b.claim_unlock_checklist.v0",
        "tenant_id": tenant_id,
        "accuracy_claim": False,
        "scoped_accuracy_claim": claim,
        "not_accuracy_certification": True,
        "claim_refuse_reason": _PRODUCT_CLAIM_REFUSE,
        "accept_accuracy_claim": bool(att.get("accept_accuracy_claim")),
        "gates": gates,
        "g2b_scoped_ready": len(g2b_scoped_blockers) == 0,
        "g2b_scoped_blockers": g2b_scoped_blockers,
        "broader_trust_blockers": broader_trust_blockers,
        "pass_rate": pass_rate,
        "wilson_ci95": wilson or None,
        "sample_n": n,
        "qa_resign_checklist": arena_rung.get("qa_resign_checklist")
        or arena.get("qa_resign_checklist"),
        "honesty": (
            "scoped_accuracy_claim mirrors attestation accept + aggregate "
            "--claim-ready; product accuracy_claim stays false. Arena QA / staging / "
            "external audit remain separate; ≠ process_split / security cert / "
            "length-smoke replacement."
        ),
    }


def g2b_l5_gap_disclosure(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """Distance-to-L5 / G2b threshold disclosure; scoped claim from evidence.

    Args:
        tenant_id: 租户 ID。
    """
    status = g2b_pack_status(tenant_id=tenant_id)
    claim, _att, acc = _scoped_accuracy_claim()
    pass_rate = acc.get("pass_rate")
    wilson = acc.get("wilson_ci95") if isinstance(acc.get("wilson_ci95"), list) else []
    wilson_lo = float(wilson[0]) if len(wilson) >= 1 and wilson[0] is not None else None
    wilson_hi = float(wilson[1]) if len(wilson) >= 2 and wilson[1] is not None else None
    n = int(acc.get("n") or status.get("closeout_n") or 0)
    unlock = g2b_claim_unlock_checklist(tenant_id=tenant_id)

    gaps: List[str] = []
    if not status.get("dual_human_complete"):
        gaps.append(f"pending_dual_human:{status.get('pending_dual_human')}")
    if pass_rate is None:
        gaps.append("pass_rate_missing")
    elif float(pass_rate) < G2B_PASS_RATE_TARGET:
        gaps.append(f"pass_rate_below_target:{pass_rate}<{G2B_PASS_RATE_TARGET}")
    if wilson_lo is None:
        gaps.append("wilson_lower_missing")
    elif wilson_lo < G2B_WILSON_LOWER_THRESHOLD:
        gaps.append(
            f"wilson_lower_below_threshold:{wilson_lo}<{G2B_WILSON_LOWER_THRESHOLD}"
        )
    if n < L5_DEFAULT_MIN_SAMPLE_N:
        gaps.append(f"sample_n_below_l5:{n}<{L5_DEFAULT_MIN_SAMPLE_N}")
    if unlock.get("g2b_scoped_blockers"):
        gaps.append(
            "claim_unlock_blockers:" + ",".join(unlock["g2b_scoped_blockers"])
        )

    # Broader L5 claims_gate stays unauthorized; G2b scoped claim is separate.
    from core.apps.eval.service.claims_gate import evaluate_l5_claims_gate

    gate = evaluate_l5_claims_gate(
        {
            "object_type": "agent",
            "object_id": "g2b_pack",
            "object_version": "v0",
            "runtime_tier": "workspace_execute",
            "plan_id": "g2b",
            "set_ids": ["g2b"],
            "oracle_types": ["human_adjudicated"],
            "dimensions": ["task_result"],
            "sample_n": n,
            "has_run_evidence": n > 0,
            "untested_applicable_n": int(status.get("pending_dual_human") or 0),
            "runtime_claim": False,
            "fixture_only": False,
            "human_review": bool(status.get("dual_human_complete")),
            "min_sample_n": L5_DEFAULT_MIN_SAMPLE_N,
        },
        explicit_authorize=False,
    )

    section4_met = (
        pass_rate is not None
        and float(pass_rate) >= G2B_PASS_RATE_TARGET
        and wilson_lo is not None
        and wilson_lo >= G2B_WILSON_LOWER_THRESHOLD
        and n >= L5_DEFAULT_MIN_SAMPLE_N
    )
    if claim and unlock.get("g2b_scoped_ready"):
        distance = "g2b_scoped_accuracy_claim_accepted"
    elif section4_met and unlock.get("g2b_scoped_blockers") == [
        "owner_accept_accuracy_claim"
    ]:
        distance = "awaiting_owner_accept_attestation"
    elif not gaps:
        distance = "ready_for_scoped_owner_review"
    else:
        distance = "thresholds_not_met"
    return {
        "schema": "eval.g2b_l5_gap.v1",
        "ok": True,
        "tenant_id": tenant_id,
        "pack_status": status,
        "pass_rate": pass_rate,
        "wilson_ci95": [wilson_lo, wilson_hi],
        "wilson_lower_threshold": G2B_WILSON_LOWER_THRESHOLD,
        "pass_rate_target": G2B_PASS_RATE_TARGET,
        "sample_n": n,
        "l5_default_min_sample_n": L5_DEFAULT_MIN_SAMPLE_N,
        "gaps": gaps,
        "distance_summary": distance,
        "claim_unlock": unlock,
        "claims_gate": gate,
        "accuracy_claim": False,
        "scoped_accuracy_claim": claim,
        "not_accuracy_certification": True,
        "claim_refuse_reason": _PRODUCT_CLAIM_REFUSE,
        "explicit_authorize": claim,
        "note": (
            "scoped_accuracy_claim from attestation + aggregate --claim-ready; "
            "product accuracy_claim=false. Broader L5 claims_gate stays unauthorized; "
            "≠ security cert / process_split / staging / length-smoke replacement."
        ),
    }
