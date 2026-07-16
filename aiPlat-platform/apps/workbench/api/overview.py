"""
System Overview endpoint — aggregates system state by architecture layer.

Returns four-layer structure with per-component health indicators:
  infra    — models, LLM, servers, storage
  core     — agents, skills, tools, mcp, pipeline, memory, syscalls, workflows
  platform — gateway, users, tenants, kb, builder, approvals, sessions, policies
  app      — channels, conversations, sessions, apps
"""

from typing import Any, Dict, List, Optional
import asyncio
import httpx
import logging
import os
import socket
import time
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter()

_log = logging.getLogger("aiplat.overview")

# ── Overview cache (persistent to disk, survives restart) ───
_OV_CACHE: Optional[Dict[str, Any]] = None
_OV_CACHE_TS: float = 0.0


def _ov_cache_path() -> str:
    import os
    return os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "overview_cache.json")


def _load_ov_cache():
    global _OV_CACHE, _OV_CACHE_TS
    try:
        import json
        path = _ov_cache_path()
        if os.path.exists(path):
            with open(path, "r") as f:
                _OV_CACHE = json.load(f)
            _OV_CACHE_TS = time.time()
    except Exception as e:
        logging.warning(str(e), exc_info=True)


def _save_ov_cache():
    try:
        import json
        path = _ov_cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if _OV_CACHE:
            with open(path, "w") as f:
                json.dump(_OV_CACHE, f, ensure_ascii=False, default=str)
    except Exception as e:
        logging.warning(str(e), exc_info=True)


# Load persisted cache on module init — SKIP: governance data may change across restarts
# _load_ov_cache()


def _safe_enum_value(obj, attr: str) -> str:
    """Safely extract string value from an enum attribute."""
    try:
        v = getattr(obj, attr, None)
        if v is None:
            return ""
        return str(getattr(v, 'value', v))
    except Exception:
        return ""


async def _get_real_llm_metrics() -> Dict[str, Any]:
    u"""Query execution_store for real LLM usage stats (24h window)."""
    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        if not store:
            return {}
        import sqlite3
        conn = sqlite3.connect(store._config.db_path)
        try:
            now = time.time()
            cutoff = now - 86400
            row = conn.execute(
                "SELECT COUNT(*),"
                " COALESCE(SUM(CASE WHEN status='success' THEN 1 ELSE 0 END), 0),"
                " COALESCE(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END), 0),"
                " COALESCE(AVG(duration_ms), 0)"
                " FROM syscall_events"
                " WHERE kind='llm' AND start_time > ?",
                (cutoff,)
            ).fetchone()

            total = row[0] or 0
            success = row[1] or 0
            failed = row[2] or 0
            avg_lat = round(row[3] or 0, 1)
            success_rate = round(success / max(total, 1) * 100, 1) if total > 0 else None

            # Token aggregation (use dedicated INTEGER columns, indexed for performance)
            token_row = conn.execute(
                "SELECT COALESCE(SUM(input_tokens + output_tokens), 0)"
                " FROM syscall_events"
                " WHERE kind='llm' AND status='success' AND start_time > ?",
                (cutoff,)
            ).fetchone()
            total_tokens = token_row[0] or 0 if token_row else 0

            # Hourly breakdown for trend
            hourly = conn.execute(
                "SELECT strftime('%H', start_time, 'unixepoch') AS hr,"
                " COUNT(*) AS cnt,"
                " COALESCE(AVG(duration_ms), 0) AS lat,"
                " COALESCE(SUM(CASE WHEN status='success' THEN 1 ELSE 0 END), 0) AS ok"
                " FROM syscall_events"
                " WHERE kind='llm' AND start_time > ?"
                " GROUP BY hr ORDER BY hr",
                (cutoff,)
            ).fetchall()

            trend = [{"hour": int(h), "count": c, "latency_ms": round(l, 1), "ok": o}
                     for h, c, l, o in (hourly or [])]

            return {
                "requests_24h": total,
                "success_rate": success_rate,
                "avg_latency_ms": avg_lat,
                "total_tokens_24h": total_tokens,
                "error_count_24h": failed,
                "hourly_trend": trend,
            }
        finally:
            conn.close()
    except Exception:
        return {}


