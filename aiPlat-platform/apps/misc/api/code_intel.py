from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request

from core.harness.kernel.runtime import get_kernel_runtime

# Shared graph functions — extracted to harness layer (CLAUDE.md §5.x compliance)
from core.harness.knowledge.code_graph import (
    _PY_IMPORT_RE as _PY_IMPORT_RE_ORIG, _JS_IMPORT_RE,
    repo_root, default_roots,
    _strip_py_type_checking, _is_code_file, _should_skip, _read_text,
    _resolve_js_relative, _resolve_py_module, _detect_issues,
    build_graph as _build_graph,
    convert_file_graph_to_symbols,
    count_cycles as _count_cycles,
    health_score as _health_score,
    blast,
    ScanResult,
)

router = APIRouter()


def _is_aggregator_file(path: str) -> Tuple[bool, str]:
    """
    Heuristic: files that act as "wiring"/"barrel"/"router include" hubs.
    These tend to have extremely high degree and can distort health metrics.
    """
    p = str(path).replace("\\", "/")
    name = p.split("/")[-1]
    if name in {"server.py"}:
        return True, "server_entry"
    # Kernel runtime is a global registry / facade used across the codebase.
    if path.replace("\\", "/").endswith("core/harness/kernel/runtime.py"):
        return True, "kernel_runtime_registry"
    # Harness integration is a unified entry point (facade) that intentionally wires many pieces.
    if path.replace("\\", "/").endswith("core/harness/integration.py"):
        return True, "harness_integration_facade"
    if name in {"__init__.py"}:
        return True, "python_package_init"
    if name in {"index.ts", "index.tsx", "index.js", "index.jsx"}:
        return True, "frontend_barrel_index"
    if p.endswith("aiPlat-management/frontend/src/App.tsx") or p.endswith("aiPlat-management/frontend/src/main.tsx"):
        return True, "frontend_app_entry"
    if "/core/api/routers/" in p:
        return True, "api_router_module"
    if p.endswith("/api/rest/routes.py") or p.endswith("/api/rest/routes.ts"):
        return True, "routes_entry"
    if p.endswith("/gateway/router.py") or p.endswith("/gateway/router.ts"):
        return True, "gateway_router"
    return False, ""


