#!/usr/bin/env python3
"""Record-level and sequence-level semantic checks for the v4.2 knowledge standard."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
APPENDIX = BASE.parent / "normative-appendix.md"
CASES = BASE / "semantic_cases.json"
POLICY = BASE / "conformance" / "reference_policy.json"

MAPPING = {
    "A": [("source", 0)],
    "B": [("object_type", 0), ("link_type", 1)],
    "C": [("action_contract", 0), ("action_execution", 1), ("function_contract", 2), ("interface", 3)],
    "D": [("fact", 0), ("claim", 1)],
    "E": [("object_set_request", 0), ("object_set_response", 1)],
    "F": [("query_response", 0), ("verification_result", 1)],
    "H": [("security_policy", 0), ("scenario", 1), ("package", 2)],
    "I": [("error_response", 0)],
    "K": [("source_policy", 0), ("claim_state", 1)],
    "L": [("fact", 0)],
    "M": [("query_request", 0), ("query_response", 1)],
}

TRANSITIONS = {
    "fact_review": {
        "draft": {"reviewed", "rejected"},
        "reviewed": {"published", "rejected"},
        "published": {"reviewed", "rejected"},
        "rejected": {"draft"},
    },
    "fact_lifecycle": {
        "active": {"superseded", "retracted", "archived"},
        "superseded": {"archived"},
        "retracted": {"archived"},
        "archived": set(),
    },
    "claim_status": {
        "accepted": {"contested", "retracted", "archived"},
        "contested": {"accepted", "retracted", "archived"},
        "retracted": {"archived"},
        "archived": set(),
    },
}


def blocks(text: str, section: str) -> list[str]:
    match = re.search(rf"^## {re.escape(section)}\..*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return re.findall(r"```json\n(.*?)\n```", match.group(1), re.S) if match else []


def example_errors(kind: str, data: dict) -> list[str]:
    errors: list[str] = []
    if kind in {"fact", "claim"}:
        if not data.get("evidence"):
            errors.append("evidence is empty")
        if data.get("review_status") == "published" and data.get("status") not in {"active", "accepted"}:
            errors.append("published review must have active/accepted lifecycle status")
        if data.get("review_status") != "published" and data.get("status") in {"active", "accepted"}:
            errors.append("active/accepted lifecycle requires published review")
        if data.get("valid_from") and data.get("recorded_at") and data["recorded_at"] < data["valid_from"]:
            errors.append("recorded_at earlier than valid_from")
    if kind == "action_contract" and data.get("risk_level") in {"high", "critical"} and not data.get("rollback_action_id"):
        errors.append("high/critical action requires rollback_action_id")
    if kind == "action_execution":
        if data.get("status") == "succeeded" and "result" not in data:
            errors.append("succeeded execution requires result")
        if data.get("status") == "failed" and "error" not in data:
            errors.append("failed execution requires error")
    if kind == "query_response":
        if data.get("abstained") is True and data.get("citations"):
            errors.append("abstained response must not contain citations")
        if data.get("partial") is True and not data.get("degraded_reason"):
            errors.append("partial response requires degraded_reason")
        if data.get("degraded") is True and not data.get("degraded_reason"):
            errors.append("degraded response requires degraded_reason")
    if kind == "verification_result":
        if data.get("valid") is True:
            if data.get("status") != "ok":
                errors.append("valid=true requires status=ok")
            if not data.get("checks_run"):
                errors.append("valid=true requires non-empty checks_run")
            if data.get("skipped_checks"):
                errors.append("valid=true requires empty skipped_checks")
    if kind == "source_policy" and not data.get("scope"):
        errors.append("source policy scope is empty")
    if kind == "claim_state" and not data.get("decision"):
        errors.append("claim state requires decision")
    return errors


def run_examples() -> tuple[int, int]:
    text = APPENDIX.read_text(encoding="utf-8")
    total = 0
    failed = 0
    for section, entries in MAPPING.items():
        section_blocks = blocks(text, section)
        for kind, index in entries:
            total += 1
            try:
                data = json.loads(section_blocks[index])
            except (IndexError, json.JSONDecodeError) as exc:
                failed += 1
                print(f"FAIL example {section}/{kind}: {exc}")
                continue
            errors = example_errors(kind, data)
            if errors:
                failed += 1
                print(f"FAIL example {section}/{kind}: {'; '.join(errors)}")
            else:
                print(f"OK   example {section}/{kind}")
    print(f"semantic_examples={total} failed={failed}")
    return total, failed


def transition_ok(machine: str, steps: list[str]) -> bool:
    for a, b in zip(steps, steps[1:]):
        if b not in TRANSITIONS.get(machine, {}).get(a, set()):
            return False
    return True


def run_cases() -> tuple[int, int, set[str]]:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    seen_idempotency: set[str] = set()
    total = 0
    failed = 0
    for case in cases:
        total += 1
        kind = case["kind"]
        if kind == "transition":
            allowed = TRANSITIONS.get(case["machine"], {}).get(case["from"], set())
            actual = case["to"] in allowed
        elif kind == "sequence":
            actual = transition_ok(case["machine"], case["steps"])
        elif kind == "action_contract":
            rec = case["record"]
            actual = not (rec.get("risk_level") in {"high", "critical"} and not rec.get("rollback_action_id"))
        elif kind == "action_execution":
            rec = case["record"]
            if rec.get("status") == "succeeded":
                actual = "result" in rec
            elif rec.get("status") == "failed":
                actual = "error" in rec
            else:
                actual = True
        elif kind == "query_response":
            rec = case["record"]
            actual = (
                not (rec.get("abstained") is True and rec.get("citations"))
                and not (rec.get("partial") is True and not rec.get("degraded_reason"))
                and not (rec.get("degraded") is True and not rec.get("degraded_reason"))
            )
        elif kind == "verification":
            rec = case["record"]
            actual = not (
                rec.get("valid") is True
                and (
                    rec.get("status") != "ok"
                    or not rec.get("checks_run")
                    or rec.get("skipped_checks")
                )
            )
        elif kind == "conflict":
            accepted = [c["id"] for c in case["claims"] if case["expected"].get(c["id"]) == "accepted"]
            actual = len(accepted) == 1
        elif kind == "permission":
            if case["actor_tenant"] != case["target_tenant"]:
                actual_result = "deny"
            else:
                actual_result = policy["roles"].get(case["role"], {}).get(case["action"], "deny")
            actual = actual_result == case["expected"]
        elif kind == "reconciliation":
            key = case["idempotency_key"]
            if key in seen_idempotency:
                actual_result = "no_duplicate"
            else:
                seen_idempotency.add(key)
                actual_result = case["external_status"] if case["execution_status"] == "unknown" else case["execution_status"]
            actual = actual_result == case["expected"]
        else:
            actual = False
        if actual == case["valid"]:
            print(f"OK   case {case['name']}")
        else:
            failed += 1
            print(f"FAIL case {case['name']}: actual={actual} expected={case['valid']}")
    print(f"cases={total} failed={failed}")
    return total, failed, seen_idempotency


def main() -> int:
    _, ex_failed = run_examples()
    _, case_failed, _ = run_cases()
    return 1 if (ex_failed or case_failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