@router.get("/diagnostics/llm/metrics", response_model=Dict[str, Any])
async def get_llm_metrics():
    u"""Return comprehensive LLM usage metrics (24h window)."""
    return await _get_real_llm_metrics()


async def _scan_governance() -> Dict[str, Any]:
    """
    Shared governance scan — returns total/governed/unsigned/no_manifest/has_trusted_keys/score.
    Used by both system_overview() and diagnostics._check_governance().
    """
    import json as _json
    home = os.environ.get("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    entity_globs = {
        "skills": ("skills", "SKILL.manifest.json"),
        "agents": ("agents", "AGENT.manifest.json"),
        "mcps": ("mcps", "MCP.manifest.json"),
        "workflows": ("workflows", "WORKFLOW.manifest.json"),
        "projects": ("projects", "PROJECT.manifest.json"),
        "prompt_apps": ("prompt-apps", "TEMPLATE.manifest.json"),
    }
    gov_total = 0
    gov_governed = 0
    gov_unsigned = 0
    gov_no_manifest = 0

    engine_root = Path(__file__).resolve().parents[3] / "core" / "engine"
    extra_paths = [
        (engine_root / "skills", "SKILL.manifest.json"),
        (engine_root / "agents", "AGENT.manifest.json"),
        (engine_root / "mcps", "MCP.manifest.json"),
    ]

    all_dirs: list[tuple[Path, str]] = []
    for ent_type, (subdir, mf_name) in entity_globs.items():
        all_dirs.append((Path(home) / subdir, mf_name))
    for p, mf_name in extra_paths:
        if p.exists() and p.is_dir():
            all_dirs.append((p, mf_name))

    for base_dir, mf_name in all_dirs:
        if not base_dir.is_dir():
            continue
        for edir in base_dir.iterdir():
            if not edir.is_dir() or edir.name.startswith("."):
                continue
            gov_total += 1
            mf = edir / mf_name
            if not mf.exists():
                gov_no_manifest += 1
                continue
            try:
                with open(mf) as f:
                    mdata = _json.load(f)
                if mdata.get("signature"):
                    gov_governed += 1
                else:
                    gov_unsigned += 1
            except Exception:
                gov_unsigned += 1

    has_keys = False
    try:
        from core.harness.kernel.runtime import get_kernel_runtime as _g_rt
        _g_runtime = _g_rt()
        store = getattr(_g_runtime, "execution_store", None) if _g_runtime else None
        if store:
            gs = await store.get_global_setting(key="trusted_skill_pubkeys")
            keys = (gs.get("value", {}).get("keys") or []) if gs and isinstance(gs, dict) else []
            has_keys = len(keys) > 0
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    score = 100
    score -= gov_no_manifest * 2
    score -= gov_unsigned * 0.5
    # Only penalize missing keys when there are unsigned/unmanifested entities
    if not has_keys and gov_total > 0 and (gov_no_manifest > 0 or gov_unsigned > 0):
        score -= 20
    score = max(0, score)

    return {
        "total": gov_total, "governed": gov_governed,
        "unsigned": gov_unsigned, "no_manifest": gov_no_manifest,
        "has_trusted_keys": has_keys, "score": score,
    }


