#!/usr/bin/env python3
"""Retrieval recall evaluation — measures how well the system retrieves relevant pages.

Usage:
  python scripts/eval_retrieval.py --queries ~/.aiplat/test_docs/queries.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys as _sys
from collections import defaultdict
from pathlib import Path as _Path

_PROJECT = _Path(__file__).resolve().parent.parent
_sys.path.insert(0, str(_PROJECT / "aiPlat-core"))
_sys.path.insert(0, str(_PROJECT / "aiPlat-infra"))


def load_queries(path: str) -> list:
    queries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                queries.append(json.loads(line))
    return queries


def evaluate_retrieval(queries: list, *, collection_id: str = "default") -> dict:
    """For each query, search wiki pages locally and compute recall.
    
    Uses wiki_engine.search_pages() (FTS5 + keyword matching) instead of
    requiring a running core server. Pages must exist on disk first.
    """
    from core.harness.knowledge.wiki_engine import search_pages as _wiki_search

    results = []
    all_recall_5 = []
    all_recall_10 = []
    all_mrr = []

    for i, q in enumerate(queries):
        query_text = q["query"]
        relevant = set(q.get("relevant_pages", []))
        if not relevant:
            continue

        try:
            resp = _wiki_search(query_text, limit=10, collection_id=collection_id)
        except Exception:
            resp = []

        retrieved_titles = []
        if isinstance(resp, list):
            retrieved_titles = [r.get("title", "") for r in resp if r.get("title")]
        elif isinstance(resp, dict):
            items = resp.get("pages", resp.get("results", resp.get("items", [])))
            if isinstance(items, list):
                retrieved_titles = [it.get("title", "") for it in items if it.get("title")]

        # Recall@K
        found_5 = relevant & set(retrieved_titles[:5])
        found_10 = relevant & set(retrieved_titles[:10])
        recall_5 = len(found_5) / len(relevant) if relevant else 0
        recall_10 = len(found_10) / len(relevant) if relevant else 0

        # MRR
        mrr = 0
        for j, title in enumerate(retrieved_titles[:10]):
            if title in relevant:
                mrr = 1.0 / (j + 1)
                break

        # Precision@K
        precision_5 = len(found_5) / 5 if retrieved_titles else 0
        precision_10 = len(found_10) / min(10, max(len(retrieved_titles), 1))

        # NDCG@10 — higher rank = higher gain, relevance = (1 if in relevant else 0)
        dcg = 0
        idcg = 0
        for j in range(min(10, len(retrieved_titles))):
            rel = 1 if retrieved_titles[j] in relevant else 0
            dcg += rel / (__import__('math').log2(j + 2))
        for j in range(min(10, len(relevant))):
            idcg += 1 / (__import__('math').log2(j + 2))
        ndcg = dcg / idcg if idcg > 0 else 0

        results.append({
            "query": query_text[:60],
            "relevant": len(relevant),
            "found_5": len(found_5),
            "found_10": len(found_10),
            "recall_5": recall_5,
            "recall_10": recall_10,
            "precision_5": precision_5,
            "precision_10": precision_10,
            "mrr": mrr,
            "ndcg": round(ndcg, 3),
        })
        all_recall_5.append(recall_5)
        all_recall_10.append(recall_10)
        all_mrr.append(mrr)

    avg_recall_5 = sum(all_recall_5) / len(all_recall_5) if all_recall_5 else 0
    avg_recall_10 = sum(all_recall_10) / len(all_recall_10) if all_recall_10 else 0
    avg_mrr = sum(all_mrr) / len(all_mrr) if all_mrr else 0

    return {
        "results": results,
        "avg_recall_5": avg_recall_5,
        "avg_recall_10": avg_recall_10,
        "avg_mrr": avg_mrr,
        "total_queries": len(queries),
        "evaluated": len(results),
    }


def print_report(report: dict):
    print(f"  {'Query':50s} {'Rel':>4s} {'R@5':>5s} {'R@10':>5s} {'MRR':>5s}")
    print("  " + "-" * 72)
    for r in report["results"]:
        print(f"  {r['query'][:48]:50s} {r['relevant']:4d} {r['recall_5']:5.2f} {r['recall_10']:5.2f} {r['mrr']:5.2f}")
    print("  " + "-" * 72)
    print(f"  {'AVERAGE':50s} {'':>4s} {report['avg_recall_5']:5.2f} {report['avg_recall_10']:5.2f} {report['avg_mrr']:5.2f}")
    print(f"\n  Queries: {report['evaluated']}/{report['total_queries']} evaluated")
    target = 0.85
    print(f"  Target: Recall@10 > {target}  |  Actual: {report['avg_recall_10']:.2f} {'✅' if report['avg_recall_10'] >= target else '❌'}")


def main():
    parser = argparse.ArgumentParser(description="Retrieval recall evaluation")
    parser.add_argument("--queries", default=str(_Path.home() / ".aiplat" / "test_docs" / "queries.jsonl"))
    args = parser.parse_args()

    queries = load_queries(args.queries)
    if not queries:
        print("No queries found.")
        _sys.exit(1)

    print(f"  Loaded {len(queries)} queries")
    report = evaluate_retrieval(queries)
    print_report(report)


if __name__ == "__main__":
    main()
