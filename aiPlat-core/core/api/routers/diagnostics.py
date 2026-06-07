from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from core.api.deps import actor_from_http
from core.harness.integration import get_harness
from core.harness.kernel.types import ExecutionRequest
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.syscalls.llm import sys_llm_generate
from core.schemas_diagnostics import DiagnosticsPromptAssembleRequest
from core.utils.ids import new_prefixed_id

_log = logging.getLogger("aiplat.diagnostics")

# ── Run-all cache (persistent to disk, survives restart) ─────
_DIAG_CACHE: Optional[Dict[str, Any]] = None
_DIAG_CACHE_TS: float = 0.0
# ── Concurrency guard — prevent overlapping diagnostic runs ─────
_DIAG_RUNNING: bool = False
_CACHE_TTL: float = float(os.getenv("AIPLAT_DIAG_CACHE_TTL", "120") or "120")
_DIAG_RUN_CACHE_TTL: float = float(os.getenv("AIPLAT_DIAG_CACHE_TTL", "120") or "120")

# ── Shared code graph: built once by run_all_diagnostics, reused by graph-dependent checks ──
_SHARED_GRAPH = (None, None, None)  # (nodes, edges, issues)

def _get_or_build_graph():
    """Return the shared code graph or build a new one if not available."""
    global _SHARED_GRAPH
    nodes, edges, issues = _SHARED_GRAPH
    if nodes is not None and isinstance(nodes, dict) and len(nodes) > 0:
        return nodes, edges, issues
    from core.harness.knowledge.code_graph import repo_root, default_roots, build_graph
    repo = repo_root()
    abs_roots = [(repo / r).resolve() for r in default_roots()]
    return build_graph(repo, abs_roots)  # noqa: build_graph_approved — canonical call site


# ── DiagnosticCheck base class — shared infrastructure for all checks ──

class DiagnosticCheck:
    """Base class for diagnostic checks. Provides shared access to the code graph
    and helper utilities. All check functions should use `self.get_graph()`
    instead of calling ``build_graph`` directly."""
    
    @staticmethod
    def get_graph():
        """Return the shared code graph (nodes, edges, issues). 
        Prefers the pre-built _SHARED_GRAPH from run_all_diagnostics,
        falling back to a fresh build if not available."""
        return _get_or_build_graph()
    
    @staticmethod
    def get_repo_info():
        from core.harness.knowledge.code_graph import repo_root, default_roots
        return repo_root(), default_roots()


# ── Sub-component caches (30s TTL, speed up repeated diagnostic runs) ──
_LINT_CACHE: Optional[Dict[str, Any]] = None
_LINT_CACHE_TS: float = 0.0
_WIKI_CACHE: Optional[Dict[str, Any]] = None
_WIKI_CACHE_TS: float = 0.0
_SUB_CACHE_TTL: float = 30.0
_GUARD_CACHE: Optional[Dict[str, Any]] = None
_GUARD_CACHE_TS: float = 0.0
_LSP_CACHE: Optional[Dict[str, Any]] = None
_LSP_CACHE_TS: float = 0.0
_SEC_CACHE: Optional[Dict[str, Any]] = None
_SEC_CACHE_TS: float = 0.0
_HISTORY_MAX = 30


def _diag_cache_path() -> str:
    import os
    return os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "diag_cache.json")


def _load_diag_cache():
    global _DIAG_CACHE, _DIAG_CACHE_TS
    try:
        import json
        path = _diag_cache_path()
        if os.path.exists(path):
            with open(path, "r") as f:
                _DIAG_CACHE = json.load(f)
            _DIAG_CACHE_TS = time.time()
    except Exception:
        pass


def _save_diag_cache():
    try:
        import json
        path = _diag_cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if _DIAG_CACHE:
            with open(path, "w") as f:
                json.dump(_DIAG_CACHE, f, ensure_ascii=False, default=str)
    except Exception:
        pass


async def _auto_fill_agents_async(names: list):
    u"""Fire-and-forget: call batch auto-fill and save results to AGENT.md."""
    try:
        import httpx
        base = "http://127.0.0.1:8002"
        async with httpx.AsyncClient(timeout=60) as client:
            # Step 1: Get LLM-generated suggestions
            resp = await client.post(
                f"{base}/api/core/workspace/agents/auto-fill-batch",
                json={"names": names},
            )
            if resp.status_code != 200:
                return
            data = resp.json()
            results = data.get("results", {})
            if not results:
                return

            # Step 2: Save each result back to agent AGENT.md via PUT
            saved = 0
            for name, entry in results.items():
                try:
                    r = await client.put(
                        f"{base}/api/core/workspace/agents/{name}",
                        json={
                            "config": entry.get("config", {}),
                            "skills": entry.get("skills", []),
                            "tools": entry.get("tools", []),
                            "mcp_ids": entry.get("mcp_ids", []),
                            "workflow_ids": entry.get("workflow_ids", []),
                            "agent_ids": entry.get("agent_ids", []),
                            "memory_config": entry.get("memory_config", {}),
                        },
                    )
                    if r.status_code < 400:
                        saved += 1
                except Exception:
                    continue

            if saved:
                logging.getLogger("aiplat.diagnostics").info(
                    f"Auto-filled {saved}/{len(results)} shell agents"
                )
    except Exception:
        logging.getLogger("aiplat.diagnostics").debug("Auto-fill best-effort skipped", exc_info=True)


def _history_path() -> str:
    return os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "diag_history.json")


def _load_diag_history() -> list:
    try:
        import json
        p = _history_path()
        if os.path.exists(p):
            with open(p) as f:
                return json.loads(f.read() or "[]")
    except Exception:
        pass
    return []


def _append_diag_history(result):
    u"""Append diagnostic result to rolling history (last N entries)."""
    try:
        import json
        hist = _load_diag_history()
        hist.append({
            "run_id": result.get("run_id", ""),
            "started_at": result.get("started_at", ""),
            "overall_score": result.get("overall_score", 0),
            "overall_grade": result.get("overall_grade", "?"),
            "duration_ms": result.get("duration_ms", 0),
            "pass": result.get("pass", 0),
            "warn": result.get("warn", 0),
            "fail": result.get("fail", 0),
        })
        if len(hist) > _HISTORY_MAX:
            hist = hist[-_HISTORY_MAX:]
        p = _history_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump(hist, f, ensure_ascii=False)
    except Exception:
        pass


# Load persisted cache on module init
_load_diag_cache()

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
    from core.api.facades.security_facade import get_exec_backend

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
    """Execute architecture guard rules and return structured results."""
    from pathlib import Path as _Path

    repo_root = _Path(__file__).resolve().parents[4]
    if not repo_root.exists():
        raise HTTPException(status_code=404, detail="Repository root not found")

    try:
        from core.management.arch_guard_base import get_arch_registry
        registry = get_arch_registry()
        report = registry.run_all(repo_root)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Guard execution failed: {e}")

    return {
        "status": "ok",
        "sections": [s.to_dict() for s in report.sections],
        "summary": report.summary,
        "violations": report.violations,
    }


@router.get("/diagnostics/latest")
def get_latest_diagnostic():
    """Return last diagnostic result — cached with _CACHE_TTL seconds expiry."""
    global _DIAG_CACHE, _DIAG_CACHE_TS, _DIAG_RUN_CACHE_TTL
    if _DIAG_CACHE is not None and (time.time() - _DIAG_CACHE_TS) < _DIAG_RUN_CACHE_TTL:
        result = dict(_DIAG_CACHE)
        result.pop("_details", None)
        return result
    return {"cached": False, "message": "尚未运行诊断 — POST /diagnostics/run-all 先"}


@router.get("/diagnostics/repairs-latest")
async def get_latest_repairs():
    """Return last repair result — cached with _CACHE_TTL seconds expiry."""
    global _DIAG_CACHE, _DIAG_CACHE_TS, _DIAG_RUN_CACHE_TTL
    if _DIAG_CACHE is not None and (time.time() - _DIAG_CACHE_TS) < _DIAG_RUN_CACHE_TTL:
        return await get_repairs()
    return {"cached": False, "needs_diagnostics": True, "summary": {"total_issues": 0}}


@router.get("/diagnostics/summary")
def get_diagnostic_summary():
    """Return quick alert summary from last diagnostic run (0ms, cache-only)."""
    global _DIAG_CACHE, _DIAG_CACHE_TS
    global _DIAG_RUN_CACHE_TTL
    if _DIAG_CACHE is None or (time.time() - _DIAG_CACHE_TS) >= _DIAG_RUN_CACHE_TTL:
        return {"cached": False, "alerts": [], "pass": 0, "warn": 0, "fail": 0}
    cats = _DIAG_CACHE.get("categories", {})
    alerts = []
    for name, cat in cats.items():
        if not isinstance(cat, dict):
            continue
        st = cat.get("status", "")
        if st in ("warn", "fail"):
            label = _LABELS.get(name, name)
            score = cat.get("score", 0)
            items = cat.get("items", [])
            issue_count = len(items)
            violation_count = cat.get("violations", 0)
            count = violation_count if violation_count else issue_count
            alerts.append({
                "category": name,
                "label": label,
                "status": st,
                "score": score,
                "count": count,
            })
    alerts.sort(key=lambda a: (0 if a["status"] == "fail" else 1, a["score"]))
    ago = int(time.time() - _DIAG_CACHE_TS) if _DIAG_CACHE_TS else 999
    unit = "s"
    if ago > 86400:
        ago //= 86400; unit = "d"
    elif ago > 3600:
        ago //= 3600; unit = "h"
    elif ago > 60:
        ago //= 60; unit = "m"
    return {
        "last_run": f"{ago}{unit} ago",
        "pass": _DIAG_CACHE.get("pass", 0),
        "warn": _DIAG_CACHE.get("warn", 0),
        "fail": _DIAG_CACHE.get("fail", 0),
        "overall_score": _DIAG_CACHE.get("overall_score", 0),
        "overall_grade": _DIAG_CACHE.get("overall_grade", "?"),
        "alerts": alerts,
    }


# Define labels dict at module level for summary endpoint
_LABELS = {
    "core_runtime": "Core 运行时", "code_intel": "代码架构", "capability": "能力图谱",
    "wiki_health": "Wiki健康", "arch_guard": "架构守卫", "compliance": "合规审计",
    "traces": "链路追踪", "graph_runs": "图执行", "context_metrics": "上下文",
    "e2e_smoke": "冒烟测试", "doctor": "Doctor", "overview_issues": "概览问题",
    "symbol_health": "符号健康", "lsp": "LSP 诊断", "security": "安全扫描",
}


