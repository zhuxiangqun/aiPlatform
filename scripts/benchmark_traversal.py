#!/usr/bin/env python3
"""Graph traversal performance benchmark — measure latency across graph sizes.

Usage:
  python scripts/benchmark_traversal.py --domain ai-knowledge --runs 100
"""

from __future__ import annotations

import argparse
import statistics
import sys as _sys
import time as _time
from pathlib import Path as _Path

_PROJECT = _Path(__file__).resolve().parent.parent
_sys.path.insert(0, str(_PROJECT / "aiPlat-core"))
_sys.path.insert(0, str(_PROJECT / "aiPlat-infra"))


def build_test_graph(node_count: int, edge_density: float = 2.0):
    """Build a synthetic graph with node_count nodes and approximate edge_density edges/node."""
    from core.harness.ontology_engine.graph_index import GraphIndex

    g = GraphIndex("bench")
    for i in range(node_count):
        g.add_entity(f"n{i}", f"Node_{i}", "Entity")
    # Add edges in a star-like pattern
    for i in range(1, node_count):
        g.add_relation("n0", f"n{i}", "connected", relation_label="连接")
    # Extra edges for density
    extra = max(0, int(node_count * (edge_density - 1)))
    for i in range(min(extra, node_count - 2)):
        g.add_relation(f"n{i+1}", f"n{i+2}", "next", relation_label="下一步")
    return g


def benchmark_traversal(graph, runs: int = 100):
    """Run traversal repeatedly and collect timing data."""
    from core.harness.ontology_engine.graph_traversal import traverse

    times_ms = []
    for _ in range(runs):
        result = traverse("n0", graph, max_hops=3, direction="outgoing")
        times_ms.append(result.timing_ms)
    return times_ms


def print_stats(label: str, times_ms: list):
    sv = sorted(times_ms)
    p50 = sv[len(sv) // 2]
    p95 = sv[min(int(len(sv) * 0.95), len(sv) - 1)]
    p99 = sv[min(int(len(sv) * 0.99), len(sv) - 1)]
    avg = sum(sv) / len(sv)
    print(f"  {label:12s}  avg={avg:7.2f}ms  P50={p50:7.2f}ms  P95={p95:7.2f}ms  P99={p99:7.2f}ms  min={sv[0]:7.2f}ms")
    return p95


def main():
    parser = argparse.ArgumentParser(description="Graph traversal benchmark")
    parser.add_argument("--runs", type=int, default=100, help="Number of traversal runs per size")
    args = parser.parse_args()

    sizes = [10, 50, 200, 1000]
    max_p95 = 0

    print(f"{'Graph Size':15s} {'avg':>8s} {'P50':>8s} {'P95':>8s} {'P99':>8s} {'min':>8s}")
    print("-" * 65)
    for size in sizes:
        graph = build_test_graph(size)
        times = benchmark_traversal(graph, args.runs)
        sv = sorted(times)
        p50 = sv[len(sv)//2]
        p95 = sv[min(int(len(sv)*0.95), len(sv)-1)]
        p99 = sv[min(int(len(sv)*0.99), len(sv)-1)]
        avg = sum(sv)/len(sv)
        print(f"  {size}n/{graph.stats()['edge_count']}e        {avg:7.2f}ms {p50:7.2f}ms {p95:7.2f}ms {p99:7.2f}ms {sv[0]:7.2f}ms")
        max_p95 = max(max_p95, p95)

    print("-" * 65)
    target = 500
    print(f"\n  Target: P95 < {target}ms  |  Max P95: {max_p95:.1f}ms {'✅' if max_p95 < target else '❌'}")


if __name__ == "__main__":
    main()
