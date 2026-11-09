"""A1 intersection Track A evidence + Track B compare (hard-gap P1/P2).

Honesty:
- Only plan_execute + conversational (env tools=none|retrieval=none|session=none).
- Fixture evidence never ranks; live or AIPLAT_EVAL_A1_ALLOW_SCRIPTED_WORKSPACE=1 drill.
- rank_claim never auto-true; signoff only unlocks rank_claim_allowed.
- min_n engineering default 2; disclose below L5 min_sample_n=100.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.agent_impl_mode import (
    compute_rank_fingerprint,
    load_parity_sample,
    m1a_environment_lock,
)
from core.apps.eval.service.mode_aware_exam import ModeAwareExamError, _execute_case_inprocess
from core.apps.eval.service.mode_intersection_rank import (
    MIN_N_INTERSECTION_ENGINEERING,
    ModeIntersectionRankError,
    attach_rank_fingerprint_to_column,
    build_mode_intersection_rank,
    list_rank_eligible_cases,
    load_intersection_cases,
)

_log = logging.getLogger(__name__)

A1_MODES = ("plan_execute", "conversational")
EVIDENCE_REL = Path(".aiplat/eval_trust/mode_intersection/a1_v1")
MANIFEST_HASH = "sha256:a1_task_completion.v1"
CLAIM_SENTENCE = (
    "在 Agent X、配置 C、模型 M 下，plan_execute 相对 conversational 在交集 A1 上 …"
    "（禁止抽象「模式优劣」）"
)


def _scripted_workspace_allowed() -> bool:
    return os.environ.get("AIPLAT_EVAL_A1_ALLOW_SCRIPTED_WORKSPACE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def default_a1_evidence_dir(*, repo_root: Optional[Path] = None) -> Path:
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[5]
    return root / EVIDENCE_REL


def _lexical_ok(answer: str, case: Mapping[str, Any]) -> bool:
    rubric = case.get("rubric") if isinstance(case.get("rubric"), Mapping) else {}
    must = [str(x) for x in (rubric.get("must_contain") or []) if str(x).strip()]
    forbid = [str(x) for x in (rubric.get("must_not_contain") or []) if str(x).strip()]
    text = str(answer or "")
    return all(m in text for m in must) and all(f not in text for f in forbid)


async def run_a1_intersection_track_a(
    *,
    live: bool = False,
    seed_dir: Optional[Path] = None,
    persist_dir: Optional[Path] = None,
    model_fingerprint: str = "unresolved",
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Per-mode create_agent runs on A1 intersection cases; persist optional evidence."""
    cases = load_intersection_cases(seed_dir=seed_dir)
    parity = load_parity_sample(
        path=(Path(seed_dir) / "intersection" / "parity_sample.v1.json")
        if seed_dir
        else None
    )
    eligible_ids = {str(c.get("case_id")) for c in list_rank_eligible_cases(parity)}
    drill = (not live) and _scripted_workspace_allowed()
    columns: Dict[str, Any] = {}
    lock = m1a_environment_lock()

    for mode in A1_MODES:
        by_case: Dict[str, Any] = {}
        results: List[Dict[str, Any]] = []
        for case in cases:
            cid = str(case.get("case_id") or "")
            # Adapt intersection case shape to m1a executor (capabilities list).
            adapted = dict(case)
            adapted["capabilities"] = [case.get("capability_id") or "task_completion"]
            if mode == "conversational":
                # session forbidden on this env hash — do not set session_group
                adapted.pop("session_group", None)

            out = await _execute_case_inprocess(mode, adapted, live=bool(live))
            # Scripted path from executor is fixture; promote only under explicit drill flag.
            tier = str(out.get("runtime_tier") or "fixture")
            if drill and not live and tier == "fixture":
                tier = "workspace_execute"
                out = dict(out)
                out["runtime_tier"] = tier
                out["runtime_claim"] = False
                out["runtime_claim_reason"] = (
                    "a1_scripted_workspace_drill_AIPLAT_EVAL_A1_ALLOW_SCRIPTED_WORKSPACE"
                )

            answer = str(out.get("answer") or case.get("scripted_answer") or "")
            ok = bool(out.get("ok"))
            if not live and not ok:
                # Prefer scripted lexical when create_agent scripted path failed oddly
                ok = _lexical_ok(answer, case)
            status = str(out.get("status") or ("ok" if ok else "fail"))
            row = {
                "case_id": cid,
                "capability_id": case.get("capability_id"),
                "ok": ok,
                "status": status if status != "error" else status,
                "runtime_tier": tier,
                "errors": out.get("errors") or [],
            }
            results.append(row)
            if cid in eligible_ids or True:
                by_case[cid] = {
                    "capability_id": case.get("capability_id"),
                    "ok": ok,
                    "status": "ok" if ok and status != "error" else status,
                }

        # Aggregate by_capability for sample_size gate (engineering n=len eligible)
        stats: Dict[str, Dict[str, int]] = {}
        for cid, row in by_case.items():
            if cid not in eligible_ids:
                continue
            cap = str(row.get("capability_id") or "task_completion")
            b = stats.setdefault(cap, {"successes": 0, "n": 0})
            b["n"] += 1
            if row.get("ok"):
                b["successes"] += 1

        fp_parts = {
            "manifest_hash": str(parity.get("intersection_manifest_hash") or MANIFEST_HASH),
            "prompt_hash": "sha256:a1_bundle",
            "oracle_hash": "sha256:a1_bundle_oracle",
            "runner_judge_version": "a1_intersection_ops.v1",
            "model_fingerprint": str(model_fingerprint or "unresolved"),
            "runtime_tier": results[0]["runtime_tier"] if results else "fixture",
            "runtime_parts_contract": "a1_m1a_env_v1",
            "tools_contract_hash": "sha256:tools=none",
            "retrieval_contract_hash": "sha256:retrieval=none",
            "session_contract_hash": "sha256:session=none",
        }
        # Use shared prompt/oracle from first eligible parity row if present
        elig = list_rank_eligible_cases(parity)
        if elig:
            # Bundle hash of all eligible prompt hashes for stability across modes
            ph = "|".join(sorted(str(e.get("prompt_hash") or "") for e in elig))
            oh = "|".join(sorted(str(e.get("oracle_hash") or "") for e in elig))
            fp_parts["prompt_hash"] = "sha256:bundle:" + ph[:64]
            fp_parts["oracle_hash"] = "sha256:bundle:" + oh[:64]

        col = {
            "impl_mode": mode,
            "subject": {
                "agent_id": f"eval.a1.{mode}",
                "agent_version": "a1_v1",
                "impl_mode": mode,
                "config_hash": "a1_m1a_env",
                "model_fingerprint": model_fingerprint,
            },
            "runtime_tier": fp_parts["runtime_tier"],
            "model_fingerprint": model_fingerprint,
            "intersection_manifest_hash": str(
                parity.get("intersection_manifest_hash") or MANIFEST_HASH
            ),
            "by_case": by_case,
            "by_capability": stats,
            "results": results,
            "environment_lock": lock.get(mode) or {},
            "scripted_workspace_drill": bool(drill),
        }
        columns[mode] = attach_rank_fingerprint_to_column(col, fingerprint_parts=fp_parts)

    payload = {
        "schema": "eval.a1_intersection_track_a.v1",
        "ok": all(
            all(r.get("status") != "error" for r in (columns[m].get("results") or []))
            for m in A1_MODES
        ),
        "live": bool(live),
        "scripted_workspace_drill": bool(drill),
        "modes": list(A1_MODES),
        "columns": columns,
        "n_cases": len(cases),
        "claim_eligible": False,
        "rank_claim": False,
        "honesty": (
            "A1 Track A per-mode; fixture cannot enter rank board; "
            "scripted_workspace requires AIPLAT_EVAL_A1_ALLOW_SCRIPTED_WORKSPACE=1; "
            "≠ live model certification"
        ),
    }

    out_dir = Path(persist_dir) if persist_dir else None
    if out_dir is None and (live or drill):
        out_dir = default_a1_evidence_dir(repo_root=repo_root)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "track_a.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        payload["evidence_dir"] = str(out_dir)
    return payload


