#!/usr/bin/env python3
"""Ontology Pipeline Benchmark — batch process documents and output metrics.

Usage:
  python scripts/benchmark_ontology.py --dir ~/.aiplat/test_docs/ --domain ai-knowledge
  python scripts/benchmark_ontology.py --file doc.md --domain ship-design
"""

from __future__ import annotations

import argparse
import os as _os
import sys as _sys
import time as _time
from dataclasses import dataclass, field
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional

# Add project root to path
_PROJECT = _Path(__file__).resolve().parent.parent
_sys.path.insert(0, str(_PROJECT / "aiPlat-core"))
_sys.path.insert(0, str(_PROJECT / "aiPlat-infra"))


@dataclass
class DocMetrics:
    file: str = ""
    format: str = ""
    chunks: int = 0
    instances: int = 0
    merged: int = 0
    tables: int = 0
    transitions: int = 0
    relations: int = 0
    graph_nodes: int = 0
    graph_edges: int = 0
    inferred_edges: int = 0
    time_parse: float = 0.0
    time_classify: float = 0.0
    time_indicators: float = 0.0
    time_state: float = 0.0
    time_resolve: float = 0.0
    time_graph: float = 0.0
    time_total: float = 0.0
    warnings: List[str] = field(default_factory=list)


def benchmark_file(file_path: str, domain_id: str = "ai-knowledge") -> DocMetrics:
    m = DocMetrics(file=_Path(file_path).name)
    t0 = _time.time()

    from core.harness.ontology_engine.document_parser import DocumentParser
    from core.harness.ontology_engine.engine import load_engine
    from core.harness.ontology_engine.class_mapper import ClassMapper
    from core.harness.ontology_engine.state_machine import EvalContext, compute_indicators
    from core.harness.ontology_engine.entity_resolver import EntityResolver

    dp = DocumentParser()
    parsed = dp.parse_file(file_path)
    m.format = parsed.format
    m.chunks = len(parsed.chunks)
    m.time_parse = _time.time() - t0
    m.tables = len(getattr(parsed, 'tables', []) or [])

    engine = load_engine(domain_id)
    if not engine:
        m.warnings.append("domain not found: " + domain_id)
        m.time_total = _time.time() - t0
        return m

    mapper = ClassMapper(engine._domain)
    t1 = _time.time()
    instances = []
    for ch in parsed.chunks:
        cls = mapper.classify_text(ch.text, threshold=0.5)
        if cls:
            instances.append({
                "class_name": cls,
                "entity_text": (ch.heading_path[-1] if ch.heading_path else ch.text[:40]),
                "properties": {"name": ch.heading_path[-1] if ch.heading_path else ch.text[:40]},
                "chunk_id": ch.id,
                "frontmatter": {"tags": []},
            })
    m.time_classify = _time.time() - t1

    # Entity resolver
    t2 = _time.time()
    if len(instances) > 1:
        resolver = EntityResolver(engine._domain)
        resolved = resolver.resolve(instances, doc_type=parsed.format)
        m.merged = resolved.stats.get("merged", 0)
        instances = resolved.merged
    m.time_resolve = _time.time() - t2
    m.instances = len(instances)

    # Indicators
    t3 = _time.time()
    ctx = EvalContext(instances)
    compute_indicators(instances, ctx)
    m.time_indicators = _time.time() - t3

    # State machine
    sm = getattr(engine, "_state_machine", None)
    t4 = _time.time()
    for inst in instances:
        chain = sm.evaluate_chain(inst, ctx)
        if chain:
            m.transitions += len(chain)
            inst["properties"]["state"] = chain[-1].to_state
    m.time_state = _time.time() - t4

    # Relations + Graph
    t5 = _time.time()
    from core.harness.ontology_engine.graph_index import GraphIndex
    graph = GraphIndex(domain_id)
    for inst in instances:
        graph.add_entity(inst.get("entity_text", inst.get("properties", {}).get("name", "")),
                         inst.get("entity_text", inst.get("properties", {}).get("name", "")),
                         inst.get("class_name", ""))

    # Simple document-wide relation detection
    rel_count = 0
    rel_map = {
        ("AI方法", "AI系统"): "implements",
        ("AI系统", "AI概念"): "applies",
        ("AI方法", "业务问题"): "solves",
        ("AI系统", "业务问题"): "addresses",
    }
    for ia in instances:
        for ib in instances:
            if ia is ib:
                continue
            key = (ia.get("class_name", ""), ib.get("class_name", ""))
            if key in rel_map:
                graph.add_relation(ia.get("entity_text", ""), ib.get("entity_text", ""),
                                   rel_map[key], inverse_name=rel_map[key] + "_by")
                rel_count += 1

    graph.save()
    m.relations = rel_count
    m.graph_nodes = len(graph)
    m.graph_edges = graph.stats().get("edge_count", 0)
    m.time_graph = _time.time() - t5
    m.time_total = _time.time() - t0
    return m


