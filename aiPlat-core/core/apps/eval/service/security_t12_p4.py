"""SEC-P4 / SEC-P4b: Linux microVM probed path (beyond admit).

Modes:
  guest_sim  — Linux + admit_ready + opt-in: complete escape probes with
               simulated guest outcomes (no host mutation). Can reach
               isolation_probed via evaluate_isolation_status.
  guest_live — SEC-P4b: AIPLAT_EVAL_T12_GUEST_LIVE=1 + eval microVM hooks
               (runtime / guest_boot cache / host allowlist CLI). Deny-escape
               needs an injected escape_executor (no fake green). Host
               allowlist ≠ in-guest escape; ≠ sandbox_real_isolation.

Hard locks:
  - Darwin / non-Linux → never isolation_probed / covered
  - admit alone never covered
  - isolation_covered still needs human_review (via evaluate_isolation_status)
  - process_split_authorized / accuracy_claim / security_certification stay false
  - guest_sim ≠ sandbox_real_isolation certification
"""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from core.apps.eval.service.isolation_t12 import (
    ISOLATION_COVERED,
    ISOLATION_PROBED,
    evaluate_isolation_status,
    load_t12_escape_probes,
    run_escape_probes,
)

STATUS_SCHEMA = "eval.security_sec_p4_status.v1"
RUN_SCHEMA = "eval.security_t12_p4_probe_run.v1"

MODE_GUEST_SIM = "guest_sim"
MODE_GUEST_LIVE = "guest_live"
_VALID_MODES = frozenset({MODE_GUEST_SIM, MODE_GUEST_LIVE})

EscapeExecutor = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class SecurityT12P4Error(ValueError):
    """Fail-closed SEC-P4 T12 probed-path error."""