def _effective_health(
    *,
    nodes: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, str]],
    issues: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute health metrics excluding aggregator files (wiring / routers / barrel exports).
    This gives a more actionable signal for architecture refactors.
    """
    excluded: Set[str] = set()
    for p in nodes.keys():
        ok, _ = _is_aggregator_file(p)
        if ok:
            excluded.add(p)
    if not excluded:
        cyc = _count_cycles(nodes)
        return _health_score(nodes=nodes, edges=edges, issues=issues, cycles_back_edges=cyc)

    filt_nodes = {k: v for k, v in nodes.items() if k not in excluded}
    filt_edges = [e for e in edges if (e.get("from") not in excluded) and (e.get("to") not in excluded)]
    filt_issues = [it for it in issues if str(it.get("file") or "") not in excluded]
    cyc = _count_cycles(filt_nodes) if filt_nodes else 0
    base = _health_score(nodes=filt_nodes or {"_": {"out": [], "in": 0}}, edges=filt_edges, issues=filt_issues, cycles_back_edges=cyc)
    base["excluded_aggregators"] = len(excluded)
    return base


def _aggregate_by_folder(
    *,
    nodes: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, str]],
    depth: int = 2,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """
    Reduce node count by folding file paths into folder buckets:
      depth=1 => "aiPlat-core"
      depth=2 => "aiPlat-core/core"
    """
    depth = max(1, min(6, int(depth)))

    def bucket(path: str) -> str:
        parts = [p for p in str(path).split("/") if p]
        return "/".join(parts[:depth]) if parts else str(path)

    agg: Dict[str, Dict[str, Any]] = {}
    for p, n in nodes.items():
        b = bucket(p)
        if b not in agg:
            agg[b] = {"id": b, "path": b, "kind": "folder", "file_count": 0, "issue_count": 0, "in": 0, "out_count": 0}
        agg[b]["file_count"] += 1
        agg[b]["issue_count"] += int(n.get("issue_count") or 0)

    # edges between buckets
    out_sets: Dict[str, Set[str]] = {k: set() for k in agg.keys()}
    in_counts: Dict[str, int] = {k: 0 for k in agg.keys()}
    edge_set: Set[Tuple[str, str]] = set()
    for e in edges:
        a = bucket(e.get("from") or "")
        b = bucket(e.get("to") or "")
        if not a or not b or a == b:
            continue
        if a not in agg or b not in agg:
            continue
        if (a, b) not in edge_set:
            edge_set.add((a, b))
            out_sets[a].add(b)
            in_counts[b] += 1

    out_edges = [{"from": a, "to": b} for (a, b) in sorted(edge_set)]
    for k, v in out_sets.items():
        agg[k]["out_count"] = len(v)
        agg[k]["in"] = int(in_counts.get(k) or 0)

    return list(agg.values()), out_edges


def _layer_bucket(path: str) -> str:
    """
    Productized "architecture layer" bucketing for this monorepo.
    Goal: stable, readable groups (not pure depth-based).
    """
    p = str(path).replace("\\", "/")

    # aiPlat-core layers
    if p.startswith("aiPlat-core/core/"):
        rest = p[len("aiPlat-core/core/") :]
        if rest.startswith("api/"):
            return "aiPlat-core:api"
        if rest.startswith("harness/"):
            return "aiPlat-core:harness"
        if rest.startswith("apps/"):
            return "aiPlat-core:apps"
        if rest.startswith("services/"):
            return "aiPlat-core:services"
        if rest.startswith("governance/"):
            return "aiPlat-core:governance"
        if rest.startswith("security/"):
            return "aiPlat-core:security"
        if rest.startswith("learning/"):
            return "aiPlat-core:learning"
        if rest.startswith("management/"):
            return "aiPlat-core:management"
        if rest.startswith("mcp/"):
            return "aiPlat-core:mcp"
        if rest.startswith("observability/"):
            return "aiPlat-core:observability"
        if rest.startswith("orchestration/"):
            return "aiPlat-core:orchestration"
        return "aiPlat-core:core-other"
    if p.startswith("aiPlat-core/agents/"):
        return "aiPlat-core:agents"
    if p.startswith("aiPlat-core/scripts/"):
        return "aiPlat-core:scripts"

    # aiPlat-infra layers
    if p.startswith("aiPlat-infra/infra/"):
        rest = p[len("aiPlat-infra/infra/"):]
        for sub in ("llm", "vector", "cache", "database", "storage", "network",
                    "messaging", "monitoring", "observability", "memory",
                    "config", "http", "di", "management", "logging", "utils"):
            if rest.startswith(f"{sub}/") or rest == sub:
                return f"infra:{sub}"
        return "infra:other"
    if p.startswith("aiPlat-infra/config/"):
        return "infra:config"
    if p.startswith("aiPlat-infra/"):
        return "infra:root"

    # aiPlat-platform layers
    if p.startswith("aiPlat-platform/"):
        rest = p[len("aiPlat-platform/"):]
        for sub in ("api", "auth", "billing", "builder", "deployment",
                    "gateway", "governance", "kb", "messaging", "registry",
                    "services", "storage", "tenants", "utils", "data"):
            if rest.startswith(f"{sub}/") or rest == sub:
                return f"platform:{sub}"
        return "platform:other"

    # aiPlat-app layers
    if p.startswith("aiPlat-app/"):
        rest = p[len("aiPlat-app/"):]
        for sub in ("api", "channels", "cli", "events", "generated",
                    "services", "storage", "utils", "workbench", "data"):
            if rest.startswith(f"{sub}/") or rest == sub:
                return f"app:{sub}"
        return "app:other"

    # Frontend layers (management frontend)
    if p.startswith("aiPlat-management/frontend/"):
        rest = p[len("aiPlat-management/frontend/") :]
        if rest.startswith("src/pages/"):
            return "frontend:pages"
        if rest.startswith("src/services/"):
            return "frontend:services"
        if rest.startswith("src/components/"):
            return "frontend:components"
        if rest.startswith("src/utils/"):
            return "frontend:utils"
        if rest.startswith("src/hooks/"):
            return "frontend:hooks"
        if rest.startswith("src/store/"):
            return "frontend:store"
        if rest.startswith("src/"):
            return "frontend:src-other"
        return "frontend:other"

    # Management backend layers
    if p.startswith("aiPlat-management/management/"):
        rest = p[len("aiPlat-management/management/"):]
        for sub in ("api", "diagnostics", "monitoring", "alerting",
                    "dashboard", "services", "config"):
            if rest.startswith(f"{sub}/") or rest == sub:
                return f"management:{sub}"
        return "management:other"

    # Fallback
    if p.startswith("aiPlat-core/"):
        return "aiPlat-core:other"
    if p.startswith("aiPlat-infra/"):
        return "infra:other"
    if p.startswith("aiPlat-platform/"):
        return "platform:other"
    if p.startswith("aiPlat-app/"):
        return "app:other"
    if p.startswith("aiPlat-management/"):
        return "aiPlat-management:other"
    return "other"


def _aggregate_by_layer(
    *,
    nodes: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, str]],
    bucket_fn=_layer_bucket,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Aggregate file graph into "architecture layers" based on repo-aware rules.
    - nodes: layers with file_count/issue_count
    - edges: unique directed edges between layers, with weight (# underlying edges)
    """
    agg: Dict[str, Dict[str, Any]] = {}
    file_to_layer: Dict[str, str] = {}

    for p, n in nodes.items():
        b = str(bucket_fn(p))
        file_to_layer[p] = b
        if b not in agg:
            agg[b] = {
                "id": b,
                "path": b,
                "kind": "layer",
                "file_count": 0,
                "issue_count": 0,
                "in": 0,
                "out_count": 0,
                "out": [],
            }
        agg[b]["file_count"] += 1
        agg[b]["issue_count"] += int(n.get("issue_count") or 0)

    # edge weights between layers
    weights: Dict[Tuple[str, str], int] = {}
    out_sets: Dict[str, Set[str]] = {k: set() for k in agg.keys()}
    in_counts: Dict[str, int] = {k: 0 for k in agg.keys()}

    for e in edges:
        src = str(e.get("from") or "")
        dst = str(e.get("to") or "")
        a = file_to_layer.get(src) or bucket_fn(src)
        b = file_to_layer.get(dst) or bucket_fn(dst)
        if not a or not b or a == b:
            continue
        if a not in agg or b not in agg:
            continue
        weights[(a, b)] = weights.get((a, b), 0) + 1
        out_sets[a].add(b)

    # finalize in/out counts
    for (a, b), w in weights.items():
        in_counts[b] = in_counts.get(b, 0) + 1
    for k, v in out_sets.items():
        agg[k]["out"] = sorted(v)
        agg[k]["out_count"] = len(v)
    for k in agg.keys():
        agg[k]["in"] = int(in_counts.get(k) or 0)

    out_edges = [{"from": a, "to": b, "weight": w} for (a, b), w in sorted(weights.items(), key=lambda x: (-x[1], x[0][0], x[0][1]))]
    return list(agg.values()), out_edges


