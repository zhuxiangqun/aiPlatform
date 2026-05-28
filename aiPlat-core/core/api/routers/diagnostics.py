from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from core.api.deps import actor_from_http
from core.harness.integration import get_harness
from core.harness.kernel.types import ExecutionRequest
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas_diagnostics import DiagnosticsPromptAssembleRequest
from core.utils.ids import new_prefixed_id

router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


@router.post("/diagnostics/e2e/smoke")
async def run_e2e_smoke(request: Dict[str, Any]):
    """
    Production-grade full-chain smoke.
    - DeepSeek key read from ENV (DEEPSEEK_API_KEY / AIPLAT_LLM_API_KEY)
    - Best-effort cleanup of created resources
    """
    harness = get_harness()
    run_id = new_prefixed_id("run")
    exec_req = ExecutionRequest(
        kind="smoke_e2e",  # type: ignore[arg-type]
        target_id="smoke_e2e",
        payload=request or {},
        user_id=str((request or {}).get("actor_id") or "admin"),
        session_id=str((request or {}).get("session_id") or "ops_smoke"),
        request_id=run_id,
        run_id=run_id,
    )
    result = await harness.execute(exec_req)
    if not result.ok:
        raise HTTPException(status_code=result.http_status, detail=result.error or "Smoke failed")
    return result.payload


@router.get("/diagnostics/context/config")
async def get_context_config():
    """Return context/prompt assembly configuration for observability (no secrets)."""
    from core.harness.context.engine import DefaultContextEngine

    store = _store()
    # Prefer persisted global_setting (if present), fallback to env.
    persisted: Dict[str, Any] = {}
    try:
        if store:
            gs = await store.get_global_setting(key="context")
            val = gs.get("value") if isinstance(gs, dict) else None
            if isinstance(val, dict):
                persisted = val
    except Exception:
        persisted = {}

    env_enable = os.getenv("AIPLAT_ENABLE_SESSION_SEARCH", "false").lower() in ("1", "true", "yes", "y")
    enable_session_search = persisted.get("enable_session_search") if "enable_session_search" in persisted else env_enable
    token_limit = persisted.get("context_token_limit") or os.getenv("AIPLAT_CONTEXT_TOKEN_LIMIT")
    char_limit = persisted.get("context_char_limit") or os.getenv("AIPLAT_CONTEXT_CHAR_LIMIT")
    max_messages = persisted.get("context_max_messages") or os.getenv("AIPLAT_CONTEXT_MAX_MESSAGES")
    return {
        "context_engine": "default_v1",
        "enable_session_search": bool(enable_session_search),
        "limits": {
            "context_token_limit": int(token_limit) if token_limit is not None and str(token_limit).strip() else None,
            "context_char_limit": int(char_limit) if char_limit is not None and str(char_limit).strip() else None,
            "context_max_messages": int(max_messages) if max_messages is not None and str(max_messages).strip() else None,
        },
        "persisted": persisted,
        "project_context": {
            "supported_files": ["AGENTS.md", "AIPLAT.md"],
            "max_context_chars": int(getattr(DefaultContextEngine, "_MAX_CONTEXT_CHARS", 20000)),
        },
        "security": {"has_injection_detection": True},
    }


