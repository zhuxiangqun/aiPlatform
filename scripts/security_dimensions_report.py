#!/usr/bin/env python3
"""Security quality dimensions coverage report (25-dim SoT).

Contract:
  - schema_ok  = YAML parseable, exactly 25 dims, field rules, E⇒≥1 V|T
  - coverage_ok = no P0 dim is G; every E has V|T (already in schema);
                  every O has owner + last_reviewed
  - schema_ok ≠ coverage_ok ≠ security_certification

Exit: 0 if schema_ok (default). --strict-gaps → also require coverage_ok.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_YAML = ROOT / "reports" / "security" / "security_quality_dimensions.yaml"

STATUS_OK = frozenset({"E", "I", "O", "G"})
EVIDENCE_LEVELS = frozenset({"V", "T", "D", "U", "A"})
EXPECTED_COUNT = 25


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


def validate_document(doc: Dict[str, Any]) -> Tuple[bool, List[str], List[Dict[str, Any]]]:
    """Return schema_ok, errors, normalized dimension summaries."""
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

        # Hard contract: E with only D (or no V/T) → schema_ok=false (no silent demote)
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

        summaries.append(
            {
                "id": did,
                "name": d.get("name"),
                "status": status,
                "p0": bool(d.get("p0")),
                "v3_id": d.get("v3_id"),
                "owner": d.get("owner") or "",
            }
        )

    if len(ids) != len(set(ids)):
        errors.append("duplicate_dimension_ids")

    expected_ids = [f"D{n:02d}" for n in range(1, EXPECTED_COUNT + 1)]
    if ids and ids != expected_ids and len(ids) == EXPECTED_COUNT:
        errors.append(f"dimension_ids_order_or_set:{ids[:3]}...")

    schema_ok = not errors
    return schema_ok, errors, summaries


def coverage_ok_from(
    doc: Dict[str, Any], summaries: List[Dict[str, Any]]
) -> Tuple[bool, List[str]]:
    gaps: List[str] = []
    for s in summaries:
        if s.get("p0") and s.get("status") == "G":
            gaps.append(str(s["id"]))
    # Also list non-P0 G for reporting (does not fail coverage unless P0)
    all_g = [str(s["id"]) for s in summaries if s.get("status") == "G"]
    ok = not gaps
    return ok, gaps if gaps else all_g


def build_report(path: Path) -> Dict[str, Any]:
    try:
        doc = _load_yaml(path)
    except Exception as e:
        return {
            "schema": "eval.security_dimensions_report.v1",
            "path": str(path),
            "schema_ok": False,
            "coverage_ok": False,
            "gaps": [],
            "errors": [f"load_failed:{type(e).__name__}:{e}"],
            "security_certification": False,
            "honesty": "schema_ok ≠ coverage_ok ≠ certification",
        }

    schema_ok, errors, summaries = validate_document(doc)
    cov_ok, gap_ids = coverage_ok_from(doc, summaries) if schema_ok else (False, [])
    status_counts: Dict[str, int] = {"E": 0, "I": 0, "O": 0, "G": 0}
    for s in summaries:
        st = str(s.get("status") or "")
        if st in status_counts:
            status_counts[st] += 1

    return {
        "schema": "eval.security_dimensions_report.v1",
        "path": str(path),
        "schema_version": doc.get("schema_version"),
        "superset_of": doc.get("superset_of"),
        "dimension_count": len(summaries),
        "schema_ok": schema_ok,
        "coverage_ok": bool(schema_ok and cov_ok),
        "gaps": gap_ids,
        "gap_count": len(gap_ids),
        "status_counts": status_counts,
        "errors": errors,
        "dimensions": summaries,
        "reviewed_at_doc": doc.get("last_reviewed"),
        "security_certification": False,
        "accuracy_claim": False,
        "honesty": "schema_ok ≠ coverage_ok ≠ certification",
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="25-dim security coverage report")
    parser.add_argument("--path", default=str(DEFAULT_YAML))
    parser.add_argument(
        "--strict-gaps",
        action="store_true",
        help="Exit 1 when coverage_ok is false (publish gate only)",
    )
    args = parser.parse_args(argv)
    report = build_report(Path(args.path))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report.get("schema_ok"):
        print(
            f"FAIL schema_ok errors={report.get('errors')}",
            file=sys.stderr,
        )
        return 1
    if args.strict_gaps and not report.get("coverage_ok"):
        print(
            f"FAIL --strict-gaps coverage_ok=false gaps={report.get('gaps')}",
            file=sys.stderr,
        )
        return 1
    print(
        f"dimensions schema_ok={report['schema_ok']} "
        f"coverage_ok={report['coverage_ok']} gaps={report.get('gap_count')} cert=false",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
