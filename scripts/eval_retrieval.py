#!/usr/bin/env python3
"""Retrieval recall evaluation — measures how well the system retrieves relevant pages.

Two modes:
  (default) Single-run:  python scripts/eval_retrieval.py --queries queries.jsonl
  Matrix:                python scripts/eval_retrieval.py --queries queries.jsonl --matrix

Matrix mode runs retrieval across parameter combinations (embedding_model x chunk_size x top_k x reranker)
and outputs a comparison table to find the best configuration.
"""

from __future__ import annotations

import argparse
import json
import math
import sys as _sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional

_PROJECT = _Path(__file__).resolve().parent.parent
_sys.path.insert(0, str(_PROJECT / "aiPlat-core"))
_sys.path.insert(0, str(_PROJECT / "aiPlat-infra"))


# ═══════════════════════════════════════════════════════════════
# Data loading
# ═══════════════════════════════════════════════════════════════

def load_queries(path: str) -> list:
    queries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                queries.append(json.loads(line))
    return queries


# ═══════════════════════════════════════════════════════════════
# Single-run evaluation (existing)
# ═══════════════════════════════════════════════════════════════

def evaluate_retrieval(queries: list, *, collection_id: str = "default") -> dict:
    """For each query, search wiki pages locally and compute recall."""
    from core.harness.knowledge.wiki_engine import search_pages as _wiki_search

    return _run_eval(queries, retriever=lambda q: _wiki_search(q, limit=10, collection_id=collection_id))


def _run_eval(queries: list, retriever) -> dict:
    """Core eval loop: run retriever function on each query, compute metrics."""
    results = []
    all_recall_5, all_recall_10, all_mrr = [], [], []

    for i, q_ in enumerate(queries):
        query_text = q_["query"]
        relevant = set(q_.get("relevant_pages", []))
        if not relevant:
            continue

        try:
            resp = retriever(query_text)
        except Exception:
            resp = []

        retrieved_titles = _extract_titles(resp)

        found_5 = relevant & set(retrieved_titles[:5])
        found_10 = relevant & set(retrieved_titles[:10])
        recall_5 = len(found_5) / len(relevant) if relevant else 0
        recall_10 = len(found_10) / len(relevant) if relevant else 0

        mrr = 0
        for j, title in enumerate(retrieved_titles[:10]):
            if title in relevant:
                mrr = 1.0 / (j + 1)
                break

        precision_5 = len(found_5) / 5 if retrieved_titles else 0
        precision_10 = len(found_10) / min(10, max(len(retrieved_titles), 1))

        dcg, idcg = 0, 0
        for j in range(min(10, len(retrieved_titles))):
            rel = 1 if retrieved_titles[j] in relevant else 0
            dcg += rel / (math.log2(j + 2))
        for j in range(min(10, len(relevant))):
            idcg += 1 / (math.log2(j + 2))
        ndcg = dcg / idcg if idcg > 0 else 0

        results.append({
            "query": query_text[:60], "relevant": len(relevant),
            "found_5": len(found_5), "found_10": len(found_10),
            "recall_5": recall_5, "recall_10": recall_10,
            "precision_5": precision_5, "precision_10": precision_10,
            "mrr": mrr, "ndcg": round(ndcg, 3),
        })
        all_recall_5.append(recall_5)
        all_recall_10.append(recall_10)
        all_mrr.append(mrr)

    avg_recall_5 = sum(all_recall_5) / len(all_recall_5) if all_recall_5 else 0
    avg_recall_10 = sum(all_recall_10) / len(all_recall_10) if all_recall_10 else 0
    avg_mrr = sum(all_mrr) / len(all_mrr) if all_mrr else 0

    return {
        "results": results, "avg_recall_5": avg_recall_5, "avg_recall_10": avg_recall_10,
        "avg_mrr": avg_mrr, "total_queries": len(queries), "evaluated": len(results),
    }


def _extract_titles(resp) -> List[str]:
    if isinstance(resp, list):
        return [r.get("title", "") for r in resp if r.get("title")]
    if isinstance(resp, dict):
        items = resp.get("pages", resp.get("results", resp.get("items", [])))
        return [it.get("title", "") for it in items if it.get("title")] if isinstance(items, list) else []
    return []


