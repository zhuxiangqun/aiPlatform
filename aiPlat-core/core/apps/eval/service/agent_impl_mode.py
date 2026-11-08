"""Agent impl_mode resolve + rank_fingerprint (M0 contracts; no live runner).

Authority: docs/architecture/plans/eval-agent-impl-mode-exam.md
Hard rule: selection union ≠ execution union.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

import yaml

from core.apps.eval.service.capability_case_bank import default_seed_dir
from core.apps.eval.service.capability_id_map import CANONICAL_IDS, resolve_capability_id

_log = logging.getLogger(__name__)

MATRIX_SCHEMA = "eval.mode_core_capabilities.v1"
MATRIX_FILENAME = "mode_core_capabilities.v1.yaml"
PARITY_FILENAME = "intersection/parity_sample.v1.json"

KNOWN_MODES = frozenset(
    {
        "react",
        "tool_loop",
        "plan_execute",
        "conversational",
        "rag",
        "multi_agent",
        "pipeline",
        "operator",
        "unknown",
        "deferred",
    }
)
DEFERRED_MODES = frozenset({"multi_agent", "pipeline", "operator"})
CONFIDENCE_VALUES = frozenset({"explicit", "derived"})
SOURCE_VALUES = frozenset({"AGENT.md", "registry", "config", "derived"})


class AgentImplModeError(ValueError):
    """Fail-closed mode / matrix / fingerprint error."""


def _sha256_hex(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canon_list(raw: Any) -> List[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    out: List[str] = []
    for x in raw:
        s = str(x or "").strip().lower()
        if s:
            out.append(s)
    return out


def default_matrix_path() -> Path:
    return default_seed_dir() / MATRIX_FILENAME


def default_parity_path() -> Path:
    return default_seed_dir() / PARITY_FILENAME


def load_mode_core_matrix(*, path: Optional[Path] = None) -> Dict[str, Any]:
    """Load + shallow-validate mode_core_capabilities.v1.yaml."""
    p = Path(path) if path else default_matrix_path()
    if not p.is_file():
        raise AgentImplModeError(f"matrix_missing:{p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise AgentImplModeError("matrix_not_object")
    if str(raw.get("schema") or "") != MATRIX_SCHEMA:
        raise AgentImplModeError(f"matrix_schema:{raw.get('schema')}")
    modes = raw.get("modes")
    if not isinstance(modes, Mapping) or not modes:
        raise AgentImplModeError("matrix_modes_missing")
    return dict(raw)


def resolve_impl_modes(
    source: Mapping[str, Any] | None,
    *,
    allow_derived: bool = True,
) -> Dict[str, Any]:
    """Resolve multi-value impl_modes from AGENT.md / registry / config mapping.

    Never defaults unknown → react. Deferred modes keep primary=deferred.
    """
    src = dict(source or {})
    # Prefer nested impl_modes block; else flat agent_type / supported_loop_types.
    block = src.get("impl_modes") if isinstance(src.get("impl_modes"), Mapping) else None
    if block is not None:
        primary = str(block.get("primary") or "").strip().lower()
        secondary = _canon_list(block.get("secondary"))
        confidence = str(block.get("confidence") or "explicit").strip().lower()
        source_tag = str(block.get("source") or "config").strip()
    else:
        primary = str(
            src.get("agent_type") or src.get("impl_mode") or src.get("primary") or ""
        ).strip().lower()
        secondary = _canon_list(
            src.get("secondary") or src.get("supported_loop_types") or []
        )
        # Flat agent_type without explicit impl_modes → derived hint only.
        confidence = "derived" if primary else "explicit"
        source_tag = "derived" if confidence == "derived" else "config"
        if not allow_derived and confidence == "derived":
            primary = ""

    if primary in DEFERRED_MODES:
        return {
            "schema": "eval.impl_modes.v1",
            "primary": "deferred",
            "secondary": [m for m in secondary if m not in DEFERRED_MODES],
            "deferred_as": primary,
            "confidence": confidence if confidence in CONFIDENCE_VALUES else "explicit",
            "source": source_tag if source_tag in SOURCE_VALUES else "config",
            "ok": True,
            "errors": [],
        }

    errors: List[str] = []
    if not primary:
        primary = "unknown"
        errors.append("missing_primary")
    elif primary not in KNOWN_MODES:
        errors.append(f"unknown_mode:{primary}")
        primary = "unknown"

    # Drop deferred from secondary into disclosure only.
    clean_secondary: List[str] = []
    deferred_secondary: List[str] = []
    for m in secondary:
        if m == primary:
            continue
        if m in DEFERRED_MODES:
            deferred_secondary.append(m)
            continue
        if m not in KNOWN_MODES or m in {"unknown", "deferred"}:
            errors.append(f"unknown_secondary:{m}")
            continue
        if m not in clean_secondary:
            clean_secondary.append(m)

    if confidence not in CONFIDENCE_VALUES:
        errors.append(f"bad_confidence:{confidence}")
        confidence = "derived"

    return {
        "schema": "eval.impl_modes.v1",
        "primary": primary,
        "secondary": clean_secondary,
        "deferred_secondary": deferred_secondary,
        "confidence": confidence,
        "source": source_tag if source_tag in SOURCE_VALUES else "config",
        "ok": primary != "unknown" and not any(e.startswith("unknown_mode") for e in errors),
        "errors": errors,
        "honesty": "derived confidence must not alone unlock covered claims",
    }


def select_capabilities_union(
    impl_modes: Mapping[str, Any],
    matrix: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Selection layer: union of mode_core across primary+secondary.

    Does NOT imply a single execution covering all modes.
    """
    mat = matrix or load_mode_core_matrix()
    modes_cfg = mat.get("modes") if isinstance(mat.get("modes"), Mapping) else {}
    primary = str(impl_modes.get("primary") or "unknown").strip().lower()
    secondary = _canon_list(impl_modes.get("secondary"))
    mode_list = [primary] + [m for m in secondary if m != primary]

    cores: Set[str] = set()
    na: Set[str] = set()
    per_mode: Dict[str, Dict[str, Any]] = {}
    for mode in mode_list:
        if mode in {"unknown", "deferred"}:
            per_mode[mode] = {"status": mode, "mode_core": [], "mode_not_applicable": []}
            continue
        cfg = modes_cfg.get(mode) if isinstance(modes_cfg.get(mode), Mapping) else None
        if cfg is None:
            per_mode[mode] = {"status": "missing_in_matrix", "mode_core": []}
            continue
        core = []
        for c in _canon_list(cfg.get("mode_core")):
            try:
                cid = resolve_capability_id(c, fail_closed=True)
            except Exception:
                continue
            if cid in CANONICAL_IDS:
                core.append(cid)
                cores.add(cid)
        na_list = []
        for c in _canon_list(cfg.get("mode_not_applicable")):
            try:
                cid = resolve_capability_id(c, fail_closed=True)
            except Exception:
                continue
            na_list.append(cid)
            na.add(cid)
        per_mode[mode] = {
            "status": "ok",
            "mode_core": core,
            "mode_optional": _canon_list(cfg.get("mode_optional")),
            "mode_not_applicable": na_list,
            "environment_required": str(cfg.get("environment_required") or "none"),
            "m1_phase": str(cfg.get("m1_phase") or ""),
        }

    return {
        "schema": "eval.mode_selection_union.v1",
        "selection_union": sorted(cores),
        "not_applicable_union": sorted(na),
        "per_mode": per_mode,
        "execution_policy": "per_mode_separate_runs",
        "honesty": "selection union ≠ execution union",
        "claim_eligible": False,
    }


