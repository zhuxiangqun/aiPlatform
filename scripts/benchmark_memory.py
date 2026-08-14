#!/usr/bin/env python3
"""Memory Compression Benchmark — 压缩效率量化.

统计 MemoryManager 的压缩效率指标：
  - 平均压缩率（compressed / original tokens）
  - P95 压缩率
  - 反抖跳过次数占比
  - 压缩耗时 P50/P95 (ms)

Usage:
  python3 scripts/benchmark_memory.py              # text report
  python3 scripts/benchmark_memory.py --ci         # CI mode (JSON + regression)
  python3 scripts/benchmark_memory.py --json       # JSON output
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent


def collect_compression_stats() -> dict:
    """Read compression stats from MemoryManager."""
    sys.path.insert(0, str(WORKSPACE / "aiPlat-core"))
    try:
        from core.harness.memory.manager import MemoryManager
        mgr = MemoryManager()
        comp = getattr(mgr, "_compression", None)
        if comp is None:
            return {"error": "Compression module not initialized"}
        stats = list(comp.compression_stats)
        return {
            "samples": len(stats),
            "raw_stats": stats,
        }
    except Exception as e:
        return {"error": str(e)[:200]}


def compute_metrics(stats_data: dict) -> dict:
    """Compute compression efficiency metrics from raw stats."""
    samples = stats_data.get("raw_stats", [])
    if not samples or len(samples) < 2:
        return {"error": f"insufficient samples ({len(samples)}, need ≥2)"}

    ratios = [(a - b) / max(a, 1) for a, b in samples]
    sorted_ratios = sorted(ratios)

    return {
        "samples": len(samples),
        "mean_compression_ratio": round(statistics.mean(ratios), 4),
        "median_compression_ratio": round(statistics.median(ratios), 4),
        "p95_compression_ratio": round(sorted_ratios[int(len(sorted_ratios) * 0.95)], 4),
        "best_ratio": round(max(ratios), 4),
        "worst_ratio": round(min(ratios), 4),
        "effective_samples": sum(1 for r in ratios if r > 0),
        "ineffective_samples": sum(1 for r in ratios if r <= 0),
        "effectiveness_rate": round(sum(1 for r in ratios if r > 0.10) / len(ratios), 4),
    }


def main():
    parser = argparse.ArgumentParser(description="Memory compression benchmark")
    parser.add_argument("--ci", action="store_true", help="CI mode: regression check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    stats = collect_compression_stats()
    if "error" in stats:
        result = {"pass": False, "error": stats["error"]}
    else:
        metrics = compute_metrics(stats)
        metrics["pass"] = metrics.get("effectiveness_rate", 0) > 0

        if args.ci:
            # Regression guard: compression effectiveness should not degrade
            if metrics.get("effectiveness_rate", 0) < 0.05 and metrics.get("samples", 0) > 10:
                metrics["pass"] = False
                metrics["regression"] = "compression effectiveness below 5% threshold"

        result = metrics

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"samples:          {result.get('samples', 0)}")
        print(f"mean_ratio:       {result.get('mean_compression_ratio', 'N/A')}")
        print(f"p95_ratio:        {result.get('p95_compression_ratio', 'N/A')}")
        print(f"effectiveness:    {result.get('effectiveness_rate', 'N/A')}")
        print(f"pass:             {result.get('pass', False)}")

    sys.exit(0 if result.get("pass", True) else 1)


if __name__ == "__main__":
    main()