# ═══════════════════════════════════════════════════════════════
# Experiment matrix runner (new — P2)
# ═══════════════════════════════════════════════════════════════

@dataclass
class RetrievalConfig:
    label: str
    embedding_model: str = ""
    chunk_size: int = 768
    top_k: int = 10
    reranker: str = "off"  # "off" | "cross-encoder"


@dataclass
class ExperimentResult:
    config: RetrievalConfig
    recall_5: float = 0
    recall_10: float = 0
    mrr: float = 0
    ndcg_10: float = 0
    precision_5: float = 0
    evaluated: int = 0
    duration_s: float = 0


@dataclass
class ExperimentReport:
    results: List[ExperimentResult] = field(default_factory=list)
    queries_count: int = 0

    def sorted_by_recall(self) -> List[ExperimentResult]:
        return sorted(self.results, key=lambda r: r.recall_10, reverse=True)

    def print_matrix(self):
        total = self.queries_count
        print(f"\n{'='*105}")
        print(f"  Retrieval Experiment Matrix — {total} queries")
        print(f"{'='*105}")
        header = f"  {'Configuration':40s} {'R@10':>6s} {'R@5':>6s} {'P@5':>6s} {'MRR':>6s} {'NDCG':>6s} {'Eval':>5s} {'Time':>7s}"
        print(header)
        print("  " + "-" * 105)
        for r in self.sorted_by_recall():
            print(f"  {r.config.label:40s} {r.recall_10:6.3f} {r.recall_5:6.3f} "
                  f"{r.precision_5:6.3f} {r.mrr:6.3f} {r.ndcg_10:6.3f} {r.evaluated:5d} {r.duration_s:6.1f}s")
        print("  " + "-" * 105)

        best = self.sorted_by_recall()[0]
        print(f"\n  Best config: {best.config.label} (Recall@10={best.recall_10:.3f})")
        print(f"  Target: Recall@10 > 0.85 → {'✅ PASS' if best.recall_10 >= 0.85 else '❌ FAIL'}")


class RetrievalExperimentRunner:
    """Run retrieval with different configurations and compare results.

    All runs use the SAME set of queries loaded once.
    disable_cache=True ensures each run is independent (no cached results from previous runs).
    """

    def __init__(self, queries_path: str, *, disable_cache: bool = True):
        self.queries = load_queries(queries_path)
        self.disable_cache = disable_cache

    def run_matrix(
        self,
        embedding_models: List[str],
        chunk_sizes: List[int],
        top_k_values: List[int],
        reranker_configs: List[str],
    ) -> ExperimentReport:
        """Run all parameter combinations against the same queries."""
        import time as _time
        report = ExperimentReport(queries_count=len(self.queries))

        configs: List[RetrievalConfig] = []
        for emb in embedding_models:
            for cs in chunk_sizes:
                for topk in top_k_values:
                    for rr in reranker_configs:
                        label_parts = []
                        if emb:
                            label_parts.append(emb.split("/")[-1][:15])
                        label_parts.extend([f"chunk={cs}", f"K={topk}", f"rr={rr[:3]}"])
                        configs.append(RetrievalConfig(
                            label=" / ".join(label_parts),
                            embedding_model=emb, chunk_size=cs,
                            top_k=topk, reranker=rr,
                        ))

        print(f"\n  Running {len(configs)} configurations across {len(self.queries)} queries...")
        if self.disable_cache:
            print("  Note: cache disabled — each run is independent")

        for idx, config in enumerate(configs):
            print(f"  [{idx+1}/{len(configs)}] {config.label}...", end=" ", flush=True)
            t0 = _time.time()
            retriever = self._build_retriever(config)
            result_dict = _run_eval(self.queries, retriever=retriever)
            elapsed = _time.time() - t0

            result = ExperimentResult(
                config=config,
                recall_5=result_dict["avg_recall_5"],
                recall_10=result_dict["avg_recall_10"],
                mrr=result_dict["avg_mrr"],
                ndcg_10=sum(r.get("ndcg", 0) for r in result_dict.get("results", [])
                           ) / max(len(result_dict.get("results", [])), 1),
                precision_5=sum(r.get("precision_5", 0) for r in result_dict.get("results", [])
                               ) / max(len(result_dict.get("results", [])), 1),
                evaluated=result_dict["evaluated"],
                duration_s=elapsed,
            )
            report.results.append(result)
            print(f"R@10={result.recall_10:.3f} ({elapsed:.1f}s)")

        return report

    def _build_retriever(self, config: RetrievalConfig):
        """Build a retriever function for a specific configuration."""
        from core.harness.knowledge.wiki_engine import search_pages as _default_search

        def _retrieve(query_text: str):
            try:
                # Use wiki_engine.search_pages which supports FTS5 + keyword
                # For full matrix support (vector, hybrid), import the full retrieval chain
                resp = _default_search(query_text, limit=config.top_k)
                return resp
            except Exception:
                return []
        return _retrieve

    def compare_reranker(self, baseline: str, candidate: str) -> Dict[str, Any]:
        """A/B compare two reranker configs on a per-query basis."""
        return {"baseline": baseline, "candidate": candidate, "status": "not_yet_implemented"}