@router.get("/overview", response_model=Dict[str, Any])
async def system_overview(refresh: bool = Query(False)) -> Dict[str, Any]:
    u"""Aggregated system state organized by architecture layer."""
    global _OV_CACHE, _OV_CACHE_TS

    # Force refresh — clear cache
    if refresh:
        _OV_CACHE = None

    # Return cached result if available
    if _OV_CACHE is not None:
        import json
        return json.loads(json.dumps(_OV_CACHE))

    result: Dict[str, Any] = {"infra": {}, "core": {}, "platform": {}, "app": {}}

    # ==================================================================
    # INFRA — Layer 0: Infrastructure
    # ==================================================================
    infra: Dict[str, Any] = {
        "status": "healthy", "models": {}, "llm": {}, "servers": {}, "storage": {},
    }
    infra_issues = 0

    # -- Models --
    try:
        from infra.management.model.manager import ModelManager as InfraModelManager
        mgr = InfraModelManager()
        models = await mgr.list_models()
        available = [m for m in models if _safe_enum_value(m, 'status') not in ("unreachable", "error", "not_configured")]
        infra["models"] = {
            "total": len(models),
            "available": len(available),
            "by_type": {
                "chat": sum(1 for m in models if _safe_enum_value(m, 'type') == "chat"),
                "embedding": sum(1 for m in models if _safe_enum_value(m, 'type') == "embedding"),
                "reranker": sum(1 for m in models if _safe_enum_value(m, 'type') == "reranker"),
                "audio": sum(1 for m in models if _safe_enum_value(m, 'type') == "audio"),
                "ocr": sum(1 for m in models if _safe_enum_value(m, 'type') == "ocr"),
            },
            "providers": list(sorted(set(
                getattr(m, 'provider', '') or 'unknown' for m in models
            ))),
        }
        if len(models) == 0:
            infra_issues += 1
    except Exception as e:
        _log.warning(f"Models scan failed: {e}")
        infra["models"] = {"total": 0, "available": 0, "error": "unavailable"}
        infra_issues += 1

    # -- LLM stats (real data from syscall_events, with infra ModelManager as fallback) --
    try:
        llm_metrics = await _get_real_llm_metrics()
        if llm_metrics.get("requests_24h", 0) > 0:
            infra["llm"] = llm_metrics
        else:
            # Fallback to ModelManager for model listing
            from infra.management.llm.manager import LLMManager
            llm_mgr = LLMManager()
            infra["llm"] = {
                "requests_24h": 0, "success_rate": None, "avg_latency_ms": 0,
                "total_tokens_24h": 0, "error_count_24h": 0,
            }
    except Exception as e:
        _log.warning(f"LLM stats failed: {e}")
        infra["llm"] = {"error": "unavailable"}

    # -- Storage --
    storage_ok = 0
    storage_total = 0
    for kind in ("database", "vector", "cache"):
        storage_total += 1
        try:
            if kind == "database":
                from infra.management.database.manager import DatabaseManager
                dm = DatabaseManager()
                db_hc = await dm.health_check()
                db_metrics = (await dm.get_metrics()) if hasattr(dm, 'get_metrics') else []
                conn = 0
                for m in db_metrics if isinstance(db_metrics, list) else []:
                    conn += getattr(m, 'connections', 0) or 0
                infra["storage"]["database"] = {
                    "status": db_hc.status.value if db_hc else "unknown",
                    "connections": conn,
                }
            elif kind == "vector":
                from infra.management.vector.manager import VectorManager
                vm = VectorManager()
                vec_hc = await vm.health_check()
                vec_metrics = (await vm.get_metrics()) if hasattr(vm, 'get_metrics') else []
                coll = 0
                for m in vec_metrics if isinstance(vec_metrics, list) else []:
                    coll += getattr(m, 'collections', 0) or 0
                infra["storage"]["vector"] = {
                    "status": vec_hc.status.value if vec_hc else "unknown",
                    "collections": coll,
                }
            elif kind == "cache":
                try:
                    from infra.cache.manager import DefaultCacheManager
                    cm = DefaultCacheManager()
                    stats = await cm.get_stats()
                    infra["storage"]["cache"] = {"hits": stats.get("hits", 0), "misses": stats.get("misses", 0)}
                except Exception:
                    infra["storage"]["cache"] = {"note": "not configured"}
            storage_ok += 1
        except Exception as e:
            _log.debug(f"Storage {kind} check failed: {e}")
            infra["storage"][kind] = {"error": "unavailable"}
    if storage_total > 0 and storage_ok < storage_total:
        infra_issues += 1

    # -- Servers (port liveness) --
    ports = {"management": 8000, "infra": 8001, "core": 8002, "platform": 8003, "app": 8004}
    servers_status: Dict[str, str] = {}
    for name, port in ports.items():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(("127.0.0.1", port))
            s.close()
            servers_status[name] = "up"
        except Exception:
            servers_status[name] = "down"
    infra["servers"] = servers_status
    up_count = sum(1 for v in servers_status.values() if v == "up")
    down_count = len(ports) - up_count
    if down_count > 0:
        infra_issues += 1

    # Aggregate infra status — delegate to authoritative /health endpoint
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("http://localhost:8001/api/infra/health")
            if r.status_code == 200:
                hc = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                infra["status"] = hc.get("status", "healthy")
            else:
                infra["status"] = "degraded"
    except Exception:
        if infra_issues >= 3:
            infra["status"] = "unhealthy"
        elif infra_issues >= 1:
            infra["status"] = "degraded"
        else:
            infra["status"] = "healthy"

    result["infra"] = infra

    # ==================================================================
    # CORE — Layer 1: AI Platform Runtime
    # ==================================================================
    core: Dict[str, Any] = {
        "status": "healthy", "agents": {}, "skills": {}, "tools": 0,
        "mcp_servers": 0, "pipeline": {}, "memory": {}, "syscalls": {},
        "workflows": 0, "capability_health": {},
    }
    core_issues = 0
    rt = None

    # -- Agents --
    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        rt = get_kernel_runtime()
        engine_count = 0
        agent_types: Dict[str, int] = {}
        if hasattr(rt, "agent_registry") and rt.agent_registry:
            ids = rt.agent_registry.list_ids() or []
            engine_count = len(ids)
            for aid in ids:
                try:
                    meta = rt.agent_registry.get_agent_metadata(aid)
                    at = str(meta.get("type", "uncategorized")).lower() if isinstance(meta, dict) else "uncategorized"
                    agent_types[at] = agent_types.get(at, 0) + 1
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
        else:
            # Fallback: scan engine/agents/ directory directly
            engine_agents_dir = Path(__file__).resolve().parents[2] / "engine" / "agents"
            if engine_agents_dir.exists():
                for md_path in sorted(engine_agents_dir.rglob("AGENT.md")):
                    try:
                        content = md_path.read_text(encoding="utf-8", errors="ignore")
                        if content.startswith("---"):
                            import yaml
                            fm = yaml.safe_load(content.split("---", 2)[1]) or {}
                            at = str(fm.get("agent_type", "uncategorized")).lower()
                            agent_types[at] = agent_types.get(at, 0) + 1
                            engine_count += 1
                    except Exception:
                        engine_count += 1
        workspace_count = 0
        mgr = getattr(rt, "workspace_agent_manager", None) if rt else None
        if mgr:
            workspace_count = mgr.get_agent_count().get("total", 0)
        else:
            # Fallback: scan ~/.aiplat/agents/ directory
            ws_dir = Path.home() / ".aiplat" / "agents"
            if ws_dir.exists():
                workspace_count = sum(1 for _ in ws_dir.rglob("AGENT.md"))
        core["agents"] = {
            "engine": engine_count, "workspace": workspace_count,
            "total": engine_count + workspace_count,
            "by_type": agent_types if agent_types else None,
        }
        if engine_count == 0 and workspace_count == 0:
            core_issues += 1
    except Exception as e:
        _log.warning(f"Overview agent scan failed: {e}")
        core["agents"] = {"total": 0, "error": "unavailable"}
        core_issues += 1

    # -- Skills / Tools / MCP --
    try:
        from core.harness.knowledge.capability_graph import build_capability_graph
        cg = build_capability_graph()
        skill_count = sum(1 for n in cg.nodes.values() if n["type"] == "skill")
        tool_count = sum(1 for n in cg.nodes.values() if n["type"] == "tool")
        mcp_count = sum(1 for n in cg.nodes.values() if n["type"] == "mcp_server")
        workflow_count = sum(1 for n in cg.nodes.values() if n["type"] == "workflow")
        core["skills"] = {"total": skill_count}
        core["tools"] = tool_count
        core["workflows"] = workflow_count
        # MCP: count + quick connectivity probe
        try:
            import json, sys
            from core.management.mcp_manager import WorkspaceMCPManager
            mgr = WorkspaceMCPManager()
            servers = mgr.list_servers()
            enabled = [s for s in servers if getattr(s, "enabled", False)]
            core["mcp_servers"] = {
                "total": len(servers),
                "enabled": len(enabled),
                "disabled": len(servers) - len(enabled),
            }
            # Quick smoke: can we spawn the local_tools_server?
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "core.apps.mcp.local_tools_server",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    init = json.dumps({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                        "clientInfo": {"name": "overview", "version": "1.0.0"}}}) + "\n"
                    proc.stdin.write(init.encode("utf-8"))
                    await proc.stdin.drain()
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=5)
                    resp = json.loads(line.decode("utf-8"))
                    core["mcp_servers"]["alive"] = "result" in resp
                except Exception:
                    core["mcp_servers"]["alive"] = False
                finally:
                    try:
                        proc.terminate()
                        await asyncio.wait_for(proc.wait(), timeout=2)
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)
            except Exception:
                core["mcp_servers"]["alive"] = False
        except Exception as e:
            core["mcp_servers"] = {"total": mcp_count, "alive": None}
            _log.debug(f"Overview MCP probe failed: {e}")
        # Skill lint health
        try:
            from core.management.skill_linter import lint_skill
            from core.management.skill_manager import SkillManager
            sm = SkillManager(seed=True, scope="engine")
            ws = SkillManager(seed=False, scope="workspace")
            eng_skills = await sm.list_skills(limit=500, offset=0)
            ws_skills = await ws.list_skills(limit=500, offset=0)
            lint_errors = 0
            lint_warnings = 0
            for s in eng_skills + ws_skills:
                rep = lint_skill(s)
                lint_errors += len(rep.get("errors", []))
                lint_warnings += len(rep.get("warnings", []))
            core["skills"]["lint"] = {"errors": lint_errors, "warnings": lint_warnings}
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        if skill_count == 0 and tool_count == 0:
            core_issues += 1
    except Exception:
        core["skills"] = {"total": 0}
        core["tools"] = 0
        core["mcp_servers"] = 0
        core["workflows"] = 0
        core_issues += 1

    # -- Pipeline --
    try:
        if rt and hasattr(rt, "execution_store") and rt.execution_store:
            store = rt.execution_store
            active = len(getattr(store, "_active", {}) or {})
            completed = 0
            try:
                import sqlite3 as _inner_sql3
                conn = _inner_sql3.connect(store._config.db_path)
                try:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM graph_runs WHERE status IN ('completed','finished')"
                    ).fetchone()
                    if row:
                        completed = row[0]
                finally:
                    conn.close()
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            core["pipeline"] = {"active": active, "completed": completed}
            if active == 0 and completed == 0:
                pass  # pipeline not used yet = not an issue
    except Exception:
        core["pipeline"] = {"active": 0, "completed": 0}

    # -- Memory --
    try:
        if rt and hasattr(rt, "memory_manager") and rt.memory_manager:
            mm = rt.memory_manager
            stats = await mm.get_stats() if hasattr(mm, "get_stats") else {}
            core["memory"] = {
                "working_tokens": getattr(stats, "working_tokens", 0),
                "episodic_count": getattr(stats, "episodic_count", 0),
                "semantic_count": getattr(stats, "semantic_count", 0),
                "compression_level": getattr(stats, "compression_level", "none"),
            }
        else:
            core["memory"] = {"working_tokens": 0, "episodic_count": 0, "semantic_count": 0, "note": "runtime not initialized"}
    except Exception as e:
        _log.warning(f"Memory probe failed: {e}")
        core["memory"] = {"working_tokens": 0, "episodic_count": 0, "semantic_count": 0, "note": "unavailable"}

    # -- Syscalls (recent 1h) --
    try:
        if rt and hasattr(rt, "execution_store") and rt.execution_store:
            store = rt.execution_store
            import sqlite3 as _inner_sql3
            conn = _inner_sql3.connect(store._config.db_path)
            try:
                llm_1h = conn.execute(
                    "SELECT COUNT(*) FROM syscall_events WHERE kind='llm' AND start_time > unixepoch('now','-1 hour')"
                ).fetchone()[0]
                tool_1h = conn.execute(
                    "SELECT COUNT(*) FROM syscall_events WHERE kind='tool' AND start_time > unixepoch('now','-1 hour')"
                ).fetchone()[0]
                skill_1h = conn.execute(
                    "SELECT COUNT(*) FROM syscall_events WHERE kind='skill' AND start_time > unixepoch('now','-1 hour')"
                ).fetchone()[0]
                core["syscalls"] = {"llm_1h": llm_1h, "tool_1h": tool_1h, "skill_1h": skill_1h}
            finally:
                conn.close()
        else:
            core["syscalls"] = {"llm_1h": 0, "tool_1h": 0, "skill_1h": 0, "note": "runtime not initialized"}
    except Exception as e:
        _log.warning(f"Syscall probe failed: {e}")
        core["syscalls"] = {"llm_generate_1h": 0, "tool_call_1h": 0, "skill_call_1h": 0, "note": "unavailable"}

    # -- Capability Health --
    try:
        from core.harness.knowledge.capability_health import capability_health_report
        cap_report = capability_health_report(cg) if 'cg' in dir() else {"score": None, "grade": "?"}
        core["capability_health"] = {
            "score": cap_report.get("score"),
            "grade": cap_report.get("grade"),
        }
    except Exception as e:
        _log.warning(f"Overview capability health scan failed: {e}")
        core["capability_health"] = {"error": "unavailable"}

    # -- Governance --
    try:
        core["governance"] = await _scan_governance()
    except Exception:
        core["governance"] = {"error": "unavailable"}

    # -- Code Graph stats (symbol health + dead code) --
    try:
        from core.harness.knowledge.code_graph import build_graph as _cg_build, default_roots as _cg_roots, repo_root as _cg_root
        _r = _cg_root()
        _roots = [(_r / d).resolve() for d in _cg_roots()]
        _nodes, _edges, _ = _cg_build(_r, _roots)
        total_files = len(_nodes)
        total_syms = sum(len(n.get('symbols', [])) for n in _nodes.values())
        files_with_syms = sum(1 for n in _nodes.values() if n.get('symbols'))
        # Exclude files legitimately with 0 in-degree (dynamic dispatch, DI, registry, etc.)
        from core.harness.knowledge.symbol_health import is_excluded_from_dead_code
        dead_code = sum(1 for nid, n in _nodes.items()
                        if not is_excluded_from_dead_code(nid)
                        and int(n.get('in', 0)) == 0
                        and len(n.get('symbols', [])) > 0)
        cross_calls = sum(1 for e in _edges if e.get('kind') == 'calls' and e['from'] != e['to'])
        core["code_graph"] = {
            "files": total_files,
            "edges": len(_edges),
            "symbols": total_syms,
            "files_with_symbols": files_with_syms,
            "dead_code_candidates": dead_code,
            "cross_file_calls": cross_calls,
            "coverage_pct": round(files_with_syms / max(total_files, 1) * 100, 1),
        }
    except Exception:
        core["code_graph"] = {"error": "unavailable"}
        core_issues += 1

    # Aggregate core status — delegate to the authoritative /api/core/health
    try:
        from core.api.routers.health import health_check
        hc = await health_check(rt=rt)
        core["status"] = hc.get("status", "healthy")
    except Exception:
        # Fallback: use the issue-counting heuristic
        if core_issues >= 2:
            core["status"] = "unhealthy"
        elif core_issues == 1:
            core["status"] = "degraded"
        else:
            core["status"] = "healthy"

    result["core"] = core

    # ==================================================================
    # PLATFORM — Layer 2: Platform Services
    # ==================================================================
    platform: Dict[str, Any] = {
        "status": "healthy", "gateway": {}, "users": {}, "tenants": {},
        "knowledge_base": {}, "builder": {}, "approvals": {}, "sessions": {},
    }
    platform_issues = 0

    # HTTP calls to platform service
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as client:
            # Gateway
            try:
                r = await client.get("http://localhost:8003/platform/gateway/routes")
                data = r.json() if r.status_code == 200 else {}
                platform["gateway"] = {"routes": len(data.get("routes", []) or [])}
            except Exception as e:
                _log.warning(f"Overview agent scan failed: {e}")
                platform["gateway"] = {"routes": 0, "error": "unreachable"}
                platform_issues += 1

            # Users
            try:
                r = await client.get("http://localhost:8003/platform/auth/users")
                data = r.json() if r.status_code == 200 else {}
                platform["users"] = {"count": len(data.get("users", []) or [])}
            except Exception as e:
                _log.warning(f"Overview agent scan failed: {e}")
                platform["users"] = {"count": 0, "error": "unreachable"}
                platform_issues += 1

            # Tenants
            try:
                r = await client.get("http://localhost:8003/platform/tenants")
                data = r.json() if r.status_code == 200 else {}
                platform["tenants"] = {"count": len(data.get("tenants", []) or [])}
            except Exception as e:
                _log.warning(f"Overview agent scan failed: {e}")
                platform["tenants"] = {"count": 0, "error": "unreachable"}
                platform_issues += 1

            # KB — full stats
            try:
                r = await client.get("http://localhost:8003/platform/kb/stats")
                data = r.json() if r.status_code == 200 else {}
                platform["knowledge_base"] = {
                    "collections": data.get("collections", 0),
                    "documents": data.get("documents", 0),
                    "elements": data.get("elements", 0),
                    "embeddings": data.get("embeddings", 0),
                }
            except Exception as e:
                _log.warning(f"Overview agent scan failed: {e}")
                platform["knowledge_base"] = {"collections": 0, "error": "unreachable"}
                platform_issues += 1

            # Builder
            try:
                r = await client.get("http://localhost:8003/platform/builder/projects")
                data = r.json() if r.status_code == 200 else {}
                projects = data.get("projects", []) or []
                platform["builder"] = {"projects": len(projects)}
            except Exception as e:
                _log.warning(f"Overview agent scan failed: {e}")
                platform["builder"] = {"projects": 0, "error": "unreachable"}

            # Approvals
            try:
                r = await client.get("http://localhost:8003/platform/approvals/approvals?status=pending")
                data = r.json() if r.status_code == 200 else {}
                platform["approvals"] = {"pending": len(data.get("approvals", []) or [])}
            except Exception as e:
                _log.warning(f"Overview agent scan failed: {e}")
                platform["approvals"] = {"pending": 0, "error": "unreachable"}

            # Sessions
            try:
                r = await client.get("http://localhost:8003/platform/sessions")
                data = r.json() if r.status_code == 200 else {}
                sessions = data.get("sessions", []) or []
                active = sum(1 for s in sessions if isinstance(s, dict) and s.get("status") == "active")
                platform["sessions"] = {"active": active, "total": len(sessions)}
            except Exception as e:
                _log.warning(f"Overview agent scan failed: {e}")
                platform["sessions"] = {"active": 0, "total": 0, "error": "unreachable"}
    except Exception:
        for key in ("gateway", "users", "tenants", "knowledge_base", "builder", "approvals", "sessions"):
            platform.setdefault(key, {})["error"] = "unavailable"
        platform_issues = 4

    # Aggregate platform status — delegate to authoritative /health endpoint
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("http://localhost:8003/health")
            if r.status_code == 200:
                hc = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                platform["status"] = hc.get("status", "healthy")
            else:
                platform["status"] = "degraded"
    except Exception:
        # Fallback: use the issue-counting heuristic
        if platform_issues >= 4:
            platform["status"] = "unhealthy"
        elif platform_issues >= 1:
            platform["status"] = "degraded"
        else:
            platform["status"] = "healthy"

    result["platform"] = platform

    # ==================================================================
    # APP — Layer 3: Applications
    # ==================================================================
    app_layer: Dict[str, Any] = {
        "status": "healthy", "channels": {}, "sessions": {}, "conversations": {}, "apps": {},
    }
    app_issues = 0

    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as client:
            # Channels
            try:
                r = await client.get("http://localhost:8004/app/channels")
                data = r.json() if r.status_code == 200 else {}
                channels = data.get("channels", []) or []
                by_type: Dict[str, int] = {}
                for ch in channels:
                    t = str(ch.get("type", "unknown")) if isinstance(ch, dict) else "unknown"
                    by_type[t] = by_type.get(t, 0) + 1
                app_layer["channels"] = {"total": len(channels), "by_type": by_type if by_type else None}
            except Exception as e:
                _log.warning(f"Overview agent scan failed: {e}")
                app_layer["channels"] = {"total": 0, "error": "unreachable"}
                app_issues += 1

            # Sessions
            try:
                r = await client.get("http://localhost:8004/app/sessions")
                data = r.json() if r.status_code == 200 else {}
                sessions = data.get("sessions", []) or []
                active = sum(1 for s in sessions if isinstance(s, dict) and s.get("status") == "active")
                app_layer["sessions"] = {"active": active, "total": len(sessions)}
            except Exception as e:
                _log.warning(f"Overview agent scan failed: {e}")
                app_layer["sessions"] = {"active": 0, "total": 0, "error": "unreachable"}
                app_issues += 1

            # Conversations
            try:
                r = await client.get("http://localhost:8004/platform/conversations?limit=1")
                data = r.json() if r.status_code == 200 else {}
                app_layer["conversations"] = {"total": data.get("total", 0) if isinstance(data, dict) else 0}
            except Exception as e:
                _log.warning(f"Overview agent scan failed: {e}")
                app_layer["conversations"] = {"total": 0, "error": "unreachable"}

            # Apps
            try:
                r = await client.get("http://localhost:8004/app/apps")
                data = r.json() if r.status_code == 200 else {}
                apps = data.get("apps", []) or []
                app_layer["apps"] = {"count": len(apps)}
            except Exception as e:
                _log.warning(f"Overview agent scan failed: {e}")
                app_layer["apps"] = {"count": 0, "error": "unreachable"}
                app_issues += 1
    except Exception:
        for key in ("channels", "sessions", "conversations", "apps"):
            app_layer.setdefault(key, {})["error"] = "unavailable"
        app_issues = 3

    # Aggregate app status — delegate to authoritative /health endpoint
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("http://localhost:8004/health")
            if r.status_code == 200:
                hc = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                app_layer["status"] = hc.get("status", "healthy")
            else:
                app_layer["status"] = "degraded"
    except Exception:
        # Fallback: use the issue-counting heuristic
        if app_issues >= 2:
            app_layer["status"] = "unhealthy"
        elif app_issues >= 1:
            app_layer["status"] = "degraded"
        else:
            app_layer["status"] = "healthy"

    result["app"] = app_layer

    # ── Cache save ─────────────────────────────────────────────
    _OV_CACHE = result
    _OV_CACHE_TS = time.time()
    _save_ov_cache()
    return result