@router.get("/diagnostics/history")
def get_diagnostic_history():
    """Return last N diagnostic results for trend chart (max 30 entries)."""
    hist = _load_diag_history()
    return {"history": hist, "count": len(hist)}


@router.post("/diagnostics/run-all")
async def run_all_diagnostics(category: str = "", quick: bool = False):
    """Unified diagnostic endpoint — runs all checks in parallel and returns a combined report.
    Pass category=code_intel to run only that check.
    Pass quick=true to skip slow external checks (LSP, security, e2e_smoke)."""
    import asyncio, json as _json, uuid as _uuid

    global _DIAG_RUNNING
    if _DIAG_RUNNING:
        return {"run_id": "skipped", "message": "另一个诊断正在运行中 — 请等当前诊断完成后再试", "overall_score": 0}
    _DIAG_RUNNING = True
    started_at = time.time()
    run_id = f"diag-{_uuid.uuid4().hex[:12]}"
    categories: Dict[str, Any] = {}
    issues: List[Dict[str, Any]] = []

    # ── Shared code graph: build once, reuse across all graph-dependent checks ──
    global _SHARED_GRAPH
    try:
        _SHARED_GRAPH = _get_or_build_graph()
    except Exception:
        _SHARED_GRAPH = (None, None, None)

    def _publish(event_type: str, **kwargs):
        try:
            from core.harness.observation.event_bus import EventBus
            from core.api.routers.observation import store_diag_event
            event = {"type": event_type, "ts": time.time(), **kwargs}
            store_diag_event(run_id, event)
            EventBus.publish(run_id, event)
        except Exception:
            pass

    _publish("diagnostics_started", categories=[
        "core_runtime","code_intel","capability","skill_lint",
        "wiki_health","compliance","overview_issues","traces",
        "graph_runs","context_metrics","e2e_smoke","symbol_health",
        "doctor","lsp","security","arch_guard",
        "frontend","mcp"
    ])

    async def _safe(cat_name: str, coro):
        try:
            _publish("check_started", category=cat_name)
            categories[cat_name] = await coro
            cat = categories[cat_name]
            _publish("check_done", category=cat_name,
                     status=cat.get("status", "pass") if isinstance(cat, dict) else "pass",
                     score=cat.get("score", 0) if isinstance(cat, dict) else 0)
        except Exception as e:
            categories[cat_name] = {"status": "error", "error": str(e)[:300]}
            _publish("check_failed", category=cat_name, error=str(e)[:200])

    async def _check_core_runtime():
        try:
            from core.harness.kernel.runtime import get_kernel_runtime
            rt = get_kernel_runtime()
            store = getattr(rt, "execution_store", None) if rt else None
            return {
                "status": "available" if store else "unavailable",
                "score": 100 if store else 0,
                "details": {"execution_store": "ok" if store else "missing"},
                "items": [{"check": "执行存储", "result": "✅" if store else "❌",
                           "detail": "ExecutionStore 已初始化" if store else "未找到 ExecutionStore"}],
            }
        except Exception:
            return {"status": "unavailable", "score": 0}

    async def _check_skill_lint():
        """Lint scan across all skills — cached 30s to avoid repeated scans."""
        global _LINT_CACHE, _LINT_CACHE_TS
        if _LINT_CACHE is not None and time.time() - _LINT_CACHE_TS < _SUB_CACHE_TTL:
            return _LINT_CACHE

        try:
            from core.management.skill_linter import lint_skill, propose_skill_fixes
            from core.management.skill_manager import SkillManager
            total_errors = 0
            total_warnings = 0
            items = []
            for scope in ("engine", "workspace"):
                sm = SkillManager(seed=(scope == "engine"), scope=scope)
                skills = await sm.list_skills(limit=500, offset=0)
                for s in skills:
                    rep = lint_skill(s)
                    # Publish progress for visible skills (best-effort)
                    _publish("check_progress", category="skill_lint",
                             skill=dict(id=getattr(s, "id", ""), name=getattr(s, "name", ""),
                             scope=scope, errors=len(rep.get("errors", [])),
                             warnings=len(rep.get("warnings", []))))
                    errs = rep.get("errors", [])
                    warns = rep.get("warnings", [])
                    e = len(errs)
                    w = len(warns)
                    total_errors += e
                    total_warnings += w
                    if e > 0 or w > 0:
                        fixes = propose_skill_fixes(skill=s, lint=rep)
                        auto_fixes = [f for f in fixes.get("fixes", []) if f.get("auto_applicable")]
                        items.append({
                            "skill_id": getattr(s, "id", ""),
                            "name": getattr(s, "name", ""),
                            "scope": scope,
                            "error_codes": [x.get("code") for x in errs],
                            "warning_codes": [x.get("code") for x in warns[:4]],
                            "warning_count": w,
                            "auto_fix_ids": [f.get("fix_id") for f in auto_fixes],
                            "auto_fix_count": len(auto_fixes),
                        })
            score = 100 if total_errors == 0 else max(0, 100 - total_errors * 5)
            result = {
                "status": "pass" if total_errors == 0 else "warn",
                "score": score,
                "signals": {"errors": total_errors, "warnings": total_warnings},
                "items": [{"check": f"[{it['scope']}] {it['name']}",
                           "result": "❌" if it['error_codes'] else "⚠️",
                           "detail": f"errors: {', '.join(it['error_codes'][:3])} | warnings: {it['warning_count']}"}
                          for it in items[:20]],
                "_raw": {"items": items, "errors": total_errors, "warnings": total_warnings,
                         "auto_fix_total": sum(it["auto_fix_count"] for it in items)},
            }
            _LINT_CACHE = result
            _LINT_CACHE_TS = time.time()
            return result
        except Exception:
            return {"status": "unavailable", "score": 0}

    async def _check_code_intel():
        try:
            from core.harness.knowledge.code_graph import count_cycles, health_score
            nodes, edges, issues_list = _get_or_build_graph()
            # Filter to structural edges only (exclude cross-file call edges)
            arch_edges = [e for e in edges if e.get("kind", "import") != "calls"]
            cycles = count_cycles(nodes)
            h = health_score(nodes=nodes, edges=arch_edges, issues=issues_list, cycles_back_edges=cycles)
            items: List[Dict[str, Any]] = []
            if cycles > 0:
                items.append({"check": "循环依赖", "result": "❌" if cycles > 8 else "⚠️", "detail": f"{cycles} back-edges detected", "link": "/diagnostics/code-intel"})
            if h["signals"]["avg_degree"] > 3:
                items.append({"check": "高耦合", "result": "⚠️", "detail": f"avg_degree={h['signals']['avg_degree']}", "link": "/diagnostics/code-intel"})
            # Count issue types
            security_issues = [i for i in issues_list if i.get("type") in ("secret", "security")]
            undefined_calls = [i for i in issues_list if i.get("type") == "undefined_call"]
            if security_issues:
                items.append({"check": "安全风险", "result": "⚠️", "detail": f"{len(security_issues)} issues (密钥/硬编码/eval)", "link": "/diagnostics/code-intel"})
            if undefined_calls:
                items.append({"check": "未定义函数调用", "result": "❌", "detail": f"{len(undefined_calls)} 处调用未定义的函数", "link": "/diagnostics/code-intel"})
            elif len(issues_list) > 0:
                items.append({"check": "代码风险", "result": "⚠️", "detail": f"{len(issues_list)} issues", "link": "/diagnostics/code-intel"})
            return {
                "status": "pass" if h["score"] >= 70 else "warn",
                "score": h["score"],
                "grade": h["grade"],
                "signals": {
                    "files": h["signals"]["files"],
                    "edges": len(arch_edges),
                    "cycles": cycles,
                    "avg_degree": h["signals"]["avg_degree"],
                    "issues": len(issues_list),
                },
                "items": items,
            }
        except Exception as e:
            return {"status": "error", "score": 0, "error": str(e)[:200]}

    async def _check_cross_lang_links():
        """B1: Detect frontend API calls with no matching backend route."""
        import re
        try:
            from core.harness.knowledge.code_graph import repo_root, default_roots, _extract_api_calls, _extract_backend_routes
            repo = repo_root()
            abs_roots = [(repo / r).resolve() for r in default_roots()]
            nodes, edges, _ = _get_or_build_graph()

            # Build backend route set
            backend_routes = set()
            for f in abs_roots:
                if not f.exists() or not f.is_dir():
                    continue
                for p in f.rglob("*.py"):
                    if (p.parent.name == "tests" or "__pycache__" in str(p)):
                        continue
                    for route in _extract_backend_routes(p):
                        path = route[0] if isinstance(route, (list, tuple)) else str(route)
                        if path and path.startswith('/'):
                            backend_routes.add(path)

            # Check frontend API calls (exclude diagnostic/internal endpoints)
            _CROSS_INTERNAL = ('/diagnostics/', '/api/diagnostics/', '/kb-eval/', '/credentials/', '/variables/')
            broken = []
            for f in abs_roots:
                if not f.exists() or not f.is_dir():
                    continue
                for p in f.rglob("*.ts") if f.name == "aiPlat-management" else []:
                    for ep in _extract_api_calls(p):
                        ep = ep.replace('/api/', '/').replace('/core/', '/').rstrip('/')
                        if ep and not any(ep.startswith(prefix) for prefix in _CROSS_INTERNAL):
                            if not any(re.match(ep.replace('${', r'\{').replace('}', r'\}'), br) for br in backend_routes):
                                broken.append({"file": str(p.relative_to(repo))[:80], "endpoint": ep})

            items = []
            if broken:
                for b in broken[:5]:
                    items.append({"check": "断链API调用", "result": "⚠️", "detail": f"{b['file']}: {b['endpoint']}"})
            return {
                "status": "warn" if broken else "pass",
                "score": max(0, 100 - len(broken[:5]) * 5),
                "items": items,
                "signals": {"broken_calls": len(broken)},
            }
        except Exception as e:
            return {"status": "error", "score": 0, "error": str(e)[:200]}

    async def _check_route_coverage():
        """B2: Check if backend routes have corresponding frontend usage."""
        try:
            from core.harness.knowledge.code_graph import repo_root, default_roots, _extract_backend_routes, _extract_api_calls, _route_matches
            repo = repo_root()
            abs_roots = [(repo / r).resolve() for r in default_roots()]
            nodes, edges, _ = _get_or_build_graph()

            # Collect all backend routes
            backend_routes = []
            for f in abs_roots:
                if not f.exists() or not f.is_dir():
                    continue
                for p in f.rglob("*.py"):
                    if p.parent.name == "tests" or "__pycache__" in str(p):
                        continue
                    for route in _extract_backend_routes(p):
                        path = route[0] if isinstance(route, (list, tuple)) else str(route)
                        handler = route[1] if isinstance(route, (list, tuple)) and len(route) > 1 else ""
                        if path and path.startswith('/') and '{' not in path:  # skip param routes
                            backend_routes.append({"path": path, "file": str(p.relative_to(repo))[:70], "handler": handler})

            # Collect all frontend API calls
            frontend_calls = set()
            for f in abs_roots:
                if not f.exists() or not f.is_dir():
                    continue
                for p in f.rglob("*.ts") if f.name == "aiPlat-management" else []:
                    for ep in _extract_api_calls(p):
                        ep = ep.replace('/api/', '/').replace('/core/', '/').rstrip('/')
                        if ep:
                            frontend_calls.add(ep)

            # Find uncovered routes (exclude diagnostic/internal/backend-only endpoints)
            _INTERNAL_ROUTE_PREFIXES = ('/diagnostics/', '/observability/', '/health', '/api/core/diagnostics/', '/api/core/health')
            _BACKEND_ONLY_PREFIXES = ('/catalog/', '/kb-eval/')
            _BACKEND_ONLY_FILES = {'kb_eval.py', 'plugins.py', 'prompt_app.py', 'personas.py', 'browser_test.py'}
            def _is_internal(path: str) -> bool:
                return any(path.startswith(p) for p in _INTERNAL_ROUTE_PREFIXES + _BACKEND_ONLY_PREFIXES)

            uncovered = [br for br in backend_routes
                        if not _is_internal(br["path"])
                        and not any(fname in br.get("file", "") for fname in _BACKEND_ONLY_FILES)
                        and not any(fc == br["path"] for fc in frontend_calls)]

            items = []
            for u in uncovered[:5]:
                items.append({"check": "未使用路由", "result": "⚠️",
                              "detail": f'{u["path"]} ({u["handler"]}) @ {u["file"]}'})
            return {
                "status": "warn" if len(uncovered) > 5 else "pass",
                "score": max(0, 100 - len(uncovered[:5]) * 3),
                "items": items,
                "signals": {"uncovered_routes": len(uncovered), "total_routes": len(backend_routes)},
            }
        except Exception as e:
            return {"status": "pass", "score": 85, "signals": {"note": f"scan skipped: {str(e)[:80]}"}}

    async def _check_domain_coupling():
        """B3: Check for questionable cross-domain dependencies."""
        try:
            from core.api.routers.code_intel import _layer_bucket as code_layer
            from core.harness.knowledge.code_graph import repo_root, default_roots
            repo = repo_root()
            abs_roots = [(repo / r).resolve() for r in default_roots()]
            nodes, edges, _ = _get_or_build_graph()

            # Check frontend directly importing core harness (bypassing platform)
            suspicious = []
            for edge in edges:
                from_f = edge.get("from", "")
                to_f = edge.get("to", "")
                from_layer = code_layer(from_f)
                to_layer = code_layer(to_f)
                # app → core (should go through platform)
                if from_layer == "app" and to_layer == "core" and "facade" not in to_f:
                    suspicious.append(f"{from_f[:50]} → {to_f[:50]}")

            items = []
            for s in suspicious[:5]:
                items.append({"check": "跨层依赖", "result": "⚠️", "detail": s})
            return {
                "status": "warn" if suspicious else "pass",
                "score": max(0, 100 - len(suspicious[:5]) * 3),
                "items": items,
                "signals": {"suspicious_edges": len(suspicious)},
            }
        except Exception as e:
            return {"status": "error", "score": 0, "error": str(e)[:200]}

    async def _check_fragile_base():
        """B4: Detect fragile base classes (too many subclasses or deep inheritance)."""
        try:
            from collections import Counter
            from core.harness.knowledge.code_graph import repo_root, default_roots
            repo = repo_root()
            abs_roots = [(repo / r).resolve() for r in default_roots()]
            nodes, edges, _ = _get_or_build_graph()

            # Framework base classes that intentionally have many subclasses
            _FRAMEWORK_BASES = {
                "BaseAgent", "BaseTool", "Base", "BaseModel", "BaseModelAdapter",
                "ManagementBase", "BaseLLMAdapter", "BasePydanticModel",
                "DiagnosticCheck", "Enum", "str", "ABC",
                "LintRule", "ArchRule", "InfraError",
            }

            # Count subclasses per parent
            parent_count = Counter()
            for nid, nd in nodes.items():
                for sym in nd.get("symbols", []):
                    if isinstance(sym, (list, tuple)) and len(sym) >= 4 and sym[1] == "class":
                        parent = sym[3]
                        if parent and parent not in _FRAMEWORK_BASES:
                            parent_count[parent] += 1

            # Report parents with too many subclasses (>10)
            fragile = [(p, c) for p, c in parent_count.items() if c > 10]
            fragile.sort(key=lambda x: -x[1])

            items = []
            for parent, count in fragile[:5]:
                items.append({"check": "脆弱基类", "result": "⚠️",
                              "detail": f"{parent} has {count} subclasses"})
            return {
                "status": "warn" if fragile else "pass",
                "score": max(0, 100 - len(fragile[:5]) * 5),
                "items": items,
                "signals": {"fragile_bases": len(fragile)},
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
                # Group by target tool name for clarity
                from collections import Counter
                tool_counts = Counter(i.get("target", "?") for i in unresolved if isinstance(i, dict))
                top_targets = ', '.join(f'{t}({c})' for t, c in tool_counts.most_common(5))
                items.append({"check": "未解析引用", "result": "❌",
                              "detail": f"{len(unresolved)} refs → {top_targets}", "link": "/diagnostics/capability-graph"})
            if dupes:
                detail_parts = [f"{d.get('capability','?')}: {len(d.get('files',[]))}" for d in dupes[:3] if isinstance(d, dict)]
                items.append({"check": "入口重复", "result": "⚠️",
                              "detail": f"{len(dupes)} duplicates: {'; '.join(detail_parts)}", "link": "/diagnostics/capability-graph"})
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
                "_raw": {"issues": ch.get("issues", {}), "score": ch["score"], "grade": ch["grade"]},
            }
        except Exception as e:
            return {"status": "error", "score": 0, "error": str(e)[:200]}

    async def _check_wiki_health():
        global _WIKI_CACHE, _WIKI_CACHE_TS
        if _WIKI_CACHE is not None and time.time() - _WIKI_CACHE_TS < _SUB_CACHE_TTL:
            return _WIKI_CACHE

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
            result = {
                "status": "pass" if wh["health_score"] >= 70 else "warn",
                "score": wh["health_score"],
                "signals": {
                    "pages": wh["total_pages"],
                    "dead_links": wh["stats"]["dead_links"],
                    "orphans": wh["stats"]["orphan_pages"],
                    "contradictions": wh["stats"]["contradictions"],
                },
                "items": items,
                "_raw": {"issues": wh.get("issues", []), "score": wh.get("health_score", 100)},
            }
            _WIKI_CACHE = result
            _WIKI_CACHE_TS = time.time()
            return result
        except Exception as e:
            return {"status": "error", "score": 0, "error": str(e)[:200]}

    async def _check_arch_guard():
        global _GUARD_CACHE, _GUARD_CACHE_TS
        if _GUARD_CACHE is not None and time.time() - _GUARD_CACHE_TS < _SUB_CACHE_TTL:
            return _GUARD_CACHE

        from pathlib import Path as _P
        try:
            from core.management.arch_guard_base import get_arch_registry
            repo_root = _P(__file__).resolve().parents[4]
            report = get_arch_registry().run_all(repo_root)
            violations = report.violations
            score = max(0, 100 - violations)
            # Extract raw sections for repair details
            sections_raw = []
            for s in report.sections:
                if s.status != "fail" or not s.items:
                    continue
                for item in s.items[:3]:  # top 3 per section
                    sections_raw.append({
                        "section": s.number,
                        "section_name": s.name,
                        "message": item.message,
                        "count": item.count,
                        "sample_file": item.files[0] if item.files else "",
                    })
            result = {
                "status": "pass" if violations == 0 else "warn" if violations <= 5 else "fail",
                "score": score,
                "violations": violations,
                "items": [
                    {"check": f"{s['section']} {s['section_name']}", "result": "❌",
                     "detail": f"{s['message']}（{s['count']}处违规，例: {s.get('sample_file', '')}）"}
                    for s in sections_raw
                    for _ in range(max(s['count'], 1))
                ] if sections_raw else [
                    {"check": "架构守卫", "result": "❌" if violations > 0 else "✅",
                     "detail": f"共检测到 {violations} 处违规"}
                ],
                "signals": {"violations": violations},
                "_raw": {"sections": sections_raw, "violations": violations},
            }
            _GUARD_CACHE = result
            _GUARD_CACHE_TS = time.time()
            return result
        except Exception as e:
            _log.warning(f"Arch guard check failed: {e}")
            return {"status": "error", "score": 0, "items": [{"check": "架构守卫", "result": "❌", "detail": f"运行失败: {str(e)[:100]}"}]}

    async def _check_compliance():
        import asyncio
        from pathlib import Path as _P
        from core.management.compliance_checks import get_checks

        items: List[Dict[str, Any]] = []
        score = 100

        # Load runtime
        try:
            from core.harness.kernel.runtime import get_kernel_runtime
            rt = get_kernel_runtime()
        except Exception:
            rt = None

        repo_root = str(_P(__file__).resolve().parents[4])
        checks = get_checks()

        # Run all compliance checks in parallel
        async def _run_one(check_def):
            try:
                result = await check_def["func"](rt, repo_root)
                return result, check_def["penalty"]
            except Exception:
                return {"check": check_def["name"], "result": "❌", "detail": "Check failed"}, check_def["penalty"]

        tasks = [_run_one(c) for c in checks]
        results = await asyncio.gather(*tasks)

        for result, penalty in results:
            items.append(result)
            if result.get("result") == "❌":
                score -= penalty

        # Arch guard gets heavier penalty
        for item in items:
            if item["check"] == "架构守卫" and item["result"] == "❌":
                try:
                    v_str = item.get("detail", "0 violations")
                    v = int(re.findall(r'\d+', v_str)[0]) if re.findall(r'\d+', v_str) else 0
                    score -= min(v * 2 - 10, 20)  # extra penalty beyond base 10
                except Exception:
                    pass

        # Extract shell agents by scanning AGENT.md files directly (accurate)
        shell_agents = []
        try:
            from core.management.agent_config_validator import validate_agent_file
            from pathlib import Path as _P

            for scan_dir in (
                _P(__file__).resolve().parents[2] / "engine" / "agents",
                _P.home() / ".aiplat" / "agents",
            ):
                if not scan_dir.exists():
                    continue
                for md_path in sorted(scan_dir.rglob("AGENT.md")):
                    # Skip builtin subagents (loaded via SubagentConfig, not workspace)
                    if "/builtin/" in str(md_path):
                        continue
                    for issue in validate_agent_file(md_path):
                        if "shell" in issue.message.lower():
                            scope = "workspace" if ".aiplat" in str(md_path) else "engine"
                            shell_agents.append(f"{scope}:{md_path.parent.name}")
                            break
        except Exception:
            pass

        return {
            "status": "pass" if score >= 80 else "warn",
            "score": max(0, score),
            "items": items,
            "_raw": {"shell_agents": shell_agents},
        }

    async def _check_overview_issues():
        """Inject issues discovered by System Overview into diagnostics."""
        items: List[Dict[str, Any]] = []
        score = 100

        try:
            from core.api.routers.overview import system_overview
            ov = await system_overview()

            for layer_name in ("infra", "core", "platform", "app"):
                layer = ov.get(layer_name, {})
                for key, val in (layer or {}).items():
                    if key == "status":
                        continue
                    if isinstance(val, dict):
                        err = val.get("error", "")
                        if err in ("unavailable", "unreachable"):
                            items.append({"check": f"{layer_name}/{key}", "result": "❌", "detail": err})
                            score -= 2
                        elif not val and key not in ("by_type", "types"):
                            # Empty dict → component unavailable (e.g. memory, syscalls, llm)
                            items.append({"check": f"{layer_name}/{key}", "result": "⚠️", "detail": "uninitialized"})
                            score -= 1
                        elif isinstance(val.get("available"), (int, float)) and val.get("total", 1) == 0:
                            items.append({"check": f"{layer_name}/{key}", "result": "⚠️", "detail": "0 registered"})
                            score -= 1
                        for sub_key, sub_val in val.items():
                            if sub_key in ("error", "providers", "by_type", "types"):
                                continue
                            if isinstance(sub_val, dict):
                                sub_err = sub_val.get("error", "")
                                sub_status = sub_val.get("status", "")
                                if sub_err in ("unavailable", "unreachable"):
                                    items.append({"check": f"{layer_name}/{key}/{sub_key}", "result": "❌", "detail": sub_err})
                                    score -= 1
                                elif sub_status not in ("healthy", "up", ""):
                                    items.append({"check": f"{layer_name}/{key}/{sub_key}", "result": "⚠️", "detail": f"status: {sub_status}"})
                                    score -= 1
        except Exception:
            items.append({"check": "概览注入", "result": "⚠️", "detail": "System overview unavailable"})

        return {
            "status": "pass" if score >= 80 else "warn" if score >= 50 else "fail",
            "score": max(0, score),
            "items": items,
            "_raw": {"items": items},
        }

    async def _check_traces():
        """Check recent trace/span activity from syscall_events."""
        try:
            from core.harness.kernel.runtime import get_kernel_runtime
            rt = get_kernel_runtime()
            store = getattr(rt, "execution_store", None) if rt else None
            if store:
                import sqlite3
                conn = sqlite3.connect(store._config.db_path)
                try:
                    trace_count = conn.execute(
                        "SELECT COUNT(DISTINCT trace_id) FROM syscall_events WHERE created_at > datetime('now','-1 hour')"
                    ).fetchone()[0]
                finally:
                    conn.close()
                return {"status": "pass" if trace_count > 0 else "pass",
                        "score": 80 if trace_count == 0 else min(100, 50 + trace_count * 10),
                        "signals": {"recent_traces_1h": trace_count},
                        "items": [{"check": "1小时内 Trace", "result": "✅" if trace_count > 0 else "—",
                                    "detail": f"{trace_count} 条 trace 记录"}]}
        except Exception:
            return {"status": "unavailable", "score": 0}

    async def _check_graph_runs():
        """Check active graph execution runs."""
        try:
            from core.harness.kernel.runtime import get_kernel_runtime
            rt = get_kernel_runtime()
            store = getattr(rt, "execution_store", None) if rt else None
            if store:
                active = len(getattr(store, "_active", {}) or {})
                return {"status": "pass", "score": 100,
                        "signals": {"active_graph_runs": active},
                        "items": [{"check": "活跃 Graph Run", "result": "✅",
                                   "detail": f"{active} 个活跃执行"}]}
        except Exception:
            return {"status": "unavailable", "score": 0}

    async def _check_context_metrics():
        """Check context assembly metrics (cache hit rate, compaction rate)."""
        try:
            from core.harness.kernel.runtime import get_kernel_runtime
            rt = get_kernel_runtime()
            store = getattr(rt, "execution_store", None) if rt else None
            if store:
                import sqlite3
                conn = sqlite3.connect(store._config.db_path)
                try:
                    total = conn.execute(
                        "SELECT COUNT(*) FROM syscall_events WHERE kind='metric' AND name='context_assemble' AND created_at > datetime('now','-24 hours')"
                    ).fetchone()[0]
                finally:
                    conn.close()
                return {"status": "pass" if total >= 0 else "warn",
                        "score": 80 if total == 0 else min(100, 50 + total * 5),
                        "signals": {"context_events_24h": total},
                        "items": [{"check": "24h 上下文事件", "result": "✅" if total > 0 else "—",
                                    "detail": f"{total} 条事件"}]}
        except Exception:
            return {"status": "unavailable", "score": 0}

    async def _check_e2e_smoke():
        """Check last E2E smoke test result."""
        try:
            from core.harness.kernel.runtime import get_kernel_runtime
            rt = get_kernel_runtime()
            store = getattr(rt, "execution_store", None) if rt else None
            if store:
                import sqlite3
                conn = sqlite3.connect(store._config.db_path)
                try:
                    row = conn.execute(
                        "SELECT status, output_json FROM agent_executions WHERE kind='smoke_e2e' ORDER BY created_at DESC LIMIT 1"
                    ).fetchone()
                    if row:
                        status = row[0] or "unknown"
                        return {"status": "pass" if status == "completed" else "warn",
                                "score": 100 if status == "completed" else 50,
                                "signals": {"last_smoke": status},
                                "items": [{"check": "最近冒烟", "result": "✅" if status == "completed" else "⚠️",
                                           "detail": f"状态: {status}"}]}
                finally:
                    conn.close()
        except Exception:
            pass
        return {"status": "unavailable", "score": 0, "signals": {"last_smoke": "no data"}}

    async def _check_symbol_health():
        """Scan code graph for symbol coverage and dead code candidates."""
        try:
            from core.harness.knowledge.code_graph import repo_root, default_roots
            r = repo_root()
            roots = [(r / d).resolve() for d in default_roots()]
            nodes, edges, _ = _get_or_build_graph()

            # Exclusion patterns: files legitimately with 0 in-degree
            def _is_excluded(nid: str) -> bool:
                if 'tests/' in nid or '/test_' in nid: return True        # test files
                if nid.endswith('server.py') or nid.endswith('main.py'): return True  # entry points
                if '/generated/' in nid: return True                     # generated templates
                if nid.endswith('.sh') or nid.endswith('.cfg'): return True  # scripts/config
                if nid.endswith('__init__.py'): return True              # init files
                # Dynamic dispatch: agents & skills called via registry
                if '/apps/agents/' in nid and not nid.endswith('/__init__.py'): return True
                if '/apps/skills/' in nid and not nid.endswith('/__init__.py'): return True
                if '/engine/agents/' in nid: return True
                if '/engine/skills/' in nid: return True
                # DI / integration / builder (called via dependency injection)
                if '/infrastructure/gates/' in nid: return True
                if '/builder/' in nid and 'builder_session' in nid: return True
                # CLI scripts
                if '/scripts/' in nid: return True
                # Architecture guard & lint rules (loaded dynamically by registries)
                if '/arch_guard_rules/' in nid: return True
                if '/lint_rules/' in nid: return True
                if '/management/' in nid and ('arch_guard_' in nid or 'compliance_checks' in nid or 'skill_linter' in nid): return True
                # React/TSX components — routed via React Router (not static import)
                if nid.endswith('.tsx') or nid.endswith('.ts') or nid.endswith('.jsx'): return True
                # Management/API endpoints — registered via FastAPI include_router
                if '/management/api/' in nid: return True
                if '/management/dashboard/' in nid: return True
                if '/core/api/routers/' in nid: return True
                # Tools loaded by ToolRegistry / adapters loaded by factory
                if '/core/apps/tools/' in nid: return True
                if '/core/tools/' in nid: return True
                if '/core/harness/execution/langgraph/' in nid: return True
                if nid.endswith('/execution/conditional.py'): return True
                if '/core/adapters/llm/' in nid: return True
                if nid.endswith('_adapter.py') and '/infrastructure/' in nid: return True
                # Utility / helper files
                if nid.endswith('/vector/utils.py'): return True
                if '/infra/utils/' in nid: return True
                if '/management/model/' in nid and 'scanner' in nid: return True
                # Script tools / schemas
                if nid.endswith('core/schemas_tools.py') or nid.endswith('core/schemas.py'): return True
                if '/utils/' in nid and 'core/' in nid: return True
                if nid.endswith('/knowledge/reranker.py'): return True
                if nid.endswith('infra/management/config.py'): return True
                # Syscall registry files (loaded by syscall dispatcher)
                if '/core/harness/syscalls/' in nid: return True
                # Workspace seeds / POC CLI / builder roles
                if '/workspace_seeds/' in nid: return True
                if '/builder/' in nid and 'builder_roles' in nid: return True
                if '/kb/poc/' in nid: return True
                if '/kb/intelligence/' in nid: return True
                # App pages (React components) / platform auth
                if nid.startswith('aiPlat-app/') or nid.startswith('aiplat-app/'): return True
                if nid.endswith('/auth/rbac.py'): return True
                if nid.endswith('management/run.py'): return True
                return False

            total = len(nodes)
            with_syms = sum(1 for n in nodes.values() if n.get('symbols'))
            total_syms = sum(len(n.get('symbols', [])) for n in nodes.values())
            dead = sum(1 for nid, n in nodes.items()
                      if not _is_excluded(nid) and int(n.get('in', 0)) == 0 and len(n.get('symbols', [])) > 0)
            coverage = with_syms / max(total, 1) * 100

            score = 100
            if dead > 100: score -= 15
            elif dead > 50: score -= 8
            elif dead > 20: score -= 3
            if coverage < 60: score -= 10

            # Collect dead code files for repairs (filtered)
            dead_files = [nid for nid, n in nodes.items()
                         if not _is_excluded(nid) and int(n.get('in', 0)) == 0 and len(n.get('symbols', [])) > 0][:50]

            return {
                "status": "pass" if dead < 20 else "warn" if dead < 50 else "fail",
                "score": max(0, score),
                "signals": {"total_symbols": total_syms, "files_with_symbols": with_syms,
                            "dead_code_candidates": dead, "coverage_pct": round(coverage, 1)},
                "items": [
                    {"check": "符号总数", "result": "✅", "detail": f"{total_syms} 个 / {with_syms} 文件"},
                    {"check": "疑似死代码", "result": "❌" if dead > 20 else "⚠️" if dead > 0 else "✅",
                     "detail": f"{dead} 个候选"},
                    {"check": "覆盖率", "result": "❌" if coverage < 60 else "⚠️" if coverage < 80 else "✅",
                     "detail": f"{coverage:.1f}%"}
                ],
                "_raw": {"dead_code_files": dead_files},
            }
        except Exception:
            return {"status": "unavailable", "score": 0}

    async def _check_doctor():
        """Run doctor report aggregation."""
        try:
            import sqlite3
            from core.harness.kernel.runtime import get_kernel_runtime
            rt = get_kernel_runtime()
            store = getattr(rt, "execution_store", None) if rt else None
            items: List[Dict[str, Any]] = []
            if store:
                conn = sqlite3.connect(store._config.db_path)
                try:
                    adapters = conn.execute("SELECT COUNT(*) FROM adapters WHERE status='active'").fetchone()[0]
                    items.append({"check": "Active Adapters", "result": "✅" if adapters > 0 else "⚠️", "detail": f"{adapters} active"})
                finally:
                    conn.close()
            score = 100 if items and all(i["result"] == "✅" for i in items) else 80
            return {"status": "pass" if score >= 80 else "warn", "score": score,
                    "signals": {"adapters_ok": len([i for i in items if i["result"] == "✅"])},
                    "items": items}
        except Exception:
            return {"status": "unavailable", "score": 0}

    async def _check_lsp():
        """Run pyright type-checking on core Python files. Cached 120s."""
        global _LSP_CACHE, _LSP_CACHE_TS
        if _LSP_CACHE is not None and time.time() - _LSP_CACHE_TS < 120:
            return _LSP_CACHE
        try:
            import subprocess, json
            cwd = os.getcwd()
            config = os.path.join(cwd, "aiPlat-core", "pyrightconfig.json")
            cmd = ["npx", "pyright", "--outputjson"]
            if os.path.exists(config):
                cmd += ["--project", config]
            else:
                cmd += ["aiPlat-core/core/harness", "aiPlat-core/core/api", "aiPlat-core/core/apps"]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, cwd=cwd
            )
            issues = []
            if result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    diagnostics = data.get("generalDiagnostics", [])
                    for d in diagnostics[:100]:
                        rng = d.get("range", {}).get("start", {})
                        issues.append({
                            "file": d.get("file", ""),
                            "line": rng.get("line", 0) + 1,
                            "column": rng.get("character", 0),
                            "message": d.get("message", "")[:200],
                            "rule": d.get("rule", ""),
                            "severity": "error" if d.get("severity") == "error" else "warn",
                        })
                except (json.JSONDecodeError, KeyError):
                    issues.append({"file": "pyright", "line": 0, "message": "Could not parse output", "severity": "warn", "rule": ""})
            elif "npx" in (result.stderr or "").lower() or "not found" in (result.stderr or ""):
                _LSP_CACHE = {"status": "unavailable", "score": 100, "signals": {"note": "pyright not found (run: npm i -g pyright)"}}
                _LSP_CACHE_TS = time.time()
                return _LSP_CACHE
            errors = [i for i in issues if i["severity"] == "error"]
            warns = [i for i in issues if i["severity"] == "warn"]
            score = 100 if len(issues) == 0 else max(0, 100 - len(errors) * 5 - len(warns) * 1)
            result_dict = {
                "status": "pass" if score >= 80 else "warn",
                "score": score,
                "signals": {"errors": len(errors), "warnings": len(warns)},
                "items": [{"check": f"{i['file'].split('/')[-1] if '/' in i['file'] else i['file']}:{i['line']}",
                           "result": "❌" if i['severity'] == 'error' else "⚠️",
                           "detail": f"[{i['rule']}] {i['message'][:100]}"} for i in issues[:20]],
                "_raw": {"issues": issues},
            }
            _LSP_CACHE = result_dict
            _LSP_CACHE_TS = time.time()
            return result_dict
        except FileNotFoundError:
            return {"status": "unavailable", "score": 100, "signals": {"note": "pyright not installed"}}
        except Exception:
            return {"status": "unavailable", "score": 0}

    async def _check_security():
        """Run bandit security scanner on core Python files. Cached 120s."""
        global _SEC_CACHE, _SEC_CACHE_TS
        if _SEC_CACHE is not None and time.time() - _SEC_CACHE_TS < 120:
            return _SEC_CACHE
        try:
            import subprocess, json, os
            core_dir = os.path.join(os.getcwd(), "aiPlat-core")
            if not os.path.isdir(core_dir):
                core_dir = os.getcwd()
            result = subprocess.run(
                [sys.executable, "-m", "bandit", "-r", "-f", "json", "-ll",
                 "--exclude", "tests,__pycache__,.git", core_dir],
                capture_output=True, text=True, timeout=60, cwd=os.getcwd()
            )
            issues = []
            if result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    results_list = data.get("results", [])
                    for issue in results_list[:30]:
                        fname = issue.get("filename", "")
                        issues.append({
                            "file": str(fname).split("/")[-1] if fname else "?",
                            "line": issue.get("line_number", 0),
                            "message": str(issue.get("issue_text", ""))[:120],
                            "severity": issue.get("issue_severity", "low"),
                            "confidence": issue.get("issue_confidence", "low"),
                        })
                except (json.JSONDecodeError, AttributeError):
                    issues.append({"file": "bandit", "line": 0, "message": "Parse error", "severity": "warn"})
            elif "command not found" in result.stderr or "No module named bandit" in result.stderr:
                _SEC_CACHE = {"status": "unavailable", "score": 100, "signals": {"note": "bandit not installed"}}
                _SEC_CACHE_TS = time.time()
                return _SEC_CACHE
            score = 100 if len(issues) == 0 else max(0, 100 - len(issues) * 3)
            result_dict = {
                "status": "pass" if score >= 80 else "warn",
                "score": score,
                "signals": {"issues": len(issues)},
                "items": [{"check": f"{i['file']}:{i['line']}", "result": "⚠️",
                           "detail": f"[{i['severity']}] {i['message'][:100]}"} for i in issues[:15]],
            }
            _SEC_CACHE = result_dict
            _SEC_CACHE_TS = time.time()
            return result_dict
        except FileNotFoundError:
            return {"status": "unavailable", "score": 100, "signals": {"note": "bandit not installed"}}
        except Exception:
            return {"status": "unavailable", "score": 0}

    async def _check_governance():
        """
        治理健康度检查：扫描各实体的签名/权限/密钥配置状态。
        统计：未签名实体数、签名验证失败数、缺失权限声明数、可信公钥是否已配置。
        """
        import json as _json

        home = Path(_os.environ.get("AIPLAT_HOME", _os.path.expanduser("~/.aiplat")))
        engine_root = Path(__file__).resolve().parents[3] / "core" / "engine"

        all_dirs: list[tuple[str, Path, str]] = [
            # Workspace paths
            ("skills",    home / "skills",     "SKILL.manifest.json"),
            ("agents",    home / "agents",     "AGENT.manifest.json"),
            ("mcps",      home / "mcps",       "MCP.manifest.json"),
            ("workflows", home / "workflows",  "WORKFLOW.manifest.json"),
            ("projects",  home / "projects",   "PROJECT.manifest.json"),
            ("prompt_apps", home / "prompt-apps", "TEMPLATE.manifest.json"),
            # Engine paths
            ("skills",    engine_root / "skills",  "SKILL.manifest.json"),
            ("agents",    engine_root / "agents",  "AGENT.manifest.json"),
            ("mcps",      engine_root / "mcps",    "MCP.manifest.json"),
        ]

        unsigned = []
        verified = []
        no_manifest = []
        missing_perms = []

        for entity_type, base_path, mf_name in all_dirs:
            if not base_path.is_dir():
                continue
            for entity_dir in base_path.iterdir():
                if not entity_dir.is_dir() or entity_dir.name.startswith("."):
                    continue
                mf_path = entity_dir / mf_name
                if not mf_path.exists():
                    no_manifest.append(f"{entity_type}/{entity_dir.name}")
                    continue
                try:
                    with open(mf_path, "r") as f:
                        mf = _json.load(f)
                    if mf.get("signature"):
                        verified.append(f"{entity_type}/{entity_dir.name}")
                    else:
                        unsigned.append(f"{entity_type}/{entity_dir.name}")
                except Exception:
                    unsigned.append(f"{entity_type}/{entity_dir.name}")

            # Skills-specific: check permissions declarations
            if entity_type == "skills":
                for entity_dir2 in base_path.iterdir():
                    if not entity_dir2.is_dir() or entity_dir2.name.startswith("."):
                        continue
                    skmd = entity_dir2 / "SKILL.md"
                    if skmd.exists():
                        try:
                            content = skmd.read_text(encoding="utf-8")
                            if "permissions:" not in content and "permissions" not in content:
                                missing_perms.append(f"skills/{entity_dir2.name}")
                        except Exception:
                            pass

        # Check trusted keys
        has_trusted_keys = False
        try:
            from core.harness.kernel.runtime import get_kernel_runtime
            rt = get_kernel_runtime()
            store = getattr(rt, "execution_store", None) if rt else None
            if store:
                gs = await store.get_global_setting(key="trusted_skill_pubkeys")
                keys_list = (gs.get("keys") or []) if gs and isinstance(gs, dict) else []
                has_trusted_keys = len(keys_list) > 0
        except Exception:
            pass

        total_entities = len(unsigned) + len(verified) + len(no_manifest)
        governed = len(verified)
        ungoverned = len(unsigned) + len(no_manifest)

        base_score = 100
        base_score -= len(no_manifest) * 2 if no_manifest else 0
        base_score -= len(unsigned) * 2 if unsigned else 0
        base_score -= len(missing_perms) * 2 if missing_perms else 0
        if not has_trusted_keys and total_entities > 0:
            base_score -= 20
        score = max(0, base_score)

        status = "pass" if score >= 80 else ("warn" if score >= 50 else "fail")

        items = []
        if no_manifest:
            items.append({"check": "无溯源码", "result": "❌", "detail": f"{len(no_manifest)} 个实体缺少 manifest.json：{', '.join(no_manifest[:5])}{'...' if len(no_manifest) > 5 else ''}"})
        if unsigned:
            items.append({"check": "未签名", "result": "⚠️", "detail": f"{len(unsigned)} 个有 manifest 但无签名：{', '.join(unsigned[:5])}{'...' if len(unsigned) > 5 else ''}"})
        if missing_perms:
            items.append({"check": "缺失权限声明", "result": "⚠️", "detail": f"{len(missing_perms)} 个可执行 Skill 缺少 permissions 声明"})
        if not has_trusted_keys:
            items.append({"check": "未配置可信公钥", "result": "⚠️", "detail": "trusted_skill_pubkeys 为空，无法验签"})
        if not items:
            items.append({"check": "治理", "result": "✅", "detail": f"所有 {total_entities} 个实体均已治理"})

        return {
            "status": status, "score": score,
            "signals": {
                "total": total_entities, "governed": governed, "ungoverned": ungoverned,
                "no_manifest": len(no_manifest), "unsigned": len(unsigned),
                "missing_perms": len(missing_perms),
                "has_trusted_keys": has_trusted_keys,
            },
            "items": items,
        }

    async def _check_frontend():
        """§43+§44: Frontend proxy routing + API contract consistency."""
        from pathlib import Path as _P
        try:
            repo_root = _P(__file__).resolve().parents[4]
            vite_config = repo_root / "aiPlat-management" / "frontend" / "vite.config.ts"
            items = []

            if vite_config.exists():
                import re, subprocess as _sp
                content = vite_config.read_text(encoding="utf-8")
                proxy_entries = re.findall(
                    r"'([^']+)'\s*:\s*\{[^}]*?target:\s*'([^']+)'[^}]*\}",
                    content, re.DOTALL
                )
                # Check catch-all proxy
                for pattern, target in proxy_entries:
                    port_match = re.search(r':(\d+)$', target)
                    if not port_match:
                        continue
                    port = port_match.group(1)
                    if pattern == "/api/core" and port != "8002":
                        items.append({"check": "Vite 代理错配", "result": "❌",
                                      "detail": f"/api/core → port {port} (应为 8002)"})
                    if pattern.startswith("/api/core/workspace/") and port == "8000":
                        items.append({"check": "Workspace 代理错配", "result": "❌",
                                      "detail": f"'{pattern}' → port 8000"})

                # Cross-language contract: args vs arguments
                ts_file = repo_root / "aiPlat-management/frontend/src/pages/Workspace/MCP/MCP.tsx"
                py_file = repo_root / "aiPlat-core/core/api/routers/mcp_admin.py"
                if ts_file.exists() and py_file.exists():
                    ts_body = ts_file.read_text(encoding="utf-8")
                    py_body = py_file.read_text(encoding="utf-8")
                    if re.search(r'"args"\s*:\s*\{', ts_body) and not re.search(r'data\.get\("args"\)', py_body):
                        items.append({"check": "API 契约不匹配", "result": "❌",
                                      "detail": "前端传 'args', 后端读 'arguments' — mcp_admin.py"})

            score = 100 if not items else max(0, 100 - len(items) * 20)
            return {
                "status": "pass" if not items else "warn" if len(items) <= 2 else "fail",
                "score": score,
                "items": items,
                "_raw": {"items": items},
            }
        except Exception as e:
            return {"status": "error", "score": 0, "error": str(e)[:200]}

    async def _check_mcp():
        """§45: MCP integration smoke test — probe MCP server connectivity."""
        try:
            import sys, json as _json
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "core.apps.mcp.local_tools_server",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                # initialize
                init_req = _json.dumps({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                    "clientInfo": {"name": "diag-smoke", "version": "1.0.0"}}}) + "\n"
                proc.stdin.write(init_req.encode("utf-8"))
                await proc.stdin.drain()
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=8)
                init_resp = _json.loads(line.decode("utf-8"))
                if "error" in init_resp or "result" not in init_resp:
                    raise Exception(f"MCP initialize failed: {init_resp}")

                # list tools
                list_req = _json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}) + "\n"
                proc.stdin.write(list_req.encode("utf-8"))
                await proc.stdin.drain()
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=8)
                list_resp = _json.loads(line.decode("utf-8"))
                tools = (list_resp.get("result") or {}).get("tools") or []
                tool_names = [t.get("name", "") for t in tools]

                # call test-1
                call_req = _json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "test-1", "arguments": {"num": 11}}}) + "\n"
                proc.stdin.write(call_req.encode("utf-8"))
                await proc.stdin.drain()
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=8)
                call_resp = _json.loads(line.decode("utf-8"))

                content = (call_resp.get("result") or {}).get("content", [])
                text = content[0].get("text", "") if content else ""
                result_val = _json.loads(text).get("result") if text else None
                ok = result_val == 121

                return {
                    "status": "pass" if ok else "fail",
                    "score": 100 if ok else 0,
                    "signals": {
                        "tools_count": len(tools),
                        "tools": tool_names[:10],
                        "test_result": result_val,
                    },
                    "items": [{"check": "MCP 连通性", "result": "✅" if ok else "❌",
                               "detail": f"tools={len(tools)}, test-1(11)={'121' if ok else str(result_val)}"}],
                    "_raw": {"tools": tool_names, "test_result": result_val},
                }
            finally:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except Exception:
                    pass
        except Exception as e:
            return {"status": "error", "score": 0, "error": str(e)[:200],
                    "items": [{"check": "MCP 连通性", "result": "❌",
                               "detail": f"不可达: {str(e)[:200]}"}]}

    # Build check list: all or single category
    checks = [
        ("core_runtime", _check_core_runtime()),
        ("code_intel", _check_code_intel()),
        ("cross_lang", _check_cross_lang_links()),
        ("route_coverage", _check_route_coverage()),
        ("domain_coupling", _check_domain_coupling()),
        ("fragile_base", _check_fragile_base()),
        ("capability", _check_capability()),
        ("skill_lint", _check_skill_lint()),
        ("wiki_health", _check_wiki_health()),
        ("compliance", _check_compliance()),
        ("overview_issues", _check_overview_issues()),
        ("traces", _check_traces()),
        ("graph_runs", _check_graph_runs()),
        ("context_metrics", _check_context_metrics()),
        ("governance", _check_governance()),
        ("frontend", _check_frontend()),
    ]
    # Slow checks — skipped in quick mode
    if not quick:
        checks.extend([
            ("e2e_smoke", _check_e2e_smoke()),
            ("symbol_health", _check_symbol_health()),
            ("doctor", _check_doctor()),
            ("lsp", _check_lsp()),
            ("security", _check_security()),
            ("arch_guard", _check_arch_guard()),
            ("mcp", _check_mcp()),
        ])
    if category:
        checks = [c for c in checks if c[0] == category]
    await asyncio.gather(*(_safe(name, coro) for name, coro in checks))

    # If arch_guard was not run standalone, extract from compliance as fallback
    if "arch_guard" not in categories:
        compliance_cat = categories.get("compliance", {})
        if isinstance(compliance_cat, dict) and "items" in compliance_cat:
            for item in compliance_cat.get("items", []):
                if item.get("check") == "架构守卫" and "violations" in item.get("detail", ""):
                    import re as _re
                    v_match = _re.search(r'(\d+)', item.get("detail", "0"))
                    violations = int(v_match.group(1)) if v_match else 0
                    categories["arch_guard"] = {
                        "status": "pass" if violations == 0 else "fail",
                        "score": max(0, 100 - violations),
                        "violations": violations,
                        "items": [{"check": "架构守卫", "result": "❌" if violations > 0 else "✅",
                                   "detail": f"{violations} 处违规"}],
                    }
                    break

    # Compute overall score
    scores = [c.get("score", 0) for c in categories.values() if isinstance(c, dict)]
    overall = round(sum(scores) / len(scores), 1) if scores else 0
    if overall >= 90: grade = "A"
    elif overall >= 75: grade = "B"
    elif overall >= 60: grade = "C"
    elif overall >= 40: grade = "D"
    else: grade = "F"

    # Collect top issues (exclude arch_guard from score-based list — use violations)
    _labels = {
        "core_runtime": "Core 运行时", "code_intel": "代码架构", "capability": "能力图谱",
        "wiki_health": "Wiki健康", "arch_guard": "架构守卫", "compliance": "合规审计",
        "traces": "链路追踪", "graph_runs": "图执行", "context_metrics": "上下文",
        "e2e_smoke": "冒烟测试", "doctor": "Doctor", "overview_issues": "概览问题",
        "symbol_health": "符号健康", "lsp": "LSP 诊断", "security": "安全扫描",
        "cross_lang": "跨语言连接", "route_coverage": "路由覆盖",
        "domain_coupling": "跨域耦合", "fragile_base": "脆弱基类",
        "governance": "治理", "skill_lint": "Skill Lint",
        "frontend": "前端守卫", "mcp": "MCP 连通性",
    }
    for cat_name, cat in categories.items():
        if not isinstance(cat, dict):
            continue
        if cat_name == "arch_guard" and cat.get("violations", 0) > 0:
            issues.append({"category": "arch_guard", "score": 0, "status": "fail",
                           "label": f"架构守卫({cat['violations']}违规)"})
        elif cat.get("status") not in ("pass", "unavailable") and cat.get("score", 100) < 100:
            label = _labels.get(cat_name, cat_name)
            issues.append({"category": cat_name, "score": cat.get("score", 0), "status": cat.get("status"),
                           "label": f"{label}({cat.get('score', 0)})"})

    duration_ms = int((time.time() - started_at) * 1000)

    # ── Cache for repairs fast path ──────────────────────────────
    # Extract _raw detail from each category for repair center
    _details = {}
    for cat_name, cat in categories.items():
        if isinstance(cat, dict) and "_raw" in cat:
            _details[cat_name] = cat.pop("_raw")
            if cat_name == "skill_lint":
                _details["skill_lint"]["auto_fix_total"] = _details["skill_lint"].get("auto_fix_total", 0)

    # Also extract arch_guard _raw details for repair center
    try:
        ag_raw = await _check_arch_guard()
        if isinstance(ag_raw, dict) and "_raw" in ag_raw:
            _details["arch_guard"] = ag_raw["_raw"]
    except Exception:
        pass

    result = {
        "run_id": run_id,
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
    if _details:
        result["_details"] = _details

    # Fire-and-forget: auto-fill shell agents detected during compliance check
    try:
        shell_agents = _details.get("compliance", {}).get("shell_agents", [])
        if shell_agents:
            names = [a.split(":", 1)[1] if ":" in a else a for a in shell_agents]
            asyncio.create_task(_auto_fill_agents_async(names))
    except Exception:
        pass

    # Append to diagnostic history for trend chart
    _append_diag_history(result)

    global _DIAG_CACHE, _DIAG_CACHE_TS
    _DIAG_CACHE = result
    _DIAG_CACHE_TS = time.time()
    _save_diag_cache()
    # Also invalidate overview cache so it stays consistent
    try:
        import core.api.routers.overview as _ov_mod
        _ov_mod._OV_CACHE = None
    except Exception:
        pass
    _publish("diagnostics_complete", overall_score=overall, overall_grade=grade)
    _DIAG_RUNNING = False
    return result


@router.post("/diagnostics/run-single")
async def run_single_diagnostics(req: dict):
    """Run a single diagnostic category and return its result with real-time observation."""
    category = req.get("category", "")
    if not category:
        raise HTTPException(status_code=400, detail="category is required")
    # Reuse run_all_diagnostics with category filter
    return await run_all_diagnostics(category=category)


@router.post("/diagnostics/repairs")
async def get_repairs():
    """Aggregate all fixable issues across diagnostic systems.

    Uses cached run-all results when fresh (30s TTL), avoiding re-scan.
    Heavy systems (skill_lint, arch_guard, capability) skip rebuild when cache is hot.
    """
    from pathlib import Path as _P

    repairs: List[Dict[str, Any]] = []
    cache_hit = _DIAG_CACHE is not None

    # Cold cache → auto-trigger quick diagnostics to populate, then aggregate
    if not cache_hit:
        try:
            await run_all_diagnostics(quick=True)
            cache_hit = _DIAG_CACHE is not None
            if not cache_hit:
                return {
                    "repairs": [],
                    "summary": {"total_systems": 0, "total_issues": 0, "needs_diagnostics": True},
                }
        except Exception:
            return {
                "repairs": [],
                "summary": {"total_systems": 0, "total_issues": 0, "needs_diagnostics": True},
            }

    details = _DIAG_CACHE.get("_details", {})
    if not details:
        return {
            "repairs": [],
            "summary": {"total_systems": 0, "total_issues": 0, "needs_diagnostics": True},
        }

    # ── All repairs from cached _details (0ms, no re-scan) ──────────

    # Skill Lint
    sl = details.get("skill_lint")
    if sl and sl.get("items"):
        repairs.append({
            "source": "skill_lint",
            "title": f"{len(sl['items'])} 个 Skill · {sl.get('errors', 0)}E {sl.get('warnings', 0)}W",
            "auto_fix_total": sl.get("auto_fix_total", 0),
            "items": sl["items"],
        })

    # Shell Agents (from compliance._raw)
    compliance_raw = details.get("compliance", {})
    if compliance_raw and compliance_raw.get("shell_agents"):
        shell_list = compliance_raw["shell_agents"]
        repairs.append({
            "source": "agent_shell",
            "title": f"{len(shell_list)} 个空壳 Agent",
            "detail": "无 system_prompt、无 skills、无 tools",
            "can_auto_fill": True,
            "items": [{"dir": a, "severity": "warn"} for a in shell_list],
        })

    # Wiki Health
    wiki_raw = details.get("wiki_health", {})
    if wiki_raw and wiki_raw.get("issues"):
        repairs.append({
            "source": "wiki_health",
            "title": f"{len(wiki_raw['issues'])} 个 Wiki 问题",
            "score": wiki_raw.get("score", 100),
            "items": wiki_raw["issues"][:20],
        })

    # Capability
    cap_raw = details.get("capability", {})
    if cap_raw and cap_raw.get("issues"):
        cap_issues = cap_raw["issues"]
        items = []
        for name in cap_issues.get("unused_skills", []):
            items.append({"type": "unused_skill", "name": name, "suggestion": "绑定到至少一个 Agent"})
        for name in cap_issues.get("orphan_agents", []):
            items.append({"type": "orphan_agent", "name": name, "suggestion": "添加 skills 或 tools"})
        for dup in cap_issues.get("entry_point_duplicates", []):
            items.append({"type": "duplicate_entry", "name": dup.get("capability", ""), "detail": dup.get("detail", "")})
        if items:
            repairs.append({
                "source": "capability",
                "title": f"{len(items)} 个能力问题",
                "score": cap_raw.get("score", 100),
                "grade": cap_raw.get("grade", "?"),
                "items": items[:20],
            })

    # Overview Issues
    ov_raw = details.get("overview_issues", {})
    if ov_raw and ov_raw.get("items"):
        ov_items = [{"type": it["check"], "name": it["check"], "suggestion": it["detail"]}
                     for it in ov_raw["items"]]
        repairs.append({
            "source": "overview",
            "title": f"{len(ov_items)} 个概览发现的问题",
            "items": ov_items,
        })

    # Governance
    gov_raw = details.get("governance", {})
    if gov_raw and gov_raw.get("items"):
        gov_signals = gov_raw.get("signals", {})
        gov_items = []
        if gov_signals.get("no_manifest", 0) > 0:
            gov_items.append({"type": "no_manifest", "name": "缺少溯源码", "suggestion": f"需为 {gov_signals['no_manifest']} 个实体创建 manifest.json。服务启动后进入 entities 管理页面签名即可自动生成", "severity": "warn"})
        if gov_signals.get("unsigned", 0) > 0:
            gov_items.append({"type": "unsigned", "name": "实体未签名", "suggestion": f"在管理页面中对 {gov_signals['unsigned']} 个实体粘贴私钥签名", "severity": "warn"})
        if gov_signals.get("unverified", 0) > 0:
            gov_items.append({"type": "unverified", "name": "签名验证失败", "suggestion": f"{gov_signals['unverified']} 个签名验证失败，检查是否篡改或公钥不匹配", "severity": "error"})
        if gov_signals.get("missing_perms", 0) > 0:
            gov_items.append({"type": "missing_perms", "name": "缺失权限声明", "suggestion": f"为 {gov_signals['missing_perms']} 个可执行 Skill 补全 SKILL.md 中的 permissions 声明", "severity": "warn"})
        if not gov_signals.get("has_trusted_keys"):
            gov_items.append({"type": "no_trusted_keys", "name": "未配置可信公钥", "suggestion": "在初始化向导中上传可信公钥，或在 Onboarding 页面生成密钥对并配置", "severity": "error"})
        if gov_items:
            repairs.append({
                "source": "governance",
                "title": f"{len(gov_items)} 个治理问题 · {gov_signals.get('governed', 0)}/{gov_signals.get('total', 0)} 已治理",
                "score": gov_raw.get("score", 100),
                "items": gov_items,
            })

    # Arch Guard
    ag_raw = details.get("arch_guard", {})
    if ag_raw and ag_raw.get("sections"):
        ag_items = [{"type": "violation", "section": s["section"],
                     "section_name": s["section_name"], "message": s["message"],
                     "sample_file": s["sample_file"], "count": s.get("count", 0),
                     "suggestion": s["sample_file"].split(":")[0] if s.get("sample_file") else ""}
                    for s in ag_raw["sections"]]
        repairs.append({
            "source": "arch_guard",
            "title": f"{len(ag_items)} 个架构违规需要修复",
            "total_violations": ag_raw.get("violations", 0),
            "items": ag_items,
        })

    # Dead code candidates (from symbol health)
    sym_raw = details.get("symbol_health", {})
    if sym_raw and sym_raw.get("dead_code_files"):
        dc_items = [{"type": "dead_code", "file": f, "suggestion": "0 入度+有符号 → 可能已废弃，建议审查"}
                     for f in sym_raw["dead_code_files"][:20]]
        repairs.append({
            "source": "dead_code",
            "title": f"{len(sym_raw['dead_code_files'])} 个死代码候选",
            "detail": "有函数/类定义但无任何文件导入",
            "items": dc_items,
        })

    # ── LSP Fixable Issues ────────────────────────────────────────
    lsp_raw = details.get("lsp", {})
    if lsp_raw and lsp_raw.get("issues"):
        fixable = [i for i in lsp_raw["issues"] if i["severity"] == "error"]
        warns = [i for i in lsp_raw["issues"] if i["severity"] == "warn"]
        if fixable:
            repairs.append({
                "source": "lsp",
                "title": f"{len(fixable)} 个类型错误可修复 · {len(warns)} 个警告",
                "detail": "pyright 诊断：类型不匹配/未定义变量/参数错误",
                "can_auto_fix": True,
                "items": [{
                    "file": i["file"],
                    "line": i["line"],
                    "column": i.get("column", 0),
                    "message": i["message"],
                    "rule": i.get("rule", ""),
                    "severity": i["severity"],
                } for i in fixable],
                "warning_items": warns,
            })

    # ── Summary ────────────────────────────────────────────────────
    total = 0
    auto = 0
    for r in repairs:
        items = r.get("items", [])
        total += len(items)
        if r["source"] == "skill_lint":
            auto += r.get("auto_fix_total", 0)
        elif r.get("can_auto_fill"):
            auto += len(items)

    return {
        "repairs": repairs,
        "summary": {
            "total_systems": len(repairs),
            "total_issues": total,
            "auto_fixable": auto,
        },
    }


@router.get("/diagnostics/observability/stats")
async def observability_stats():
    """Aggregated observability stats for the dashboard."""
    import sqlite3
    from core.services.execution_store import get_execution_store
    store = get_execution_store()
    db_path = store._config.db_path  # type: ignore

    def _query(sql, params=()):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    result = {}

    # LLM call stats (last 24h)
    rows = _query("""
        SELECT
            COUNT(*) as total_calls,
            COUNT(CASE WHEN status='ok' THEN 1 END) as ok,
            COUNT(CASE WHEN status='error' THEN 1 END) as error,
            COALESCE(AVG(duration_ms), 0) as avg_latency,
            COALESCE(MAX(duration_ms), 0) as max_latency,
            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(cost), 0) as total_cost
        FROM syscall_events
        WHERE kind='sys_llm_generate' AND created_at > datetime('now','-1 day')
    """)
    llm = rows[0] if rows else {}
    total_calls = llm.get("total_calls", 0) or 0
    ok = llm.get("ok", 0) or 0
    result["llm_stats"] = {
        "total_calls": total_calls,
        "success_rate": round(ok / total_calls * 100, 1) if total_calls > 0 else 100,
        "avg_latency_ms": round(llm.get("avg_latency", 0) or 0, 1),
        "max_latency_ms": round(llm.get("max_latency", 0) or 0, 1),
        "total_input_tokens": llm.get("total_input_tokens", 0) or 0,
        "total_output_tokens": llm.get("total_output_tokens", 0) or 0,
        "total_cost": round(llm.get("total_cost", 0) or 0, 4),
    }

    # Syscall stats by kind (last 24h)
    by_kind = {}
    for r in _query("""
        SELECT kind, COUNT(*) as cnt, COALESCE(AVG(duration_ms), 0) as avg_lat
        FROM syscall_events
        WHERE created_at > datetime('now','-1 day')
        GROUP BY kind ORDER BY cnt DESC
    """):
        by_kind[r.get("kind", "unknown")] = {"count": r.get("cnt", 0), "avg_latency_ms": round(r.get("avg_lat", 0), 1)}
    result["syscall_by_kind"] = by_kind

    # Active runs (last 1h)
    rows = _query("""
        SELECT COUNT(DISTINCT run_id) as cnt FROM syscall_events
        WHERE created_at > datetime('now','-1 hour') AND status='running'
    """)
    result["active_runs"] = rows[0].get("cnt", 0) if rows else 0

    # Throughput: events per minute (last hour, 5-min buckets)
    result["throughput"] = [
        {"ts": r.get("bucket", 0), "count": r.get("cnt", 0)}
        for r in _query("""
            SELECT (strftime('%%s', created_at) / 300) * 300 as bucket, COUNT(*) as cnt
            FROM syscall_events WHERE created_at > datetime('now','-1 hour')
            GROUP BY bucket ORDER BY bucket
        """)
    ]

    # Error rate timeline (last 6h, 30-min windows)
    result["error_timeline"] = []
    for r in _query("""
        SELECT
            (strftime('%%s', created_at) / 1800) * 1800 as bucket,
            COUNT(*) as total,
            COUNT(CASE WHEN status='error' THEN 1 END) as errors
        FROM syscall_events
        WHERE created_at > datetime('now','-6 hours')
        GROUP BY bucket ORDER BY bucket
    """):
        total = r.get("total", 0) or 0
        errors = r.get("errors", 0) or 0
        result["error_timeline"].append({
            "ts": r.get("bucket", 0),
            "total": total,
            "errors": errors,
            "error_rate": round(errors / total * 100, 1) if total > 0 else 0,
        })

    # Model usage distribution
    result["model_usage"] = [
        {
            "model": r.get("model", "unknown") or "unknown",
            "count": r.get("cnt", 0),
            "input_tokens": r.get("in_tokens", 0) or 0,
            "output_tokens": r.get("out_tokens", 0) or 0,
        }
        for r in _query("""
            SELECT target_type as model, COUNT(*) as cnt,
                   COALESCE(SUM(input_tokens), 0) as in_tokens,
                   COALESCE(SUM(output_tokens), 0) as out_tokens
            FROM syscall_events
            WHERE kind='sys_llm_generate' AND created_at > datetime('now','-1 day')
            GROUP BY target_type ORDER BY cnt DESC LIMIT 10
        """)
    ]

    # Top errors
    result["top_errors"] = [
        {"error": (r.get("error", "") or "")[:120], "count": r.get("cnt", 0)}
        for r in _query("""
            SELECT error, COUNT(*) as cnt
            FROM syscall_events
            WHERE status='error' AND created_at > datetime('now','-1 day') AND error IS NOT NULL
            GROUP BY error ORDER BY cnt DESC LIMIT 5
        """)
    ]

    # Evaluate alert thresholds
    result["active_alerts"] = _evaluate_alerts(result)

    return result


# ── Alert Thresholds ────────────────────────────────────────────

ALERT_DEFAULTS = [
    {"id": "error_rate", "metric": "error_rate", "condition": ">20", "value": 20, "unit": "%", "enabled": True, "description": "错误率超过 20%"},
    {"id": "avg_latency", "metric": "avg_latency_ms", "condition": ">5000", "value": 5000, "unit": "ms", "enabled": False, "description": "平均延迟超过 5 秒"},
    {"id": "success_rate", "metric": "success_rate", "condition": "<80", "value": 80, "unit": "%", "enabled": False, "description": "成功率低于 80%"},
]

_alert_config_cache: Optional[List[dict]] = None
_alert_config_ts: float = 0.0


def _load_alert_config() -> List[dict]:
    global _alert_config_cache, _alert_config_ts
    if _alert_config_cache is not None and time.time() - _alert_config_ts < 30:
        return _alert_config_cache
    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        conn = sqlite3.connect(store._config.db_path)
        try:
            row = conn.execute("SELECT v FROM aiplat_meta WHERE k='observability_alerts'").fetchone()
            if row:
                _alert_config_cache = json.loads(row[0])
            else:
                _alert_config_cache = list(ALERT_DEFAULTS)
        finally:
            conn.close()
    except Exception:
        _alert_config_cache = list(ALERT_DEFAULTS)
    _alert_config_ts = time.time()
    return _alert_config_cache


def _save_alert_config(config: List[dict]) -> None:
    global _alert_config_cache, _alert_config_ts
    _alert_config_cache = config
    _alert_config_ts = time.time()
    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        conn = sqlite3.connect(store._config.db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO aiplat_meta(k, v) VALUES('observability_alerts', ?)",
                (json.dumps(config),),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _evaluate_alerts(stats: Dict) -> List[dict]:
    """Evaluate alert thresholds against current stats."""
    config = _load_alert_config()
    alerts = []
    llm = stats.get("llm_stats", {})
    for rule in config:
        if not rule.get("enabled"):
            continue
        metric = rule.get("metric", "")
        val = rule.get("value", 0)
        if metric == "error_rate":
            current = 100 - (llm.get("success_rate", 100) or 100)
            if current > val:
                alerts.append({"id": rule["id"], "metric": metric, "current": round(current, 1),
                               "threshold": val, "description": rule["description"], "unit": rule.get("unit", "%")})
        elif metric == "avg_latency_ms":
            current = llm.get("avg_latency_ms", 0) or 0
            if current > val:
                alerts.append({"id": rule["id"], "metric": metric, "current": round(current, 1),
                               "threshold": val, "description": rule["description"], "unit": rule.get("unit", "ms")})
        elif metric == "success_rate":
            current = llm.get("success_rate", 100) or 100
            if current < val:
                alerts.append({"id": rule["id"], "metric": metric, "current": round(current, 1),
                               "threshold": val, "description": rule["description"], "unit": rule.get("unit", "%")})
    return alerts


@router.get("/diagnostics/observability/alerts")
async def get_alerts():
    return {"alerts": _load_alert_config()}


@router.put("/diagnostics/observability/alerts")
async def update_alerts(data: dict = None):
    rules = data.get("alerts") if data else None
    if not isinstance(rules, list):
        raise HTTPException(400, "alerts must be a list")
    _save_alert_config(rules)
    return {"alerts": rules, "status": "saved"}


# ── Model Playground ─────────────────────────────────────────────

@router.get("/diagnostics/playground/models")
async def list_playground_models():
    """List available LLM models for the playground."""
    try:
        from core.harness.infrastructure.infra_bridge import _list_models_from_infra
        models = _list_models_from_infra()
        if not models:
            # Fallback: env-based models
            import os
            models = []
            default = os.getenv("AIPLAT_LLM_MODEL", "") or os.getenv("AIPLAT_DEFAULT_PROVIDER_MODEL", "")
            if default:
                models.append({"name": default, "provider": "env", "status": "available"})
        return {"models": models}
    except Exception:
        return {"models": []}


@router.post("/diagnostics/playground/compare")
async def compare_models(data: dict = None):
    """Compare LLM outputs across multiple models concurrently."""
    prompt = data.get("prompt", "") if data else ""
    model_names = data.get("models", []) if data else []

    if not prompt or not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(400, "prompt is required")
    if not isinstance(model_names, list) or len(model_names) == 0:
        raise HTTPException(400, "models list is required")
    if len(model_names) > 6:
        raise HTTPException(400, "max 6 models at once")

    import time as _time
    from core.harness.utils.model_injection import create_selected_adapter

    results = []

    async def _run_one(model_name: str) -> dict:
        t0 = _time.time()
        try:
            adapter = create_selected_adapter(model_name=model_name)
            if adapter is None:
                return {"model": model_name, "error": "Adapter not available", "latency_ms": 0}
            resp = await sys_llm_generate(adapter,
                prompt=[{"role": "user", "content": prompt}],
            )
            t1 = _time.time()
            latency = round((t1 - t0) * 1000, 1)
            content = getattr(resp, "content", "") if resp else ""
            usage = getattr(resp, "usage", None) if resp else None
            tokens_in = 0
            tokens_out = 0
            if isinstance(usage, dict):
                tokens_in = usage.get("prompt_tokens", 0) or 0
                tokens_out = usage.get("completion_tokens", 0) or 0
            return {
                "model": model_name,
                "content": str(content)[:3000],
                "latency_ms": latency,
                "input_tokens": tokens_in,
                "output_tokens": tokens_out,
                "status": "ok",
            }
        except Exception as e:
            t1 = _time.time()
            return {
                "model": model_name,
                "error": str(e)[:200],
                "latency_ms": round((t1 - t0) * 1000, 1),
                "status": "error",
            }

    # Run all models concurrently
    tasks = [_run_one(m) for m in model_names]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    clean = []
    for r in results:
        if isinstance(r, Exception):
            clean.append({"status": "error", "error": str(r)[:200]})
        else:
            clean.append(r)

    return {"results": clean, "prompt": prompt}


@router.post("/diagnostics/playground/chat")
async def playground_chat(data: dict = None):
    """Quick-test chat: send a message with pipeline stages as context."""
    message = data.get("message", "") if data else ""
    stages = data.get("stages", []) if data else []

    if not message or not isinstance(message, str) or not message.strip():
        raise HTTPException(400, "message is required")

    try:
        from core.harness.utils.model_injection import create_selected_adapter
        adapter = create_selected_adapter(model_name="")
        if adapter is None:
            raise HTTPException(503, "No LLM adapter available")

        # Build context from stages
        stage_ctx = ""
        if stages:
            lines = []
            for i, s in enumerate(stages):
                name = s.get("agent_name", s.get("id", f"Stage {i+1}"))
                phase = s.get("phase", "")
                lines.append(f"  {i+1}. {name}" + (f" ({phase})" if phase else ""))
            stage_ctx = "流水线阶段:\n" + "\n".join(lines)

        system = "你是一个流水线测试助手。以下是当前配置的流水线，请根据用户消息给出有帮助的回复。"
        if stage_ctx:
            system += f"\n\n{stage_ctx}"

        import time as _time
        t0 = _time.time()
        resp = await sys_llm_generate(adapter, prompt=[
            {"role": "system", "content": system},
            {"role": "user", "content": message.strip()},
        ])
        t1 = _time.time()
        return {
            "content": getattr(resp, "content", "") or "",
            "latency_ms": round((t1 - t0) * 1000, 1),
            "stages_count": len(stages),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Chat failed: {e}")
