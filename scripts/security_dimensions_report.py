#!/usr/bin/env python3
"""Security quality dimensions report (26-dim SoT = 25 + D26; A1+A2 semantics).

Contract (ledger_ok primary; schema_ok is alias):
  - ledger_ok / schema_ok = parseable, count, field rules, E⇒≥1 V|T
  - accounted_ok          = every P0 has owner; G has owner+gap+next (G allowed)
  - release_ok            = accounted_ok ∧ no unaccepted release-blocking gap
  - coverage_ok           = every P0 is E with empty gap
  - ledger ≠ accounted ≠ release ≠ coverage ≠ security_certification

Gates:
  default CI / --ledger-gate  → ledger_ok
  --release-gate              → ledger ∧ accounted ∧ release
  --claim-gate / --strict-gaps → ledger ∧ coverage  (claim only; not default publish)

ID stability: D01–D25 keep meaning; D26 appended (artifact authz). Do not renumber.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_YAML = ROOT / "reports" / "security" / "security_quality_dimensions.yaml"

STATUS_OK = frozenset({"E", "I", "O", "G"})
EVIDENCE_LEVELS = frozenset({"V", "T", "D", "U", "A"})
EXPECTED_COUNT = 26
HONESTY = "ledger_ok ≠ accounted_ok ≠ release_ok ≠ coverage_ok ≠ certification"


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as e:
        raise RuntimeError("PyYAML required: pip install pyyaml") from e
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("root_not_mapping")
    return raw


def _evidence_has_vt(evidence: Any) -> bool:
    if not isinstance(evidence, list) or not evidence:
        return False
    for item in evidence:
        if not isinstance(item, dict):
            continue
        if str(item.get("level") or "").upper() in ("V", "T"):
            return True
    return False


def _gap_open(d: Dict[str, Any]) -> bool:
    return bool(str(d.get("gap") or "").strip())


def _acceptance_block(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Prefer release_risk_acceptance; accept legacy risk_acceptance alias."""
    raw = d.get("release_risk_acceptance")
    if raw is None:
        raw = d.get("risk_acceptance")
    return raw if isinstance(raw, dict) else None