def _top_insights(
    *,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, str]],
    max_items: int = 15,
    compute_blast_for_top: int = 10,
) -> Dict[str, Any]:
    """
    Product-ish insights for UI: top degree / top issues / top blast.
    Bounded-cost: blast is computed only for the top-N degree candidates.
    """
    deg: Dict[str, int] = {}
    out_map: Dict[str, List[str]] = {}
    node_by_id: Dict[str, Dict[str, Any]] = {}

    for n in nodes:
        pid = str(n.get("path") or n.get("id") or "")
        if not pid:
            continue
        node_by_id[pid] = n
        out = n.get("out") if isinstance(n.get("out"), list) else None
        out_count = len(out) if isinstance(out, list) else int(n.get("out_count") or 0)
        inn = int(n.get("in") or 0)
        deg[pid] = out_count + inn
        out_map[pid] = [str(x) for x in out] if isinstance(out, list) else []

    top_degree = sorted(
        [{"path": k, "degree": int(v), "issue_count": int((node_by_id.get(k) or {}).get("issue_count") or 0)} for k, v in deg.items()],
        key=lambda x: (x.get("degree", 0), x.get("issue_count", 0)),
        reverse=True,
    )[: max_items]

    top_issues = sorted(
        [
            {
                "path": str(n.get("path") or n.get("id") or ""),
                "issue_count": int(n.get("issue_count") or 0),
                "degree": int(deg.get(str(n.get("path") or n.get("id") or ""), 0)),
            }
            for n in nodes
            if str(n.get("path") or n.get("id") or "")
        ],
        key=lambda x: (x.get("issue_count", 0), x.get("degree", 0)),
        reverse=True,
    )[: max_items]

    # Blast for top candidates (best-effort; bounded)
    blast_rank: List[Dict[str, Any]] = []
    nodes_dict: Dict[str, Dict[str, Any]] = {k: {"out": out_map.get(k) or []} for k in out_map.keys()}
    for it in top_degree[: max(1, int(compute_blast_for_top))]:
        p = str(it.get("path") or "")
        if p and p in nodes_dict:
            blast_rank.append(
                {
                    "path": p,
                    "blast_count": len(blast(nodes_dict, p)),
                    "degree": int(it.get("degree") or 0),
                    "issue_count": int(it.get("issue_count") or 0),
                }
            )
    blast_rank.sort(key=lambda x: (x.get("blast_count", 0), x.get("degree", 0)), reverse=True)
    blast_rank = blast_rank[: max_items]

    recs: List[str] = []
    if top_degree and int(top_degree[0].get("degree") or 0) >= 25:
        recs.append("存在高耦合节点：建议优先拆分/抽象边界（从 Top Degree 开始）")
    if top_issues and int(top_issues[0].get("issue_count") or 0) >= 3:
        recs.append("存在多风险文件：建议把硬编码密钥/危险用法纳入 CI 或在 Gate 中升级为阻断")
    if blast_rank and int(blast_rank[0].get("blast_count") or 0) >= 40:
        recs.append("存在大影响面节点：建议对相关变更强制走更严格的 GatePolicy（autosmoke+approval）")

    return {"top_degree": top_degree, "top_issues": top_issues, "top_blast": blast_rank, "recommendations": recs}


