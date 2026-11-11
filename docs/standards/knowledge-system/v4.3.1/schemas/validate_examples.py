#!/usr/bin/env python3
"""Validate the JSON examples in the normative appendix against the v4.2 schema bundle.

Requires: jsonschema >= 4.18 (Draft 2020-12).
Run from repository root:
    python docs/whitepaper/knowledge-system/schemas/validate_examples.py
"""
from __future__ import annotations
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

BASE = Path(__file__).resolve().parent.parent
APPENDIX = BASE / "aiplat-knowledge-system-engineering-appendix-v4.2-2026-11-11.md"
SCHEMA = BASE / "schemas" / "knowledge-system.v4.2.schema.json"
PENDING = BASE / "schemas" / "conformance" / "approval-record.pending.json"
APPROVED = BASE / "schemas" / "conformance" / "approval-record.approved.json"

FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time")
def is_datetime(value):
    if not isinstance(value, str):
        return True
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True

MAPPING = {
    "A": [("source", 0)],
    "B": [("object_type", 0), ("link_type", 1)],
    "C": [("action_contract", 0), ("action_execution", 1), ("function_contract", 2), ("interface", 3)],
    "D": [("fact", 0), ("claim", 1)],
    "E": [("object_set_request", 0), ("object_set_response", 1)],
    "F": [("query_response", 0)],
    "H": [("security_policy", 0), ("scenario", 1), ("package", 2)],
    "I": [("error_response", 0)],
    "K": [("source_policy", 0), ("claim_state", 1)],
    "L": [("fact", 0)],
    "M": [("query_request", 0), ("query_response", 1)],
}


def blocks(text: str, section: str) -> list[str]:
    match = re.search(rf"^## {re.escape(section)}\..*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not match:
        return []
    return re.findall(r"```json\n(.*?)\n```", match.group(1), re.S)


def main() -> int:
    text = APPENDIX.read_text(encoding="utf-8")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    failures = 0
    total = 0
    for section, entries in MAPPING.items():
        section_blocks = blocks(text, section)
        for name, index in entries:
            total += 1
            if index >= len(section_blocks):
                print(f"{section}/{name}: MISSING")
                failures += 1
                continue
            try:
                instance = json.loads(section_blocks[index])
            except json.JSONDecodeError as exc:
                print(f"{section}/{name}: JSON parse error: {exc}")
                failures += 1
                continue
            subschema = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$defs": schema["$defs"],
                "$ref": f"#/$defs/{name}",
            }
            errors = sorted(Draft202012Validator(subschema, format_checker=FORMAT_CHECKER).iter_errors(instance), key=lambda e: list(e.path))
            if errors:
                failures += 1
                print(f"{section}/{name}: FAIL")
                for error in errors[:5]:
                    print(f"  {list(error.path)}: {error.message}")
            else:
                print(f"{section}/{name}: OK")
    # Normative conformance fixture, not an appendix example.
    pending = json.loads(PENDING.read_text(encoding="utf-8"))
    subschema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": schema["$defs"],
        "$ref": "#/$defs/approval_record",
    }
    pending_errors = list(Draft202012Validator(subschema, format_checker=FORMAT_CHECKER).iter_errors(pending))
    if pending_errors:
        failures += 1
        print("approval-record.pending.json: FAIL")
        for error in pending_errors[:5]:
            print(f"  {list(error.path)}: {error.message}")
    else:
        print("approval-record.pending.json: OK")

    approved = json.loads(APPROVED.read_text(encoding="utf-8"))
    approved_errors = list(Draft202012Validator(subschema, format_checker=FORMAT_CHECKER).iter_errors(approved))
    if any("(author)" in approver for approver in approved.get("approvers", [])) and "conflict_waiver" not in approved:
        approved_errors.append("author approver requires conflict_waiver")
    if approved_errors:
        failures += 1
        print("approval-record.approved.json: FAIL")
        for error in approved_errors[:5]:
            print(f"  {error.message if hasattr(error, 'message') else error}")
    else:
        print("approval-record.approved.json: OK")

    print(f"validated={total} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
