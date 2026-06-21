#!/usr/bin/env python3
"""State transition accuracy audit — sample transitions from state_changes.db for manual review.

Usage:
  python scripts/audit_reasoning_paths.py --domain ai-knowledge --sample 50 --output audit.csv
"""

from __future__ import annotations

import argparse
import csv
import random
import sqlite3 as _sqlite3
import sys as _sys
from pathlib import Path as _Path


def get_db_path() -> str:
    home = _Path.home() / ".aiplat" / "state_history" / "state_changes.db"
    return str(home)


def sample_transitions(domain_id: str, limit: int = 50) -> list:
    db = get_db_path()
    conn = _sqlite3.connect(db)
    rows = conn.execute(
        """SELECT id, entity_name, class_name, from_state, to_state, trigger_type,
                  transition_desc, doc_id, timestamp
           FROM state_changes
           WHERE domain_id = ?
           ORDER BY RANDOM()
           LIMIT ?""",
        (domain_id, limit),
    ).fetchall()
    conn.close()
    return [{
        "id": r[0], "entity_name": r[1], "class_name": r[2],
        "from_state": r[3], "to_state": r[4], "trigger_type": r[5],
        "transition_desc": r[6] or "", "doc_id": r[7] or "", "timestamp": r[8],
    } for r in rows]


def auto_annotate(transitions: list, domain_id: str) -> tuple:
    """Auto-annotate transitions by checking against YAML state machine rules.
    
    Returns (annotated_list, correct_count, total_count).
    A transition is correct if from_state→to_state exists in the class's YAML transitions.
    """
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from pathlib import Path as _P

    home = _P.home() / ".aiplat" / "ontologies"
    yaml_path = home / f"{domain_id}.yaml"
    if not yaml_path.exists():
        return transitions, 0, len(transitions)

    domain = load_ontology_from_yaml(str(yaml_path))
    # Build valid transition map: class_label → set of (from, to) pairs
    valid_transitions: dict = {}
    for cls in domain.classes:
        pairs = set()
        for trans in getattr(cls, "transitions", []) or []:
            from_list = trans.get("from", [])
            if isinstance(from_list, str):
                from_list = [from_list]
            to_state = trans.get("to", "")
            for f in from_list:
                pairs.add((f, to_state))
        if pairs:
            valid_transitions[cls.label] = pairs

    correct = 0
    for t in transitions:
        cls = t["class_name"]
        pair = (t["from_state"], t["to_state"])
        valid = valid_transitions.get(cls, set())
        if pair in valid:
            t["is_correct"] = 1
            t["reviewer_note"] = "auto: valid per YAML"
            correct += 1
        else:
            t["is_correct"] = 0
            valid_str = ", ".join(f"{f}→{to}" for f, to in sorted(valid)[:5])
            t["reviewer_note"] = f"auto: not in YAML ({valid_str}...)" if valid else "auto: no transitions defined"
    return transitions, correct, len(transitions)


def write_csv(transitions: list, output_path: str):
    with open(output_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "entity_name", "class_name", "from_state", "to_state",
                     "trigger_type", "transition_desc", "is_correct", "reviewer_note"])
        for t in transitions:
            w.writerow([
                t["id"], t["entity_name"], t["class_name"],
                t["from_state"], t["to_state"], t["trigger_type"],
                t["transition_desc"][:80], "", "",
            ])


def compute_accuracy(csv_path: str) -> dict:
    total = 0
    correct = 0
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            if row.get("is_correct", "").strip().lower() in ("1", "yes", "true", "y"):
                correct += 1
    return {"total": total, "correct": correct, "accuracy": correct / total if total else 0}


def main():
    parser = argparse.ArgumentParser(description="State transition accuracy audit")
    parser.add_argument("--domain", default="ai-knowledge")
    parser.add_argument("--sample", type=int, default=50)
    parser.add_argument("--output", default="audit_transitions.csv")
    parser.add_argument("--score", action="store_true", help="Score a reviewed CSV")
    parser.add_argument("--auto", action="store_true", help="Auto-annotate and score immediately")
    args = parser.parse_args()

    if args.auto:
        transitions = sample_transitions(args.domain, args.sample)
        if not transitions:
            print(f"  No transitions found for domain '{args.domain}'. Run engine first.")
            _sys.exit(1)
        annotated, correct, total = auto_annotate(transitions, args.domain)
        accuracy = correct / total if total else 0
        write_csv(annotated, args.output)
        print(f"  Sampled {total} transitions from {args.domain}")
        print(f"  Auto-annotated: {correct}/{total} correct ({accuracy:.1%})")
        print(f"  Output: {args.output}")
        target = 0.80
        print(f"  Target: > {target:.0%}  |  {'✅' if accuracy >= target else '❌'}")
    elif args.score:
        result = compute_accuracy(args.output)
        target = 0.80
        print(f"  Reviewed: {result['total']}")
        print(f"  Correct:  {result['correct']}")
        print(f"  Accuracy: {result['accuracy']:.2%}")
        print(f"  Target: > {target:.0%}  |  {'✅' if result['accuracy'] >= target else '❌'}")
    else:
        transitions = sample_transitions(args.domain, args.sample)
        if not transitions:
            print(f"  No transitions found for domain '{args.domain}'. Run engine first.")
            _sys.exit(1)
        write_csv(transitions, args.output)
        print(f"  Sampled {len(transitions)} transitions from {args.domain}")
        print(f"  Output: {args.output}")
        print(f"  Review: fill in 'is_correct' column (1/0), then run with --score")


if __name__ == "__main__":
    main()
