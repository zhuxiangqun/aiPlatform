#!/usr/bin/env python3
"""coupling_metrics.py — 耦合度量基线工具（roadmap Phase 0.2 闭环, 2026-08-25）。

AST 扫描 aiPlat-core/core 下每个 .py 的 import 依赖，输出：
  - avg_degree     平均入边+出边
  - max_degree     最大入边+出边（非聚合点，排除已知聚合点）
  - top-20 高耦合模块
  - baseline 对比（ratchet：新提交不得高于基线，仅允许下降）

用法:
  python3 scripts/coupling_metrics.py                 # 扫描并打印当前指标
  python3 scripts/coupling_metrics.py --baseline PATH  # 对比基线（超基线 → exit 1）
  python3 scripts/coupling_metrics.py --write-baseline PATH  # 生成基线快照

设计依据：docs/research/architecture-evolution-roadmap.md §0.2。
聚合点（允许高入度）：core_facade / integration / schemas 等门面枢纽。
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

# 已知聚合点（门面/枢纽）——排除出 max_degree 计算，避免把聚合点误判为高耦合
AGGREGATION_POINTS = {
    "core/api/core_facade.py",
    "core/harness/integration.py",
    "core/schemas.py",
    "core/harness/syscalls/llm.py",
    "core/harness/knowledge/types.py",
    "core/harness/execution/pipeline_engine.py",
}

EXCLUDE_DIRS = {"__pycache__", "tests", "test", ".venv", "node_modules"}


def _iter_py_files(root: Path):
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in EXCLUDE_DIRS]
        for name in fn:
            if name.endswith(".py"):
                yield Path(dp) / name


def _import_targets(file_path: Path, root: Path) -> Set[str]:
    """AST 提取该文件的 import 依赖（相对 core/ 的模块路径）。"""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return set()
    targets: Set[str] = set()

    def _resolve(name: str) -> str:
        # 把 "core.harness.x" / "core.api.y" 归一为相对路径
        if name.startswith("core."):
            return name.replace(".", "/") + ".py"
        return name

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(_resolve(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                targets.add(_resolve(node.module))
    return targets


def compute_metrics(root: Path) -> Tuple[Dict[str, int], Dict[str, List[str]], List[str]]:
    """返回 (degree_map, dependents_map, module_list)。"""
    modules: List[str] = []
    in_edges: Dict[str, Set[str]] = defaultdict(set)  # module → 谁 import 它
    out_edges: Dict[str, Set[str]] = defaultdict(set)  # module → 它 import 谁

    for f in _iter_py_files(root):
        rel = str(f.relative_to(root))
        if not rel.endswith(".py"):
            continue
        modules.append(rel)
        for tgt in _import_targets(f, root):
            if tgt.endswith(".py"):
                out_edges[rel].add(tgt)
                in_edges[tgt].add(rel)

    degree: Dict[str, int] = {}
    for m in modules:
        degree[m] = len(in_edges.get(m, set())) + len(out_edges.get(m, set()))
    return degree, {k: sorted(v) for k, v in in_edges.items()}, sorted(modules)


def summarize(degree: Dict[str, int], modules: List[str]) -> Dict[str, object]:
    non_agg = {m: d for m, d in degree.items() if m not in AGGREGATION_POINTS}
    avg = sum(degree.values()) / max(len(degree), 1)
    top = sorted(degree.items(), key=lambda x: -x[1])[:20]
    max_non_agg = max(non_agg.values()) if non_agg else 0
    max_non_agg_mod = [m for m, d in non_agg.items() if d == max_non_agg][:5]
    return {
        "module_count": len(modules),
        "avg_degree": round(avg, 3),
        "max_degree_non_aggregation": max_non_agg,
        "max_degree_non_aggregation_modules": max_non_agg_mod,
        "top_20_high_coupling": [{"module": m, "degree": d} for m, d in top],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="耦合度量基线（roadmap §0.2）")
    parser.add_argument("--root", default="aiPlat-core/core", help="扫描根（相对 workspace）")
    parser.add_argument("--baseline", default="", help="基线 JSON 路径（对比，超基线 exit 1）")
    parser.add_argument("--write-baseline", default="", help="写出基线 JSON 路径")
    args = parser.parse_args()

    ws = Path(os.path.dirname(os.path.abspath(__file__))).parent
    root = ws / args.root if not Path(args.root).is_absolute() else Path(args.root)
    if not root.is_dir():
        print(f"error: scan root not found: {root}", file=sys.stderr)
        return 2

    degree, _in, modules = compute_metrics(root)
    stats = summarize(degree, modules)

    if args.write_baseline:
        out = Path(args.write_baseline)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"baseline written: {out}")
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(stats, ensure_ascii=False, indent=2))

    if args.baseline:
        bp = Path(args.baseline)
        if not bp.exists():
            print(f"error: baseline not found: {bp}", file=sys.stderr)
            return 2
        base = json.loads(bp.read_text(encoding="utf-8"))
        violations = []
        if stats["avg_degree"] > base.get("avg_degree", 1e9) + 1e-9:
            violations.append(
                f"avg_degree {stats['avg_degree']} > baseline {base.get('avg_degree')} (ratchet: only下降)")
        if stats["max_degree_non_aggregation"] > base.get("max_degree_non_aggregation", 1e9):
            violations.append(
                f"max_degree(non-agg) {stats['max_degree_non_aggregation']} > baseline "
                f"{base.get('max_degree_non_aggregation')}")
        if violations:
            print("FAIL: " + "; ".join(violations), file=sys.stderr)
            return 1
        print("baseline OK (无新违规，ratchet 通过)")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
