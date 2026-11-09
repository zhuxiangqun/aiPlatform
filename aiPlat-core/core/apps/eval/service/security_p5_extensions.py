"""SEC-P5: T11 deferred graduate gate + deep OOS extension disclosure.

Scope:
  - Codify when T11 may leave deferred_m2 (all conditions; never auto-graduate)
  - Catalog-only deep supply-chain / model-poison extension cards (stay OOS)
  - Keep T13-escape deferred and process_split_authorized=false

Honesty locks:
  - accuracy_claim / security_certification / claim_eligible always false
  - OOS-01/02/03/05/06 never claimed covered by this slice
  - T13 shallow (P1c) ≠ OOS-06 deep MCP supply chain
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import yaml

from core.apps.eval.service.security_family_report import load_threat_family_catalog
from core.apps.eval.service.security_s1_disclosure import OOS_LABELS

GATES_SCHEMA = "eval.security_p5_extension_gates.v1"
STATUS_SCHEMA = "eval.security_sec_p5_status.v1"
T11_GATE_SCHEMA = "eval.security_t11_deferred_gate.v1"
OOS_EXT_SCHEMA = "eval.security_oos_extension_disclosure.v1"


class SecurityP5ExtensionError(ValueError):
    """Fail-closed SEC-P5 extension error."""


def default_p5_gates_path() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "eval"
        / "agent_capability"
        / "security"
        / "p5_extension_gates.v1.yaml"
    )


def load_p5_extension_gates(*, path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else default_p5_gates_path()
    if not p.is_file():
        raise SecurityP5ExtensionError(f"p5_gates_missing:{p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise SecurityP5ExtensionError("p5_gates_not_object")
    if str(raw.get("schema") or "") != GATES_SCHEMA:
        raise SecurityP5ExtensionError(f"p5_gates_schema_mismatch:{raw.get('schema')}")
    if not isinstance(raw.get("t11_deferred"), Mapping):
        raise SecurityP5ExtensionError("p5_t11_deferred_missing")
    out = dict(raw)
    out["path"] = str(p)
    out["accuracy_claim"] = False
    out["security_certification"] = False
    out["claim_eligible"] = False
    return out


def evaluate_t11_deferred_gate(
    *,
    gates: Optional[Mapping[str, Any]] = None,
    evidence: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate T11 graduate conditions. Default: remains deferred.

    ``evidence`` optional keys (all default false/empty):
      multi_agent_runtime_wired: bool
      handoff_session_trace_harness: bool
      fixture_count: int
      human_authorize_graduate: bool
      human_reviewer: str
    """
    g = dict(gates) if gates is not None else load_p5_extension_gates()
    t11 = dict(g.get("t11_deferred") or {})
    reqs = [dict(x) for x in (t11.get("graduate_requires_all") or []) if isinstance(x, Mapping)]
    ev = dict(evidence or {})

    checks: List[Dict[str, Any]] = []
    for req in reqs:
        rid = str(req.get("id") or "")
        ok = False
        detail = ""
        if rid == "multi_agent_runtime_wired":
            ok = bool(ev.get("multi_agent_runtime_wired"))
            detail = "runtime_wired" if ok else "runtime_not_wired"
        elif rid == "handoff_session_trace_harness":
            ok = bool(ev.get("handoff_session_trace_harness"))
            detail = "harness_ready" if ok else "harness_missing"
        elif rid == "min_fixture_pack":
            min_n = int(req.get("min_n") or 5)
            n = int(ev.get("fixture_count") or 0)
            ok = n >= min_n
            detail = f"fixtures={n}_min={min_n}"
        elif rid == "human_authorize_graduate":
            ok = bool(ev.get("human_authorize_graduate")) and bool(
                str(ev.get("human_reviewer") or "").strip()
            )
            detail = "authorized" if ok else "human_authorize_required"
        else:
            ok = False
            detail = f"unknown_requirement:{rid}"
        checks.append(
            {
                "id": rid,
                "description": req.get("description"),
                "ok": ok,
                "detail": detail,
            }
        )

    all_ok = bool(checks) and all(bool(c.get("ok")) for c in checks)
    graduated = bool(all_ok)
    status = "graduated_engineering" if graduated else str(t11.get("status") or "deferred_m2")

    return {
        "schema": T11_GATE_SCHEMA,
        "ok": True,
        "threat_id": "T11",
        "related_oos": list(t11.get("related_oos") or ["OOS-05"]),
        "deferred": not graduated,
        "graduated": graduated,
        "status": status,
        "checks": checks,
        "claim_forbidden": list(t11.get("claim_forbidden_until_graduate") or []),
        "accuracy_claim": False,
        "security_certification": False,
        "claim_eligible": False,
        "honesty": (
            "T11 multi-agent abuse remains deferred until every graduate "
            "condition is explicitly satisfied; ≠ OOS-05 covered; ≠ certification."
        ),
    }


