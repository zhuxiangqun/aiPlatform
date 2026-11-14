"""P1-4: Linux/KVM real-escape harness (engineering).

Acceptance (improvement plan):
  guest_boot + host file / network / device / privilege probes + negative control
  → at most ``isolation_probed``; **never** auto ``isolation_covered``.

Hard locks:
  - HTTP black-box ≠ escape (reject http_only evidence)
  - Darwin / no guest_boot live → unknown / incomplete
  - guest_sim path is engineering only (not certification)
  - accuracy_claim / security_certification / claim_eligible stay false
"""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from core.apps.eval.service.isolation_t12 import (
    ISOLATION_COVERED,
    ISOLATION_PROBED,
    ISOLATION_UNKNOWN,
    evaluate_isolation_status,
)
from core.apps.eval.service.security_t12_p4 import (
    MODE_GUEST_LIVE,
    MODE_GUEST_SIM,
    run_linux_microvm_probes,
)

SCHEMA = "eval.security_p1_4_kvm_escape.v1"
PROBE_SCHEMA = "eval.security_p1_4_kvm_escape_probes.v1"
STATUS_SCHEMA = "eval.security_p1_4_status.v1"

REQUIRED_KINDS = frozenset(
    {"host_file", "network", "device", "privilege", "negative_control"}
)

# GuestChannel: execute one probe inside guest; return observed outcome.
GuestChannel = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class SecurityP14Error(ValueError):
    """Fail-closed P1-4 KVM escape error."""


def default_p14_probes_path() -> Path:
    """返回 P1-4 KVM escape probe 种子 JSON 的默认路径。"""
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "agent_capability"
        / "security"
        / "p1_4_kvm_escape_probes.v1.json"
    )