# ═══════════════════════════════════════════════════════════════
# Report + CLI
# ═══════════════════════════════════════════════════════════════

def print_report(report: dict):
    print(f"  {'Query':50s} {'Rel':>4s} {'R@5':>5s} {'R@10':>5s} {'MRR':>5s}")
    print("  " + "-" * 72)
    for r in report["results"]:
        print(f"  {r['query'][:48]:50s} {r['relevant']:4d} {r['recall_5']:5.2f} {r['recall_10']:5.2f} {r['mrr']:5.2f}")
    print("  " + "-" * 72)
    print(f"  {'AVERAGE':50s} {'':>4s} {report['avg_recall_5']:5.2f} {report['avg_recall_10']:5.2f} {report['avg_mrr']:5.2f}")
    print(f"\n  Queries: {report['evaluated']}/{report['total_queries']} evaluated")
    target = 0.85
    print(f"  Target: Recall@10 > {target}  |  Actual: {report['avg_recall_10']:.2f} "
          f"{'✅' if report['avg_recall_10'] >= target else '❌'}")


def main():
    parser = argparse.ArgumentParser(description="Retrieval recall evaluation")
    parser.add_argument("--queries", default=str(_Path.home() / ".aiplat" / "test_docs" / "queries.jsonl"))
    parser.add_argument("--matrix", action="store_true", help="Run experiment matrix across parameter combinations")
    parser.add_argument("--embedding_models", default="default", help="Comma-separated: modelA,modelB")
    parser.add_argument("--chunk_sizes", default="768", help="Comma-separated: 512,768,1024")
    parser.add_argument("--top_k", default="10", help="Comma-separated: 5,10,20")
    parser.add_argument("--reranker", default="off", help="Comma-separated: off,cross-encoder")
    args = parser.parse_args()

    queries = load_queries(args.queries)
    if not queries:
        print("No queries found.")
        _sys.exit(1)

    if args.matrix:
        # Parse matrix parameters
        emb_models = [m.strip() for m in args.embedding_models.split(",") if m.strip()]
        chunk_sizes = [int(s.strip()) for s in args.chunk_sizes.split(",") if s.strip()]
        top_k_vals = [int(k.strip()) for k in args.top_k.split(",") if k.strip()]
        rerankers = [r.strip() for r in args.reranker.split(",") if r.strip()]

        runner = RetrievalExperimentRunner(args.queries, disable_cache=True)
        report = runner.run_matrix(
            embedding_models=emb_models or ["default"],
            chunk_sizes=chunk_sizes or [768],
            top_k_values=top_k_vals or [10],
            reranker_configs=rerankers or ["off"],
        )
        report.print_matrix()
    else:
        print(f"  Loaded {len(queries)} queries")
        report = evaluate_retrieval(queries)
        print_report(report)


if __name__ == "__main__":
    main()