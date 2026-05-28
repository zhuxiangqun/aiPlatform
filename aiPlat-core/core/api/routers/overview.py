"""
System Overview endpoint — aggregates health data from knowledge graphs
plus runtime status (models, agents, servers, pipelines, capability graph).
"""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/overview")
async def system_overview() -> Dict[str, Any]:
    u"""Aggregated system health overview from all layers.

    Returns: {code_health, wiki_health, skill_deps, arch_guard, models, agents, servers, pipeline}
    """
    result: Dict[str, Any] = {}

    # 1. Code graph health
    try:
        from core.harness.knowledge.code_graph import repo_root, default_roots, build_graph, count_cycles, health_score
        repo = repo_root()
        abs_roots = [(repo / r).resolve() for r in default_roots()]
        nodes, edges, issues = build_graph(repo, abs_roots)
        cycles = count_cycles(nodes)
        h = health_score(nodes=nodes, edges=edges, issues=issues, cycles_back_edges=cycles)
        from core.harness.knowledge.code_graph import _find_orphans
        result["code_health"] = {
            "score": h["score"], "grade": h["grade"],
            "files": h["signals"]["files"], "edges": h["signals"]["edges"],
            "cycles": h["signals"]["cycles_back_edges"],
            "avg_degree": h["signals"]["avg_degree"],
            "issues": h["signals"]["issues"],
            "orphan_files": len(_find_orphans(nodes)),
        }
    except Exception:
        result["code_health"] = {"score": 0, "error": "unavailable"}

    # 2. Wiki health
    try:
        from core.harness.knowledge.wiki_engine import wiki_health_report
        wh = wiki_health_report()
        result["wiki_health"] = {
            "score": wh["health_score"], "pages": wh["total_pages"],
            "dead_links": wh["stats"]["dead_links"],
            "orphans": wh["stats"]["orphan_pages"],
            "contradictions": wh["stats"]["contradictions"],
            "categories": wh["stats"].get("categories", {}),
        }
    except Exception:
        result["wiki_health"] = {"score": 0, "error": "unavailable"}

    # 3. Skill dependencies (backward compat — prefer capability_health for full graph)
    try:
        from core.harness.knowledge.skill_deps import build_skill_deps
        sd = build_skill_deps()
        result["skill_deps"] = {
            "skills": sd["stats"]["total_skills"],
            "agents": sd["stats"]["total_agents"],
            "syscalls_used": sd["stats"]["total_syscalls_used"],
            "unknown_refs": sd["stats"]["unknown_references"],
            "unused_skills": sd["stats"]["unused_skills"],
        }
    except Exception:
        result["skill_deps"] = {"skills": 0, "error": "unavailable"}

    # 3b. Capability graph health (replaces skill_deps as primary capability view)
    try:
        from core.harness.knowledge.capability_graph import build_capability_graph
        from core.harness.knowledge.capability_health import capability_health_report
        cg = build_capability_graph()
        ch = capability_health_report(cg)
        result["capability_health"] = {
            "score": ch["score"],
            "grade": ch["grade"],
            "agents": ch["signals"]["agents"],
            "skills": ch["signals"]["skills"],
            "tools": ch["signals"]["tools"],
            "mcp_servers": ch["signals"]["mcp_servers"],
            "used_skills": ch["signals"]["used_skills"],
            "total_nodes": ch["signals"]["total_nodes"],
            "total_edges": ch["signals"]["total_edges"],
            "unused_skills": ch["issues"]["unused_skills"],
            "orphan_agents": ch["issues"]["orphan_agents"],
            "unresolved_refs": len(ch["issues"]["unresolved_refs"]),
        }
    except Exception:
        result["capability_health"] = {"score": 0, "error": "unavailable"}

    # 4. Model status
    try:
        from core.harness.infrastructure.infra_bridge import ModelManager
        models = ModelManager.list_models()
        available = [m for m in models if m.get("status") != "unreachable"]
        result["models"] = {
            "total": len(models),
            "available": len(available),
            "list": [{"name": m.get("name", "?"), "status": m.get("status", "?")}
                     for m in models[:10]],
        }
    except Exception:
        result["models"] = {"total": 0, "available": 0, "list": []}

    # 6. Agent status
    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        rt = get_kernel_runtime()
        agents = []
        if hasattr(rt, 'agent_registry') and rt.agent_registry:
            for aid in list(rt.agent_registry.list_ids() or [])[:20]:
                a = rt.agent_registry.get(aid)
                if a:
                    agents.append({"id": aid, "status": "ready"})
        result["agents"] = {"total": len(agents), "ready": len(agents), "list": agents}
    except Exception:
        result["agents"] = {"total": 0, "ready": 0, "list": []}

    # 7. Server status (port liveness check)
    ports = {"8000": "management", "8001": "infra", "8002": "core", "8003": "platform"}
    servers: Dict[str, str] = {}
    import socket
    for port, name in ports.items():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(("127.0.0.1", int(port)))
            s.close()
            servers[name] = "up"
        except Exception:
            servers[name] = "down"
    result["servers"] = servers

    # 8. Pipeline stats
    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        rt = get_kernel_runtime()
        pipeline = {"active": 0, "completed": 0, "failed": 0}
        if hasattr(rt, 'execution_store') and rt.execution_store:
            store = rt.execution_store
            pipeline["active"] = len(getattr(store, '_active', {}) or {})
        result["pipeline"] = pipeline
    except Exception:
        result["pipeline"] = {"active": 0, "completed": 0, "failed": 0}

    return result
