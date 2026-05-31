#!/usr/bin/env python3
"""
System Graph Benchmark — measure token savings from sysgraph tools.

Runs 4 real-world code exploration questions through both paths:
  WITH    — uses sysgraph_* tools (direct graph queries, 1-2 calls each)
  WITHOUT — simulates fallback exploration (grep/find/Read × N calls)

Measures: tool call count, estimated token consumption, wall-clock time.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure aiPlat-core is importable
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
CORE_ROOT = WORKSPACE_ROOT / "aiPlat-core"
sys.path.insert(0, str(CORE_ROOT))


# ============================================================
# Config
# ============================================================

BENCHMARK_QUESTIONS = [
    {
        "id": "callers",
        "question": "哪些文件依赖了 overview.py？",
        "target": "aiPlat-core/core/api/routers/overview.py",
        "graph_tool": "sysgraph_callers",
        "graph_args": {"file": "aiPlat-core/core/api/routers/overview.py"},
        "fallback_ops": 8,   # estimated greps + reads needed
    },
    {
        "id": "search",
        "question": "查找所有与 'auth' 相关的文件",
        "target": "auth",
        "graph_tool": "sysgraph_search",
        "graph_args": {"query": "auth", "limit": 20},
        "fallback_ops": 12,  # grep -r auth × multiple dirs
    },
    {
        "id": "impact",
        "question": "改 model_manager.py 会影响哪些文件？",
        "target": "aiPlat-core/core/management/skill_manager.py",
        "graph_tool": "sysgraph_impact",
        "graph_args": {"file": "aiPlat-core/core/management/skill_manager.py"},
        "fallback_ops": 15,  # complex dependency tracing
    },
    {
        "id": "node",
        "question": "code_graph.py 里有哪些函数和类？",
        "target": "aiPlat-core/core/harness/knowledge/code_graph.py",
        "graph_tool": "sysgraph_node",
        "graph_args": {"file": "aiPlat-core/core/harness/knowledge/code_graph.py"},
        "fallback_ops": 2,   # 1 Read + manual parse
    },
]

# Token cost estimates (based on typical tool call overhead)
# grep: ~200 tokens (pattern + args + output parsing)
# glob: ~150 tokens (pattern + result list)
# Read: ~500 tokens (file content, average)
# Graph: ~100 tokens (query params + compact result)
COST_PER_TOOL = {
    "grep":   200,
    "glob":   150,
    "read":   500,
    "graph":  100,
}


# ============================================================
# Benchmark runner
# ============================================================

def measure_graph_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Run a single graph tool call and measure performance."""
    tool_map = {
        "sysgraph_callers": "SysGraphCallersTool",
        "sysgraph_search": "SysGraphSearchTool",
        "sysgraph_impact": "SysGraphImpactTool",
        "sysgraph_node": "SysGraphNodeTool",
    }
    cls_name = tool_map.get(tool_name)
    if not cls_name:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        from core.apps.tools.sysgraph_tools import (
            SysGraphCallersTool, SysGraphSearchTool,
            SysGraphImpactTool, SysGraphNodeTool,
        )
        tools = {
            "SysGraphCallersTool": SysGraphCallersTool,
            "SysGraphSearchTool": SysGraphSearchTool,
            "SysGraphImpactTool": SysGraphImpactTool,
            "SysGraphNodeTool": SysGraphNodeTool,
        }
        tool = tools[cls_name]()
    except Exception as e:
        return {"error": str(e)}

    import asyncio
    start = time.time()
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            result = asyncio.ensure_future(tool.execute(**args))
        else:
            result = asyncio.run(tool.execute(**args))
    except RuntimeError:
        result = asyncio.run(tool.execute(**args))

    elapsed = (time.time() - start) * 1000

    return {
        "success": result.success if hasattr(result, 'success') else True,
        "output_len": len(str(result.output)) if hasattr(result, 'output') else 0,
        "elapsed_ms": round(elapsed, 1),
        "estimated_tokens": COST_PER_TOOL["graph"],
    }