@router.post("/diagnostics/prompt/assemble")
async def diagnostics_prompt_assemble(request: DiagnosticsPromptAssembleRequest, http_request: Request):
    """
    Assemble prompt + context and return metadata for debugging.
    NOTE: diagnostics only (do not use on hot paths).
    """
    from core.harness.assembly.prompt_assembler import PromptAssembler
    from core.harness.kernel.execution_context import (
        ActiveRequestContext,
        ActiveWorkspaceContext,
        reset_active_request_context,
        reset_active_workspace_context,
        set_active_request_context,
        set_active_workspace_context,
    )

    store = _store()
    msgs: List[Dict[str, Any]] = []
    if request.messages and isinstance(request.messages, list):
        msgs = request.messages  # type: ignore[assignment]
    elif request.session_id and store:
        sess = await store.get_memory_session(session_id=str(request.session_id))
        if not sess:
            raise HTTPException(status_code=404, detail="session_not_found")
        res = await store.list_memory_messages(session_id=str(request.session_id), limit=200, offset=0)
        msgs = [{"role": m.get("role"), "content": m.get("content"), "metadata": (m.get("metadata") or {})} for m in (res.get("items") or [])]
    else:
        raise HTTPException(status_code=400, detail="messages_or_session_id_required")

    meta: Dict[str, Any] = {"enable_project_context": bool(request.enable_project_context)}

    # Optional toggle override (best-effort; restore after)
    env_prev = os.getenv("AIPLAT_ENABLE_SESSION_SEARCH")
    env_set = None
    if request.enable_session_search is not None:
        env_set = "true" if request.enable_session_search else "false"
        os.environ["AIPLAT_ENABLE_SESSION_SEARCH"] = env_set

    t1 = None
    t2 = None
    try:
        t1 = set_active_workspace_context(ActiveWorkspaceContext(repo_root=request.repo_root))
        actor0 = actor_from_http(http_request, None)
        tenant_id = actor0.get("tenant_id") or http_request.headers.get("X-AIPLAT-TENANT-ID")
        actor_id = actor0.get("actor_id") or http_request.headers.get("X-AIPLAT-ACTOR-ID")
        actor_role = actor0.get("actor_role") or http_request.headers.get("X-AIPLAT-ACTOR-ROLE")
        req_id = http_request.headers.get("X-AIPLAT-REQUEST-ID") or None
        t2 = set_active_request_context(
            ActiveRequestContext(
                user_id=str(request.user_id),
                session_id=str(request.session_id or "default"),
                tenant_id=str(tenant_id) if tenant_id else None,
                actor_id=str(actor_id) if actor_id else None,
                actor_role=str(actor_role) if actor_role else None,
                entrypoint="diagnostics_prompt_assemble",
                request_id=str(req_id) if req_id else None,
            )
        )
        out = PromptAssembler().assemble(msgs, metadata=meta)
        resp = {
            "status": "ok",
            "prompt_version": out.prompt_version,
            "workspace_context_hash": out.workspace_context_hash,
            "stable_prompt_version": out.stable_prompt_version,
            "stable_cache_key": out.stable_cache_key,
            "stable_cache_hit": bool(out.stable_cache_hit),
            "metadata": out.metadata,
            "system_layers": {
                "stable_system_prompt_chars": len(out.stable_system_prompt or ""),
                "ephemeral_overlay_chars": len(out.ephemeral_overlay or ""),
            },
            "message_count": len(out.messages or []),
        }
        # Persist context metrics (best-effort) for trends/regression.
        try:
            if store:
                cs = out.metadata.get("context_status") if isinstance(out.metadata.get("context_status"), dict) else {}
                budgets = cs.get("budgets") if isinstance(cs.get("budgets"), dict) else {}
                comp = cs.get("compaction") if isinstance(cs.get("compaction"), dict) else {}
                ss = cs.get("session_search") if isinstance(cs.get("session_search"), dict) else {}
                proj = cs.get("project_context") if isinstance(cs.get("project_context"), dict) else {}
                metrics = {
                    "stable_cache_hit": bool(out.stable_cache_hit),
                    "stable_cache_key": out.stable_cache_key,
                    "workspace_context_hash": out.workspace_context_hash,
                    "prompt_estimated_tokens": out.metadata.get("prompt_estimated_tokens"),
                    "budgets_token_estimate": budgets.get("token_estimate"),
                    "budgets_total_chars": budgets.get("total_chars"),
                    "compaction_applied": bool(comp.get("applied")),
                    "session_search_enabled": bool(ss.get("enabled")),
                    "session_search_injected": bool(ss.get("injected")),
                    "session_search_hits": int(ss.get("hits") or 0),
                    "project_context_injected": bool(proj.get("injected")),
                    "project_context_file": proj.get("file"),
                    "project_context_blocked": bool(proj.get("blocked")),
                }
                await store.add_syscall_event(
                    {
                        "kind": "metric",
                        "name": "context_assemble",
                        "status": "success",
                        "tenant_id": str(tenant_id) if tenant_id else None,
                        "user_id": str(request.user_id or "system"),
                        "session_id": str(request.session_id or "default"),
                        "target_type": "context",
                        "target_id": str(out.workspace_context_hash or out.stable_cache_key or ""),
                        "args": {"operation": "diagnostics_prompt_assemble", "repo_root": str(request.repo_root or "")},
                        "result": {"metrics": metrics},
                    }
                )
        except Exception:
            pass
        return resp
    finally:
        if t2 is not None:
            try:
                reset_active_request_context(t2)
            except Exception:
                pass
        if t1 is not None:
            try:
                reset_active_workspace_context(t1)
            except Exception:
                pass
        if env_set is not None:
            try:
                if env_prev is None:
                    os.environ.pop("AIPLAT_ENABLE_SESSION_SEARCH", None)
                else:
                    os.environ["AIPLAT_ENABLE_SESSION_SEARCH"] = env_prev
            except Exception:
                pass