def _top_hubs(
    *,
    nodes: Dict[str, Dict[str, Any]],
    issues: List[Dict[str, Any]],
    limit: int = 20,
    compute_blast_for_top: int = 10,
) -> List[Dict[str, Any]]:
    issue_count_by_file: Dict[str, int] = {}
    for it in issues:
        f = str(it.get("file") or "")
        if f:
            issue_count_by_file[f] = issue_count_by_file.get(f, 0) + 1

    deg_list: List[Tuple[str, int, int, int]] = []  # (path, degree, in, out)
    for p, n in nodes.items():
        out = n.get("out") or []
        outc = len(out) if isinstance(out, list) else 0
        inc = int(n.get("in") or 0)
        deg_list.append((p, outc + inc, inc, outc))
    deg_list.sort(key=lambda x: x[1], reverse=True)

    # blast on a bounded subset (best-effort)
    blast_counts: Dict[str, int] = {}
    tiny_nodes = {k: {"out": (v.get("out") or [])} for k, v in nodes.items()}
    for p, _, _, _ in deg_list[: max(1, int(compute_blast_for_top))]:
        try:
            blast_counts[p] = len(blast(tiny_nodes, p))
        except Exception:
            blast_counts[p] = 0

    out: List[Dict[str, Any]] = []
    for p, d, inc, outc in deg_list[: int(limit)]:
        is_ag, reason = _is_aggregator_file(p)
        out.append(
            {
                "path": p,
                "degree": int(d),
                "in": int(inc),
                "out": int(outc),
                "issue_count": int(issue_count_by_file.get(p) or int(nodes.get(p, {}).get("issue_count") or 0)),
                "blast_count": int(blast_counts.get(p) or 0),
                "is_aggregator": bool(is_ag),
                "aggregator_reason": reason or None,
            }
        )
    return out