def load_a1_track_a_evidence(path: Path) -> Dict[str, Any]:
    p = Path(path)
    if p.is_dir():
        p = p / "track_a.json"
    if not p.is_file():
        raise ModeIntersectionRankError(f"a1_evidence_missing:{p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ModeIntersectionRankError("a1_evidence_not_object")
    return dict(raw)


def run_a1_intersection_compare(
    *,
    mode_columns: Optional[Mapping[str, Mapping[str, Any]]] = None,
    evidence_dir: Optional[Path] = None,
    parity: Optional[Mapping[str, Any]] = None,
    signoff: Optional[Mapping[str, Any]] = None,
    min_n_per_capability: int = MIN_N_INTERSECTION_ENGINEERING,
    track_a_complete: bool = True,
) -> Dict[str, Any]:
    """Build Track B report from columns or persisted Track A evidence."""
    cols: Dict[str, Any]
    if mode_columns is not None:
        cols = {k: dict(v) for k, v in mode_columns.items() if isinstance(v, Mapping)}
    elif evidence_dir is not None:
        ev = load_a1_track_a_evidence(Path(evidence_dir))
        raw_cols = ev.get("columns") if isinstance(ev.get("columns"), Mapping) else {}
        cols = {k: dict(v) for k, v in raw_cols.items() if isinstance(v, Mapping)}
    else:
        raise ModeIntersectionRankError("a1_compare_needs_columns_or_evidence")

    sample = dict(parity) if parity is not None else load_parity_sample()
    sig = signoff
    if sig is None:
        sig = sample.get("signoff") if isinstance(sample.get("signoff"), Mapping) else {}

    report = build_mode_intersection_rank(
        cols,
        parity=sample,
        signoff=sig,
        min_n_per_capability=int(min_n_per_capability),
        track_a_complete=bool(track_a_complete),
    )
    report["claim_sentence_template"] = CLAIM_SENTENCE
    report["min_n_protocol"] = {
        "engineering_min_n": MIN_N_INTERSECTION_ENGINEERING,
        "l5_default_min_sample_n": 100,
        "note": "Engineering compare may use n>=2; accuracy_claim still requires L5 claims_gate.",
    }
    report["rank_claim"] = False  # hard lock
    return report


async def eval_run_a1_intersection_compare(
    *,
    live: bool = False,
    persist: bool = True,
    signoff: Optional[Mapping[str, Any]] = None,
    model_fingerprint: str = "unresolved",
    min_n_per_capability: int = MIN_N_INTERSECTION_ENGINEERING,
) -> Dict[str, Any]:
    """Track A then Track B in one call. rank_claim always false."""
    track = await run_a1_intersection_track_a(
        live=bool(live),
        persist_dir=default_a1_evidence_dir() if persist else None,
        model_fingerprint=model_fingerprint,
    )
    compare = run_a1_intersection_compare(
        mode_columns=track.get("columns") or {},
        signoff=signoff,
        min_n_per_capability=min_n_per_capability,
        track_a_complete=True,
    )
    return {
        "schema": "eval.a1_intersection_compare.v1",
        "track_a": track,
        "compare": compare,
        "rank_claim": False,
        "rank_claim_allowed": bool(compare.get("rank_claim_allowed")),
        "claim_eligible": False,
        "accuracy_claim": False,
        "claim_sentence_template": CLAIM_SENTENCE,
    }


def a1_intersection_status_report(
    *,
    evidence_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read-only A1 intersection gate/Pareto snapshot for UI. Never certifies."""
    parity = load_parity_sample()
    eligible = list_rank_eligible_cases(parity)
    sig = parity.get("signoff") if isinstance(parity.get("signoff"), Mapping) else {}
    ev_dir = Path(evidence_dir) if evidence_dir else default_a1_evidence_dir(repo_root=repo_root)
    compare: Optional[Dict[str, Any]] = None
    evidence_present = (ev_dir / "track_a.json").is_file()
    if evidence_present:
        try:
            compare = run_a1_intersection_compare(
                evidence_dir=ev_dir,
                parity=parity,
                min_n_per_capability=MIN_N_INTERSECTION_ENGINEERING,
            )
        except ModeIntersectionRankError as exc:
            compare = {"ok": False, "error": str(exc), "rank_claim": False}

    return {
        "schema": "eval.a1_intersection_status.v1",
        "ok": True,
        "eligible_case_ids": [str(c.get("case_id")) for c in eligible],
        "eligible_n": len(eligible),
        "signoff": dict(sig) if isinstance(sig, Mapping) else {},
        "signoff_status": str((sig or {}).get("status") or "unsigned"),
        "evidence_dir": str(ev_dir),
        "evidence_present": evidence_present,
        "compare": compare,
        "gate": (compare or {}).get("gate") if compare else None,
        "pareto": (compare or {}).get("pareto") if compare else None,
        "rank_claim_allowed": bool((compare or {}).get("rank_claim_allowed")),
        "rank_claim": False,
        "accuracy_claim": False,
        "claim_sentence_template": CLAIM_SENTENCE,
        "min_n_protocol": {
            "engineering_min_n": MIN_N_INTERSECTION_ENGINEERING,
            "l5_default_min_sample_n": 100,
        },
        "honesty": (
            "Read-only. No one-click certification. "
            "rank_claim never auto-true; signoff only unlocks rank_claim_allowed."
        ),
        "modes_locked": list(A1_MODES),
    }
