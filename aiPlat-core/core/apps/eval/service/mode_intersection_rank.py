"""M3 intersection rank — rank gate + Wilson CI + Pareto (no default winner).

Honesty (eval-agent-impl-mode-exam.md):
- Compare only on rank_eligible intersection cases with matching rank_fingerprint.
- Fixture tiers never enter the board.
- rank_claim never auto-emitted from a completed run; needs gate + three-party signoff.
- unknown must not count as 0 or pass.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.apps.eval.service.agent_impl_mode import (
    AgentImplModeError,
    compute_rank_fingerprint,
    load_parity_sample,
)
from core.apps.eval.service.capability_case_bank import default_seed_dir

RANK_SCHEMA = "eval.mode_intersection_rank.v1"
GATE_SCHEMA = "eval.mode_rank_gate.v1"
CI_METHOD = "wilson"
CI_VERSION = "wilson_z1.96_v1"
MIN_N_DEFAULT = 5
# Engineering intersection compare (A1 hard-gap); L5 accuracy still uses claims_gate min_sample_n=100.
MIN_N_INTERSECTION_ENGINEERING = 2
A1_CASES_REL = "intersection/cases/a1_task_completion.v1.json"


class ModeIntersectionRankError(ValueError):
    """Fail-closed intersection / rank gate error."""


def wilson_score_ci(
    successes: int,
    n: int,
    *,
    z: float = 1.96,
) -> Tuple[Optional[float], Optional[float]]:
    """Wilson score interval (same formula as packages g2b helper; local copy)."""
    if n <= 0:
        return None, None
    successes = max(0, min(int(successes), int(n)))
    n = int(n)
    p = successes / float(n)
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = p + z2 / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)
    lo = (centre - margin) / denom
    hi = (centre + margin) / denom
    return round(max(0.0, lo), 4), round(min(1.0, hi), 4)


def dominance_relation(
    a_lo: Optional[float],
    a_hi: Optional[float],
    b_lo: Optional[float],
    b_hi: Optional[float],
) -> str:
    """A dominates B iff A.ci_lower >= B.ci_upper; else undetermined (incl. tie)."""
    if a_lo is None or a_hi is None or b_lo is None or b_hi is None:
        return "undetermined"
    if a_lo >= b_hi:
        return "dominates"
    if b_lo >= a_hi:
        return "dominated"
    # Overlapping CIs — including equal point rates
    if a_lo == b_lo and a_hi == b_hi:
        return "tie"
    return "undetermined"


def pareto_frontier(
    mode_vectors: Mapping[str, Mapping[str, float]],
) -> Dict[str, Any]:
    """Pareto on per-capability rates (higher better). No single winner by default.

    ``mode_vectors``: mode -> {capability_id: rate in [0,1]}
    """
    modes = [m for m, v in mode_vectors.items() if isinstance(v, Mapping)]
    caps: List[str] = sorted(
        {c for v in mode_vectors.values() if isinstance(v, Mapping) for c in v.keys()}
    )
    dominated: Dict[str, List[str]] = {m: [] for m in modes}
    for a in modes:
        va = mode_vectors[a]
        for b in modes:
            if a == b:
                continue
            vb = mode_vectors[b]
            # a dominated by b if b >= a on all caps and > on at least one
            ge_all = True
            gt_one = False
            for c in caps:
                ra = float(va.get(c, 0.0))
                rb = float(vb.get(c, 0.0))
                if rb < ra:
                    ge_all = False
                    break
                if rb > ra:
                    gt_one = True
            if ge_all and gt_one:
                dominated[a].append(b)

    frontier = [m for m in modes if not dominated[m]]
    return {
        "schema": "eval.pareto_frontier.v1",
        "capabilities": caps,
        "frontier": frontier,
        "dominated_by": dominated,
        "single_winner": None,
        "note": "Pareto on capability vectors; never emit macro-average champion",
    }


def list_rank_eligible_cases(
    parity: Mapping[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    sample = dict(parity) if parity is not None else load_parity_sample()
    out: List[Dict[str, Any]] = []
    for c in list(sample.get("cases") or []):
        if not isinstance(c, Mapping):
            continue
        if not bool(c.get("rank_eligible")):
            continue
        if str(c.get("parity_status") or "") == "blocked_trace_parity":
            continue
        if str(c.get("parity_status") or "") != "passed":
            continue
        out.append(dict(c))
    return out


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_prompt_hash(prompt: str) -> str:
    return _sha256_text(str(prompt or ""))


def compute_oracle_hash(case: Mapping[str, Any]) -> str:
    blob = {
        "rubric": case.get("rubric"),
        "oracle": case.get("oracle"),
        "scripted_answer": case.get("scripted_answer"),
    }
    return _sha256_text(json.dumps(blob, sort_keys=True, ensure_ascii=False))


def compute_env_contract_hash(env_contract: str) -> str:
    return _sha256_text(str(env_contract or ""))


def verify_intersection_case_hashes(case: Mapping[str, Any]) -> List[str]:
    """Fail-closed: body must match declared prompt/oracle/env hashes."""
    errors: List[str] = []
    ph = str(case.get("prompt_hash") or "")
    oh = str(case.get("oracle_hash") or "")
    eh = str(case.get("env_contract_hash") or "")
    if "placeholder" in ph or "pending" in ph:
        errors.append("prompt_hash_placeholder")
    if "placeholder" in oh or "pending" in oh:
        errors.append("oracle_hash_placeholder")
    if ph and ph != compute_prompt_hash(str(case.get("prompt") or "")):
        errors.append("prompt_hash_mismatch")
    if oh and oh != compute_oracle_hash(case):
        errors.append("oracle_hash_mismatch")
    env = str(case.get("env_contract") or "")
    if env and eh and eh != compute_env_contract_hash(env):
        errors.append("env_contract_hash_mismatch")
    return errors


def load_intersection_cases(
    *,
    seed_dir: Optional[Path] = None,
    rel_path: str = A1_CASES_REL,
    verify_hashes: bool = True,
) -> List[Dict[str, Any]]:
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    path = root / rel_path
    if not path.is_file():
        raise ModeIntersectionRankError(f"intersection_cases_missing:{path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ModeIntersectionRankError("intersection_cases_not_object")
    cases = raw.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ModeIntersectionRankError("intersection_cases_empty")
    out: List[Dict[str, Any]] = []
    for c in cases:
        if not isinstance(c, Mapping):
            continue
        row = dict(c)
        if verify_hashes:
            errs = verify_intersection_case_hashes(row)
            if errs:
                raise ModeIntersectionRankError(
                    f"intersection_hash_fail:{row.get('case_id')}:{','.join(errs)}"
                )
        out.append(row)
    return out


def evaluate_rank_gate(
    *,
    mode_columns: Mapping[str, Mapping[str, Any]],
    parity: Mapping[str, Any] | None = None,
    signoff: Mapping[str, Any] | None = None,
    min_n_per_capability: int = MIN_N_DEFAULT,
    track_a_complete: bool = True,
) -> Dict[str, Any]:
    """Full M3 rank gate. Fail closed → rank_claim stays false."""
    sample = dict(parity) if parity is not None else load_parity_sample()
    sig = dict(signoff) if signoff is not None else dict(sample.get("signoff") or {})
    checks: List[Dict[str, Any]] = []
    blockers: List[str] = []

    def _add(cid: str, ok: bool, detail: str = "") -> None:
        checks.append({"id": cid, "ok": ok, "detail": detail})
        if not ok:
            blockers.append(cid if not detail else f"{cid}:{detail}")

    _add("track_a_complete", bool(track_a_complete))

    modes = [m for m, col in mode_columns.items() if isinstance(col, Mapping)]
    _add("modes_present", len(modes) >= 2, f"n={len(modes)}")

    eligible = list_rank_eligible_cases(sample)
    _add("rank_eligible_cases", bool(eligible), f"n={len(eligible)}")

    # No fixture on board
    tiers = {
        str((mode_columns[m] or {}).get("runtime_tier") or "")
        for m in modes
    }
    _add("no_fixture_on_board", "fixture" not in tiers and all(tiers), f"tiers={sorted(tiers)}")
    _add(
        "same_runtime_tier",
        len(tiers) == 1,
        f"tiers={sorted(tiers)}",
    )

    fps = {
        str((mode_columns[m] or {}).get("model_fingerprint") or "")
        for m in modes
    }
    _add("same_model_fingerprint", len(fps) == 1 and "" not in fps, f"fps={sorted(fps)}")

    rfps = {
        str((mode_columns[m] or {}).get("rank_fingerprint") or "")
        for m in modes
    }
    _add(
        "rank_fingerprint_consistent",
        len(rfps) == 1 and "" not in rfps and all(
            bool((mode_columns[m] or {}).get("rank_fingerprint_ok", True)) for m in modes
        ),
        f"n_distinct={len(rfps)}",
    )

    # Completion: every eligible case must appear with status ok|fail (not error/unknown)
    completion_ok = True
    unknown_as_pass = False
    sample_ok = True
    if eligible and modes:
        for m in modes:
            col = mode_columns[m] or {}
            by_case = col.get("by_case") if isinstance(col.get("by_case"), Mapping) else {}
            by_cap = col.get("by_capability") if isinstance(col.get("by_capability"), Mapping) else {}
            for ec in eligible:
                cid = str(ec.get("case_id") or "")
                row = by_case.get(cid) if isinstance(by_case.get(cid), Mapping) else None
                if row is None:
                    completion_ok = False
                    continue
                st = str(row.get("status") or "")
                if st in {"error", "unknown", "skipped"}:
                    completion_ok = False
                if row.get("counted_as") == "unknown_as_pass" or row.get("unknown_as_zero"):
                    unknown_as_pass = True
            for cap, stats in by_cap.items():
                if not isinstance(stats, Mapping):
                    continue
                n = int(stats.get("n") or 0)
                if n < int(min_n_per_capability):
                    sample_ok = False
    else:
        completion_ok = False
        sample_ok = False

    _add("completion_rate_100", completion_ok)
    _add("unknown_not_as_pass_or_zero", not unknown_as_pass)
    _add(
        "sample_size_ci",
        sample_ok and bool(eligible),
        f"min_n={min_n_per_capability}",
    )

    # Oracle / env hashes present on eligible cases
    hash_ok = all(
        str(c.get("prompt_hash") or "")
        and str(c.get("oracle_hash") or "")
        and str(c.get("env_contract_hash") or "")
        for c in eligible
    ) if eligible else False
    _add("oracle_env_hashes", hash_ok)

    # Same intersection manifest id (optional field)
    manifests = {
        str((mode_columns[m] or {}).get("intersection_manifest_hash") or "")
        for m in modes
    }
    _add(
        "same_intersection_manifest",
        (len(manifests) == 1 and "" not in manifests) or not modes,
        f"manifests={sorted(manifests)}",
    )

    signed = (
        str(sig.get("method_owner") or "").strip()
        and str(sig.get("engineering") or "").strip()
        and str(sig.get("independent_qa") or "").strip()
        and str(sig.get("status") or "").strip().lower() in {"signed", "approved"}
    )
    _add("three_party_signoff", bool(signed), str(sig.get("status") or "unsigned"))

    gate_ok = not blockers
    return {
        "schema": GATE_SCHEMA,
        "ok": gate_ok,
        "checks": checks,
        "blockers": blockers,
        "rank_claim_allowed": False if not gate_ok else bool(signed),
        "ci_method": CI_METHOD,
        "ci_version": CI_VERSION,
        "eligible_case_ids": [str(c.get("case_id")) for c in eligible],
        "signoff": sig,
        "honesty": (
            "rank_claim requires all gate checks + three-party signoff; "
            "never auto from run completion"
        ),
    }


def _capability_stats_from_column(
    col: Mapping[str, Any],
    eligible_ids: Sequence[str],
) -> Dict[str, Dict[str, int]]:
    """Per-capability successes/n. Prefer explicit by_capability; else aggregate by_case."""
    if isinstance(col.get("by_capability"), Mapping) and col.get("by_capability"):
        stats: Dict[str, Dict[str, int]] = {}
        for cap, raw in col["by_capability"].items():
            if isinstance(raw, Mapping):
                stats[str(cap)] = {
                    "successes": int(raw.get("successes") or 0),
                    "n": int(raw.get("n") or 0),
                }
        return stats
    by_case = col.get("by_case") if isinstance(col.get("by_case"), Mapping) else {}
    stats = {}
    for cid in eligible_ids:
        row = by_case.get(cid)
        if not isinstance(row, Mapping):
            continue
        if str(row.get("status") or "") in {"error", "unknown", "skipped"}:
            continue
        cap = str(row.get("capability_id") or "").strip()
        if not cap:
            continue
        bucket = stats.setdefault(cap, {"successes": 0, "n": 0})
        bucket["n"] += 1
        if bool(row.get("ok")):
            bucket["successes"] += 1
    return stats


def build_mode_intersection_rank(
    mode_columns: Mapping[str, Mapping[str, Any]],
    *,
    parity: Mapping[str, Any] | None = None,
    signoff: Mapping[str, Any] | None = None,
    min_n_per_capability: int = MIN_N_DEFAULT,
    track_a_complete: bool = True,
    force_rank_claim: bool = False,
) -> Dict[str, Any]:
    """Build Track B intersection comparison report (default: no single winner).

    ``mode_columns[mode]`` expected fields:
      subject, runtime_tier, model_fingerprint, rank_fingerprint,
      intersection_manifest_hash, by_case[case_id]={capability_id, ok, status}
    """
    if force_rank_claim:
        raise ModeIntersectionRankError("force_rank_claim_forbidden")

    sample = dict(parity) if parity is not None else load_parity_sample()
    gate = evaluate_rank_gate(
        mode_columns=mode_columns,
        parity=sample,
        signoff=signoff,
        min_n_per_capability=min_n_per_capability,
        track_a_complete=track_a_complete,
    )
    eligible = list_rank_eligible_cases(sample)
    eligible_ids = [str(c.get("case_id")) for c in eligible]

    per_mode: Dict[str, Any] = {}
    rate_vectors: Dict[str, Dict[str, float]] = {}
    pairwise: List[Dict[str, Any]] = []

    modes = [m for m, col in mode_columns.items() if isinstance(col, Mapping)]
    for mode in modes:
        col = mode_columns[mode]
        stats = _capability_stats_from_column(col, eligible_ids)
        caps_out: Dict[str, Any] = {}
        rates: Dict[str, float] = {}
        for cap, st in stats.items():
            lo, hi = wilson_score_ci(st["successes"], st["n"])
            rate = (st["successes"] / st["n"]) if st["n"] else None
            caps_out[cap] = {
                "successes": st["successes"],
                "n": st["n"],
                "rate": None if rate is None else round(rate, 4),
                "wilson_ci": [lo, hi],
                "ci_method": CI_METHOD,
            }
            if rate is not None:
                rates[cap] = float(rate)
        per_mode[mode] = {
            "subject": col.get("subject"),
            "runtime_tier": col.get("runtime_tier"),
            "model_fingerprint": col.get("model_fingerprint"),
            "rank_fingerprint": col.get("rank_fingerprint"),
            "capabilities": caps_out,
        }
        rate_vectors[mode] = rates

    # Pairwise dominance per capability
    for i, a in enumerate(modes):
        for b in modes[i + 1 :]:
            caps = sorted(set(rate_vectors.get(a, {})) | set(rate_vectors.get(b, {})))
            per_cap: Dict[str, str] = {}
            for cap in caps:
                a_stats = (per_mode[a]["capabilities"] or {}).get(cap) or {}
                b_stats = (per_mode[b]["capabilities"] or {}).get(cap) or {}
                a_ci = a_stats.get("wilson_ci") or [None, None]
                b_ci = b_stats.get("wilson_ci") or [None, None]
                per_cap[cap] = dominance_relation(a_ci[0], a_ci[1], b_ci[0], b_ci[1])
            pairwise.append(
                {
                    "mode_a": a,
                    "mode_b": b,
                    "per_capability": per_cap,
                    "claim_sentence_template": (
                        f"在 Agent×Config×Model 固定下，{a} 相对 {b} 在交集能力上 …"
                        "（禁止抽象「模式优劣」）"
                    ),
                }
            )

    frontier = pareto_frontier(rate_vectors)
    rank_claim = False  # never auto; gate.rank_claim_allowed only unlocks permission
    return {
        "schema": RANK_SCHEMA,
        "phase": "m3",
        "ok": True,  # engineering report always builds; claim separate
        "gate": gate,
        "ci_method": CI_METHOD,
        "ci_version": CI_VERSION,
        "eligible_cases": eligible,
        "per_mode": per_mode,
        "pairwise_dominance": pairwise,
        "pareto": frontier,
        "single_winner": None,
        "rank_claim": rank_claim,
        "rank_claim_allowed": bool(gate.get("rank_claim_allowed")),
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": (
            "Track B intersection only; fixture banned; unknown≠0/pass; "
            "Pareto+CI no default winner; rank_claim requires gate+signoff "
            "(not emitted by this builder)"
        ),
    }


def attach_rank_fingerprint_to_column(
    column: Mapping[str, Any],
    *,
    fingerprint_parts: Mapping[str, Any],
) -> Dict[str, Any]:
    """Helper: compute rank_fingerprint and merge into a mode column dict."""
    fp = compute_rank_fingerprint(**dict(fingerprint_parts))
    out = dict(column)
    out["rank_fingerprint"] = fp.get("rank_fingerprint")
    out["rank_fingerprint_ok"] = bool(fp.get("ok"))
    out["rank_fingerprint_parts"] = fp.get("parts")
    return out


def load_parity_for_rank(*, seed_dir: Optional[Path] = None) -> Dict[str, Any]:
    if seed_dir is None:
        return load_parity_sample()
    path = Path(seed_dir) / "intersection" / "parity_sample.v1.json"
    try:
        return load_parity_sample(path=path)
    except AgentImplModeError as exc:
        raise ModeIntersectionRankError(str(exc)) from exc
