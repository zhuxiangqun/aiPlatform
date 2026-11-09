"""SEC-P0b: T12 isolation state machine + escape probe interface.

States (strict ascending; never skip evidence):
  unknown → isolation_admitted → isolation_probed → isolation_covered

Hard locks:
- Darwin / non-Linux: cannot reach isolation_covered; typically stay unknown
  or admitted=false.
- admit_ready alone never yields isolation_covered.
- process_split_authorized never flipped here.
- accuracy_claim / security_certification always false.
"""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

ISOLATION_UNKNOWN = "unknown"
ISOLATION_ADMITTED = "isolation_admitted"
ISOLATION_PROBED = "isolation_probed"
ISOLATION_COVERED = "isolation_covered"

_VALID_STATES = frozenset(
    {
        ISOLATION_UNKNOWN,
        ISOLATION_ADMITTED,
        ISOLATION_PROBED,
        ISOLATION_COVERED,
    }
)

PROBE_SCHEMA = "eval.security_t12_escape_probes.v1"
STATUS_SCHEMA = "eval.security_t12_isolation_status.v1"


class IsolationT12Error(ValueError):
    """Fail-closed T12 isolation error."""


def default_t12_probes_path() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "agent_capability"
        / "security"
        / "t12_escape_probes.v1.json"
    )