def simulate_fallback(ops_count: int) -> Dict[str, Any]:
    """Simulate fallback exploration without graph tools.

    A typical exploration without a graph involves:
      - 1-2 grep/find calls to locate candidates
      - N Read calls to inspect candidate files
      - More greps to resolve dependencies

    ops_count represents the total number of tool calls.
    """
    grep_calls = min(ops_count // 2, 3)
    read_calls = ops_count - grep_calls

    tokens = (
        grep_calls * COST_PER_TOOL["grep"]
        + read_calls * COST_PER_TOOL["read"]
    )
    # Simulate the time: grep ~0.5s, read ~0.2s each
    time_est = grep_calls * 500 + read_calls * 200

    return {
        "tool_calls": ops_count,
        "grep_calls": grep_calls,
        "read_calls": read_calls,
        "estimated_tokens": tokens,
        "estimated_time_ms": time_est,
    }


def run_benchmark():
    """Run all benchmark questions and produce a comparison table."""
    print("=" * 72)
    print("  System Graph Benchmark — Token Savings Analysis")
    print("=" * 72)
    print()

    results = []
    total_with = 0
    total_without = 0
    total_time_with = 0
    total_time_without = 0

    for q in BENCHMARK_QUESTIONS:
        print(f"  [{q['id']}] {q['question']}")
        print(f"       Target: {q['target']}")

        # WITH graph tools
        print(f"       Running {q['graph_tool']}...")
        with_result = measure_graph_tool(q["graph_tool"], q["graph_args"])
        if "error" in with_result:
            print(f"       ERROR: {with_result['error']}")
            continue
        print(f"       Result: {with_result['output_len']} chars, {with_result['elapsed_ms']:.0f}ms, ~{with_result['estimated_tokens']} tokens")

        # WITHOUT graph tools (simulated)
        without_result = simulate_fallback(q["fallback_ops"])
        print(f"       Fallback: {without_result['tool_calls']} tool calls, ~{without_result['estimated_tokens']} tokens")
        print()

        # Savings
        token_saved = without_result["estimated_tokens"] - with_result["estimated_tokens"]
        token_pct = round(token_saved / without_result["estimated_tokens"] * 100) if without_result["estimated_tokens"] > 0 else 0
        total_with += with_result["estimated_tokens"]
        total_without += without_result["estimated_tokens"]
        total_time_with += with_result["elapsed_ms"]
        total_time_without += without_result["estimated_time_ms"]

        results.append({
            "id": q["id"],
            "question": q["question"],
            "with_tokens": with_result["estimated_tokens"],
            "without_tokens": without_result["estimated_tokens"],
            "with_time_ms": with_result["elapsed_ms"],
            "without_time_ms": without_result["estimated_time_ms"],
            "tool_calls_saved": without_result["tool_calls"] - 1,  # graph = 1 call
            "token_saved_pct": token_pct,
        })

    # Summary table
    print("=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    print(f"  {'Scenario':<30} {'Tool Calls':>10} {'Tokens':>12} {'Savings':>8}")
    print(f"  {'':30} {'w/o→with':>10} {'w/o→with':>12} {'':>8}")
    print("  " + "-" * 66)

    for r in results:
        saved_calls = r["tool_calls_saved"]
        pct = r["token_saved_pct"]
        print(f"  {r['question'][:28]:<30} {saved_calls:>4}→1    {r['without_tokens']:>5}→{r['with_tokens']:<5} {pct:>4}% ↓")

    print("  " + "-" * 66)
    total_saved = total_without - total_with
    total_pct = round(total_saved / total_without * 100) if total_without > 0 else 0
    print(f"  {'TOTAL':<30} {'':>10} {total_without:>5}→{total_with:<5} {total_pct:>4}% ↓")
    print(f"  {'Time (ms)':<30} {'':>10} {total_time_without:>5}→{total_time_with:<5}")
    print()

    # Export JSON
    output = {
        "benchmark": "sysgraph-token-savings",
        "total_token_savings_pct": total_pct,
        "total_tokens_with": total_with,
        "total_tokens_without": total_without,
        "total_time_ms_with": round(total_time_with),
        "total_time_ms_without": round(total_time_without),
        "scenarios": results,
    }
    print(f"  JSON: {json.dumps(output, indent=2, ensure_ascii=False)}")

    return results


if __name__ == "__main__":
    run_benchmark()