def _tarjan_scc(graph: Dict[str, List[str]]) -> List[List[str]]:
    """
    Tarjan SCC algorithm.
    graph: node -> outgoing list
    """
    index = 0
    stack: List[str] = []
    on_stack: Set[str] = set()
    idx: Dict[str, int] = {}
    low: Dict[str, int] = {}
    out: List[List[str]] = []

    def strongconnect(v: str):
        nonlocal index
        idx[v] = index
        low[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)

        for w in graph.get(v, []) or []:
            if w not in idx:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], idx[w])

        if low[v] == idx[v]:
            comp: List[str] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                comp.append(w)
                if w == v:
                    break
            out.append(comp)

    for v in list(graph.keys()):
        if v not in idx:
            strongconnect(v)
    return out


def _top_cycles(
    *,
    nodes: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, str]],
    limit: int = 20,
) -> List[Dict[str, Any]]:
    graph: Dict[str, List[str]] = {k: list(v.get("out") or []) for k, v in nodes.items()}
    comps = _tarjan_scc(graph)
    # keep SCCs with size >= 2
    sccs = [c for c in comps if len(c) >= 2]
    # score by size + internal edges
    edge_set = {(str(e.get("from") or ""), str(e.get("to") or "")) for e in edges}
    scored: List[Tuple[int, int, List[str]]] = []
    for comp in sccs:
        s = set(comp)
        internal = 0
        for a in comp:
            for b in graph.get(a, []) or []:
                if b in s and (a, b) in edge_set:
                    internal += 1
        scored.append((len(comp), internal, sorted(comp)))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    out: List[Dict[str, Any]] = []
    for size, internal, comp in scored[: int(limit)]:
        out.append({"size": int(size), "internal_edges": int(internal), "nodes": comp[:200]})
    return out


def _health_by_root(*, roots: List[str], nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]], issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for r in roots:
        prefix = str(r).rstrip("/") + "/"
        sub_nodes = {k: v for k, v in nodes.items() if str(k).startswith(prefix) or str(k) == str(r)}
        if not sub_nodes:
            continue
        sub_edges = [e for e in edges if str(e.get("from") or "").startswith(prefix) and str(e.get("to") or "").startswith(prefix)]
        sub_issues = [it for it in issues if str(it.get("file") or "").startswith(prefix)]
        cyc = _count_cycles(sub_nodes)
        out[r] = _health_score(nodes=sub_nodes, edges=sub_edges, issues=sub_issues, cycles_back_edges=cyc)
    return out


async def code_intel_scan(rt, roots: List[str]) -> ScanResult:
    roots_key = ",".join(roots)

    _repo_root = repo_root()
    abs_roots = [(_repo_root / r).resolve() for r in roots]
    nodes, edges, issues = _build_graph(_repo_root, abs_roots)
    cycles = _count_cycles(nodes)
    health = _health_score(nodes=nodes, edges=edges, issues=issues, cycles_back_edges=cycles)
    stats = {
        "_repo_root": str(_repo_root),
        "roots": [str(r) for r in roots],
        "files": len(nodes),
        "edges": len(edges),
        "cycles_back_edges": cycles,
        "issues": len(issues),
    }
    return ScanResult(created_at=time.time(), roots_key=roots_key, stats=stats, nodes=nodes, edges=edges, issues=issues, health=health)