def plan_executions_per_mode(
    impl_modes: Mapping[str, Any],
    matrix: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Execution layer: one independent run plan per mode (never merged)."""
    sel = select_capabilities_union(impl_modes, matrix=matrix)
    runs: List[Dict[str, Any]] = []
    for mode, info in (sel.get("per_mode") or {}).items():
        if mode in {"unknown", "deferred"}:
            runs.append(
                {
                    "impl_mode": mode,
                    "status": mode,
                    "capabilities": [],
                    "separate_manifest": True,
                    "separate_create_agent": True,
                }
            )
            continue
        if info.get("status") != "ok":
            runs.append(
                {
                    "impl_mode": mode,
                    "status": str(info.get("status")),
                    "capabilities": [],
                    "separate_manifest": True,
                    "separate_create_agent": True,
                }
            )
            continue
        runs.append(
            {
                "impl_mode": mode,
                "status": "planned",
                "capabilities": list(info.get("mode_core") or []),
                "environment_required": info.get("environment_required"),
                "m1_phase": info.get("m1_phase"),
                "separate_manifest": True,
                "separate_create_agent": True,
                "separate_evidence": True,
            }
        )
    return {
        "schema": "eval.mode_execution_plan.v1",
        "runs": runs,
        "merged_execution_forbidden": True,
        "honesty": "each mode must have its own create_agent / manifest / run",
        "claim_eligible": False,
    }


def compute_rank_fingerprint(
    *,
    manifest_hash: str = "",
    prompt_hash: str = "",
    oracle_hash: str = "",
    runner_judge_version: str = "",
    model_fingerprint: str = "",
    runtime_tier: str = "",
    runtime_parts_contract: str = "",
    tools_contract_hash: str = "",
    retrieval_contract_hash: str = "",
    session_contract_hash: str = "",
    # Explicitly ignored if passed (fail closed if only these differ):
    subject_id: str = "",
    agent_id: str = "",
    workspace_id: str = "",
    display_name: str = "",
    run_time: str = "",
) -> Dict[str, Any]:
    """Stable cross-subject fingerprint for rank gate (excludes identity/time)."""
    _ = (subject_id, agent_id, workspace_id, display_name, run_time)  # excluded by design
    parts = {
        "manifest_hash": str(manifest_hash or "").strip(),
        "prompt_hash": str(prompt_hash or "").strip(),
        "oracle_hash": str(oracle_hash or "").strip(),
        "runner_judge_version": str(runner_judge_version or "").strip(),
        "model_fingerprint": str(model_fingerprint or "").strip(),
        "runtime_tier": str(runtime_tier or "").strip(),
        "runtime_parts_contract": str(runtime_parts_contract or "").strip(),
        "tools_contract_hash": str(tools_contract_hash or "").strip(),
        "retrieval_contract_hash": str(retrieval_contract_hash or "").strip(),
        "session_contract_hash": str(session_contract_hash or "").strip(),
    }
    missing = [k for k, v in parts.items() if not v]
    canonical = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "schema": "eval.rank_fingerprint.v1",
        "rank_fingerprint": _sha256_hex(canonical),
        "parts": parts,
        "excluded_fields": [
            "subject_id",
            "agent_id",
            "workspace_id",
            "display_name",
            "run_time",
        ],
        "ok": not missing,
        "missing_parts": missing,
        "claim_eligible": False,
        "rank_claim": False,
    }


def load_parity_sample(*, path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else default_parity_path()
    if not p.is_file():
        raise AgentImplModeError(f"parity_missing:{p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise AgentImplModeError("parity_not_object")
    return dict(raw)


def m1a_environment_lock(matrix: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    mat = matrix or load_mode_core_matrix()
    lock = mat.get("m1a_environment_lock")
    if not isinstance(lock, Mapping):
        raise AgentImplModeError("m1a_environment_lock_missing")
    return dict(lock)


def m1b_environment_lock(matrix: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    mat = matrix or load_mode_core_matrix()
    lock = mat.get("m1b_environment_lock")
    if not isinstance(lock, Mapping):
        raise AgentImplModeError("m1b_environment_lock_missing")
    return dict(lock)


def m1c_environment_lock(matrix: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    mat = matrix or load_mode_core_matrix()
    lock = mat.get("m1c_environment_lock")
    if not isinstance(lock, Mapping):
        raise AgentImplModeError("m1c_environment_lock_missing")
    return dict(lock)


def evaluate_m0_impl_mode_contracts(
    *,
    seed_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """M0 gate: matrix + parity sample + semantic invariants (no live execute)."""
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    checks: List[Dict[str, Any]] = []
    errors: List[str] = []

    def _add(cid: str, ok: bool, detail: str = "") -> None:
        checks.append({"id": cid, "ok": ok, "detail": detail})
        if not ok:
            errors.append(f"{cid}:{detail}" if detail else cid)

    try:
        matrix = load_mode_core_matrix(path=root / MATRIX_FILENAME)
        _add("matrix_load", True, MATRIX_SCHEMA)
    except AgentImplModeError as exc:
        matrix = {}
        _add("matrix_load", False, str(exc))

    modes = matrix.get("modes") if isinstance(matrix.get("modes"), Mapping) else {}
    required = {"plan_execute", "conversational", "rag", "react"}
    _add("matrix_has_m1_modes", required.issubset(set(modes.keys())), ",".join(sorted(required)))

    five = {"mode_core", "mode_optional", "mode_not_applicable"}
    field_ok = True
    for mid, cfg in modes.items():
        if not isinstance(cfg, Mapping):
            field_ok = False
            break
        if not five.issubset(set(cfg.keys())):
            field_ok = False
            break
        if "environment_required" not in cfg:
            field_ok = False
            break
    _add("matrix_five_field_shape", field_ok)

    pe = modes.get("plan_execute") if isinstance(modes.get("plan_execute"), Mapping) else {}
    a6_ok = "tool_failure_recovery" in set(pe.get("a6_forbidden_subtypes") or []) and set(
        pe.get("a6_allowed_subtypes") or []
    ) >= {"replan", "step_conflict", "text_recovery"}
    _add("plan_execute_a6_subtypes", bool(a6_ok))

    try:
        lock = m1a_environment_lock(matrix)
        pe_lock = lock.get("plan_execute") if isinstance(lock.get("plan_execute"), Mapping) else {}
        cv_lock = (
            lock.get("conversational") if isinstance(lock.get("conversational"), Mapping) else {}
        )
        lock_ok = (
            pe_lock.get("tools") == "none"
            and pe_lock.get("retrieval") == "none"
            and pe_lock.get("network") == "none"
            and pe_lock.get("session") == "none"
            and cv_lock.get("tools") == "none"
            and cv_lock.get("retrieval") == "none"
            and cv_lock.get("network") == "none"
            and cv_lock.get("session") == "allowed"
        )
        _add("m1a_environment_lock", lock_ok)
    except AgentImplModeError as exc:
        _add("m1a_environment_lock", False, str(exc))

    try:
        lock_b = m1b_environment_lock(matrix)
        rag_lock = lock_b.get("rag") if isinstance(lock_b.get("rag"), Mapping) else {}
        m1b_ok = (
            rag_lock.get("tools") == "none"
            and rag_lock.get("retrieval") == "required"
            and rag_lock.get("network") == "none"
            and rag_lock.get("session") == "none"
        )
        _add("m1b_environment_lock", m1b_ok)
    except AgentImplModeError as exc:
        _add("m1b_environment_lock", False, str(exc))

    try:
        lock_c = m1c_environment_lock(matrix)
        react_lock = lock_c.get("react") if isinstance(lock_c.get("react"), Mapping) else {}
        m1c_ok = (
            react_lock.get("tools") == "required"
            and react_lock.get("sandbox") == "required"
            and react_lock.get("retrieval") == "none"
        )
        _add("m1c_environment_lock", m1c_ok)
    except AgentImplModeError as exc:
        _add("m1c_environment_lock", False, str(exc))

    # selection ≠ execution
    resolved = resolve_impl_modes(
        {"impl_modes": {"primary": "react", "secondary": ["conversational"], "confidence": "explicit", "source": "config"}}
    )
    sel = select_capabilities_union(resolved, matrix=matrix)
    exe = plan_executions_per_mode(resolved, matrix=matrix)
    _add(
        "selection_ne_execution",
        bool(sel.get("execution_policy") == "per_mode_separate_runs")
        and bool(exe.get("merged_execution_forbidden"))
        and len(exe.get("runs") or []) >= 2,
        "union_ok_separate_runs",
    )

    unknown = resolve_impl_modes({"agent_type": ""})
    _add("unknown_not_default_react", unknown.get("primary") == "unknown")

    deferred = resolve_impl_modes({"agent_type": "multi_agent"})
    _add("deferred_ne_unknown", deferred.get("primary") == "deferred")

    fp_a = compute_rank_fingerprint(
        manifest_hash="sha256:m1",
        prompt_hash="sha256:p1",
        oracle_hash="sha256:o1",
        runner_judge_version="judge.v1",
        model_fingerprint="model.x",
        runtime_tier="workspace_execute",
        runtime_parts_contract="parts.v1",
        tools_contract_hash="sha256:tools=none",
        retrieval_contract_hash="sha256:retrieval=none",
        session_contract_hash="sha256:session=none",
        agent_id="agent-A",
    )
    fp_b = compute_rank_fingerprint(
        manifest_hash="sha256:m1",
        prompt_hash="sha256:p1",
        oracle_hash="sha256:o1",
        runner_judge_version="judge.v1",
        model_fingerprint="model.x",
        runtime_tier="workspace_execute",
        runtime_parts_contract="parts.v1",
        tools_contract_hash="sha256:tools=none",
        retrieval_contract_hash="sha256:retrieval=none",
        session_contract_hash="sha256:session=none",
        agent_id="agent-B",
    )
    _add(
        "rank_fingerprint_excludes_agent_id",
        fp_a.get("rank_fingerprint") == fp_b.get("rank_fingerprint") and bool(fp_a.get("ok")),
    )

    try:
        parity = load_parity_sample(path=root / PARITY_FILENAME)
        cases = parity.get("cases") if isinstance(parity.get("cases"), list) else []
        none_eligible = all(not bool(c.get("rank_eligible")) for c in cases if isinstance(c, Mapping))
        has_a12_block = any(
            isinstance(c, Mapping)
            and c.get("capability_id") == "observability"
            and c.get("parity_status") == "blocked_trace_parity"
            for c in cases
        )
        _add("parity_sample_no_auto_eligible", bool(cases) and none_eligible)
        _add("a12_blocked_until_trace_parity", has_a12_block)
        _add(
            "pareto_ci_rules_documented",
            str(parity.get("ci_method_default") or "") == "wilson"
            and "dominates" in str(parity.get("dominance_rule") or ""),
        )
        _add(
            "subject_unit_documented",
            "agent_id" in str(parity.get("subject_unit") or "")
            and "impl_mode" in str(parity.get("subject_unit") or ""),
        )
    except AgentImplModeError as exc:
        _add("parity_sample_load", False, str(exc))

    exit_ids = [
        "matrix_load",
        "matrix_has_m1_modes",
        "matrix_five_field_shape",
        "plan_execute_a6_subtypes",
        "m1a_environment_lock",
        "m1b_environment_lock",
        "m1c_environment_lock",
        "selection_ne_execution",
        "unknown_not_default_react",
        "deferred_ne_unknown",
        "rank_fingerprint_excludes_agent_id",
        "parity_sample_no_auto_eligible",
        "a12_blocked_until_trace_parity",
        "pareto_ci_rules_documented",
        "subject_unit_documented",
    ]
    by_id = {c["id"]: c for c in checks}
    m0_exit = {eid: bool((by_id.get(eid) or {}).get("ok")) for eid in exit_ids}
    ok = all(m0_exit.values()) and not errors

    return {
        "schema": "eval.m0_impl_mode_contracts.v1",
        "ok": ok,
        "checks": checks,
        "errors": errors,
        "m0_exit_checklist": m0_exit,
        "m1_blocked": not ok,
        "claim_eligible": False,
        "rank_claim": False,
        "accuracy_claim": False,
        "honesty": (
            "M0 contracts only; no live create_agent; "
            "selection union ≠ execution union; rank_claim requires M3 gate"
        ),
    }