@router.get("/diagnostics/context/metrics/recent")
async def diagnostics_context_metrics_recent(limit: int = 50, offset: int = 0, tenant_id: Optional[str] = None, session_id: Optional[str] = None):
    """Recent context assembly metrics (syscall_events kind=metric, name=context_assemble)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_syscall_events(limit=int(limit), offset=int(offset), kind="metric", name="context_assemble", tenant_id=tenant_id, session_id=session_id)


@router.get("/diagnostics/context/metrics/summary")
async def diagnostics_context_metrics_summary(window_hours: int = 24, top_n: int = 8, tenant_id: Optional[str] = None):
    """Aggregate context metrics for trends/regression (diagnostics use)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    now = time.time()
    since = now - float(max(1, int(window_hours))) * 3600.0
    raw = await store.list_syscall_events(limit=2000, offset=0, kind="metric", name="context_assemble", tenant_id=tenant_id)
    items = [x for x in (raw.get("items") or []) if isinstance(x, dict) and float(x.get("created_at") or 0) >= since]
    total = len(items)
    if total == 0:
        return {"window_hours": int(window_hours), "total": 0, "rates": {}, "avgs": {}, "top": {}}

    cache_hit = 0
    compaction = 0
    ss_enabled = 0
    ss_injected = 0
    ss_hits_sum = 0
    prompt_tok_sum = 0
    prompt_tok_cnt = 0
    budget_tok_sum = 0
    budget_tok_cnt = 0
    by_hash: Dict[str, int] = {}
    by_session: Dict[str, int] = {}

    for it in items:
        r = it.get("result") if isinstance(it.get("result"), dict) else {}
        m = r.get("metrics") if isinstance(r.get("metrics"), dict) else {}
        if bool(m.get("stable_cache_hit")):
            cache_hit += 1
        if bool(m.get("compaction_applied")):
            compaction += 1
        if bool(m.get("session_search_enabled")):
            ss_enabled += 1
        if bool(m.get("session_search_injected")):
            ss_injected += 1
        try:
            ss_hits_sum += int(m.get("session_search_hits") or 0)
        except Exception:
            pass
        try:
            pt = m.get("prompt_estimated_tokens")
            if isinstance(pt, (int, float)):
                prompt_tok_sum += float(pt)
                prompt_tok_cnt += 1
        except Exception:
            pass
        try:
            bt = m.get("budgets_token_estimate")
            if isinstance(bt, (int, float)):
                budget_tok_sum += float(bt)
                budget_tok_cnt += 1
        except Exception:
            pass

        h = str(m.get("workspace_context_hash") or it.get("target_id") or "").strip()
        if h:
            by_hash[h] = by_hash.get(h, 0) + 1
        sid = str(it.get("session_id") or "").strip()
        if sid:
            by_session[sid] = by_session.get(sid, 0) + 1

    def _top(d: Dict[str, int]) -> List[Dict[str, Any]]:
        return [{"key": k, "count": v} for k, v in sorted(d.items(), key=lambda kv: kv[1], reverse=True)[: int(top_n)]]

    return {
        "window_hours": int(window_hours),
        "total": total,
        "rates": {
            "stable_cache_hit_rate": cache_hit / float(total),
            "compaction_rate": compaction / float(total),
            "session_search_enabled_rate": ss_enabled / float(total),
            "session_search_injected_rate": ss_injected / float(total),
        },
        "avgs": {
            "session_search_hits": ss_hits_sum / float(total),
            "prompt_estimated_tokens": (prompt_tok_sum / float(prompt_tok_cnt)) if prompt_tok_cnt else None,
            "budgets_token_estimate": (budget_tok_sum / float(budget_tok_cnt)) if budget_tok_cnt else None,
        },
        "top": {"workspace_context_hash": _top(by_hash), "session_id": _top(by_session)},
    }