def _parse_expires_at(raw: str) -> Optional[datetime]:
    s = (raw or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def acceptance_valid(acc: Optional[Dict[str, Any]], *, now: Optional[datetime] = None) -> Tuple[bool, str]:
    """acceptance_valid。

    Args:
        acc: acc 参数。
        now: now 参数。
    """
    if not acc:
        return False, "missing"
    owner = str(acc.get("owner") or "").strip()
    reason = str(acc.get("reason") or "").strip()
    exp_raw = str(acc.get("expires_at") or "").strip()
    if not owner or not reason or not exp_raw:
        return False, "incomplete"
    exp = _parse_expires_at(exp_raw)
    if exp is None:
        return False, "expires_at_invalid"
    now = now or datetime.now(timezone.utc)
    if exp <= now:
        return False, "expired"
    return True, "ok"


def default_release_blocking(status: str, gap_open: bool) -> bool:
    """P0 defaults: E+empty gap → false; else true.

    Args:
        status: status 参数。
        gap_open: gap_open 参数。
    """
    if status == "E" and not gap_open:
        return False
    return True


def resolve_release_blocking(d: Dict[str, Any], status: str) -> bool:
    """resolve_release_blocking。

    Args:
        d: d 参数。
        status: status 参数。
    """
    if "release_blocking" in d and d.get("release_blocking") is not None:
        return bool(d.get("release_blocking"))
    return default_release_blocking(status, _gap_open(d))


def validate_document(doc: Dict[str, Any]) -> Tuple[bool, List[str], List[Dict[str, Any]]]:
    """Return ledger_ok, errors, normalized dimension summaries (raw dims attached).

    Args:
        doc: doc 参数。
    """
    errors: List[str] = []
    dims = doc.get("dimensions")
    if not isinstance(dims, list):
        return False, ["dimensions_not_list"], []

    if len(dims) != EXPECTED_COUNT:
        errors.append(f"dimension_count:{len(dims)}!={EXPECTED_COUNT}")

    ids: List[str] = []
    summaries: List[Dict[str, Any]] = []
    for i, d in enumerate(dims):
        if not isinstance(d, dict):
            errors.append(f"dim[{i}]_not_mapping")
            continue
        did = str(d.get("id") or "").strip()
        if not did:
            errors.append(f"dim[{i}]_missing_id")
            continue
        ids.append(did)
        status = str(d.get("status") or "").strip().upper()
        if status not in STATUS_OK:
            errors.append(f"{did}:invalid_status:{status or 'empty'}")
        evidence = d.get("evidence") or []
        if not isinstance(evidence, list):
            errors.append(f"{did}:evidence_not_list")
            evidence = []
        for j, ev in enumerate(evidence):
            if not isinstance(ev, dict):
                errors.append(f"{did}:evidence[{j}]_not_mapping")
                continue
            lvl = str(ev.get("level") or "").upper()
            if lvl not in EVIDENCE_LEVELS:
                errors.append(f"{did}:evidence[{j}]_bad_level:{lvl or 'empty'}")
            if not str(ev.get("path") or "").strip():
                errors.append(f"{did}:evidence[{j}]_empty_path")

        if status == "E" and not _evidence_has_vt(evidence):
            errors.append(f"{did}:E_requires_V_or_T_evidence")

        if status == "G":
            if not str(d.get("gap") or "").strip():
                errors.append(f"{did}:G_missing_gap")
            if not str(d.get("next") or "").strip():
                errors.append(f"{did}:G_missing_next")
            if not str(d.get("owner") or "").strip():
                errors.append(f"{did}:G_missing_owner")

        if status == "O":
            if not str(d.get("owner") or "").strip():
                errors.append(f"{did}:O_missing_owner")
            if not str(d.get("last_reviewed") or d.get("due") or "").strip():
                errors.append(f"{did}:O_missing_last_reviewed_or_due")

        if not str(d.get("name") or "").strip():
            errors.append(f"{did}:missing_name")
        if not str(d.get("last_reviewed") or "").strip() and status in ("E", "I"):
            errors.append(f"{did}:missing_last_reviewed")

        gap_open = _gap_open(d)
        blocking = resolve_release_blocking(d, status)
        summaries.append(
            {
                "id": did,
                "name": d.get("name"),
                "status": status,
                "p0": bool(d.get("p0")),
                "v3_id": d.get("v3_id"),
                "owner": d.get("owner") or "",
                "gap_open": gap_open,
                "release_blocking": blocking,
                "external_dependency": bool(d.get("external_dependency")),
                "_raw": d,
            }
        )

    if len(ids) != len(set(ids)):
        errors.append("duplicate_dimension_ids")

    expected_ids = [f"D{n:02d}" for n in range(1, EXPECTED_COUNT + 1)]
    if ids and ids != expected_ids and len(ids) == EXPECTED_COUNT:
        errors.append(f"dimension_ids_order_or_set:{ids[:3]}...")

    ledger_ok = not errors
    return ledger_ok, errors, summaries


def accounted_ok_from(summaries: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """P0 must be owned; G must have owner+gap+next (already schema-checked for G fields).

    Args:
        summaries: summaries 参数。
    """
    bad: List[str] = []
    for s in summaries:
        if not s.get("p0"):
            continue
        did = str(s["id"])
        if not str(s.get("owner") or "").strip():
            bad.append(did)
            continue
        if s.get("status") == "G":
            raw = s.get("_raw") or {}
            if not (
                str(raw.get("gap") or "").strip()
                and str(raw.get("next") or "").strip()
                and str(raw.get("owner") or "").strip()
            ):
                bad.append(did)
    return not bad, bad


def release_ok_from(
    summaries: List[Dict[str, Any]], *, now: Optional[datetime] = None
) -> Tuple[bool, List[str], List[str]]:
    """Return release_ok, release_blocking_ids, expired_risk_ids.

    Args:
        summaries: summaries 参数。
        now: now 参数。
    """
    blocking_ids: List[str] = []
    expired: List[str] = []
    now = now or datetime.now(timezone.utc)
    for s in summaries:
        if not s.get("p0"):
            continue
        did = str(s["id"])
        status = str(s.get("status") or "")
        gap_open = bool(s.get("gap_open"))
        blocking = bool(s.get("release_blocking"))
        raw = s.get("_raw") or {}
        acc = _acceptance_block(raw)
        ok_acc, reason = acceptance_valid(acc, now=now)

        # Clean E: always release-ok for this dim
        if status == "E" and not gap_open:
            continue

        if status == "G":
            # G always needs valid acceptance to release
            if ok_acc:
                continue
            blocking_ids.append(did)
            if reason == "expired":
                expired.append(did)
            continue

        # I/O or E-with-gap
        if not blocking:
            continue
        if ok_acc:
            continue
        blocking_ids.append(did)
        if reason == "expired":
            expired.append(did)

    return not blocking_ids, blocking_ids, expired


def coverage_ok_from(summaries: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """All P0 must be E with empty gap.

    Args:
        summaries: summaries 参数。
    """
    open_ids: List[str] = []
    for s in summaries:
        if not s.get("p0"):
            continue
        if s.get("status") != "E" or s.get("gap_open"):
            open_ids.append(str(s["id"]))
    return not open_ids, open_ids


def open_gap_ids_from(summaries: List[Dict[str, Any]]) -> List[str]:
    """open_gap_ids_from。

    Args:
        summaries: summaries 参数。
    """
    ids: List[str] = []
    for s in summaries:
        if not s.get("p0"):
            continue
        if s.get("status") != "E" or s.get("gap_open"):
            ids.append(str(s["id"]))
    return ids


def build_report(path: Path, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    """build_report。

    Args:
        path: 路径。
        now: now 参数。
    """
    try:
        doc = _load_yaml(path)
    except Exception as e:
        return {
            "schema": "eval.security_dimensions_report.v2",
            "path": str(path),
            "ledger_ok": False,
            "schema_ok": False,
            "accounted_ok": False,
            "release_ok": False,
            "coverage_ok": False,
            "open_gap_ids": [],
            "release_blocking_ids": [],
            "expired_risk_ids": [],
            "external_dependency_ids": [],
            "gaps": [],
            "errors": [f"load_failed:{type(e).__name__}:{e}"],
            "security_certification": False,
            "honesty": HONESTY,
        }

    ledger_ok, errors, summaries = validate_document(doc)
    accounted_ok, accounted_bad = (False, [])
    release_ok, release_blocking_ids, expired_risk_ids = (False, [], [])
    coverage_ok, coverage_gaps = (False, [])
    open_gap_ids: List[str] = []
    external_ids: List[str] = []

    if ledger_ok:
        accounted_ok, accounted_bad = accounted_ok_from(summaries)
        release_ok, release_blocking_ids, expired_risk_ids = release_ok_from(
            summaries, now=now
        )
        # release_ok also requires accounted
        if not accounted_ok:
            release_ok = False
            for x in accounted_bad:
                if x not in release_blocking_ids:
                    release_blocking_ids.append(x)
        coverage_ok, coverage_gaps = coverage_ok_from(summaries)
        open_gap_ids = open_gap_ids_from(summaries)
        external_ids = [
            str(s["id"])
            for s in summaries
            if s.get("p0") and s.get("external_dependency")
        ]

    status_counts: Dict[str, int] = {"E": 0, "I": 0, "O": 0, "G": 0}
    public_dims: List[Dict[str, Any]] = []
    for s in summaries:
        st = str(s.get("status") or "")
        if st in status_counts:
            status_counts[st] += 1
        public_dims.append(
            {
                "id": s["id"],
                "name": s.get("name"),
                "status": s.get("status"),
                "p0": s.get("p0"),
                "v3_id": s.get("v3_id"),
                "owner": s.get("owner") or "",
                "gap_open": s.get("gap_open"),
                "release_blocking": s.get("release_blocking"),
                "external_dependency": s.get("external_dependency"),
            }
        )

    # Compat: gaps historically listed blocking coverage issues
    gaps = coverage_gaps if coverage_gaps else open_gap_ids

    return {
        "schema": "eval.security_dimensions_report.v2",
        "path": str(path),
        "schema_version": doc.get("schema_version"),
        "dimension_set_version": doc.get("dimension_set_version") or "1.0",
        "superset_of": doc.get("superset_of"),
        "dimension_count": len(summaries),
        "ledger_ok": ledger_ok,
        "schema_ok": ledger_ok,  # alias
        "accounted_ok": bool(ledger_ok and accounted_ok),
        "release_ok": bool(ledger_ok and accounted_ok and release_ok),
        "coverage_ok": bool(ledger_ok and coverage_ok),
        "open_gap_ids": open_gap_ids,
        "release_blocking_ids": release_blocking_ids,
        "expired_risk_ids": expired_risk_ids,
        "external_dependency_ids": external_ids,
        "accounted_bad_ids": accounted_bad,
        "gaps": gaps,
        "gap_count": len(gaps),
        "status_counts": status_counts,
        "errors": errors,
        "dimensions": public_dims,
        "reviewed_at_doc": doc.get("last_reviewed"),
        "security_certification": False,
        "accuracy_claim": False,
        "honesty": HONESTY,
    }


def main(argv: Optional[List[str]] = None) -> int:
    """main。

    Args:
        argv: argv 参数。
    """
    parser = argparse.ArgumentParser(description="26-dim security ledger/release/claim report")
    parser.add_argument("--path", default=str(DEFAULT_YAML))
    parser.add_argument(
        "--ledger-gate",
        action="store_true",
        help="Exit 1 when ledger_ok is false (default CI behavior without flags)",
    )
    parser.add_argument(
        "--release-gate",
        action="store_true",
        help="Exit 1 when release_ok is false (ordinary publish)",
    )
    parser.add_argument(
        "--claim-gate",
        action="store_true",
        help="Exit 1 when coverage_ok is false (security claim only)",
    )
    parser.add_argument(
        "--strict-gaps",
        action="store_true",
        help="Alias of --claim-gate (security claim only; not default publish)",
    )
    args = parser.parse_args(argv)
    report = build_report(Path(args.path))
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if not report.get("ledger_ok"):
        print(
            f"FAIL ledger_ok errors={report.get('errors')}",
            file=sys.stderr,
        )
        return 1

    claim = bool(args.claim_gate or args.strict_gaps)
    if args.release_gate and not report.get("release_ok"):
        print(
            f"FAIL --release-gate release_ok=false "
            f"blocking={report.get('release_blocking_ids')} "
            f"expired={report.get('expired_risk_ids')}",
            file=sys.stderr,
        )
        return 1
    if claim and not report.get("coverage_ok"):
        print(
            f"FAIL --claim-gate coverage_ok=false open_gaps={report.get('open_gap_ids')}",
            file=sys.stderr,
        )
        return 1

    # --ledger-gate is explicit; default path already failed above if ledger false
    if args.ledger_gate and not report.get("ledger_ok"):
        return 1

    print(
        f"dimensions ledger_ok={report['ledger_ok']} "
        f"accounted_ok={report['accounted_ok']} "
        f"release_ok={report['release_ok']} "
        f"coverage_ok={report['coverage_ok']} "
        f"open_gaps={report.get('gap_count')} cert=false",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