def load_t12_escape_probes(*, path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else default_t12_probes_path()
    if not p.is_file():
        raise IsolationT12Error(f"t12_probes_missing:{p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise IsolationT12Error("t12_probes_not_object")
    if str(raw.get("schema") or "") != PROBE_SCHEMA:
        raise IsolationT12Error(f"t12_probes_schema_mismatch:{raw.get('schema')}")
    probes = raw.get("probes")
    if not isinstance(probes, list) or len(probes) < 4:
        raise IsolationT12Error("t12_probes_min_4")
    kinds = {str((x or {}).get("kind") or "") for x in probes if isinstance(x, Mapping)}
    if "negative_control" not in kinds:
        raise IsolationT12Error("t12_negative_control_required")
    return dict(raw)


def _probes_opt_in() -> bool:
    return os.environ.get("AIPLAT_EVAL_T12_PROBES", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def run_escape_probes(
    *,
    catalog: Optional[Mapping[str, Any]] = None,
    live: bool = False,
) -> Dict[str, Any]:
    """Execute or dry-run T12 probes. Never claims isolation_covered.

    Default (no AIPLAT_EVAL_T12_PROBES): dry inventory only (status=not_run).
    live=True + opt-in on Linux: marks deferred_guest_exec (P0b interface only).
    Completed probed evidence is SEC-P4 ``run_linux_microvm_probes(guest_sim)``.
    """
    cat = dict(catalog) if catalog is not None else load_t12_escape_probes()
    probes = [dict(x) for x in (cat.get("probes") or []) if isinstance(x, Mapping)]
    os_name = platform.system().lower()
    linux = os_name == "linux"
    opt_in = _probes_opt_in()
    results: List[Dict[str, Any]] = []

    if not live or not opt_in:
        for p in probes:
            results.append(
                {
                    "probe_id": p.get("probe_id"),
                    "kind": p.get("kind"),
                    "expect": p.get("expect"),
                    "status": "not_run",
                    "observed": None,
                    "ok": None,
                    "detail": "dry_inventory_AIPLAT_EVAL_T12_PROBES_off"
                    if not opt_in
                    else "live_false",
                }
            )
        return {
            "schema": "eval.security_t12_probe_run.v1",
            "ok": True,
            "os": os_name,
            "linux": linux,
            "live": False,
            "opt_in": opt_in,
            "probed": False,
            "all_deny_probes_negative": None,
            "negative_control_ok": None,
            "results": results,
            "honesty": "Probe catalog dry-run; ≠ isolation_probed evidence.",
            "accuracy_claim": False,
            "security_certification": False,
            "process_split_authorized": False,
        }

    if not linux:
        for p in probes:
            results.append(
                {
                    "probe_id": p.get("probe_id"),
                    "kind": p.get("kind"),
                    "expect": p.get("expect"),
                    "status": "skipped_non_linux",
                    "observed": None,
                    "ok": False,
                    "detail": "darwin_or_non_linux_hard_lock",
                }
            )
        return {
            "schema": "eval.security_t12_probe_run.v1",
            "ok": False,
            "os": os_name,
            "linux": False,
            "live": True,
            "opt_in": opt_in,
            "probed": False,
            "all_deny_probes_negative": False,
            "negative_control_ok": False,
            "results": results,
            "honesty": "Non-Linux cannot run T12 escape probes; never isolation_covered.",
            "accuracy_claim": False,
            "security_certification": False,
            "process_split_authorized": False,
        }

    # Linux opt-in: P0b interface only — deferred. Use SEC-P4 guest_sim/live.
    for p in probes:
        expect = str(p.get("expect") or "deny")
        results.append(
            {
                "probe_id": p.get("probe_id"),
                "kind": p.get("kind"),
                "expect": expect,
                "status": "deferred_guest_exec",
                "observed": None,
                "ok": None,
                "detail": "sec_p0b_interface_only_use_sec_p4_guest_sim",
            }
        )
    return {
        "schema": "eval.security_t12_probe_run.v1",
        "ok": True,
        "os": os_name,
        "linux": True,
        "live": True,
        "opt_in": opt_in,
        "probed": False,  # deferred_guest_exec ≠ completed probe evidence
        "all_deny_probes_negative": None,
        "negative_control_ok": None,
        "results": results,
        "honesty": (
            "SEC-P0b registers probe interface on Linux; "
            "completed probed path is SEC-P4 run_linux_microvm_probes. "
            "Not isolation_probed."
        ),
        "accuracy_claim": False,
        "security_certification": False,
        "process_split_authorized": False,
    }


def evaluate_isolation_status(
    *,
    admit: Optional[Mapping[str, Any]] = None,
    probe_run: Optional[Mapping[str, Any]] = None,
    human_review: bool = False,
    human_reviewer: str = "",
) -> Dict[str, Any]:
    """Derive T12 isolation_* status. Never auto-covered from admit alone."""
    from core.apps.eval.service.mode_aware_exam import probe_linux_microvm_host

    adm = dict(admit) if admit is not None else probe_linux_microvm_host()
    run = dict(probe_run) if probe_run is not None else {}

    os_name = str(adm.get("os") or platform.system().lower())
    linux = bool(adm.get("linux")) if "linux" in adm else os_name == "linux"
    admit_ready = bool(adm.get("admit_ready"))
    monitor_hook = True  # probe_linux_microvm_host is the monitor hook presence

    probed = bool(run.get("probed"))
    results = list(run.get("results") or [])
    deny_ok = True
    neg_ok = True
    ran_any = False
    for row in results:
        if not isinstance(row, Mapping):
            continue
        st = str(row.get("status") or "")
        if st in {"not_run", "skipped_non_linux", "deferred_guest_exec"}:
            continue
        ran_any = True
        expect = str(row.get("expect") or "")
        ok = row.get("ok")
        if expect == "deny":
            if ok is not True:
                deny_ok = False
        elif expect == "allow" or str(row.get("kind")) == "negative_control":
            if ok is not True:
                neg_ok = False

    if ran_any and deny_ok and neg_ok:
        probed = True
        all_neg = True
        neg_control = True
    else:
        all_neg = bool(run.get("all_deny_probes_negative")) if ran_any else None
        neg_control = bool(run.get("negative_control_ok")) if ran_any else None
        if ran_any:
            all_neg = deny_ok
            neg_control = neg_ok

    # State machine
    status = ISOLATION_UNKNOWN
    reasons: List[str] = []

    if not linux:
        status = ISOLATION_UNKNOWN
        reasons.append("non_linux_host")
        admit_ready = False
    elif not admit_ready or not monitor_hook:
        status = ISOLATION_UNKNOWN
        reasons.append("admit_not_ready")
    else:
        status = ISOLATION_ADMITTED
        reasons.append("admit_ready")
        if probed and all_neg is True and neg_control is True:
            status = ISOLATION_PROBED
            reasons.append("probes_completed_negative")
            if human_review and str(human_reviewer or "").strip():
                status = ISOLATION_COVERED
                reasons.append("human_review_signed")
            else:
                reasons.append("human_review_required_for_covered")
        elif probed:
            status = ISOLATION_PROBED
            reasons.append("probes_ran_but_not_all_negative")
        else:
            reasons.append("probes_not_completed")

    # Absolute hard locks
    if status == ISOLATION_COVERED and not linux:
        status = ISOLATION_UNKNOWN
        reasons.append("covered_forbidden_on_non_linux")
    if status == ISOLATION_COVERED and not (human_review and human_reviewer.strip()):
        status = ISOLATION_PROBED if probed else ISOLATION_ADMITTED
        reasons.append("covered_requires_human_review")
    if admit_ready and status == ISOLATION_COVERED and not probed:
        status = ISOLATION_ADMITTED
        reasons.append("covered_forbidden_from_admit_alone")

    assert status in _VALID_STATES

    return {
        "schema": STATUS_SCHEMA,
        "ok": True,
        "threat_id": "T12",
        "isolation_status": status,
        "os": os_name,
        "linux": linux,
        "admit_ready": bool(admit_ready) if linux else False,
        "monitor_hook_ready": bool(monitor_hook),
        "probed": bool(probed),
        "all_deny_probes_negative": all_neg,
        "negative_control_ok": neg_control,
        "human_review": bool(human_review and str(human_reviewer or "").strip()),
        "human_reviewer": str(human_reviewer or "") if human_review else "",
        "reasons": reasons,
        "admit": {
            "kvm_device": adm.get("kvm_device"),
            "host_ok": adm.get("host_ok"),
            "admit_ready": adm.get("admit_ready"),
            "detail": adm.get("detail"),
            "microvm_covered": False,  # legacy field; use isolation_status
            "process_split_authorized": False,
        },
        "probe_run_summary": {
            "probed": run.get("probed"),
            "n_results": len(results),
            "live": run.get("live"),
        },
        "microvm_covered": False,  # deprecated alias; always false unless covered+legacy
        "isolation_covered": status == ISOLATION_COVERED,
        "accuracy_claim": False,
        "security_certification": False,
        "process_split_authorized": False,
        "claim_eligible": False,
        "honesty": (
            "admit ≠ escape test; isolation_covered requires probes all-negative "
            "+ negative control + human review; Darwin stays unknown."
        ),
    }


def security_t12_p0b_status(
    *,
    live_probes: bool = False,
    human_review: bool = False,
    human_reviewer: str = "",
) -> Dict[str, Any]:
    """Facade-friendly SEC-P0b snapshot."""
    from core.apps.eval.service.mode_aware_exam import probe_linux_microvm_host

    catalog = load_t12_escape_probes()
    admit = probe_linux_microvm_host()
    probe_run = run_escape_probes(catalog=catalog, live=bool(live_probes))
    status = evaluate_isolation_status(
        admit=admit,
        probe_run=probe_run,
        human_review=bool(human_review),
        human_reviewer=str(human_reviewer or ""),
    )
    return {
        "schema": "eval.security_sec_p0b_status.v1",
        "ok": True,
        "slice": "SEC-P0b",
        "catalog": {
            "version": catalog.get("version"),
            "n_probes": len(catalog.get("probes") or []),
            "min_probes": catalog.get("min_probes"),
        },
        "admit": admit,
        "probe_run": probe_run,
        "isolation": status,
        "isolation_status": status.get("isolation_status"),
        "accuracy_claim": False,
        "security_certification": False,
        "process_split_authorized": False,
        "claim_eligible": False,
    }