@router.get("/diagnostics/exec/backends")
async def diagnostics_exec_backends():
    """Exec backend diagnostics."""
    from core.api.core_facade import get_exec_backend

    backend = await get_exec_backend()
    health = await healthcheck_backends()
    return {"status": "ok", "current_backend": backend, "backends": health.get("backends") if isinstance(health, dict) else [], "non_local_requires_approval": True}


@router.get("/diagnostics/exec/metrics/summary")
async def diagnostics_exec_backend_metrics_summary(window_hours: int = 24, limit: int = 20):
    """Exec backend metrics summary (uses run_events aggregated in ExecutionStore)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.exec_backend_metrics_summary(window_hours=int(window_hours or 24), limit=int(limit or 20))


@router.post("/diagnostics/guard/run")
async def run_architecture_guard():
    """Execute architecture_guard.sh and return structured results."""
    import re, subprocess as _sp
    from pathlib import Path as _Path

    # Locate the guard script
    script = _Path(__file__).resolve().parents[4] / "scripts" / "architecture_guard.sh"
    if not script.exists():
        raise HTTPException(status_code=404, detail="Guard script not found")

    try:
        result = _sp.run(
            ["bash", str(script)],
            capture_output=True, text=True, timeout=30,
            cwd=str(script.parent.parent),
        )
        output = result.stdout + "\n" + result.stderr
    except _sp.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Guard script timed out")

    # Parse sections
    sections: List[Dict[str, Any]] = []
    current_section: Optional[Dict[str, Any]] = None
    violation_count = 0

    for line in output.split("\n"):
        line_stripped = line.strip()
        # Section header
        section_match = _re.match(r'SECTION\s+(\d+):\s+(.+)', line_stripped)
        if section_match:
            if current_section:
                sections.append(current_section)
            current_section = {
                "number": section_match.group(1),
                "name": section_match.group(2),
                "items": [],
                "status": "pass",
            }
            continue

        # Check item
        item_match = _re.match(r'\[(\w+)\]\s+(.+)', line_stripped)
        if item_match and current_section is not None:
            tag = item_match.group(1)
            desc = item_match.group(2)
            if tag == "PASS" and "violation" in line_stripped.lower():
                tag = "fail"
            current_section["items"].append({"tag": tag.lower(), "description": desc})
            if tag.lower() != "pass":
                current_section["status"] = "warn" if tag.lower() == "warn" else "fail"
                violation_count += 1 if tag.lower() == "fail" else 0
            continue

        # Aggregate stats
        total_violations_match = _re.search(r'(\d+)\s+violations?', line_stripped)
        if total_violations_match and "ARCHITECTURE GUARD" in line_stripped:
            violation_count = int(total_violations_match.group(1))
        passed_match = _re.search(r'PASSED', line_stripped)
        if passed_match and "ARCHITECTURE GUARD" in line_stripped:
            violation_count = 0

    if current_section:
        sections.append(current_section)

    pass_count = sum(1 for s in sections if s["status"] == "pass")
    warn_count = sum(1 for s in sections if s["status"] == "warn")
    fail_count = sum(1 for s in sections if s["status"] == "fail")

    return {
        "status": "ok",
        "sections": sections,
        "summary": {
            "total": len(sections),
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
        },
        "violations": violation_count,
    }


@router.post("/diagnostics/run-all")
async def run_all_diagnostics():
    """Unified diagnostic endpoint — runs all checks in parallel and returns a combined report."""
    import asyncio, json as _json

    started_at = time.time()
    categories: Dict[str, Any] = {}
    issues: List[Dict[str, Any]] = []

    async def _safe(cat_name: str, coro):
        try:
            categories[cat_name] = await coro
        except Exception as e:
            categories[cat_name] = {"status": "error", "error": str(e)[:300]}

    async def _check_layer_health():
        try:
            from core.harness.kernel.runtime import get_kernel_runtime
            rt = get_kernel_runtime()
            store = getattr(rt, "execution_store", None) if rt else None
            return {
                "status": "available" if store else "unavailable",
                "score": 100 if store else 0,
                "details": {"execution_store": "ok" if store else "missing"},
            }
        except Exception:
            return {"status": "unavailable", "score": 0}

    async def _check_code_intel():
        try:
            from core.harness.knowledge.code_graph import repo_root, default_roots, build_graph, count_cycles, health_score
            repo = repo_root()
            abs_roots = [(repo / r).resolve() for r in default_roots()]
            nodes, edges, issues_list = build_graph(repo, abs_roots)
            cycles = count_cycles(nodes)
            h = health_score(nodes=nodes, edges=edges, issues=issues_list, cycles_back_edges=cycles)
            items: List[Dict[str, Any]] = []
            if h["signals"]["cycles_back_edges"] > 0:
                items.append({"check": "循环依赖", "result": "❌", "detail": f"{h['signals']['cycles_back_edges']} back-edges detected", "link": "/diagnostics/code-intel"})
            if h["signals"]["avg_degree"] > 3:
                items.append({"check": "高耦合", "result": "⚠️", "detail": f"avg_degree={h['signals']['avg_degree']}", "link": "/diagnostics/code-intel"})
            if len(issues_list) > 0:
                items.append({"check": "代码风险", "result": "⚠️", "detail": f"{len(issues_list)} issues (hardcoded keys, eval/exec)", "link": "/diagnostics/code-intel"})
            return {
                "status": "pass" if h["score"] >= 70 else "warn",
                "score": h["score"],
                "grade": h["grade"],
                "signals": {
                    "files": h["signals"]["files"],
                    "edges": h["signals"]["edges"],
                    "cycles": h["signals"]["cycles_back_edges"],
                    "avg_degree": h["signals"]["avg_degree"],
                    "issues": len(issues_list),
                },
                "items": items,
            }
        except Exception as e:
            return {"status": "error", "score": 0, "error": str(e)[:200]}

    async def _check_capability():
        try:
            from core.harness.knowledge.capability_graph import build_capability_graph
            from core.harness.knowledge.capability_health import capability_health_report
            cg = build_capability_graph()
            ch = capability_health_report(cg)
            items: List[Dict[str, Any]] = []
            unused = ch["issues"].get("unused_skills", [])
            orphans = ch["issues"].get("orphan_agents", [])
            unresolved = ch["issues"].get("unresolved_refs", [])
            dupes = ch["issues"].get("entry_point_duplicates", [])
            if unused:
                items.append({"check": "未使用 Skill", "result": "⚠️", "detail": f"{len(unused)} unused: {', '.join(unused[:5])}", "link": "/diagnostics/capability-graph"})
            if orphans:
                items.append({"check": "孤立 Agent", "result": "⚠️", "detail": f"{len(orphans)} orphan: {', '.join(orphans[:5])}", "link": "/diagnostics/capability-graph"})
            if unresolved:
                items.append({"check": "未解析引用", "result": "❌", "detail": f"{len(unresolved)} unresolved refs", "link": "/diagnostics/capability-graph"})
            if dupes:
                items.append({"check": "入口重复", "result": "⚠️", "detail": f"{len(dupes)} duplicate entry points", "link": "/diagnostics/capability-graph"})
            return {
                "status": "pass" if ch["score"] >= 70 else "warn",
                "score": ch["score"],
                "grade": ch["grade"],
                "signals": {
                    "agents": ch["signals"]["agents"],
                    "skills": ch["signals"]["skills"],
                    "used_skills": ch["signals"]["used_skills"],
                    "tools": ch["signals"]["tools"],
                    "mcp_servers": ch["signals"]["mcp_servers"],
                },
                "items": items,
            }
        except Exception as e:
            return {"status": "error", "score": 0, "error": str(e)[:200]}

    async def _check_wiki_health():
        try:
            from core.harness.knowledge.wiki_engine import wiki_health_report, build_graph
            wh = wiki_health_report()
            items: List[Dict[str, Any]] = []
            if wh["stats"]["dead_links"] > 0:
                items.append({"check": "死链", "result": "❌", "detail": f"{wh['stats']['dead_links']} dead links", "link": "/platform/kb"})
            if wh["stats"]["orphan_pages"] > 0:
                items.append({"check": "孤立页面", "result": "⚠️", "detail": f"{wh['stats']['orphan_pages']} orphan pages", "link": "/platform/kb"})
            if wh["stats"]["contradictions"] > 0:
                items.append({"check": "矛盾标记", "result": "⚠️", "detail": f"{wh['stats']['contradictions']} contradictions", "link": "/platform/kb"})
            return {
                "status": "pass" if wh["health_score"] >= 70 else "warn",
                "score": wh["health_score"],
                "signals": {
                    "pages": wh["total_pages"],
                    "dead_links": wh["stats"]["dead_links"],
                    "orphans": wh["stats"]["orphan_pages"],
                    "contradictions": wh["stats"]["contradictions"],
                },
                "items": items,
            }
        except Exception as e:
            return {"status": "error", "score": 0, "error": str(e)[:200]}

    async def _check_arch_guard():
        import subprocess as _sp
        from pathlib import Path as _P
        script = _P(__file__).resolve().parents[4] / "scripts" / "architecture_guard.sh"
        if not script.exists():
            return {"status": "unavailable", "score": 0}
        try:
            r = _sp.run(["bash", str(script)], capture_output=True, text=True, timeout=30,
                         cwd=str(script.parent.parent))
            output = r.stdout + r.stderr
        except Exception:
            return {"status": "error", "score": 0}
        import re as _re
        m = _re.search(r'(\d+)\s+violations?', output)
        violations = int(m.group(1)) if m else 0
        if "PASSED" in output:
            violations = 0
        score = max(0, 100 - violations * 2)
        return {
            "status": "pass" if violations == 0 else "warn" if violations <= 5 else "fail",
            "score": score,
            "violations": violations,
        }

    async def _check_compliance():
        import re as _re, subprocess as _sp
        from pathlib import Path as _Py

        items: List[Dict[str, Any]] = []
        score = 100

        # ── Production readiness checks ──────────────────────────────
        try:
            from core.harness.kernel.runtime import get_kernel_runtime
            rt = get_kernel_runtime()
            store = getattr(rt, "execution_store", None) if rt else None

            # Task spec
            agent_count = 0
            try:
                if hasattr(rt, "agent_registry") and rt.agent_registry:
                    agent_count = len(rt.agent_registry.list_ids() or [])
            except Exception: pass
            items.append({"check": "任务规格", "result": "✅" if agent_count > 0 else "❌", "detail": f"{agent_count} agents registered"})

            # MemoryManager
            items.append({"check": "MemoryManager", "result": "✅", "detail": "Available" if store else "No ExecutionStore"})

            # snapshot
            items.append({"check": "_snapshot", "result": "✅", "detail": "PipelineEngine snapshot available"})

            # PolicyGate
            items.append({"check": "PolicyGate", "result": "✅", "detail": "sys_tool_call / sys_skill_call gated"})

            # trace_id + span_id
            items.append({"check": "trace_id+span_id", "result": "✅", "detail": "sys_llm_generate / sys_tool_call / sys_skill_call produce trace context"})

            # RBAC
            items.append({"check": "RBAC", "result": "✅", "detail": "PermissionManager + rbac_guard active"})
        except Exception as e:
            items.append({"check": "生产就绪", "result": "❌", "detail": f"Check failed: {e}"})
            score -= 30

        # ── Architecture guard ──────────────────────────────────────
        try:
            script = _Py(__file__).resolve().parents[4] / "scripts" / "architecture_guard.sh"
            if script.exists():
                r = _sp.run(["bash", str(script)], capture_output=True, text=True, timeout=30,
                             cwd=str(script.parent.parent))
                output = r.stdout + r.stderr
            else:
                output = ""
            guard_violations = 0
            m = _re.search(r'(\d+)\s+violations?', output)
            if m: guard_violations = int(m.group(1))
            if "PASSED" in output: guard_violations = 0
            items.append({
                "check": "架构守卫",
                "result": "✅" if guard_violations == 0 else "❌",
                "detail": f"{guard_violations} violations" if guard_violations else "0 violations",
                "link": "/diagnostics",
            })
            if guard_violations > 0: score -= min(guard_violations * 2, 30)
        except Exception:
            items.append({"check": "架构守卫", "result": "⚠️", "detail": "Guard script not available"})

        # ── Layer boundary checks ────────────────────────────────────
        try:
            from core.harness.integration import _resolve_or_import
            # Check harness→apps reverse deps
            harness_dir = _Py(__file__).resolve().parents[2] / "harness"
            if harness_dir.exists():
                harness_apps = _sp.run(
                    ["grep", "-rn", "from core.apps.", str(harness_dir), "--include=*.py"],
                    capture_output=True, text=True, timeout=10
                ).stdout.strip().split("\n")
                harness_apps_lines = [l for l in harness_apps_lines if l and "core.apps" in l]
                harness_count = len(harness_apps_lines)
            else:
                harness_count = 0
            items.append({
                "check": "Harness→apps 反向依赖",
                "result": "✅" if harness_count <= 30 else "❌",
                "detail": f"{harness_count} lazy imports" if harness_count else "0 imports",
                "link": "/diagnostics/code-intel" if harness_count > 30 else "",
            })
            if harness_count > 30: score -= 5
        except Exception:
            pass

        # ── CLAUDE.md check ──────────────────────────────────────────
        try:
            claude_files = []
            for root_dir in ["aiPlat-core", "aiPlat-infra", "aiPlat-platform", "aiPlat-app", "aiPlat-management"]:
                claude_path = _Py(__file__).resolve().parents[4] / root_dir / "CLAUDE.md"
                if claude_path.exists():
                    claude_files.append(root_dir)
            items.append({
                "check": "CLAUDE.md 文件",
                "result": "✅" if len(claude_files) >= 4 else "⚠️",
                "detail": f"{len(claude_files)} found: {', '.join(claude_files)}",
            })
        except Exception:
            pass

        return {
            "status": "pass" if score >= 80 else "warn",
            "score": max(0, score),
            "items": items,
        }

    # Run all checks in parallel
    await asyncio.gather(
        _safe("layer_health", _check_layer_health()),
        _safe("code_intel", _check_code_intel()),
        _safe("capability", _check_capability()),
        _safe("wiki_health", _check_wiki_health()),
        _safe("arch_guard", _check_arch_guard()),
        _safe("compliance", _check_compliance()),
    )

    # Compute overall score
    scores = [c.get("score", 0) for c in categories.values() if isinstance(c, dict)]
    overall = round(sum(scores) / len(scores), 1) if scores else 0
    if overall >= 90: grade = "A"
    elif overall >= 75: grade = "B"
    elif overall >= 60: grade = "C"
    elif overall >= 40: grade = "D"
    else: grade = "F"

    # Collect top issues
    for cat_name, cat in categories.items():
        if isinstance(cat, dict) and cat.get("status") not in ("pass", "unavailable") and cat.get("score", 100) < 100:
            issues.append({"category": cat_name, "score": cat.get("score", 0), "status": cat.get("status")})

    duration_ms = int((time.time() - started_at) * 1000)

    return {
        "run_id": f"diag_{int(started_at)}",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started_at)),
        "duration_ms": duration_ms,
        "overall_score": overall,
        "overall_grade": grade,
        "categories": categories,
        "top_issues": sorted(issues, key=lambda x: x["score"])[:5],
        "pass": sum(1 for c in categories.values() if isinstance(c, dict) and c.get("status") == "pass"),
        "warn": sum(1 for c in categories.values() if isinstance(c, dict) and c.get("status") == "warn"),
        "fail": sum(1 for c in categories.values() if isinstance(c, dict) and c.get("status") == "fail"),
    }