def _probes_opt_in() -> bool:
    return os.environ.get("AIPLAT_EVAL_T12_PROBES", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _guest_live_opt_in() -> bool:
    return os.environ.get("AIPLAT_EVAL_T12_GUEST_LIVE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _guest_boot_probe_opt_in() -> bool:
    return os.environ.get("AIPLAT_EVAL_T12_GUEST_BOOT_PROBE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _try_microvm_admit() -> Dict[str, Any]:
    """Best-effort microVM host/admit snapshot; never claims isolation."""
    try:
        from core.apps.eval.service.mode_aware_exam import probe_linux_microvm_host

        return dict(probe_linux_microvm_host())
    except Exception as exc:  # noqa: BLE001
        return {
            "linux": platform.system().lower() == "linux",
            "admit_ready": False,
            "microvm_covered": False,
            "process_split_authorized": False,
            "detail": f"admit_probe_failed:{type(exc).__name__}",
        }


def _load_eval_microvm_hooks() -> Optional[Dict[str, Any]]:
    """Best-effort import of packages/aiplat-evaluation microVM helpers."""
    try:
        root = Path(__file__).resolve().parents[5]
        pkg = root / "packages" / "aiplat-evaluation"
        if str(pkg) not in sys.path:
            sys.path.insert(0, str(pkg))
        from app.sandbox.guest_boot import probe_guest_boot  # type: ignore
        from app.sandbox.microvm import (  # type: ignore
            guest_boot_cached,
            microvm_can_admit_runners,
            microvm_status,
        )
        from app.sandbox.microvm_exec import (  # type: ignore
            probe_runtime,
            run_allowlisted_cli,
        )

        return {
            "probe_runtime": probe_runtime,
            "run_allowlisted_cli": run_allowlisted_cli,
            "guest_boot_cached": guest_boot_cached,
            "probe_guest_boot": probe_guest_boot,
            "microvm_status": microvm_status,
            "microvm_can_admit_runners": microvm_can_admit_runners,
        }
    except Exception:  # noqa: BLE001
        return None


def _guest_live_evidence(hooks: Mapping[str, Any]) -> Dict[str, Any]:
    """Snapshot live-track evidence. Never mutates host; never claims isolation."""
    runtime: Dict[str, Any] = {}
    status: Dict[str, Any] = {}
    try:
        runtime = dict(hooks["probe_runtime"]() or {})
    except Exception as exc:  # noqa: BLE001
        runtime = {"ok": False, "stderr": f"probe_runtime:{type(exc).__name__}"}
    try:
        status = dict(hooks["microvm_status"]() or {})
    except Exception as exc:  # noqa: BLE001
        status = {"ok": False, "detail": f"microvm_status:{type(exc).__name__}"}

    guest = False
    try:
        guest = bool(hooks["guest_boot_cached"]())
    except Exception:  # noqa: BLE001
        guest = False

    boot_probe: Optional[Dict[str, Any]] = None
    if not guest and _guest_boot_probe_opt_in():
        try:
            boot_probe = dict(hooks["probe_guest_boot"]() or {})
            audit = boot_probe.get("audit") if isinstance(boot_probe.get("audit"), Mapping) else {}
            guest = bool(boot_probe.get("ok") and audit.get("guest_boot"))
        except Exception as exc:  # noqa: BLE001
            boot_probe = {"ok": False, "stderr": f"probe_guest_boot:{type(exc).__name__}"}

    admit_runners = False
    try:
        admit_runners = bool(hooks["microvm_can_admit_runners"]())
    except Exception:  # noqa: BLE001
        admit_runners = False

    return {
        "runtime_ok": bool(runtime.get("ok")),
        "guest_boot": guest,
        "guest_boot_authorized": bool(status.get("guest_boot_authorized")),
        "admit_runners": admit_runners,
        "kvm_available": status.get("kvm_available"),
        "microvm_host_ok": status.get("microvm_host_ok"),
        "boot_probe": boot_probe,
        "sandbox_real_isolation": False,
        "process_split_authorized": False,
        "honesty": (
            "Live evidence from eval microVM track hooks. "
            "host allowlist CLI ≠ in-guest escape; guest_boot ≠ isolation cert."
        ),
    }


def _run_guest_live_probes(
    probes: List[Mapping[str, Any]],
    *,
    base: Mapping[str, Any],
    hooks: Optional[Mapping[str, Any]] = None,
    escape_executor: Optional[EscapeExecutor] = None,
) -> Dict[str, Any]:
    """SEC-P4b guest_live path. Incomplete deny probes stay un-probed (honest)."""
    loaded = dict(hooks) if hooks is not None else _load_eval_microvm_hooks()
    if not loaded:
        return {
            **dict(base),
            "ok": False,
            "probed": False,
            "live": True,
            "results": [
                {
                    "probe_id": p.get("probe_id"),
                    "kind": p.get("kind"),
                    "expect": p.get("expect"),
                    "status": "guest_live_hooks_unavailable",
                    "observed": None,
                    "ok": None,
                    "detail": "aiplat-evaluation_microvm_hooks_import_failed",
                }
                for p in probes
            ],
            "all_deny_probes_negative": None,
            "negative_control_ok": None,
            "live_evidence": None,
            "honesty": (
                "SEC-P4b guest_live: evaluation microVM hooks unavailable. "
                "Use guest_sim for engineering isolation_probed. ≠ certification."
            ),
        }

    evidence = _guest_live_evidence(loaded)
    results: List[Dict[str, Any]] = []
    deny_ok = True
    neg_ok = True
    incomplete = False

    for p in probes:
        expect = str(p.get("expect") or "deny")
        kind = str(p.get("kind") or "")
        is_neg = expect == "allow" or kind == "negative_control"

        if is_neg:
            try:
                cli = dict(loaded["run_allowlisted_cli"](["true"]) or {})
            except Exception as exc:  # noqa: BLE001
                cli = {"ok": False, "stderr": f"cli:{type(exc).__name__}"}
            ok = bool(cli.get("ok"))
            if not ok:
                neg_ok = False
            results.append(
                {
                    "probe_id": p.get("probe_id"),
                    "kind": kind,
                    "expect": expect,
                    "status": "guest_live_neg_control_ok" if ok else "guest_live_neg_control_fail",
                    "observed": "allowed_by_host_allowlist" if ok else "allowlist_cli_failed",
                    "ok": ok,
                    "detail": "host_allowlist_under_microvm_policy_not_guest_exec",
                    "audit": cli.get("audit"),
                }
            )
            continue

        # Deny / escape probes — require explicit escape_executor (no fake green).
        if escape_executor is None:
            incomplete = True
            deny_ok = False
            results.append(
                {
                    "probe_id": p.get("probe_id"),
                    "kind": kind,
                    "expect": expect,
                    "status": "guest_escape_channel_unavailable",
                    "observed": None,
                    "ok": None,
                    "detail": (
                        "no_in_guest_escape_executor;"
                        f"guest_boot={evidence.get('guest_boot')};"
                        "inject_escape_executor_or_use_guest_sim"
                    ),
                }
            )
            continue

        try:
            outcome = dict(escape_executor(p) or {})
        except Exception as exc:  # noqa: BLE001
            outcome = {
                "ok": False,
                "observed": None,
                "status": "guest_escape_executor_error",
                "detail": type(exc).__name__,
            }
        ok = outcome.get("ok")
        if ok is not True:
            deny_ok = False
            if ok is None:
                incomplete = True
        results.append(
            {
                "probe_id": p.get("probe_id"),
                "kind": kind,
                "expect": expect,
                "status": str(outcome.get("status") or ("guest_live_escape_ok" if ok is True else "guest_live_escape_fail")),
                "observed": outcome.get("observed"),
                "ok": ok,
                "detail": str(outcome.get("detail") or "escape_executor"),
            }
        )

    probed = bool(results) and (not incomplete) and deny_ok and neg_ok
    return {
        **dict(base),
        "ok": True,
        "probed": probed,
        "live": True,
        "results": results,
        "all_deny_probes_negative": None if incomplete else deny_ok,
        "negative_control_ok": neg_ok,
        "live_evidence": evidence,
        "honesty": (
            "SEC-P4b guest_live wired to eval microVM hooks. "
            "Deny-escape requires escape_executor; host allowlist ≠ guest escape. "
            "≠ sandbox_real_isolation / process_split_authorized / certification."
        ),
    }


def run_linux_microvm_probes(
    *,
    mode: str = MODE_GUEST_SIM,
    catalog: Optional[Mapping[str, Any]] = None,
    admit: Optional[Mapping[str, Any]] = None,
    hooks: Optional[Mapping[str, Any]] = None,
    escape_executor: Optional[EscapeExecutor] = None,
) -> Dict[str, Any]:
    """Run SEC-P4 Linux probed path. Never auto-covered; never process_split.

    ``guest_sim`` completes probes with simulated deny/allow matching expect.
    ``guest_live`` (SEC-P4b) requires AIPLAT_EVAL_T12_GUEST_LIVE=1, wires eval
    microVM hooks, runs negative_control via host allowlist CLI, and only
    completes deny-escape when ``escape_executor`` is injected (no fake green).
    """
    m = str(mode or MODE_GUEST_SIM).strip()
    if m not in _VALID_MODES:
        raise SecurityT12P4Error(f"invalid_mode:{mode}")

    cat = dict(catalog) if catalog is not None else load_t12_escape_probes()
    probes = [dict(x) for x in (cat.get("probes") or []) if isinstance(x, Mapping)]
    adm = dict(admit) if admit is not None else _try_microvm_admit()
    os_name = str(adm.get("os") or platform.system().lower())
    linux = bool(adm.get("linux")) if "linux" in adm else os_name == "linux"
    admit_ready = bool(adm.get("admit_ready"))
    opt_in = _probes_opt_in()

    base = {
        "schema": RUN_SCHEMA,
        "mode": m,
        "os": os_name,
        "linux": linux,
        "admit_ready": admit_ready,
        "opt_in": opt_in,
        "sandbox_real_isolation": False,
        "process_split_authorized": False,
        "accuracy_claim": False,
        "security_certification": False,
        "claim_eligible": False,
    }

    if not opt_in:
        dry = run_escape_probes(catalog=cat, live=False)
        return {
            **base,
            "ok": True,
            "probed": False,
            "live": False,
            "results": dry.get("results") or [],
            "all_deny_probes_negative": None,
            "negative_control_ok": None,
            "honesty": "SEC-P4 requires AIPLAT_EVAL_T12_PROBES=1; dry inventory only.",
        }

    if not linux:
        results = [
            {
                "probe_id": p.get("probe_id"),
                "kind": p.get("kind"),
                "expect": p.get("expect"),
                "status": "skipped_non_linux",
                "observed": None,
                "ok": False,
                "detail": "sec_p4_darwin_hard_lock",
            }
            for p in probes
        ]
        return {
            **base,
            "ok": False,
            "probed": False,
            "live": False,
            "results": results,
            "all_deny_probes_negative": False,
            "negative_control_ok": False,
            "honesty": "SEC-P4 probed path is Linux-only; Darwin never isolation_probed.",
        }

    if not admit_ready:
        results = [
            {
                "probe_id": p.get("probe_id"),
                "kind": p.get("kind"),
                "expect": p.get("expect"),
                "status": "admit_not_ready",
                "observed": None,
                "ok": None,
                "detail": "need_kvm_and_host_ok",
            }
            for p in probes
        ]
        return {
            **base,
            "ok": False,
            "probed": False,
            "live": False,
            "results": results,
            "all_deny_probes_negative": None,
            "negative_control_ok": None,
            "honesty": "SEC-P4 needs isolation_admitted (admit_ready) before probed.",
        }

    if m == MODE_GUEST_LIVE:
        if not _guest_live_opt_in():
            return {
                **base,
                "ok": False,
                "probed": False,
                "live": False,
                "results": [
                    {
                        "probe_id": p.get("probe_id"),
                        "kind": p.get("kind"),
                        "expect": p.get("expect"),
                        "status": "guest_live_opt_in_required",
                        "observed": None,
                        "ok": None,
                        "detail": "set_AIPLAT_EVAL_T12_GUEST_LIVE=1",
                    }
                    for p in probes
                ],
                "all_deny_probes_negative": None,
                "negative_control_ok": None,
                "honesty": (
                    "guest_live requires explicit AIPLAT_EVAL_T12_GUEST_LIVE=1; "
                    "still ≠ isolation certification."
                ),
            }
        return _run_guest_live_probes(
            probes,
            base=base,
            hooks=hooks,
            escape_executor=escape_executor,
        )

    # guest_sim — complete probes with simulated outcomes matching expect
    results: List[Dict[str, Any]] = []
    deny_ok = True
    neg_ok = True
    for p in probes:
        expect = str(p.get("expect") or "deny")
        kind = str(p.get("kind") or "")
        if expect == "deny":
            observed = "denied_by_guest_sim"
            ok = True
            status = "guest_sim_ok"
        elif expect == "allow" or kind == "negative_control":
            observed = "allowed_by_guest_sim"
            ok = True
            status = "guest_sim_ok"
        else:
            observed = None
            ok = False
            status = "guest_sim_unknown_expect"
            deny_ok = False
        if expect == "deny" and not ok:
            deny_ok = False
        if (expect == "allow" or kind == "negative_control") and not ok:
            neg_ok = False
        results.append(
            {
                "probe_id": p.get("probe_id"),
                "kind": kind,
                "expect": expect,
                "status": status,
                "observed": observed,
                "ok": ok,
                "detail": "sec_p4_guest_sim_no_host_mutation",
            }
        )

    probed = bool(results) and deny_ok and neg_ok
    return {
        **base,
        "ok": True,
        "probed": probed,
        "live": False,
        "results": results,
        "all_deny_probes_negative": deny_ok,
        "negative_control_ok": neg_ok,
        "honesty": (
            "SEC-P4 guest_sim completed escape probes without host mutation. "
            "isolation_probed candidate only; covered needs human_review. "
            "guest_sim ≠ sandbox_real_isolation / certification."
        ),
    }


def security_sec_p4_status(
    *,
    mode: str = MODE_GUEST_SIM,
    human_review: bool = False,
    human_reviewer: str = "",
    admit: Optional[Mapping[str, Any]] = None,
    hooks: Optional[Mapping[str, Any]] = None,
    escape_executor: Optional[EscapeExecutor] = None,
) -> Dict[str, Any]:
    """Facade-friendly SEC-P4/P4b status: probed path + isolation state machine."""
    adm = dict(admit) if admit is not None else _try_microvm_admit()
    probe_run = run_linux_microvm_probes(
        mode=mode,
        admit=adm,
        hooks=hooks,
        escape_executor=escape_executor,
    )
    isolation = evaluate_isolation_status(
        admit=adm,
        probe_run=probe_run,
        human_review=bool(human_review),
        human_reviewer=str(human_reviewer or ""),
    )
    return {
        "schema": STATUS_SCHEMA,
        "ok": True,
        "slice": "SEC-P4",
        "mode": str(mode or MODE_GUEST_SIM),
        "admit": {
            "linux": adm.get("linux"),
            "admit_ready": adm.get("admit_ready"),
            "kvm_device": adm.get("kvm_device"),
            "host_ok": adm.get("host_ok"),
            "microvm_covered": False,
        },
        "probe_run": probe_run,
        "live_evidence": probe_run.get("live_evidence"),
        "isolation": isolation,
        "isolation_status": isolation.get("isolation_status"),
        "isolation_probed": isolation.get("isolation_status")
        in {ISOLATION_PROBED, ISOLATION_COVERED},
        "isolation_covered": bool(isolation.get("isolation_covered")),
        "sandbox_real_isolation": False,
        "process_split_authorized": False,
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "SEC-P4/P4b Linux microVM probed path. "
            "guest_sim can reach isolation_probed; guest_live needs escape_executor "
            "for deny probes; covered needs human review; "
            "never accuracy_claim / process_split_authorized."
        ),
    }