@router.get("/diagnostics/code-intel/scan", response_model=Dict[str, Any])
async def scan_code_intel(
    request: Request,
    roots: Optional[str] = None,
    mode: str = "file",
    depth: int = 2,
    limit: int = 0,
    rt=Depends(get_kernel_runtime),
):
    """
    Code intelligence scan (CodeFlow-inspired, server-side).
    Defaults to scanning: aiPlat-core + aiPlat-management/frontend

    mode: file | folder | layer | symbol
    """
    store = getattr(rt, "execution_store", None) if rt else None
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    root_list = [x.strip() for x in (roots.split(",") if roots else default_roots()) if x.strip()]
    res = await code_intel_scan(rt, root_list)
    mode = str(mode or "file").strip().lower()
    if mode not in {"file", "folder", "layer", "symbol"}:
        mode = "file"

    # Symbol mode: convert to per-function/class nodes
    if mode == "symbol":
        _root = repo_root()
        symbol_nodes, symbol_edges = convert_file_graph_to_symbols(res.nodes, res.edges, _root)
        return {
            "status": "ok",
            "mode": "symbol",
            "stats": {"nodes": len(symbol_nodes), "edges": len(symbol_edges)},
            "nodes": list(symbol_nodes.values()),
            "links": symbol_edges,
            "issues": [],
        }

    nodes_out: List[Dict[str, Any]]
    edges_out: List[Dict[str, str]]
    issues_out: List[Dict[str, Any]] = res.issues
    stats_out = dict(res.stats)

    if mode == "folder":
        nodes_out, edges_out = _aggregate_by_folder(nodes=res.nodes, edges=res.edges, depth=int(depth or 2))
        # in folder mode, issues list is still file-based; keep it but front-end may ignore
        stats_out["mode"] = "folder"
        stats_out["depth"] = int(depth or 2)
        stats_out["folders"] = len(nodes_out)
        stats_out["edges"] = len(edges_out)
    elif mode == "layer":
        nodes_out, edges_out = _aggregate_by_layer(nodes=res.nodes, edges=res.edges)
        stats_out["mode"] = "layer"
        stats_out["layers"] = len(nodes_out)
        stats_out["edges"] = len(edges_out)
    else:
        nodes_out = list(res.nodes.values())
        edges_out = res.edges
        stats_out["mode"] = "file"
        if int(limit or 0) > 0 and len(nodes_out) > int(limit):
            # keep most informative nodes: by (issue_count, degree)
            def _rank(n: Dict[str, Any]) -> Tuple[int, int]:
                return (int(n.get("issue_count") or 0), int((len(n.get("out") or [])) + int(n.get("in") or 0)))

            nodes_out.sort(key=_rank, reverse=True)
            keep_ids = set(str(n.get("id") or n.get("path") or "") for n in nodes_out[: int(limit)])
            nodes_out = [n for n in nodes_out if str(n.get("id") or n.get("path") or "") in keep_ids]
            edges_out = [e for e in edges_out if str(e.get("from") or "") in keep_ids and str(e.get("to") or "") in keep_ids]
            issues_out = [it for it in issues_out if str(it.get("file") or "") in keep_ids]
            stats_out["limited_to"] = int(limit)
            stats_out["files"] = len(nodes_out)
            stats_out["edges"] = len(edges_out)
            stats_out["issues"] = len(issues_out)

    health = dict(res.health)
    try:
        health["by_root"] = _health_by_root(roots=root_list, nodes=res.nodes, edges=res.edges, issues=res.issues)
    except Exception:
        health["by_root"] = {}
    # effective metrics (excluding aggregator/wiring files)
    try:
        health["effective"] = _effective_health(nodes=res.nodes, edges=res.edges, issues=res.issues)
    except Exception:
        health["effective"] = None
    insights = _top_insights(nodes=nodes_out, edges=edges_out, max_items=15, compute_blast_for_top=10)
    governance = {
        "top_hubs": _top_hubs(nodes=res.nodes, issues=res.issues, limit=20, compute_blast_for_top=10),
        "top_cycles": _top_cycles(nodes=res.nodes, edges=res.edges, limit=20),
    }

    return {
        "status": "ok",
        "stats": stats_out,
        "health": health,
        "insights": insights,
        "governance": governance,
        "nodes": nodes_out,
        "edges": edges_out,
        "issues": issues_out,
    }


@router.get("/diagnostics/code-intel/hubs", response_model=Dict[str, Any])
async def code_intel_hubs(roots: Optional[str] = None, limit: int = 30, rt=Depends(get_kernel_runtime)):
    root_list = [x.strip() for x in (roots.split(",") if roots else default_roots()) if x.strip()]
    res = await code_intel_scan(rt, root_list)
    return {"status": "ok", "roots": root_list, "hubs": _top_hubs(nodes=res.nodes, issues=res.issues, limit=int(limit or 30), compute_blast_for_top=15)}