def build_oos_extension_disclosure(
    *,
    gates: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Structured OOS extension cards for model poison + deep supply chain + T11."""
    g = dict(gates) if gates is not None else load_p5_extension_gates()
    cards: List[Dict[str, Any]] = []

    # T11 / OOS-05
    t11 = dict(g.get("t11_deferred") or {})
    cards.append(
        {
            "card_id": "t11_multi_agent",
            "threat_id": "T11",
            "oos_ids": list(t11.get("related_oos") or ["OOS-05"]),
            "status": str(t11.get("status") or "deferred_m2"),
            "claimable": False,
            "note": "handoff escape / multi-agent abuse deferred_m2",
        }
    )

    # Deep supply chain OOS-06
    dsc = dict(g.get("deep_supply_chain") or {})
    probes = [
        dict(x)
        for x in (dsc.get("extension_probes_catalog_only") or [])
        if isinstance(x, Mapping)
    ]
    cards.append(
        {
            "card_id": "deep_mcp_supply_chain",
            "threat_id": str(dsc.get("related_threat") or "T13"),
            "oos_ids": [str(dsc.get("deep_oos") or "OOS-06")],
            "status": str(dsc.get("status") or "oos_extension_card"),
            "shallow_slice": dsc.get("shallow_slice"),
            "claimable": False,
            "catalog_probe_ids": [str(p.get("id") or "") for p in probes],
            "note": str(dsc.get("honesty") or ""),
        }
    )

    # Model poison OOS-01/02/03
    mp = dict(g.get("model_poison") or {})
    mp_probes = [
        dict(x)
        for x in (mp.get("extension_probes_catalog_only") or [])
        if isinstance(x, Mapping)
    ]
    cards.append(
        {
            "card_id": "model_poison_training_extraction",
            "threat_id": None,
            "oos_ids": [str(x) for x in (mp.get("deep_oos") or ["OOS-01", "OOS-02", "OOS-03"])],
            "status": str(mp.get("status") or "oos_extension_card"),
            "claimable": False,
            "catalog_probe_ids": [str(p.get("id") or "") for p in mp_probes],
            "note": str(mp.get("honesty") or ""),
        }
    )

    # T13-escape still deferred
    esc = dict(g.get("t13_escape") or {})
    cards.append(
        {
            "card_id": "t13_escape",
            "threat_id": "T13-escape",
            "oos_ids": [],
            "status": str(esc.get("status") or "deferred_sec_p5"),
            "requires": esc.get("requires"),
            "claimable": False,
            "note": str(esc.get("honesty") or ""),
        }
    )

    oos_ids: List[str] = []
    for c in cards:
        for oid in c.get("oos_ids") or []:
            if oid not in oos_ids:
                oos_ids.append(str(oid))

    return {
        "schema": OOS_EXT_SCHEMA,
        "ok": True,
        "cards": cards,
        "oos_ids": oos_ids,
        "oos_labels": {oid: OOS_LABELS.get(oid, oid) for oid in oos_ids},
        "any_claimable": False,
        "accuracy_claim": False,
        "security_certification": False,
        "claim_eligible": False,
        "honesty": (
            "SEC-P5 publishes extension cards only. Catalog probes disclose OOS; "
            "they do not execute weight/MCP attacks or certify coverage."
        ),
    }


def evaluate_deep_supply_chain_boundary(
    *,
    gates: Optional[Mapping[str, Any]] = None,
    t13_shallow_ok: bool = False,
) -> Dict[str, Any]:
    """T13 shallow pass must not imply OOS-06 deep supply-chain coverage."""
    g = dict(gates) if gates is not None else load_p5_extension_gates()
    dsc = dict(g.get("deep_supply_chain") or {})
    return {
        "ok": True,
        "t13_shallow_ok": bool(t13_shallow_ok),
        "deep_oos": str(dsc.get("deep_oos") or "OOS-06"),
        "deep_covered": False,
        "process_split_authorized": False,
        "boundary_holds": True,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "Even if T13 allowlist shallow probes pass, OOS-06 deep MCP "
            "supply chain remains uncovered."
            if t13_shallow_ok
            else str(dsc.get("honesty") or "shallow≠deep")
        ),
    }


def security_sec_p5_status(
    *,
    t11_evidence: Optional[Mapping[str, Any]] = None,
    t13_shallow_ok: bool = False,
) -> Dict[str, Any]:
    """Facade-friendly SEC-P5 status card."""
    gates = load_p5_extension_gates()
    catalog = load_threat_family_catalog()
    families = catalog.get("families") if isinstance(catalog.get("families"), Mapping) else {}
    t11_fam = dict(families.get("T11") or {}) if isinstance(families.get("T11"), Mapping) else {}

    t11_gate = evaluate_t11_deferred_gate(gates=gates, evidence=t11_evidence)
    oos_ext = build_oos_extension_disclosure(gates=gates)
    deep_bound = evaluate_deep_supply_chain_boundary(
        gates=gates, t13_shallow_ok=bool(t13_shallow_ok)
    )

    return {
        "schema": STATUS_SCHEMA,
        "ok": True,
        "slice": "SEC-P5",
        "gates_version": gates.get("version"),
        "t11": t11_gate,
        "t11_catalog_status": t11_fam.get("status") or "deferred_m2",
        "oos_extensions": oos_ext,
        "deep_supply_chain_boundary": deep_bound,
        "process_split_authorized": False,
        "accuracy_claim": False,
        "security_certification": False,
        "claim_eligible": False,
        "honesty": (
            "SEC-P5: T11 deferred gate + OOS extension disclosure. "
            "No auto-graduate; no model-poison/MCP-depth certification."
        ),
    }