def load_p14_escape_probes(*, path: Optional[Path] = None) -> Dict[str, Any]:
    """加载并校验 P1-4 escape probe 目录（claim 锁保持关闭）。

    Args:
        path: 可选自定义 JSON 路径；缺省用 ``default_p14_probes_path()``。

    Returns:
        probe 目录 dict（含 ``probes``，且强制 ``accuracy_claim`` 等为 false）。
    """
    p = Path(path) if path else default_p14_probes_path()
    if not p.is_file():
        raise SecurityP14Error(f"p14_probes_missing:{p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise SecurityP14Error("p14_probes_not_object")
    if str(raw.get("schema") or "") != PROBE_SCHEMA:
        raise SecurityP14Error(f"p14_probes_schema_mismatch:{raw.get('schema')}")
    probes = raw.get("probes")
    if not isinstance(probes, list) or len(probes) < 5:
        raise SecurityP14Error("p14_probes_min_5")
    kinds = {str((x or {}).get("kind") or "") for x in probes if isinstance(x, Mapping)}
    missing = REQUIRED_KINDS - kinds
    if missing:
        raise SecurityP14Error(f"p14_kinds_missing:{sorted(missing)}")
    out = dict(raw)
    out["accuracy_claim"] = False
    out["security_certification"] = False
    out["claim_eligible"] = False
    return out


def _p14_live_opt_in() -> bool:
    return os.environ.get("AIPLAT_EVAL_P1_4_LIVE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _t12_probes_opt_in() -> bool:
    return os.environ.get("AIPLAT_EVAL_T12_PROBES", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def assert_not_http_escape(*, evidence_kind: str = "") -> None:
    """禁止将 HTTP 黑盒证据登记为沙箱逃逸证据。

    Args:
        evidence_kind: 证据类型标识；``http`` / ``http_only`` / ``attack_sim`` /
            ``s7_http`` 一律拒绝。
    """
    kind = str(evidence_kind or "").strip().lower()
    if kind in {"http", "http_only", "attack_sim", "s7_http"}:
        raise SecurityP14Error("http_is_not_escape;use_guest_channel")


def scripted_guest_channel(
    *,
    deny_escape: bool = False,
    break_negative: bool = False,
) -> GuestChannel:
    """Deterministic CI channel. deny_escape=True simulates successful breakout.

    Args:
        deny_escape: deny_escape 参数。
        break_negative: break_negative 参数。
    """

    def _run(probe: Mapping[str, Any]) -> Mapping[str, Any]:
        kind = str(probe.get("kind") or "")
        expect = str(probe.get("expect") or "deny")
        if kind == "negative_control" or expect == "allow":
            if break_negative:
                return {
                    "ok": False,
                    "escaped": False,
                    "observed": "echo_failed",
                    "status": "p14_neg_control_fail",
                    "detail": "scripted_break_negative",
                }
            return {
                "ok": True,
                "escaped": False,
                "observed": "echo_ok",
                "status": "p14_neg_control_ok",
                "detail": "scripted_guest",
            }
        if deny_escape:
            return {
                "ok": False,
                "escaped": True,
                "observed": "host_resource_reached",
                "status": "p14_escape_detected",
                "detail": f"scripted_escape:{kind}",
            }
        return {
            "ok": True,
            "escaped": False,
            "observed": "denied_by_guest",
            "status": "p14_escape_denied",
            "detail": f"scripted_deny:{kind}",
        }

    return _run


def build_escape_executor(
    channel: GuestChannel,
) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    """Adapt GuestChannel → SEC-P4 escape_executor (ok == expectation met).

    Args:
        channel: channel 参数。
    """

    def _exec(probe: Mapping[str, Any]) -> Mapping[str, Any]:
        out = dict(channel(probe) or {})
        expect = str(probe.get("expect") or "deny")
        kind = str(probe.get("kind") or "")
        escaped = bool(out.get("escaped"))
        is_neg = expect == "allow" or kind == "negative_control"
        if is_neg:
            ok = bool(out.get("ok")) and not escaped
            status = str(
                out.get("status") or ("p14_neg_ok" if ok else "p14_neg_fail")
            )
        else:
            # Isolation holds when guest cannot reach host resource
            ok = (not escaped) and (out.get("ok") is not False)
            if escaped:
                ok = False
            status = str(
                out.get("status")
                or (
                    "p14_escape_detected"
                    if escaped
                    else ("p14_escape_denied" if ok else "p14_escape_uncertain")
                )
            )
        return {
            "ok": ok,
            "observed": out.get("observed"),
            "status": status,
            "detail": str(out.get("detail") or "guest_channel"),
            "escaped": escaped,
        }

    return _exec


def _as_t12_catalog(p14: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema": "eval.security_t12_escape_probes.v1",
        "version": str(p14.get("version") or "1.0.0"),
        "threat_id": "T12",
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "probes": list(p14.get("probes") or []),
    }


def _base_fail(
    *,
    mode: str,
    error: str,
    live_evidence: Mapping[str, Any],
    honesty: str,
) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "ok": False,
        "mode": mode,
        "slice": "P1-4",
        "probed": False,
        "isolation_status": ISOLATION_UNKNOWN,
        "isolation_probed": False,
        "isolation_covered": False,
        "error": error,
        "live_evidence": dict(live_evidence),
        "accuracy_claim": False,
        "security_certification": False,
        "claim_eligible": False,
        "honesty": honesty,
    }


def run_p1_4_kvm_escape(
    *,
    mode: str = MODE_GUEST_SIM,
    guest_channel: Optional[GuestChannel] = None,
    guest_boot: Optional[bool] = None,
    admit: Optional[Mapping[str, Any]] = None,
    evidence_kind: str = "kvm_guest",
    human_review: bool = False,
    human_reviewer: str = "",
    catalog: Optional[Mapping[str, Any]] = None,
    hooks: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Run P1-4 escape suite. Never auto-covered; HTTP evidence rejected.

    Args:
        mode: 执行/评测模式。
        guest_channel: guest_channel 参数。
        guest_boot: guest_boot 参数。
        admit: admit 参数。
        evidence_kind: evidence_kind 参数。
        human_review: human_review 参数。
        human_reviewer: human_reviewer 参数。
        catalog: catalog 参数。
        hooks: hooks 参数。
    """
    assert_not_http_escape(evidence_kind=evidence_kind)

    p14_cat = dict(catalog) if catalog is not None else load_p14_escape_probes()
    t12_cat = _as_t12_catalog(p14_cat)
    m = str(mode or MODE_GUEST_SIM).strip()
    if m not in {MODE_GUEST_SIM, MODE_GUEST_LIVE}:
        raise SecurityP14Error(f"invalid_mode:{mode}")

    live_evidence: Dict[str, Any] = {
        "guest_boot": guest_boot,
        "evidence_kind": evidence_kind,
        "http_is_escape": False,
    }

    if not _t12_probes_opt_in():
        return _base_fail(
            mode=m,
            error="AIPLAT_EVAL_T12_PROBES_required",
            live_evidence=live_evidence,
            honesty="P1-4 requires AIPLAT_EVAL_T12_PROBES=1 (same gate as SEC-P4).",
        )

    adm = (
        dict(admit)
        if admit is not None
        else {
            "os": platform.system().lower(),
            "linux": platform.system().lower() == "linux",
            "admit_ready": False,
            "kvm_device": False,
            "host_ok": False,
        }
    )

    if m == MODE_GUEST_LIVE:
        if not _p14_live_opt_in():
            return _base_fail(
                mode=m,
                error="AIPLAT_EVAL_P1_4_LIVE_required",
                live_evidence=live_evidence,
                honesty="P1-4 live requires AIPLAT_EVAL_P1_4_LIVE=1 + guest channel.",
            )
        if not os.environ.get("AIPLAT_EVAL_T12_GUEST_LIVE", "").strip():
            return _base_fail(
                mode=m,
                error="AIPLAT_EVAL_T12_GUEST_LIVE_required",
                live_evidence=live_evidence,
                honesty="P1-4 live bridges SEC-P4b; set AIPLAT_EVAL_T12_GUEST_LIVE=1.",
            )
        if guest_boot is not True:
            return _base_fail(
                mode=m,
                error="guest_boot_required",
                live_evidence=live_evidence,
                honesty=(
                    "P1-4 live deny-escape needs guest_boot=true. HTTP≠escape. ≠cert."
                ),
            )
        if guest_channel is None:
            return _base_fail(
                mode=m,
                error="guest_channel_required",
                live_evidence=live_evidence,
                honesty="Inject GuestChannel for in-guest probes; host Python ≠ escape.",
            )

        executor = build_escape_executor(guest_channel)
        live_hooks = dict(hooks) if hooks is not None else {
            "probe_runtime": lambda: {"ok": True},
            "run_allowlisted_cli": lambda _argv: {
                "ok": True,
                "audit": {"source": "p14_neg_stub"},
            },
            "guest_boot_cached": lambda: True,
            "probe_guest_boot": lambda: {"ok": True, "audit": {"guest_boot": True}},
            "microvm_status": lambda: {
                "ok": True,
                "guest_boot_authorized": True,
                "kvm_available": True,
                "microvm_host_ok": True,
            },
            "microvm_can_admit_runners": lambda: True,
        }
        probe_run = run_linux_microvm_probes(
            mode=MODE_GUEST_LIVE,
            catalog=t12_cat,
            admit=adm,
            hooks=live_hooks,
            escape_executor=executor,
        )
        # Cross-check negative_control via guest channel (CLI stub alone ≠ guest)
        channel_neg_ok = True
        for np in t12_cat.get("probes") or []:
            if not isinstance(np, Mapping):
                continue
            if str(np.get("kind")) != "negative_control":
                continue
            cout = dict(guest_channel(np) or {})
            if not bool(cout.get("ok")):
                channel_neg_ok = False
                results = list(probe_run.get("results") or [])
                results.append(
                    {
                        "probe_id": np.get("probe_id"),
                        "kind": "negative_control",
                        "expect": "allow",
                        "status": "p14_channel_neg_fail",
                        "observed": cout.get("observed"),
                        "ok": False,
                        "detail": "guest_channel_negative_control",
                    }
                )
                probe_run = dict(probe_run)
                probe_run["results"] = results
                probe_run["probed"] = False
                probe_run["negative_control_ok"] = False
        if channel_neg_ok and probe_run.get("negative_control_ok") is not False:
            pass
        live_evidence["guest_boot"] = True
        live_evidence["channel"] = "injected"
    else:
        probe_run = run_linux_microvm_probes(
            mode=MODE_GUEST_SIM,
            catalog=t12_cat,
            admit=adm,
        )
        live_evidence["channel"] = "guest_sim"

    isolation = evaluate_isolation_status(
        admit=adm,
        probe_run=probe_run,
        human_review=bool(human_review),
        human_reviewer=str(human_reviewer or ""),
    )
    if not human_review and isolation.get("isolation_status") == ISOLATION_COVERED:
        isolation = dict(isolation)
        isolation["isolation_status"] = ISOLATION_PROBED
        isolation["isolation_covered"] = False

    status = isolation.get("isolation_status")
    return {
        "schema": SCHEMA,
        "ok": bool(probe_run.get("ok")),
        "mode": m,
        "slice": "P1-4",
        "probe_run": probe_run,
        "isolation": isolation,
        "isolation_status": status,
        "isolation_probed": status in {ISOLATION_PROBED, ISOLATION_COVERED},
        "isolation_covered": bool(isolation.get("isolation_covered")),
        "probed": bool(probe_run.get("probed")),
        "live_evidence": live_evidence,
        "required_kinds": sorted(REQUIRED_KINDS),
        "sandbox_real_isolation": False,
        "process_split_authorized": False,
        "accuracy_claim": False,
        "security_certification": False,
        "claim_eligible": False,
        "honesty": (
            "P1-4 KVM escape: guest_boot + host_file/network/device/privilege + neg. "
            "HTTP≠escape. Max isolation_probed without human_review; ≠ certification."
        ),
    }


def security_p1_4_status(
    *,
    mode: str = MODE_GUEST_SIM,
    admit: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Inventory / engineering status for P1-4 (claim locks false).

    Args:
        mode: 执行/评测模式。
        admit: admit 参数。
    """
    cat = load_p14_escape_probes()
    kinds = sorted(
        {
            str(p.get("kind"))
            for p in (cat.get("probes") or [])
            if isinstance(p, Mapping)
        }
    )
    return {
        "schema": STATUS_SCHEMA,
        "ok": True,
        "slice": "P1-4",
        "mode_default": mode,
        "catalog_version": cat.get("version"),
        "kinds": kinds,
        "required_kinds_met": set(kinds) >= REQUIRED_KINDS,
        "live_opt_in": _p14_live_opt_in(),
        "t12_probes_opt_in": _t12_probes_opt_in(),
        "admit_hint": {
            "linux": (admit or {}).get("linux"),
            "admit_ready": (admit or {}).get("admit_ready"),
        }
        if admit
        else None,
        "sec_p4_bridge": "run_linux_microvm_probes + escape_executor",
        "max_auto_status": ISOLATION_PROBED,
        "accuracy_claim": False,
        "security_certification": False,
        "claim_eligible": False,
        "honesty": (
            "P1-4 status inventory. Live needs AIPLAT_EVAL_P1_4_LIVE + "
            "AIPLAT_EVAL_T12_GUEST_LIVE + guest_boot + GuestChannel. Never auto covered."
        ),
    }