def print_report(metrics_list: List[DocMetrics]) -> None:
    print("=" * 85)
    print(f"{'File':20s} {'Fmt':4s} {'Chunks':6s} {'Inst':5s} {'Tbl':4s} {'Trans':5s} {'Rels':5s} {'Graph':10s} {'Time':>7s}")
    print("-" * 85)
    for m in metrics_list:
        graph_str = f"{m.graph_nodes}n/{m.graph_edges}e"
        print(f"{m.file[:19]:20s} {m.format:4s} {m.chunks:5d}  {m.instances:4d}  {m.tables:3d}  {m.transitions:4d}  {m.relations:4d}  {graph_str:10s} {m.time_total:6.2f}s")
    print("-" * 85)
    total_chunks = sum(m.chunks for m in metrics_list)
    total_inst = sum(m.instances for m in metrics_list)
    total_trans = sum(m.transitions for m in metrics_list)
    total_nodes = sum(m.graph_nodes for m in metrics_list)
    total_edges = sum(m.graph_edges for m in metrics_list)
    avg_time = sum(m.time_total for m in metrics_list) / len(metrics_list) if metrics_list else 0
    print(f"{'TOTAL':20s} {'':4s} {total_chunks:5d}  {total_inst:4d}  {sum(m.tables for m in metrics_list):3d}  {total_trans:4d}  {sum(m.relations for m in metrics_list):4d}  {total_nodes}n/{total_edges}e {avg_time:5.2f}s avg")
    print("=" * 85)

    # ── Percentile Statistics ──
    if len(metrics_list) >= 1:
        times = sorted([m.time_total for m in metrics_list])
        p50 = times[len(times) // 2]
        p95 = times[min(int(len(times) * 0.95), len(times) - 1)]
        p99 = times[min(int(len(times) * 0.99), len(times) - 1)]

        step_names = ["parse", "classify", "resolve", "indicators", "state", "graph"]
        step_times = {
            "parse": [m.time_parse for m in metrics_list],
            "classify": [m.time_classify for m in metrics_list],
            "resolve": [m.time_resolve for m in metrics_list],
            "indicators": [m.time_indicators for m in metrics_list],
            "state": [m.time_state for m in metrics_list],
            "graph": [m.time_graph for m in metrics_list],
        }
        print(f"\n{'Latency':15s} {'Min':>8s} {'Avg':>8s} {'P50':>8s} {'P95':>8s} {'P99':>8s}")
        print("-" * 55)
        for name in step_names:
            vals = step_times[name]
            sv = sorted(vals)
            p50v = sv[len(sv)//2]
            p95v = sv[min(int(len(sv)*0.95), len(sv)-1)]
            p99v = sv[min(int(len(sv)*0.99), len(sv)-1)]
            avgv = sum(vals)/len(vals)
            minv = min(vals)
            print(f"{name:15s} {minv:7.4f}s {avgv:7.4f}s {p50v:7.4f}s {p95v:7.4f}s {p99v:7.4f}s")
        print("-" * 55)
        svt = sorted(times)
        print(f"{'TOTAL':15s} {svt[0]:7.4f}s {avg_time:7.4f}s {p50:7.4f}s {p95:7.4f}s {p99:7.4f}s")
        print(f"\n  ✅ Pipeline target: < 60s  |  P95: {p95:.2f}s {'✅' if p95 < 60 else '❌'}")


def main():
    parser = argparse.ArgumentParser(description="Benchmark ontology pipeline")
    parser.add_argument("--dir", help="Directory of documents to process")
    parser.add_argument("--file", help="Single file to process")
    parser.add_argument("--domain", default="ai-knowledge", help="Ontology domain ID")
    parser.add_argument("--graph-only", action="store_true", help="Only print graph stats")
    args = parser.parse_args()

    files = []
    if args.dir:
        d = _Path(args.dir)
        if d.exists():
            files = sorted(str(p) for p in d.iterdir() if p.suffix in (".md", ".txt", ".html", ".pdf", ".docx"))
    if args.file:
        files.append(args.file)

    if not files:
        print("No files found. Use --dir or --file.")
        _sys.exit(1)

    metrics = []
    for f in files:
        try:
            m = benchmark_file(f, args.domain)
            metrics.append(m)
        except Exception as e:
            print(f"  ERROR {_Path(f).name}: {e}")

    if args.graph_only:
        for m in metrics:
            print(f"{m.file}: {m.graph_nodes} nodes, {m.graph_edges} edges")
    else:
        print_report(metrics)


if __name__ == "__main__":
    main()