@router.get("/diagnostics/code-intel/cycles", response_model=Dict[str, Any])
async def code_intel_cycles(roots: Optional[str] = None, limit: int = 30, rt=Depends(get_kernel_runtime)):
    root_list = [x.strip() for x in (roots.split(",") if roots else default_roots()) if x.strip()]
    res = await code_intel_scan(rt, root_list)
    return {"status": "ok", "roots": root_list, "cycles": _top_cycles(nodes=res.nodes, edges=res.edges, limit=int(limit or 30))}


@router.get("/diagnostics/code-intel/blast", response_model=Dict[str, Any])
async def blast_radius(
    file: str,
    roots: Optional[str] = None,
    rt=Depends(get_kernel_runtime),
):
    root_list = [x.strip() for x in (roots.split(",") if roots else default_roots()) if x.strip()]
    res = await code_intel_scan(rt, root_list)
    start = str(file).strip()
    out = blast(res.nodes, start)
    return {"status": "ok", "file": start, "affected": out, "count": len(out)}


@router.get("/diagnostics/code-intel/export", response_model=Dict[str, Any])
async def export_code_graph(rt=Depends(get_kernel_runtime)):
    """Export the full code graph as committable JSON for team onboarding."""
    import time as _t
    root_list = default_roots()
    res = await code_intel_scan(rt, root_list)
    nodes_export = {}
    for n in res.nodes.values():
        node_id = str(n.get("id") or n.get("path") or "")
        nodes_export[node_id] = {
            "id": node_id,
            "path": n.get("path", ""),
            "in_degree": int(n.get("in") or 0),
            "out_degree": int(len(n.get("out") or [])),
            "out": n.get("out", []),
            "routes": [{"path": r[0] if isinstance(r, (list,tuple)) else str(r), "handler": r[1] if isinstance(r, (list,tuple)) and len(r)>1 else ""} for r in (n.get("routes") or [])],
            "symbols": [s[0] if isinstance(s, (list, tuple)) else str(s) for s in (n.get("symbols") or [])],
            "layer": _layer_bucket(n.get("path", "")),
            "issue_count": int(n.get("issue_count") or 0),
        }
    return {
        "generated_at": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()),
        "stats": {"nodes": len(nodes_export), "edges": len(res.edges), "issues": len(res.issues)},
        "health": res.health,
        "nodes": nodes_export,
        "edges": res.edges,
    }


@router.get("/diagnostics/code-intel/tour", response_model=Dict[str, Any])
async def guided_tour(limit: int = 30, rt=Depends(get_kernel_runtime)):
    """Return dependency-sorted file list for guided architecture tour."""
    root_list = default_roots()
    res = await code_intel_scan(rt, root_list)
    
    sorted_nodes = sorted(
        res.nodes.values(),
        key=lambda n: (int(n.get("in") or 0), -(len(n.get("out") or [])))
    )[:int(limit)]
    
    tour = []
    for n in sorted_nodes:
        node_id = str(n.get("id") or n.get("path") or "")
        symbols = [s[0] if isinstance(s, (list, tuple)) else str(s) for s in (n.get("symbols") or [])]
        tour.append({
            "file": node_id,
            "layer": _layer_bucket(n.get("path", "")),
            "in_degree": int(n.get("in") or 0),
            "out_degree": int(len(n.get("out") or [])),
            "symbols": symbols[:8],
            "routes": [{"path": r[0] if isinstance(r, (list,tuple)) else str(r), "handler": r[1] if isinstance(r, (list,tuple)) and len(r)>1 else ""} for r in (n.get("routes") or [])],
            "issue_count": int(n.get("issue_count") or 0),
        })
    
    return {"tour": tour, "total": len(res.nodes)}


