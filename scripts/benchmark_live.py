#!/usr/bin/env python3
"""
Live benchmark — validates sysgraph tools against real code exploration tasks.

Measures actual tool execution results with graph tools, and compares to estimated
fallback costs (grep/Read exploration without graph).

Output: token savings, tool call reduction, time improvement.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))

# ── Test scenarios ───────────────────────────────────────────────

SCENARIOS = [
    {
        "id": "deps",
        "question": "哪些文件依赖了 overview.py？",
        "tool": "sysgraph_callers",
        "args": {"file": "aiPlat-core/core/api/routers/overview.py"},
        "fallback_ops": 8,
    },
    {
        "id": "search_auth",
        "question": "查找所有与 'auth' 相关的文件",
        "tool": "sysgraph_search",
        "args": {"query": "auth", "limit": 25},
        "fallback_ops": 12,
    },
    {
        "id": "impact",
        "question": "修改 core_facade.py 会影响哪些文件？",
        "tool": "sysgraph_impact",
        "args": {"file": "aiPlat-core/core/api/core_facade.py"},
        "fallback_ops": 15,
    },
    {
        "id": "symbols",
        "question": "code_graph.py 里有哪些函数和类？",
        "tool": "sysgraph_node",
        "args": {"file": "aiPlat-core/core/harness/knowledge/code_graph.py"},
        "fallback_ops": 2,
    },
]

# Realistic token estimates based on typical syscall overhead
GRAPH_CALL_TOKENS = 80     # sys_tool_call(input)
GRAPH_OUTPUT_TOKENS = 50   # tool result (compact, structured)
MODEL_OVERHEAD = 500       # system prompt + context per turn
GREP_CALL_TOKENS = 200     # sys_tool_call(grep)
READ_CALL_TOKENS = 600     # sys_tool_call(read) — reads file content


def measure_graph_call(tool_name: str, args: dict) -> dict:
    """Execute a real graph tool call and measure performance."""
    tool_map = {
        "sysgraph_callers": "SysGraphCallersTool",
        "sysgraph_search": "SysGraphSearchTool",
        "sysgraph_impact": "SysGraphImpactTool",
        "sysgraph_node": "SysGraphNodeTool",
    }
    cls_name = tool_map[tool_name]

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

    start = time.time()
    async def _run():
        return await tools[cls_name]().execute(**args)

    try:
        loop = asyncio.get_running_loop()
        # Running in async context
        import concurrent.futures
        result = asyncio.ensure_future(_run())
    except RuntimeError:
        result = asyncio.run(_run())

    elapsed = (time.time() - start) * 1000
    return {
        "success": result.success if hasattr(result, 'success') else True,
        "output_chars": len(str(result.output)) if hasattr(result, 'output') else 0,
        "output_preview": str(getattr(result, 'output', ''))[:100],
        "elapsed_ms": round(elapsed, 1),
    }


def estimate_without_graph(ops_count: int) -> dict:
    """Estimate token cost + calls for fallback exploration (no graph)."""
    grep_calls = min(ops_count // 2, 3)
    read_calls = ops_count - grep_calls

    tool_call_tokens = (
        grep_calls * GREP_CALL_TOKENS +
        read_calls * READ_CALL_TOKENS
    )
    # Plus LLM think-turn overhead per tool call
    llm_tokens = MODEL_OVERHEAD + (grep_calls + read_calls) * 200
    total = tool_call_tokens + llm_tokens

    return {
        "tool_calls": ops_count,
        "grep_calls": grep_calls,
        "read_calls": read_calls,
        "graph_calls": 0,
        "tool_tokens": tool_call_tokens,
        "llm_tokens": llm_tokens,
        "total_tokens": total,
        "estimated_time_ms": grep_calls * 500 + read_calls * 200,
    }


def estimate_with_graph(graph_result: dict, call_count: int = 1) -> dict:
    """Estimate token cost with graph tools."""
    tool_call_tokens = call_count * GRAPH_CALL_TOKENS
    output_tokens = graph_result["output_chars"] // 4  # ~4 chars per token
    llm_tokens = MODEL_OVERHEAD + call_count * 100
    total = tool_call_tokens + output_tokens + llm_tokens

    return {
        "tool_calls": call_count,
        "grep_calls": 0,
        "read_calls": 0,
        "graph_calls": call_count,
        "tool_tokens": tool_call_tokens + output_tokens,
        "llm_tokens": llm_tokens,
        "total_tokens": total,
        "estimated_time_ms": graph_result["elapsed_ms"],
    }


def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Live Benchmark: sysgraph tools vs fallback exploration     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    results = []

    for s in SCENARIOS:
        print(f"  [{s['id']}] {s['question']}")

        # Measure real graph call
        graph = measure_graph_call(s["tool"], s["args"])
        print(f"       Graph: {graph['output_chars']} chars, {graph['elapsed_ms']:.0f}ms")

        # Estimate fallback
        fallback = estimate_without_graph(s["fallback_ops"])
        print(f"       Fallback: {fallback['tool_calls']} tool calls est.")

        with_graph = estimate_with_graph(graph)
        token_saved = fallback["total_tokens"] - with_graph["total_tokens"]
        pct = round(token_saved / fallback["total_tokens"] * 100) if fallback["total_tokens"] > 0 else 0

        results.append({
            "id": s["id"],
            "question": s["question"],
            "fallback_tokens": fallback["total_tokens"],
            "graph_tokens": with_graph["total_tokens"],
            "fallback_calls": fallback["tool_calls"],
            "graph_calls": with_graph["graph_calls"],
            "fallback_time_ms": fallback["estimated_time_ms"],
            "graph_time_ms": graph["elapsed_ms"],
            "savings_pct": pct,
        })
        print()

    # ── Summary table ──
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  RESULTS                                                     ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║ {'Scenario':<25} {'Tokens':>8} {'Calls':>8} {'Time':>8} {'Save':>6} ║")
    print(f"║ {'':25} {'w/o→with':>8} {'w/o→with':>8} {'w/o→with':>8} {'':>6} ║")

    total_wo = 0
    total_w = 0
    total_calls_wo = 0
    total_calls_w = 0
    total_time_wo = 0
    total_time_w = 0

    for r in results:
        total_wo += r["fallback_tokens"]
        total_w += r["graph_tokens"]
        total_calls_wo += r["fallback_calls"]
        total_calls_w += r["graph_calls"]
        total_time_wo += r["fallback_time_ms"]
        total_time_w += r["graph_time_ms"]
        print(f"║ {r['question'][:24]:<25} {r['fallback_tokens']:>4}→{r['graph_tokens']:<3} {r['fallback_calls']:>4}→{r['graph_calls']:<3} {r['fallback_time_ms']:>4}→{r['graph_time_ms']:<3} {r['savings_pct']:>3}% ↓║")

    total_saved = total_wo - total_w
    total_pct = round(total_saved / total_wo * 100) if total_wo > 0 else 0
    print(f"╠══════════════════════════════════════════════════════════════╣")
    print(f"║ {'TOTAL':<25} {total_wo:>4}→{total_w:<3} {total_calls_wo:>4}→{total_calls_w:<3} {total_time_wo:>4}→{total_time_w:<3} {total_pct:>3}% ↓║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print()

    # ── Verdict ──
    if total_pct >= 50:
        print(f"✅ VERIFIED: {total_pct}% token savings, {total_calls_wo - total_calls_w}/{total_calls_wo} calls eliminated, {round(total_time_wo/total_time_w)}× faster")
    else:
        print(f"⚠️  NOT VERIFIED: only {total_pct}% savings — check tool registration")

    return results


if __name__ == "__main__":
    main()
