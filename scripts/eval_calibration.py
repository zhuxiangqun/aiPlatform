#!/usr/bin/env python3
"""Confidence calibration evaluation — measures if confidence scores are reliable.

Usage:
  python scripts/eval_calibration.py --queries ~/.aiplat/test_docs/calibration_queries.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys as _sys
from pathlib import Path as _Path

_PROJECT = _Path(__file__).resolve().parent.parent
_sys.path.insert(0, str(_PROJECT / "aiPlat-core"))
_sys.path.insert(0, str(_PROJECT / "aiPlat-infra"))


BINS = [(0.0, 0.6), (0.6, 0.8), (0.8, 0.9), (0.9, 1.0)]


def load_queries(path: str) -> list:
    queries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                queries.append(json.loads(line))
    return queries


def evaluate_calibration(queries: list) -> dict:
    from core.harness.knowledge.ontology_query_mapper import map_query_to_ontology

    bin_counts = {b: {"total": 0, "correct": 0} for b in BINS}

    for q in queries:
        query_text = q["query"]
        expected_class = q.get("expected_class")
        should_find = q.get("should_find_answer", True)

        try:
            mapping = map_query_to_ontology(query_text)
        except Exception:
            mapping = None

        confidence = 0.0
        predicted_class = None
        if mapping:
            matched = mapping.get("matched_classes") or []
            if matched:
                confidence = matched[0].get("score", 0)
                predicted_class = matched[0].get("label", "")

        # Determine correctness
        is_correct = False
        if should_find and expected_class:
            is_correct = (predicted_class == expected_class)
        elif not should_find:
            is_correct = (confidence < 0.5 or predicted_class is None)

        # Assign to bin
        for lo, hi in BINS:
            if lo <= confidence < hi or (hi == 1.0 and confidence == 1.0):
                bin_counts[(lo, hi)]["total"] += 1
                if is_correct:
                    bin_counts[(lo, hi)]["correct"] += 1
                break

    # Compute calibration metrics
    bin_results = []
    ece = 0.0
    total = sum(b["total"] for b in bin_counts.values())
    for lo, hi in BINS:
        b = bin_counts[(lo, hi)]
        accuracy = b["correct"] / b["total"] if b["total"] > 0 else 0
        avg_conf = (lo + hi) / 2
        gap = abs(accuracy - avg_conf)
        ece += (b["total"] / total) * gap if total > 0 else 0
        bin_results.append({
            "bin": f"[{lo:.1f}-{hi:.1f})",
            "total": b["total"],
            "correct": b["correct"],
            "accuracy": accuracy,
            "avg_confidence": avg_conf,
            "gap": gap,
        })

    return {"bins": bin_results, "ece": round(ece, 4), "total": total}


def print_report(report: dict):
    print(f"  {'Bin':12s} {'Samples':>8s} {'Expected':>8s} {'Actual':>8s} {'Gap':>8s}")
    print("  " + "-" * 50)
    for b in report["bins"]:
        print(f"  {b['bin']:12s} {b['total']:8d} {b['avg_confidence']:7.3f}  {b['accuracy']:7.3f}  {b['gap']:7.3f}")
    print("  " + "-" * 50)
    target = 0.10
    print(f"\n  ECE (Expected Calibration Error): {report['ece']:.4f}")
    print(f"  Total samples: {report['total']}")
    print(f"  Target: ECE < {target}  |  {'✅' if report['ece'] < target else '❌'}")


def main():
    parser = argparse.ArgumentParser(description="Confidence calibration evaluation")
    parser.add_argument("--queries", default=str(_Path.home() / ".aiplat" / "test_docs" / "calibration_queries.jsonl"))
    args = parser.parse_args()

    queries = load_queries(args.queries)
    if not queries:
        print("No queries found.")
        _sys.exit(1)

    print(f"  Loaded {len(queries)} calibration queries")
    report = evaluate_calibration(queries)
    print_report(report)


if __name__ == "__main__":
    main()