@router.get("/diagnostics/code-intel/domain-view", response_model=Dict[str, Any])
async def domain_view(rt=Depends(get_kernel_runtime)):
    """Aggregate code graph into business domains."""
    root_list = default_roots()
    res = await code_intel_scan(rt, root_list)
    nodes = res.nodes
    edges = res.edges

    DOMAIN_RULES = [
        (lambda p: any(x in p for x in ["agents/", "AGENT.md"]), "agent_engineering", "研发 Agent", "#3b82f6"),
        (lambda p: any(x in p for x in ["product_manager", "pm_agent", "prd"]), "product", "产品管理", "#f59e0b"),
        (lambda p: any(x in p for x in ["qa_agent", "/tests/", "/test_", "/e2e", "quality"]), "qa", "质量保证", "#22c55e"),
        (lambda p: any(x in p for x in ["architect", "/design", "design_pattern"]), "architecture", "架构设计", "#8b5cf6"),
        (lambda p: any(x in p for x in ["src/pages/", "src/components/", "App.tsx"]), "frontend_ui", "前端界面", "#ec4899"),
        (lambda p: any(x in p for x in ["src/services/", "src/hooks/", "src/stores/"]), "frontend_api", "前端数据层", "#f472b6"),
        (lambda p: any(x in p for x in ["api/routers/", "api/rest/", "facades/"]), "backend_api", "后端 API", "#6366f1"),
        (lambda p: any(x in p for x in ["harness/execution/", "harness/syscalls/"]), "core_engine", "执行引擎", "#06b6d4"),
        (lambda p: any(x in p for x in ["harness/knowledge/", "harness/memory/"]), "core_knowledge", "知识记忆", "#14b8a6"),
        (lambda p: any(x in p for x in ["apps/mcp/", "mcps/", "mcp_manager"]), "mcp_system", "MCP 系统", "#eab308"),
        (lambda p: any(x in p for x in ["infra/", "model/", "storage/"]), "infra", "基础设施", "#6b7280"),
        (lambda p: any(x in p for x in ["apps/skills/", "skills/", "SKILL.md"]), "skills", "技能库", "#10b981"),
        (lambda p: any(x in p for x in ["apps/agents/", "engine/agents/"]), "agent_definition", "Agent 定义", "#ef4444"),
        (lambda p: any(x in p for x in ["_manager.py", "governance", "audit"]), "governance", "治理审计", "#f97316"),
        (lambda p: any(x in p for x in ["workspace_seeds/", "templates/"]), "templates", "种子模板", "#84cc16"),
        (lambda p: any(x in p for x in ["docs/", "md$"]), "docs", "文档", "#9ca3af"),
        (lambda p: any(x in p for x in ["harness/assembly/", "harness/infrastructure/", "harness/coordination/", "harness/feedback", "harness/evaluation"]), "core_runtime", "核心运行时", "#0ea5e9"),
        (lambda p: any(x in p for x in ["generated/", "_stage_", "_final_"]), "generated", "生成产物", "#78716c"),
    ]

    domains: Dict[str, Dict] = {}
    for nid, nd in nodes.items():
        matched = False
        for rule_fn, domain_id, label, color in DOMAIN_RULES:
            if rule_fn(nid):
                domains.setdefault(domain_id, {"id": domain_id, "name": label, "color": color, "files": [], "total_symbols": 0})
                domains[domain_id]["files"].append(nid)
                symbols = nd.get("symbols", [])
                domains[domain_id]["total_symbols"] += len(symbols) if isinstance(symbols, list) else 0
                matched = True
                break
        if not matched:
            domains.setdefault("other", {"id": "other", "name": "其他", "color": "#4b5563", "files": [], "total_symbols": 0})
            domains["other"]["files"].append(nid)

    file_to_domain = {}
    for did, d in domains.items():
        for f in d["files"]:
            file_to_domain[f] = did

    domain_edges = []
    seen = set()
    for e in edges:
        from_d = file_to_domain.get(e.get("from", ""))
        to_d = file_to_domain.get(e.get("to", ""))
        if from_d and to_d and from_d != to_d:
            key = f"{from_d}->{to_d}"
            if key not in seen:
                seen.add(key)
                domain_edges.append({"from": from_d, "to": to_d, "kind": e.get("kind", "import")})

    domain_nodes = [{"id": d["id"], "name": d["name"], "color": d["color"], "files": len(d["files"]), "symbols": d["total_symbols"]} for d in domains.values()]
    domain_nodes.sort(key=lambda x: -x["files"])

    return {"domains": domain_nodes, "edges": domain_edges, "total_files": len(nodes)}
