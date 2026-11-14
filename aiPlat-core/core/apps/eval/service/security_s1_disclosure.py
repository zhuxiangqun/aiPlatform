"""SEC-P2a: S1 live-attack pack → CoreFacade + OOS/untested family disclosure.

Read-only facilitation:
- Load S1 pack + optional aggregate evidence (never re-runs live attacks here)
- Auto-list untested / below_min_n / deferred / OOS threat families (C15)
- Map S1 categories → threat families for coverage disclosure only

Honesty locks:
- S1 text-layer ≠ T05-exec / tool execution safety
- accuracy_claim / security_certification always false
- No one-click certification
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.security_family_report import (
    build_security_family_report,
    load_threat_family_catalog,
)

S1_PACK_SCHEMA = "eval.s1.live_attack_pack.v0"
STATUS_SCHEMA = "eval.security_sec_p2a_status.v1"
DISCLOSURE_SCHEMA = "eval.security_untested_oos_disclosure.v1"

# Engineering category→family map (S1 text layer). tool_abuse ≠ L3 T06 exec.
S1_CATEGORY_TO_THREAT: Dict[str, str] = {
    "prompt_injection": "T01",
    "jailbreak": "T02",
    "data_exfiltration": "T03",
    "tool_abuse": "T06",  # disclosure only; S1 has no live tools
    "benign_control": "T15",
}

OOS_LABELS: Dict[str, str] = {
    "OOS-01": "model_poison_backdoor",
    "OOS-02": "training_data_contamination",
    "OOS-03": "model_extraction_membership",
    "OOS-04": "full_cross_tenant_isolation",
    "OOS-05": "multi_agent_collusion",
    "OOS-06": "deep_mcp_supply_chain",
    "OOS-07": "full_system_prompt_extraction",
    "OOS-08": "fairness_bias",
    "OOS-09": "classic_appsec_non_agent",
}


class SecurityS1DisclosureError(ValueError):
    """Fail-closed S1 / OOS disclosure error."""


def default_s1_pack_path() -> Path:
    # workspace root / packages/aiplat-evaluation/...
    # security_s1_disclosure.py → service → eval → apps → core → aiPlat-core → root
    """default_s1_pack_path。
    """
    root = Path(__file__).resolve().parents[5]
    return (
        root
        / "packages"
        / "aiplat-evaluation"
        / "docs"
        / "a3"
        / "s1_live_attacks.v0.json"
    )


def default_s1_aggregate_path() -> Path:
    """default_s1_aggregate_path。
    """
    root = Path(__file__).resolve().parents[5]
    return (
        root
        / "packages"
        / "aiplat-evaluation"
        / "docs"
        / "a3"
        / "evidence"
        / "s1_prod_model_aggregate.v1.json"
    )


def load_s1_live_attack_pack(*, path: Optional[Path] = None) -> Dict[str, Any]:
    """加载 s1_live_attack_pack。

    Args:
        path: 文件或目录路径。
    """
    p = Path(path) if path else default_s1_pack_path()
    if not p.is_file():
        raise SecurityS1DisclosureError(f"s1_pack_missing:{p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise SecurityS1DisclosureError("s1_pack_not_object")
    if str(raw.get("schema") or "") != S1_PACK_SCHEMA:
        raise SecurityS1DisclosureError(f"s1_pack_schema_mismatch:{raw.get('schema')}")
    cases = raw.get("cases")
    if not isinstance(cases, list) or len(cases) < 20:
        raise SecurityS1DisclosureError("s1_pack_min_20_cases")
    out = dict(raw)
    out["path"] = str(p)
    return out


def load_s1_aggregate_evidence(*, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """加载 s1_aggregate_evidence。

    Args:
        path: 文件或目录路径。
    """
    p = Path(path) if path else default_s1_aggregate_path()
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, Mapping):
        return None
    out = dict(raw)
    out["path"] = str(p)
    # Force honesty locks on read
    out["accuracy_claim"] = False
    out["security_certification"] = False
    return out


def summarize_s1_pack(pack: Mapping[str, Any]) -> Dict[str, Any]:
    """summarize_s1_pack。

    Args:
        pack: pack 参数。
    """
    cases = [c for c in (pack.get("cases") or []) if isinstance(c, Mapping)]
    by_cat: Dict[str, int] = {}
    threat_hits: Dict[str, int] = {}
    for c in cases:
        cat = str(c.get("category") or "unknown")
        by_cat[cat] = by_cat.get(cat, 0) + 1
        tid = S1_CATEGORY_TO_THREAT.get(cat)
        if tid:
            threat_hits[tid] = threat_hits.get(tid, 0) + 1
    return {
        "n_cases": len(cases),
        "by_category": by_cat,
        "threat_family_hits": threat_hits,
        "live_skill_tools": False,
        "eval_layer": "L1_text",
        "mapped_threat_families": sorted(threat_hits.keys()),
        "honesty": (
            "S1 categories map to threat families for disclosure only; "
            "tool_abuse category ≠ T06 L3 execution; accuracy_claim=false"
        ),
    }


def build_untested_oos_disclosure(
    *,
    by_case: Optional[Mapping[str, Mapping[str, Any]]] = None,
    catalog: Optional[Mapping[str, Any]] = None,
    s1_summary: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """C15: auto-list untested / below_min_n / deferred / OOS families.

    Args:
        by_case: by_case 参数。
        catalog: catalog 参数。
        s1_summary: s1_summary 参数。
    """
    cat = dict(catalog) if catalog is not None else load_threat_family_catalog()
    report = build_security_family_report(
        by_case=by_case or {}, catalog=cat, eval_layer="L1", pack_id="disclosure"
    )
    oos_ids = [str(x) for x in (cat.get("out_of_scope") or [])]
    oos_rows = [
        {"id": oid, "name": OOS_LABELS.get(oid, oid)} for oid in oos_ids
    ]
    fams = cat.get("families") if isinstance(cat.get("families"), Mapping) else {}
    deferred = sorted(
        str(fid)
        for fid, meta in fams.items()
        if isinstance(meta, Mapping)
        and str(meta.get("status") or "").startswith("deferred")
    )
    s1_mapped = [
        str(x)
        for x in ((s1_summary or {}).get("mapped_threat_families") or [])
    ]
    # Families with S1 annotation hits are "s1_annotated" not scored runs
    s1_only = sorted(s1_mapped)

    return {
        "schema": DISCLOSURE_SCHEMA,
        "ok": True,
        "untested_threat_families": list(report.get("untested_threat_families") or []),
        "below_min_n_families": list(report.get("below_min_n_families") or []),
        "deferred_threat_families": deferred
        or list(report.get("deferred_threat_families") or []),
        "out_of_scope": oos_rows,
        "oos_ids": oos_ids,
        "s1_annotated_threat_families": s1_only,
        "engineering_ready_families": list(
            report.get("engineering_ready_families") or []
        ),
        "l5_declare_allowed_families": [],
        "family_gates": report.get("family_gates"),
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "Auto-generated untested/below_min_n/deferred/OOS lists for L5 honesty. "
            "s1_annotated ≠ scored live security run. Never unlocks accuracy_claim."
        ),
    }


def security_sec_p2a_status(
    *,
    by_case: Optional[Mapping[str, Mapping[str, Any]]] = None,
    pack_path: Optional[Path] = None,
    aggregate_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Facade-friendly SEC-P2a: S1 pack card + OOS/untested disclosure.

    Args:
        by_case: by_case 参数。
        pack_path: 路径。
        aggregate_path: 路径。
    """
    pack = load_s1_live_attack_pack(path=pack_path)
    summary = summarize_s1_pack(pack)
    aggregate = load_s1_aggregate_evidence(path=aggregate_path)
    # If no scored by_case, use S1 category hits as annotation-only coverage
    cases_for_report = by_case
    if cases_for_report is None:
        cases_for_report = {}
        for i, c in enumerate(pack.get("cases") or []):
            if not isinstance(c, Mapping):
                continue
            cat = str(c.get("category") or "")
            tid = S1_CATEGORY_TO_THREAT.get(cat)
            if not tid:
                continue
            cid = str(c.get("id") or f"s1-{i}")
            cases_for_report[cid] = {"threat_ids": [tid], "ok": True}
    disclosure = build_untested_oos_disclosure(
        by_case=cases_for_report, s1_summary=summary
    )
    # Mark annotation-only: clear rates for honesty
    disclosure["annotation_only"] = by_case is None

    agg_view = None
    if aggregate:
        agg_view = {
            "prod_model": aggregate.get("prod_model"),
            "asr": aggregate.get("asr"),
            "leak_rate": aggregate.get("leak_rate"),
            "false_refusal_rate": aggregate.get("false_refusal_rate"),
            "llm_ok_n": aggregate.get("llm_ok_n"),
            "gate_ok": aggregate.get("gate_ok"),
            "suite_id": aggregate.get("suite_id"),
            "path": aggregate.get("path"),
            "accuracy_claim": False,
            "not_security_certification": True,
        }

    return {
        "schema": STATUS_SCHEMA,
        "ok": True,
        "slice": "SEC-P2a",
        "s1_pack": {
            "schema": pack.get("schema"),
            "path": pack.get("path"),
            "n_cases": summary["n_cases"],
            "by_category": summary["by_category"],
            "threat_family_hits": summary["threat_family_hits"],
            "live_skill_tools": False,
            "accuracy_claim": False,
            "not_security_certification": True,
        },
        "s1_summary": summary,
        "s1_aggregate": agg_view,
        "disclosure": disclosure,
        "untested_threat_families": disclosure.get("untested_threat_families"),
        "below_min_n_families": disclosure.get("below_min_n_families"),
        "deferred_threat_families": disclosure.get("deferred_threat_families"),
        "oos_ids": disclosure.get("oos_ids"),
        "claim_eligible": False,
        "accuracy_claim": False,
        "security_certification": False,
        "honesty": (
            "SEC-P2a S1→Facade read-only + OOS/untested auto-list. "
            "S1 metrics ≠ security certification. accuracy_claim=false."
        ),
    }
