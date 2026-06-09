"""
System Graph API — interactive knowledge graph visualization + chat.

Endpoints:
  GET  /knowledge-graph/code       → code graph (file-level import deps)
  GET  /knowledge-graph/capability → capability graph (agent/skill/tool/MCP/workflow)  ← fixed
  GET  /knowledge-graph/wiki       → wiki knowledge graph (entities/topics)
  GET  /knowledge-graph/node/{id}  → single node detail (code + deps + blast)
  GET  /knowledge-graph/search?q=  → fuzzy search nodes
  POST /knowledge-graph/chat       → AI chat with graph context (SSE stream)
  GET  /knowledge-graph/layers     → layer statistics
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import StreamingResponse

router = APIRouter(prefix="/knowledge-graph")


def _detect_layer(path: str) -> str:
    if "aiPlat-infra" in path:
        return "infra"
    elif "aiPlat-core" in path:
        return "core"
    elif "aiPlat-platform" in path:
        return "platform"
    elif "aiPlat-app" in path:
        return "app"
    return "unknown"


def _layer_color(layer: str) -> str:
    return {"infra": "#06b6d4", "core": "#8b5cf6", "platform": "#10b981",
            "app": "#f97316", "unknown": "#6b7280"}.get(layer, "#6b7280")


def _shorten(path: str, max_len: int = 40) -> str:
    if len(path) <= max_len:
        return path
    parts = path.split("/")
    if len(parts) <= 2:
        return path[:max_len - 3] + "..."
    return f"{parts[0]}/.../{parts[-1]}"


# ── Code Graph ────────────────────────────────────────────────────

@router.get("/code")
def get_code_graph(
    layer: str = Query(None),
    center: str = Query(None),
    depth: int = Query(2),
) -> Dict[str, Any]:
    """Return code dependency graph in ECharts force-layout format.
    
    When center is provided, extracts a subgraph centered on matching nodes
    with BFS depth=depth (default 2). Otherwise returns the full graph.
    """
    try:
        from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root, count_cycles, health_score

        r = repo_root()
        roots = [(r / d).resolve() for d in default_roots()]
        nodes_raw, edges_raw, issues = build_graph(r, roots)

        # ── Subgraph extraction (when center is provided) ──
        if center:
            center_lower = center.lower()
            center_nodes = {nid for nid in nodes_raw if center_lower in nid.lower()}
            if not center_nodes:
                return {"nodes": [], "links": [], "stats": {"total_nodes": 0, "total_edges": 0},
                        "layers": {}, "categories": [],
                        "message": f"No files matching '{center}'"}
            # BFS from center nodes
            visible = set(center_nodes)
            frontier = set(center_nodes)
            for _ in range(depth):
                next_frontier = set()
                for fid in frontier:
                    for imp in nodes_raw.get(fid, {}).get("out", []):
                        if imp not in visible:
                            visible.add(imp)
                            next_frontier.add(imp)
                    for src, n in nodes_raw.items():
                        if fid in n.get("out", []) and src not in visible:
                            visible.add(src)
                            next_frontier.add(src)
                frontier = next_frontier
                if not frontier:
                    break
            # Filter nodes and edges to visible set
            all_nodes = {nid: n for nid, n in nodes_raw.items() if nid in visible}
            all_edges = [e for e in edges_raw if e["from"] in visible and e["to"] in visible]
            nodes_raw = all_nodes
            edges_raw = all_edges

        # Build ECharts nodes
        nodes_list = []
        for nid, n in nodes_raw.items():
            if layer and _detect_layer(nid) != layer:
                continue
            degree = int(n.get("in", 0)) + len(n.get("out", []))
            nodes_list.append({
                "id": nid,
                "name": _shorten(nid),
                "fullName": nid,
                "category": _detect_layer(nid),
                "symbolSize": min(50, 8 + degree * 1.5),
                "degree": degree,
                "inDegree": int(n.get("in", 0)),
                "outDegree": len(n.get("out", [])),
                "issueCount": n.get("issue_count", 0),
                "ext": n.get("ext", ""),
                "itemStyle": {"color": _layer_color(_detect_layer(nid))},
            })

        # Build ECharts links
        links_list = []
        seen_edges = set()
        for e in edges_raw:
            src, dst = e["from"], e["to"]
            if layer:
                if _detect_layer(src) != layer and _detect_layer(dst) != layer:
                    continue
            key = f"{src}→{dst}"
            if key not in seen_edges:
                seen_edges.add(key)
                links_list.append({"source": src, "target": dst})

        # Health metrics
        cycles = count_cycles(nodes_raw)
        health = health_score(nodes=nodes_raw, edges=edges_raw, issues=issues, cycles_back_edges=cycles)

        return {
            "nodes": nodes_list,
            "links": links_list,
            "stats": {
                "total_nodes": len(nodes_raw),
                "total_edges": len(edges_raw),
                "cycles": cycles,
                "health_score": health["score"],
                "health_grade": health["grade"],
                "avg_degree": health["signals"]["avg_degree"],
                "issues": len(issues),
            },
            "layers": {
                "infra": sum(1 for n in nodes_raw if "aiPlat-infra" in n),
                "core": sum(1 for n in nodes_raw if "aiPlat-core" in n and "aiPlat-infra" not in n),
                "platform": sum(1 for n in nodes_raw if "aiPlat-platform" in n),
                "app": sum(1 for n in nodes_raw if "aiPlat-app" in n),
            },
            "categories": [
                {"name": "infra", "itemStyle": {"color": "#06b6d4"}},
                {"name": "core", "itemStyle": {"color": "#8b5cf6"}},
                {"name": "platform", "itemStyle": {"color": "#10b981"}},
                {"name": "app", "itemStyle": {"color": "#f97316"}},
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Architecture View (Sankey + Treemap) ──────────────────────────

@router.get("/architecture")
def get_architecture_view() -> Dict[str, Any]:
    """Return aggregated architecture data for Sankey (cross-layer flows) and Treemap (intra-layer module structure)."""
    try:
        from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root
        from collections import defaultdict

        r = repo_root()
        roots = [(r / d).resolve() for d in default_roots()]
        nodes, edges, _ = build_graph(r, roots)

        def _layer(p: str) -> str:
            top = p.split("/")[0] if "/" in p else p
            return top.replace("aiPlat-", "") if top.startswith("aiPlat-") else top

        def _module(p: str, depth: int = 2) -> str:
            parts = p.split("/")
            return "/".join(parts[1:1+depth]) if len(parts) > 1 else p

        # ── Sankey: cross-layer import flows (real architecture dependencies) ──
        sankey_nodes_set = set()
        sankey_flows = defaultdict(int)
        for e in edges:
            if e.get("kind", "import") != "import":
                continue  # skip call edges — they're name-matching guesses, not real deps
            src = _layer(e["from"])
            dst = _layer(e["to"])
            if src == dst:
                continue
            sankey_nodes_set.add(src)
            sankey_nodes_set.add(dst)
            sankey_flows[(src, dst)] += 1

        sankey_nodes = [{"name": n} for n in sorted(sankey_nodes_set)]
        sankey_links = [{"source": s, "target": t, "value": v}
                        for (s, t), v in sorted(sankey_flows.items(), key=lambda x: -x[1])]

        # ── Treemap: per-layer module file counts ──
        layer_files = defaultdict(list)
        for p in nodes:
            layer_files[_layer(p)].append(p)

        treemap = {}
        for layer_name, paths in sorted(layer_files.items()):
            mod_tree: dict = {}
            for p in paths:
                parts = p.split("/")[1:]  # skip top-level dir
                if len(parts) < 2:
                    continue
                current = mod_tree
                for part in parts[:-1]:
                    current = current.setdefault(part, {})
                current[parts[-1]] = current.get(parts[-1], 0) + 1

            def _build_children(tree: dict) -> list:
                children = []
                for k, v in sorted(tree.items()):
                    if isinstance(v, dict):
                        children.append({"name": k, "children": _build_children(v)})
                    else:
                        children.append({"name": k, "value": v})
                return children

            treemap[layer_name] = {
                "name": layer_name,
                "file_count": len(paths),
                "children": _build_children(mod_tree),
            }

        return {
            "sankey": {"nodes": sankey_nodes, "links": sankey_links},
            "treemap": [treemap[k] for k in sorted(treemap.keys())],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Capability Graph ──────────────────────────────────────────────

@router.get("/capability")
def get_capability_graph() -> Dict[str, Any]:
    """Return capability dependency graph (agent/skill/tool/MCP/workflow) in ECharts force-layout format."""
    try:
        from core.harness.knowledge.capability_graph import build_capability_graph
        g = build_capability_graph()
        nodes_dict = g.nodes
        edges_list = g.edges

        cat_colors = {
            "agent": "#f97316", "skill": "#8b5cf6", "tool": "#06b6d4",
            "mcp_server": "#10b981", "workflow": "#f59e0b", "entry_point": "#ec4899",
        }
        nodes = []
        for nid, n in nodes_dict.items():
            ntype = n.get("type", "")
            link_count = sum(1 for e in edges_list if e["from"] == nid or e["to"] == nid)
            nodes.append({
                "id": nid,
                "name": str(n.get("label", n.get("raw_id", nid)))[:50],
                "fullName": nid,
                "category": ntype,
                "symbolSize": min(8 + link_count * 2, 50),
                "degree": link_count,
                "itemStyle": {"color": cat_colors.get(ntype, "#9ca3af")},
            })

        links = [{"source": e["from"], "target": e["to"]} for e in edges_list]

        return {
            "nodes": nodes,
            "links": links,
            "stats": {"total_nodes": len(nodes), "total_edges": len(links)},
            "categories": [
                {"name": k, "itemStyle": {"color": v}} for k, v in cat_colors.items()
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Wiki Knowledge Graph ──────────────────────────────────────────

@router.get("/wiki")
def get_wiki_graph(
    category: str = Query(""),
    keyword: str = Query(""),
    source: str = Query(""),
    max_nodes: int = Query(300),
) -> Dict[str, Any]:
    """Return wiki knowledge graph in ECharts force-layout format (3rd tab)."""
    try:
        from core.harness.knowledge.wiki_engine import build_graph as build_wiki_graph
        data = build_wiki_graph(category=category, keyword=keyword, source=source, max_nodes=max_nodes)
        return {
            "nodes": data.get("nodes", []),
            "links": data.get("edges", []),
            "stats": data.get("stats", {}),
            "categories": [
                {"name": "entities", "itemStyle": {"color": "#4d9fff"}},
                {"name": "topics", "itemStyle": {"color": "#a855f7"}},
                {"name": "contradictions", "itemStyle": {"color": "#ef4444"}},
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Node Detail ───────────────────────────────────────────────────

@router.get("/node/{node_id:path}")
def get_node_detail(node_id: str) -> Dict[str, Any]:
    """Return details for a graph node: code, capability, or wiki."""
    try:
        from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root, blast

        r = repo_root()
        roots = [(r / d).resolve() for d in default_roots()]
        nodes_raw, edges_raw, _ = build_graph(r, roots)

        # ── Code graph node ──
        if node_id in nodes_raw:
            node = nodes_raw[node_id]
            full_path = r / node_id
            code_snippet = ""
            try:
                if full_path.exists() and full_path.suffix == ".py":
                    code_snippet = full_path.read_text(encoding="utf-8", errors="ignore")[:3000]
            except Exception:
                pass
            dependencies = [{"path": d, "name": _shorten(d)} for d in node.get("out", [])[:20]]
            dependents = []
            for src, n in nodes_raw.items():
                if node_id in n.get("out", []):
                    dependents.append({"path": src, "name": _shorten(src)})
            dependents = dependents[:20]
            blast_radius = blast(nodes_raw, node_id)
            blast_list = [{"path": b, "name": _shorten(b)} for b in blast_radius[:30]]
            cross_calls: List[Dict[str, Any]] = []
            call_counts: Dict[str, int] = {}
            for e in edges_raw:
                if e.get("kind") == "calls" and e["from"] != e["to"] and e["from"] == node_id:
                    call_counts[e["to"]] = call_counts.get(e["to"], 0) + 1
            cross_calls = [{"path": k, "name": _shorten(k), "count": v}
                           for k, v in sorted(call_counts.items(), key=lambda x: -x[1])[:15]]
            return {
                "id": node_id, "name": _shorten(node_id), "fullName": node_id,
                "ext": node.get("ext", ""), "layer": _detect_layer(node_id),
                "inDegree": int(node.get("in", 0)), "outDegree": len(node.get("out", [])),
                "issueCount": node.get("issue_count", 0), "codeSnippet": code_snippet,
                "dependencies": dependencies, "dependents": dependents,
                "blastRadius": blast_list, "blastCount": len(blast_radius),
                "symbols": node.get("symbols", [])[:30], "crossCalls": cross_calls,
            }

        # ── Capability graph node (agent:, skill:, tool:, etc.) ──
        if ":" in node_id:
            try:
                from core.harness.knowledge.capability_graph import build_capability_graph
                g = build_capability_graph()
                if node_id in g.nodes:
                    n = g.nodes[node_id]
                    ntype = n.get("type", "")
                    return {
                        "id": node_id, "name": str(n.get("label", n.get("raw_id", node_id)))[:60],
                        "fullName": node_id, "ext": "", "layer": ntype,
                        "type": ntype, "category": ntype,
                        "inDegree": sum(1 for e in g.edges if e.get("to") == node_id or e.get("from") == node_id),
                        "outDegree": 0, "issueCount": 0, "codeSnippet": "",
                        "dependencies": [{"path": e["to"], "name": e["to"]} for e in g.edges if e["from"] == node_id][:20],
                        "dependents": [{"path": e["from"], "name": e["from"]} for e in g.edges if e["to"] == node_id][:20],
                        "blastRadius": [], "blastCount": 0,
                        "symbols": [], "crossCalls": [],
                    }
            except Exception:
                pass

        # ── Wiki graph node ──
        try:
            from core.harness.knowledge.wiki_engine import build_graph as build_wiki
            w = build_wiki(keyword=node_id.split("/")[-1], max_nodes=50)
            for node in w.get("nodes", []):
                if node.get("name", "") == node_id or node.get("id", "") == node_id:
                    return {
                        "id": node_id, "name": str(node.get("name", node_id))[:80],
                        "fullName": node_id, "ext": "", "layer": node.get("category", "wiki"),
                        "type": "wiki_page", "category": node.get("category", ""),
                        "inDegree": 0, "outDegree": 0, "issueCount": 0,
                        "codeSnippet": str(node.get("summary", ""))[:2000],
                        "dependencies": [], "dependents": [],
                        "blastRadius": [], "blastCount": 0,
                        "symbols": [], "crossCalls": [],
                    }
        except Exception:
            pass

        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Search ────────────────────────────────────────────────────────

@router.get("/search")
def search_nodes(q: str = Query(...), limit: int = Query(20)) -> List[Dict[str, Any]]:
    """Fuzzy search nodes by name/path."""
    try:
        from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root

        r = repo_root()
        roots = [(r / d).resolve() for d in default_roots()]
        nodes_raw, _, _ = build_graph(r, roots)

        results = []
        q_lower = q.lower()
        for nid, n in nodes_raw.items():
            if q_lower in nid.lower():
                results.append({
                    "id": nid,
                    "name": _shorten(nid),
                    "fullName": nid,
                    "layer": _detect_layer(nid),
                    "ext": n.get("ext", ""),
                    "inDegree": int(n.get("in", 0)),
                    "outDegree": len(n.get("out", [])),
                })
                if len(results) >= limit:
                    break
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Global Search (across code + capability + wiki) ────────────────

@router.get("/global-search")
def global_search(q: str = Query("", min_length=2)) -> Dict[str, Any]:
    """Search across code, capability, and wiki graphs (read-only SQLite — no rebuild)."""
    try:
        from core.harness.knowledge.code_graph_persist import has_cache, load_nodes, search_fts, init_db
        from core.harness.knowledge.cap_graph_persist import load_nodes as load_cap_nodes

        ql = q.lower()
        results: Dict[str, list] = {"code": [], "capability": [], "wiki": []}

        # ── Code graph (SQLite read-only) ──
        try:
            init_db()
            if has_cache():
                fts_matches = search_fts(ql, limit=12)
                if fts_matches:
                    nodes = load_nodes()
                    for nid in fts_matches:
                        n = nodes.get(nid, {})
                        results["code"].append({
                            "path": nid, "short": nid.split("/")[-1],
                            "degree": int(n.get("in", 0) + len(n.get("out", []))),
                            "in": int(n.get("in", 0)), "ext": n.get("ext", ""),
                        })
                        if len(results["code"]) >= 8:
                            break
                # Fallback: substring match on loaded nodes
                if not results["code"]:
                    nodes = load_nodes()
                    for nid, n in nodes.items():
                        if ql in nid.lower():
                            results["code"].append({
                                "path": nid, "short": nid.split("/")[-1],
                                "degree": int(n.get("in", 0) + len(n.get("out", []))),
                                "in": int(n.get("in", 0)), "ext": n.get("ext", ""),
                            })
                            if len(results["code"]) >= 8:
                                break
        except Exception:
            pass

        # ── Capability graph (SQLite read-only) ──
        try:
            cap_nodes = load_cap_nodes()
            for nid, n in cap_nodes.items():
                label = str(n.get("label", ""))
                raw_id = str(n.get("raw_id", ""))
                if ql in nid.lower() or ql in label.lower() or ql in raw_id.lower():
                    results["capability"].append({
                        "id": nid, "label": label[:60],
                        "type": n.get("type", ""),
                    })
                    if len(results["capability"]) >= 5:
                        break
        except Exception:
            pass

        # ── Wiki graph ──
        try:
            from core.harness.knowledge.wiki_engine import build_graph as build_wiki
            w = build_wiki(keyword=q, max_nodes=20)
            for node in w.get("nodes", []):
                results["wiki"].append({
                    "title": node.get("name", "")[:80],
                    "category": node.get("category", ""),
                    "summary": str(node.get("summary", ""))[:150],
                })
                if len(results["wiki"]) >= 5:
                    break
        except Exception:
            pass

        return {"query": q, "results": results, "total": sum(len(v) for v in results.values())}
    except Exception as e:
        return {"query": q, "error": str(e)[:200], "results": {"code": [], "capability": [], "wiki": []}, "total": 0}


# ── NL → Graph Query Translation ───────────────────────────────────

@router.post("/ask")
async def graph_ask(req: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a natural language question into a sysgraph query using a local or configured model."""
    question = str(req.get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose

        model_name = best_model_for_purpose("query_translation")
        if not model_name:
            return {"answer": "无可用模型，请配置 AIPLAT_QUERY_MODEL 或启动 Ollama/LM Studio", "results": {}}

        model = create_selected_adapter(model_name=model_name)

        from core.harness.utils.prompt_loader import _async_prompt_resolve
        prompt = await _async_prompt_resolve("graph-ask", question=question)

        resp = await model.generate([
            {"role": "system", "content": await _async_prompt_resolve("graph-system-role")},
            {"role": "user", "content": prompt},
        ], config=None)

        content = resp.content if hasattr(resp, 'content') else str(resp)
        import re as _re, json as _json
        clean = content.strip()
        # Strip markdown and extract JSON
        for prefix in ("```json", "```"):
            if clean.startswith(prefix):
                clean = clean[len(prefix):].strip()
        if clean.endswith("```"):
            clean = clean[:-3].strip()
        match = _re.search(r'\{[\s\S]*\}', clean)
        data = {}
        if match:
            try:
                data = _json.loads(match.group(0))
            except _json.JSONDecodeError:
                data = {"answer": content[:300]}

        answer = data.get("answer", "")
        tool = data.get("tool", "")
        args = data.get("args", {})

        # Execute the sysgraph tool if specified
        results = None
        if tool:
            results = _execute_graph_tool(tool, args)

        # Phase 2: translate results into natural language (reuse same model)
        if results and tool:
            try:
                import json as _json
                results_text = _json.dumps(results, ensure_ascii=False, default=str)[:3000]
                translate_prompt = await _async_prompt_resolve(
                    "graph-ask-translate", question=question, results_text=results_text
                )

                resp2 = await model.generate([
                    {"role": "system", "content": await _async_prompt_resolve("graph-architect-role")},
                    {"role": "user", "content": translate_prompt},
                ], config=None)
                answer = (resp2.content if hasattr(resp2, 'content') else str(resp2))[:800]
            except Exception:
                pass  # keep Phase 1 answer as fallback

        return {"answer": answer, "tool": tool, "args": args, "results": results}
    except Exception as e:
        return {"answer": f"查询失败: {str(e)[:200]}", "results": {}}


def _execute_graph_tool(tool: str, args: dict) -> dict:
    """Execute a sysgraph tool and return results."""
    try:
        if tool == "sysgraph_stats":
            from core.apps.tools.sysgraph_tools import SysGraphStatsTool
            import asyncio
            r = asyncio.get_event_loop().run_until_complete(SysGraphStatsTool().execute())
            return {"output": r.output[:2000] if r.output else str(r.error)} if hasattr(r, 'output') else {}
        elif tool == "sysgraph_search":
            name = args.get("name", args.get("query", ""))
            from core.apps.tools.sysgraph_tools import SysGraphSearchTool
            import asyncio
            r = asyncio.get_event_loop().run_until_complete(SysGraphSearchTool().execute(query=name))
            return {"output": r.output[:2000] if r.output else str(r.error)} if hasattr(r, 'output') else {}
        elif tool == "sysgraph_hotspots":
            metric = args.get("metric", "indegree")
            from core.apps.tools.sysgraph_tools import SysGraphHotspotsTool
            import asyncio
            r = asyncio.get_event_loop().run_until_complete(SysGraphHotspotsTool().execute(metric=metric, limit=8))
            return {"output": r.output[:2000] if r.output else str(r.error)} if hasattr(r, 'output') else {}
        elif tool == "sysgraph_churn":
            from core.apps.tools.sysgraph_tools import SysGraphChurnTool
            import asyncio
            r = asyncio.get_event_loop().run_until_complete(SysGraphChurnTool().execute(limit=10))
            return {"output": r.output[:2000] if r.output else str(r.error)} if hasattr(r, 'output') else {}
        elif tool == "sysgraph_tests":
            from core.apps.tools.sysgraph_tools import SysGraphTestsTool
            import asyncio
            r = asyncio.get_event_loop().run_until_complete(SysGraphTestsTool().execute(untested=True, limit=10))
            return {"output": r.output[:2000] if r.output else str(r.error)} if hasattr(r, 'output') else {}
        elif tool == "sysgraph_find":
            name = args.get("name", args.get("query", ""))
            kind = args.get("kind", "")
            from core.apps.tools.sysgraph_tools import SysGraphFindTool
            import asyncio
            r = asyncio.get_event_loop().run_until_complete(SysGraphFindTool().execute(name=name, kind=kind))
            return {"output": r.output[:2000] if r.output else str(r.error)} if hasattr(r, 'output') else {}
        elif tool == "sysgraph_callers":
            filepath = args.get("file", args.get("path", ""))
            from core.apps.tools.sysgraph_tools import SysGraphCallersTool
            import asyncio
            r = asyncio.get_event_loop().run_until_complete(SysGraphCallersTool().execute(file=filepath))
            return {"output": r.output[:2000] if r.output else str(r.error)} if hasattr(r, 'output') else {}
        elif tool == "sysgraph_impact":
            filepath = args.get("file", args.get("path", ""))
            from core.apps.tools.sysgraph_tools import SysGraphImpactTool
            import asyncio
            r = asyncio.get_event_loop().run_until_complete(SysGraphImpactTool().execute(file=filepath))
            return {"output": r.output[:2000] if r.output else str(r.error)} if hasattr(r, 'output') else {}
        elif tool == "describe_layer":
            return _describe_layer(
                layer=args.get("layer", "core"),
                question_type=args.get("type", "capabilities"),
            )
        return {}
    except Exception as e:
        return {"error": str(e)[:200]}


def _describe_layer(layer: str = "core", question_type: str = "capabilities") -> dict:
    u"""Auto-generated layer description from code graph + capability graph data."""
    from collections import defaultdict
    import json

    valid_layers = {"core", "infra", "platform", "app", "management"}
    if layer not in valid_layers:
        return {"error": f"Unknown layer: {layer}. Valid: {', '.join(sorted(valid_layers))}"}

    prefix = f"aiPlat-{layer}/"
    output: dict = {"layer": layer, "type": question_type}

    if question_type == "capabilities":
        # ── Module hierarchy + top symbols ──
        try:
            from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root
            r = repo_root()
            roots = [(r / d).resolve() for d in default_roots()]
            nodes, _, _ = build_graph(r, roots)
        except Exception:
            nodes = {}

        modules: dict = {}
        for path, n in nodes.items():
            if not path.startswith(prefix):
                continue
            parts = path.replace(prefix, "").split("/")
            mod_key = "/".join(parts[:2]) if len(parts) > 2 else parts[0] if parts else path
            if mod_key not in modules:
                modules[mod_key] = {"files": 0, "symbols_count": 0, "key_symbols": []}
            modules[mod_key]["files"] += 1
            modules[mod_key]["symbols_count"] += len(n.get("symbols", []))
            for name, kind, line in n.get("symbols", [])[:2]:
                if not name.startswith("_") and name not in modules[mod_key]["key_symbols"]:
                    modules[mod_key]["key_symbols"].append(name)
                    if len(modules[mod_key]["key_symbols"]) >= 3:
                        break

        # Sort by file count
        sorted_mods = sorted(modules.items(), key=lambda x: -x[1]["files"])
        output["modules"] = {k: v for k, v in sorted_mods[:20]}

        # ── Capability graph (agents, skills, tools) ──
        try:
            from core.harness.knowledge.capability_graph import build_capability_graph
            g = build_capability_graph()
            agents = [n.get("label", nid) for nid, n in g.nodes.items()
                      if n.get("type") == "agent"][:10]
            skills = [n.get("label", nid) for nid, n in g.nodes.items()
                      if n.get("type") == "skill"][:15]
            tools_count = sum(1 for nid, n in g.nodes.items() if n.get("type") == "tool")
            output["agents"] = agents
            output["skills"] = skills
            output["tools_count"] = tools_count
        except Exception:
            pass

        output["total_files"] = sum(m["files"] for m in modules.values())
        output["total_symbols"] = sum(m["symbols_count"] for m in modules.values())

    elif question_type == "relationships":
        # ── Cross-layer import flows ──
        try:
            from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root
            r = repo_root()
            roots = [(r / d).resolve() for d in default_roots()]
            _, edges, _ = build_graph(r, roots)
        except Exception:
            edges = []

        def _layer(p: str) -> str:
            top = p.split("/")[0] if "/" in p else p
            return top.replace("aiPlat-", "") if top.startswith("aiPlat-") else top

        imports_to = defaultdict(int)
        imports_from = defaultdict(int)
        for e in edges:
            if e.get("kind", "import") != "import":
                continue
            src = _layer(e["from"])
            dst = _layer(e["to"])
            if src == dst:
                continue
            if src == layer:
                imports_to[dst] += 1
            if dst == layer:
                imports_from[src] += 1

        output["imports_to"] = dict(imports_to)
        output["imports_from"] = dict(imports_from)
        output["summary"] = f'{layer} → {dict(imports_to)}, {layer} ← {dict(imports_from)}'

    elif question_type == "interfaces":
        # ── REST API endpoints ──
        import re as _re
        route_pattern = _re.compile(r'@\w+\.(?:get|post|put|delete|patch)\s*\(\s*"([^"]+)"')
        endpoints = []
        try:
            from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root
            r = repo_root()
            roots = [(r / d).resolve() for d in default_roots()]
            nodes, _, _ = build_graph(r, roots)
        except Exception:
            nodes = {}

        for path in nodes:
            if not path.startswith(prefix):
                continue
            if "api/" not in path and "routers/" not in path:
                continue
            if not path.endswith(".py"):
                continue
            fpath = r / path
            if not fpath.exists():
                continue
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")[:10000]
                for m in route_pattern.finditer(content):
                    endpoints.append(m.group(1))
            except Exception:
                pass

        output["endpoints"] = sorted(set(endpoints))[:30]
        output["endpoint_count"] = len(set(endpoints))

    return output


# ── AI Chat ───────────────────────────────────────────────────────

@router.post("/chat")
async def graph_chat(req: Dict[str, Any]) -> StreamingResponse:
    """SSE-streamed AI chat with knowledge graph context injection."""
    question = req.get("question", "")
    history = req.get("history", [])
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    async def stream() -> AsyncIterator[str]:
        try:
            # Build graph context
            from core.harness.knowledge.code_graph import build_context, _ctx_to_prompt
            ctx = build_context(question)
            if not ctx:
                yield f"data: {json.dumps({'token': '无法构建代码上下文，请确保已运行诊断。'})}\n\n"
                yield "data: [DONE]\n\n"
                return

            from core.harness.utils.prompt_loader import _async_prompt_resolve
            prompt = await _async_prompt_resolve("graph-chat-stream",
                context=_ctx_to_prompt(ctx, max_chars=2000),
                question=question,
            )

            # Stream LLM response via SSE
            from core.harness.syscalls.llm import sys_llm_generate_stream
            async for chunk in sys_llm_generate_stream(best_model_for_purpose("query_translation"), prompt, max_tokens=600):  # noqa: model-legacy
                if chunk:
                    yield f"data: {json.dumps({'token': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'token': f'Error: {e}'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Layer Stats ───────────────────────────────────────────────────

@router.get("/layers")
def get_layer_stats() -> Dict[str, Any]:
    """Return per-layer statistics."""
    try:
        from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root

        r = repo_root()
        roots = [(r / d).resolve() for d in default_roots()]
        nodes_raw, edges_raw, _ = build_graph(r, roots)

        layers = {"infra": 0, "core": 0, "platform": 0, "app": 0, "management": 0}
        for nid in nodes_raw:
            l = _detect_layer(nid)
            if l in layers:
                layers[l] += 1

        cross_edges = 0
        for e in edges_raw:
            src_layer = _detect_layer(e["from"])
            dst_layer = _detect_layer(e["to"])
            if src_layer != dst_layer:
                cross_edges += 1

        return {
            "files_per_layer": layers,
            "total_files": len(nodes_raw),
            "total_edges": len(edges_raw),
            "cross_layer_edges": cross_edges,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Codebase Stats ────────────────────────────────────────────────

@router.get("/stats")
def get_codebase_stats() -> Dict[str, Any]:
    """Return global codebase statistics for the SystemOverview panel."""
    try:
        from core.harness.knowledge.code_graph import (
            build_graph, default_roots, repo_root, health_score, count_cycles
        )
        r = repo_root()
        roots = [(r / d).resolve() for d in default_roots()]
        nodes, edges, _ = build_graph(r, roots)

        import_edges = sum(1 for e in edges if e.get("kind", "import") == "import")
        cross_calls = sum(1 for e in edges if e.get("cross"))
        total_symbols = sum(len(n.get("symbols", [])) for n in nodes.values())
        cycles = count_cycles(nodes)
        health = health_score(nodes=nodes, edges=edges, issues=[], cycles_back_edges=cycles)

        layers: Dict[str, Dict[str, int]] = {}
        for p, n in nodes.items():
            top = p.split("/")[0] if "/" in p else "other"
            layer = top.replace("aiPlat-", "") if top.startswith("aiPlat-") else "other"
            if layer not in layers:
                layers[layer] = {"files": 0, "symbols": 0}
            layers[layer]["files"] += 1
            layers[layer]["symbols"] += len(n.get("symbols", []))

        top_in = sorted(nodes.items(), key=lambda x: x[1].get("in", 0), reverse=True)[:5]
        top_out = sorted(nodes.items(), key=lambda x: len(x[1].get("out", [])), reverse=True)[:5]

        return {
            "total_files": len(nodes),
            "total_edges": len(edges),
            "import_edges": import_edges,
            "cross_calls": cross_calls,
            "total_symbols": total_symbols,
            "cycles": cycles,
            "health_score": health.get("score", 0),
            "health_grade": health.get("grade", "?"),
            "layers": layers,
            "top_imported": [{"path": p.split("/")[-1], "in": n.get("in", 0)} for p, n in top_in],
            "top_dependents": [{"path": p.split("/")[-1], "out": len(n.get("out", []))} for p, n in top_out],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
