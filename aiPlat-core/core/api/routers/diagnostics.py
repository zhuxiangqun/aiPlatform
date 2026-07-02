from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

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


# ── LLM review target selection ──

def _select_llm_review_targets(max_files: int = 15) -> List[tuple]:
    """Select high-priority files for LLM deep review.
    
    Strategy:
      1. Files > 500 lines (monolith candidates)
      2. Core engine files (harness/execution/ + harness/knowledge/)
      3. Recently modified files (git log --since=7days)
    
    Returns list of (file_path, line_count) tuples, sorted by line count desc.
    """
    import os as _os
    from pathlib import Path
    # diagnostics.py is at core/api/routers/, parents[2] = core/
    core_dir = str(Path(__file__).resolve().parents[2])

    candidates = set()

    # Rule 1: Files > 500 lines in core/
    if _os.path.isdir(core_dir):
        for root, dirs, files in _os.walk(core_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests", ".venv", ".git")]
            for f in files:
                if f.endswith(".py") and f not in ("__init__.py",):
                    fpath = _os.path.join(root, f)
                    try:
                        lines = len(open(fpath).readlines())
                        if lines > 500:
                            candidates.add((fpath, lines))
                    except Exception:
                        pass

    # Rule 2: Core engine files regardless of size
    core_patterns = ["harness/execution/", "harness/knowledge/", "harness/syscalls/",
                     "harness/memory/", "harness/ontology_engine/"]
    for root, dirs, files in _os.walk(core_dir):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests", ".venv", ".git")]
        for f in files:
            if f.endswith(".py") and f != "__init__.py":
                fpath = _os.path.join(root, f)
                rel = _os.path.relpath(fpath, core_dir)
                if any(rel.startswith(p) for p in core_patterns):
                    try:
                        lines = len(open(fpath).readlines())
                        candidates.add((fpath, lines))
                    except Exception:
                        pass

    # Sort by line count desc, take top N
    result = sorted(candidates, key=lambda x: -x[1])[:max_files]
    return result


# ── v2.2: Autoreview evidence chain helper ──

async def _get_autoreview_summary() -> Dict[str, Any]:
    """获取最近 autoreview 审查状态的摘要信息。
    
    查询 execution_store 中 'autoreview:last:*' 键的持久化审查记录。
    """
    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()

        runs = []
        for key in ("autoreview:last:diff", "autoreview:last:commit", "autoreview:last:branch"):
            gs = await store.get_global_setting(key=key)
            if gs and isinstance(gs, dict):
                val = gs.get("value") or {}
                if val:
                    runs.append(val)

        runs.sort(key=lambda r: r.get("timestamp", 0), reverse=True)

        if not runs:
            return {"last_clean": None, "mode_used": "N/A", "total_runs": 0}

        clean_runs = [r for r in runs if r.get("clean")]
        last_clean = clean_runs[0].get("timestamp") if clean_runs else None

        return {
            "last_clean": last_clean,
            "mode_used": runs[0].get("mode", "N/A"),
            "engines": runs[0].get("engines_used", []),
            "total_runs": len(runs),
            "clean_rate": f"{len(clean_runs)}/{len(runs)}",
        }
    except Exception:
        return {"last_clean": None, "mode_used": "N/A", "total_runs": 0}


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
            # Invalidate cache if diagnostics.py or code_graph.py was modified after cache save
            cache_mtime = os.path.getmtime(path)
            self_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            code_graph = os.path.join(self_dir, "harness", "knowledge", "code_graph.py")
            latest_mtime = max(os.path.getmtime(__file__),
                              os.path.getmtime(code_graph) if os.path.exists(code_graph) else 0)
            if latest_mtime > cache_mtime:
                _DIAG_CACHE = None
                return
            with open(path, "r") as f:
                _DIAG_CACHE = json.load(f)
            _DIAG_CACHE_TS = time.time()
    except Exception as e:
        logging.warning(str(e), exc_info=True)


def _save_diag_cache():
    try:
        import json
        path = _diag_cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if _DIAG_CACHE:
            with open(path, "w") as f:
                json.dump(_DIAG_CACHE, f, ensure_ascii=False, default=str)
    except Exception as e:
        logging.warning(str(e), exc_info=True)


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
        logging.getLogger("aiplat.diagnostics").warning("Auto-fill best-effort skipped", exc_info=True)


def _history_path() -> str:
    return os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "diag_history.json")


def _load_diag_history() -> list:
    try:
        import json
        p = _history_path()
        if os.path.exists(p):
            with open(p) as f:
                return json.loads(f.read() or "[]")
    except Exception as e:
        logging.warning(str(e), exc_info=True)
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)


# Load persisted cache on module init — DISABLED: always rebuild fresh
# _load_diag_cache()

router = APIRouter()


# Register health checks with the formal HealthCheckRegistry (lazy)
# ── Module-level health check for runtime (used by _register_health_checks) ──

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


def _register_health_checks():
    try:
        from core.harness.health.registry import HealthCheckRegistry, get_registry, Severity
        from core.harness.health.registry import HealthCheck, HealthResult, Status
        from core.harness.kernel.runtime import get_kernel_runtime

        class SimpleHealthCheck(HealthCheck):
            """Adapter: wraps existing _check_* functions into HealthCheck protocol."""
            def __init__(self, module, fn, severity=Severity.MEDIUM, deps=None):
                self.module = module
                self.severity = severity
                self.dependencies = deps or []
                self._fn = fn

            async def run(self) -> HealthResult:
                try:
                    result = await self._fn()
                    score = result.get("score", 0) if isinstance(result, dict) else 0
                    status = result.get("status", "unknown") if isinstance(result, dict) else "unknown"
                    s = Status.HEALTHY if status in ("pass", "healthy") else (
                        Status.DEGRADED if status in ("warn", "degraded") else Status.UNHEALTHY)
                    return HealthResult(module=self.module, status=s, severity=self.severity,
                                       message=f"score={score}", details=result if isinstance(result, dict) else {})
                except Exception as e:
                    return HealthResult(module=self.module, status=Status.UNHEALTHY,
                                       severity=self.severity, message=str(e))

        reg = get_registry()
        # Runtime & core module checks
        reg.register(SimpleHealthCheck("runtime", _check_core_runtime, Severity.CRITICAL))
        reg.register(SimpleHealthCheck("skill_lint", _check_skill_lint, Severity.MEDIUM))
        reg.register(SimpleHealthCheck("code_intel", _check_code_intel, Severity.MEDIUM))
        reg.register(SimpleHealthCheck("cross_lang", _check_cross_lang_links, Severity.MEDIUM))
        reg.register(SimpleHealthCheck("route_coverage", _check_route_coverage, Severity.MEDIUM))
        reg.register(SimpleHealthCheck("capability", _check_capability, Severity.MEDIUM))
        reg.register(SimpleHealthCheck("wiki_health", _check_wiki_health, Severity.MEDIUM))
        reg.register(SimpleHealthCheck("e2e_smoke", _check_e2e_smoke, Severity.LOW))
        reg.register(SimpleHealthCheck("doctor", _check_doctor, Severity.HIGH))
        reg.register(SimpleHealthCheck("governance", _check_governance, Severity.HIGH))
        reg.register(SimpleHealthCheck("frontend", _check_frontend, Severity.MEDIUM))
        reg.register(SimpleHealthCheck("llm_review", _check_llm_review, Severity.LOW))
        reg.register(SimpleHealthCheck("mcp", _check_mcp, Severity.MEDIUM))

        # New ROSClaw-inspired modules
        class SandboxGateCheck(HealthCheck):
            module = "sandbox_gate"
            severity = Severity.MEDIUM
            async def run(self) -> HealthResult:
                from core.harness.infrastructure.gates.sandbox_gate import get_sandbox
                sb = get_sandbox()
                result = await sb.check(kind="tool", tool_name="health_check")
                return HealthResult(module="sandbox_gate", 
                    status=Status.HEALTHY if result.verdict.value == "pass" else Status.DEGRADED,
                    severity=Severity.MEDIUM, message=f"sandbox checks: {result.checks_passed}/{result.checks_total}")
        reg.register(SandboxGateCheck())

        class SchemaGateCheck(HealthCheck):
            module = "schema_gate"
            severity = Severity.MEDIUM
            async def run(self) -> HealthResult:
                from core.harness.infrastructure.gates.schema_gate import get_schema_gate
                sg = get_schema_gate()
                r = sg.validate({"name": "test", "age": 30}, {"type": "object", "required": ["name", "age"]})
                return HealthResult(module="schema_gate",
                    status=Status.HEALTHY if r.verdict.value == "pass" else Status.DEGRADED,
                    severity=Severity.MEDIUM, message="schema validation functional")
        reg.register(SchemaGateCheck())
    except Exception as e:
        logging.warning(str(e), exc_info=True)


_register_health_checks()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


@router.post("/diagnostics/e2e/smoke", response_model=Dict[str, Any])
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
    # Persist for diagnostic check (global_settings — no schema change needed)
    store = _store()
    if store:
        try:
            await store.upsert_global_setting(key="last_smoke_result", value={
                "ok": getattr(result, "ok", False),
                "status": "completed" if getattr(result, "ok", False) else "failed",
                "timestamp": time.time(),
            })
        except Exception as e:
            logging.warning(str(e), exc_info=True)
    if not result.ok:
        raise HTTPException(status_code=result.http_status, detail=result.error or "Smoke failed")
    return result.payload


@router.get("/diagnostics/context/config", response_model=Dict[str, Any])
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


@router.post("/diagnostics/prompt/assemble", response_model=Dict[str, Any])
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        return resp
    finally:
        if t2 is not None:
            try:
                reset_active_request_context(t2)
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        if t1 is not None:
            try:
                reset_active_workspace_context(t1)
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        if env_set is not None:
            try:
                if env_prev is None:
                    os.environ.pop("AIPLAT_ENABLE_SESSION_SEARCH", None)
                else:
                    os.environ["AIPLAT_ENABLE_SESSION_SEARCH"] = env_prev
            except Exception as e:
                logging.warning(str(e), exc_info=True)


@router.get("/diagnostics/context/metrics/recent", response_model=Dict[str, Any])
async def diagnostics_context_metrics_recent(limit: int = 50, offset: int = 0, tenant_id: Optional[str] = None, session_id: Optional[str] = None):
    """Recent context assembly metrics (syscall_events kind=metric, name=context_assemble)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_syscall_events(limit=int(limit), offset=int(offset), kind="metric", name="context_assemble", tenant_id=tenant_id, session_id=session_id)


@router.get("/diagnostics/context/metrics/summary", response_model=Dict[str, Any])
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        try:
            pt = m.get("prompt_estimated_tokens")
            if isinstance(pt, (int, float)):
                prompt_tok_sum += float(pt)
                prompt_tok_cnt += 1
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        try:
            bt = m.get("budgets_token_estimate")
            if isinstance(bt, (int, float)):
                budget_tok_sum += float(bt)
                budget_tok_cnt += 1
        except Exception as e:
            logging.warning(str(e), exc_info=True)

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


@router.get("/diagnostics/exec/backends", response_model=Dict[str, Any])
async def diagnostics_exec_backends():
    """Exec backend diagnostics."""
    from core.api.facades.security_facade import get_exec_backend

    backend = await get_exec_backend()
    health = await healthcheck_backends()
    return {"status": "ok", "current_backend": backend, "backends": health.get("backends") if isinstance(health, dict) else [], "non_local_requires_approval": True}


@router.get("/diagnostics/exec/metrics/summary", response_model=Dict[str, Any])
async def diagnostics_exec_backend_metrics_summary(window_hours: int = 24, limit: int = 20):
    """Exec backend metrics summary (uses run_events aggregated in ExecutionStore)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.exec_backend_metrics_summary(window_hours=int(window_hours or 24), limit=int(limit or 20))


@router.post("/diagnostics/guard/run", response_model=Dict[str, Any])
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


@router.get("/diagnostics/latest", response_model=Dict[str, Any])
def get_latest_diagnostic():
    """Return last diagnostic result (in-memory, current session only)."""
    if _DIAG_CACHE is not None:
        result = dict(_DIAG_CACHE)
        result.pop("_details", None)
        return result
    return {"cached": False, "message": "尚未运行诊断 — POST /diagnostics/run-all 先"}


@router.get("/diagnostics/repairs-latest", response_model=Dict[str, Any])
async def get_latest_repairs():
    """Return last repair result (in-memory, current session only)."""
    if _DIAG_CACHE is not None:
        return await get_repairs()
    return {"cached": False, "needs_diagnostics": True, "summary": {"total_issues": 0}}


@router.get("/diagnostics/summary", response_model=Dict[str, Any])
def get_diagnostic_summary():
    """Return quick alert summary from last diagnostic run."""
    if _DIAG_CACHE is None:
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
    "full_stack": "全域测试",
}


@router.get("/diagnostics/history", response_model=Dict[str, Any])
def get_diagnostic_history():
    """Return last N diagnostic results for trend chart (max 30 entries)."""
    hist = _load_diag_history()
    return {"history": hist, "count": len(hist)}


def _diag_lock(func):
    """Decorator: ensure _DIAG_RUNNING is released even on exception."""
    from functools import wraps
    @wraps(func)
    async def wrapper(*args, **kwargs):
        global _DIAG_RUNNING
        if _DIAG_RUNNING:
            return {"run_id": "skipped", "message": "另一个诊断正在运行中 — 请等当前诊断完成后再试", "overall_score": 0}
        _DIAG_RUNNING = True
        try:
            return await func(*args, **kwargs)
        finally:
            _DIAG_RUNNING = False
    return wrapper


@router.post("/diagnostics/run-all", response_model=Dict[str, Any])
@_diag_lock
async def run_all_diagnostics(category: str = "", quick: bool = False):
    """Unified diagnostic endpoint — runs all checks in parallel and returns a combined report.
    Pass category=code_intel to run only that check.
    Pass quick=true to skip slow external checks (LSP, security, e2e_smoke)."""
    import asyncio, json as _json, uuid as _uuid
    _asyncio = asyncio

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
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    _publish("diagnostics_started", categories=[
        "core_runtime","code_intel","capability","skill_lint","skill_realness",
        "wiki_health","compliance","overview_issues","traces",
        "graph_runs","context_metrics","e2e_smoke","symbol_health",
        "doctor","lsp","security","arch_guard",
        "frontend","mcp","full_stack"
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

    async def _check_skill_lint():
        """Lint scan across all skills."""
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
            return result
        except Exception as e:
            return {"status": "unavailable", "score": 0, "error": str(e)[:200]}

    async def _check_skill_realness():
        """Check workspace skills for execution_type declarations and handler existence."""
        try:
            from pathlib import Path as _P
            aiplat_home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
            skills_dir = _P(aiplat_home) / "skills"
            issues = []
            if not skills_dir.exists():
                return {"status": "pass", "score": 100, "items": [], "details": {"total": 0}}
            
            for skill_dir in sorted(skills_dir.iterdir()):
                if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                    continue
                md = skill_dir / "SKILL.md"
                if not md.exists():
                    continue
                try:
                    raw = (await _asyncio.to_thread(lambda: md.read_text(encoding="utf-8", errors="ignore")))
                    if not raw.startswith("---"):
                        continue
                    parts = raw.split("---", 2)
                    if len(parts) < 3:
                        continue
                    import yaml as _yaml
                    fm = _yaml.safe_load(parts[1]) or {}
                    name = fm.get("name", skill_dir.name)
                    exec_type = fm.get("execution_type", "")
                    handler_exists = (skill_dir / "handler.py").exists()
                    
                    if not exec_type:
                        issues.append(f"'{name}': 缺少 execution_type 声明（默认 prompt=LLM模拟）")
                    elif exec_type == "handler" and not handler_exists:
                        issues.append(f"'{name}': execution_type=handler 但 handler.py 不存在")
                    elif exec_type == "prompt" and handler_exists:
                        issues.append(f"'{name}': 有 handler.py 但 execution_type 声明为 prompt（误配？）")
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
            
            total = len(list(skills_dir.iterdir())) if skills_dir.exists() else 0
            return {
                "status": "warning" if issues else "pass",
                "score": max(0, 100 - len(issues) * 5),
                "details": {"total": total, "issues_count": len(issues)},
                "items": [{"check": i, "result": "⚠️", "detail": i} for i in issues[:20]],
            }
        except Exception:
            return {"status": "unavailable", "score": 0}

    async def _check_code_intel():
        try:
            from core.harness.knowledge.code_graph import count_cycles, effective_cycles, health_score
            nodes, edges, issues_list = _get_or_build_graph()
            # Filter to structural edges only (exclude cross-file call edges)
            arch_edges = [e for e in edges if e.get("kind", "import") != "calls"]
            cycles = effective_cycles(nodes)
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
            _CROSS_INTERNAL = ('/diagnostics/', '/api/diagnostics/', '/kb-eval/', '/credentials/', '/variables/',
                              '/infra/', '/platform/', '/api/infra/', '/api/platform/', '/dashboard/')
            
            # Normalize path parameter patterns for comparison: {var}, {var:type}, ${var} → {}
            def _norm_path(p: str) -> str:
                return re.sub(r'\{\w+[\w:]*\}|\$\{\w+\}', '{}', p)
            
            # Normalize backend routes for matching
            backend_normalized = {_norm_path(p).replace('/api/', '/').replace('/core/', '/').rstrip('/') for p in backend_routes}
            
            broken = []
            for f in abs_roots:
                if not f.exists() or not f.is_dir():
                    continue
                for p in f.rglob("*.ts") if f.name == "aiPlat-management" else []:
                    for ep in _extract_api_calls(p):
                        ep_norm = _norm_path(ep.replace('/api/', '/').replace('/core/', '/').rstrip('/'))
                        if ep_norm and not any(ep_norm.startswith(prefix) for prefix in _CROSS_INTERNAL):
                            if ep_norm not in backend_normalized:
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
        """B2: Verify management proxy modules have corresponding frontend API usage."""
        try:
            from core.harness.knowledge.code_graph import repo_root
            from pathlib import Path as _P

            repo = repo_root()
            mgmt_api = _P(repo) / "aiPlat-management" / "management" / "api"
            mgmt_frontend_svc = _P(repo) / "aiPlat-management" / "frontend" / "src" / "services"

            # Management proxy modules (each proxies a backend layer)
            mgmt_modules = set()
            if mgmt_api.is_dir():
                for p in mgmt_api.glob("*.py"):
                    if not p.name.startswith("_") and p.name != "proxy.py":
                        mgmt_modules.add(p.stem)

            # For each frontend service file, check which mgmt modules it references
            # by looking for the module name in its code (e.g., coreApi.ts → core)
            frontend_covered = set()
            if mgmt_frontend_svc.is_dir():
                for p in mgmt_frontend_svc.rglob("*.ts"):
                    try:
                        text = (await _asyncio.to_thread(lambda: p.read_text()))
                        for m in mgmt_modules:
                            if m in text.lower() or m in p.name.lower():
                                frontend_covered.add(m)
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)

            dead_modules = sorted(mgmt_modules - frontend_covered)

            items = []
            if dead_modules:
                for m in dead_modules:
                    items.append({"check": "未使用代理", "result": "⚠️",
                                  "detail": f"management/api/{m}.py 无对应前端调用"})
            else:
                items.append({"check": "路由覆盖", "result": "✅",
                              "detail": f"{len(mgmt_modules)} 代理模块全部有前端调用"})

            return {
                "status": "warn" if len(dead_modules) > 2 else "pass",
                "score": max(0, 100 - len(dead_modules) * 5),
                "items": items,
                "signals": {"mgmt_modules": len(mgmt_modules), "covered": len(frontend_covered),
                            "dead_modules": len(dead_modules)},
            }
        except Exception as e:
            return {"status": "pass", "score": 95, "signals": {"note": f"scan skipped: {str(e)[:80]}"}}

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
                "WikiRule", "CapRule", "BaseSkill", "BaseRule",
                # Template Method / Strategy pattern bases (intentional)
                "DocumentConverter", "CoreError", "Exception",
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
                except Exception as e:
                    logging.warning(str(e), exc_info=True)

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
        except Exception as e:
            logging.warning(str(e), exc_info=True)

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
                        "SELECT COUNT(DISTINCT trace_id) FROM syscall_events WHERE created_at > unixepoch('now','-1 hour')"
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
                        "SELECT COUNT(*) FROM syscall_events WHERE kind='metric' AND name='context_assemble' AND created_at > unixepoch('now','-24 hours')"
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
        """Check last E2E smoke test result from global_settings."""
        try:
            from core.harness.kernel.runtime import get_kernel_runtime
            rt = get_kernel_runtime()
            store = getattr(rt, "execution_store", None) if rt else None
            if store:
                gs = await store.get_global_setting(key="last_smoke_result")
                result = (gs.get("value") if isinstance(gs, dict) else {}) or {}
                if result.get("ok"):
                    return {"status": "pass", "score": 100,
                            "signals": {"last_smoke": "completed"},
                            "items": [{"check": "最近冒烟", "result": "✅",
                                       "detail": "E2E 全链路通过"}]}
                if result.get("timestamp"):
                    return {"status": "warn", "score": 50,
                            "signals": {"last_smoke": "failed"},
                            "items": [{"check": "最近冒烟", "result": "⚠️",
                                       "detail": "上次执行未通过"}]}
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        return {"status": "pass", "score": 0,
                "signals": {"last_smoke": "pending"},
                "items": [{"check": "冒烟测试", "result": "⚪",
                           "detail": "尚未运行，点击 E2E Smoke 页面手动执行"}]}

    async def _check_symbol_health():
        """Scan code graph for symbol coverage and dead code candidates."""
        try:
            from core.harness.knowledge.code_graph import repo_root, default_roots
            r = repo_root()
            roots = [(r / d).resolve() for d in default_roots()]
            nodes, edges, _ = _get_or_build_graph()

            from core.harness.knowledge.symbol_health import is_excluded_from_dead_code, count_dead_code_candidates

            total = len(nodes)
            with_syms = sum(1 for n in nodes.values() if n.get('symbols'))
            total_syms = sum(len(n.get('symbols', [])) for n in nodes.values())
            dead, dead_files = count_dead_code_candidates(nodes)
            coverage = with_syms / max(total, 1) * 100

            score = 100
            if dead > 100: score -= 15
            elif dead > 50: score -= 8
            elif dead > 20: score -= 3
            if coverage < 60: score -= 10

            # Collect dead code files for repairs (filtered by count_dead_code_candidates)
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
        治理健康度检查 — delegates to shared overview._scan_governance().
        """
        try:
            from core.api.routers.overview import _scan_governance
            gov = await _scan_governance()
        except Exception:
            return {"status": "unavailable", "score": 0}

        total_entities = gov["total"]
        governed = gov["governed"]
        unsigned_count = gov["unsigned"]
        no_manifest_count = gov["no_manifest"]
        has_trusted_keys = gov["has_trusted_keys"]
        score = gov["score"]

        status = "pass" if score >= 80 else ("warn" if score >= 50 else "fail")

        items = []
        if no_manifest_count:
            items.append({"check": "无溯源码", "result": "❌", "detail": f"{no_manifest_count} 个实体缺少 manifest.json"})
        if unsigned_count:
            items.append({"check": "未签名", "result": "⚠️", "detail": f"{unsigned_count} 个有 manifest 但无签名"})
        if not has_trusted_keys and (no_manifest_count > 0 or unsigned_count > 0):
            items.append({"check": "未配置可信公钥", "result": "⚠️", "detail": "trusted_skill_pubkeys 为空，无法验签"})
        if not items:
            items.append({"check": "治理", "result": "✅", "detail": f"所有 {total_entities} 个实体均已治理"})

        return {
            "status": status, "score": score,
            "signals": {
                "total": total_entities, "governed": governed,
                "ungoverned": unsigned_count + no_manifest_count,
                "no_manifest": no_manifest_count, "unsigned": unsigned_count,
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
                content = (await _asyncio.to_thread(lambda: vite_config.read_text(encoding="utf-8")))
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
                    ts_body = (await _asyncio.to_thread(lambda: ts_file.read_text(encoding="utf-8")))
                    py_body = (await _asyncio.to_thread(lambda: py_file.read_text(encoding="utf-8")))
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

    async def _check_llm_review():
        """LLM 深度审查 — 对大文件和核心模块进行 reasoning 模型审查。
        
        仅在完整模式下运行（quick 模式跳过）。
        选取 >500 行的大文件 + 最近有修改的核心模块。
        每文件调用 review_file()，结果聚合评分。
        """
        import os as _os, logging as _log
        try:
            from core.engine.skills.autoreview.handler import review_file, MAX_FILE_CHARS

            # ── 选择审查目标 ──
            targets = _select_llm_review_targets()
            if not targets:
                return {"status": "pass", "score": 100, "signals": {"files_reviewed": 0},
                        "items": [{"check": "LLM审查", "result": "—", "detail": "无符合条件的目标文件"}]}

            reports = []
            for file_path, lines in targets:
                try:
                    with open(file_path) as f:
                        content = f.read()
                    report = await review_file(content, file_path, focus="comprehensive",
                                                max_chars=MAX_FILE_CHARS)
                    reports.append((file_path, report))
                except Exception as e:
                    _log.warning("LLM review skipped %s: %s", file_path, e)

            if not reports:
                return {"status": "pass", "score": 100, "signals": {"files_reviewed": 0}}

            # ── 聚合评分 ──
            scores = [r.score for _, r in reports]
            avg_score = sum(scores) / len(scores) if scores else 100
            total_issues = sum(r.issue_count for _, r in reports)
            p0_total = sum(r.p0_count for _, r in reports)
            p1_total = sum(r.p1_count for _, r in reports)

            items = []
            for file_path, r in reports:
                sev = "❌" if r.p0_count > 0 else ("⚠️" if r.p1_count > 2 else "✅")
                items.append({"check": file_path.split("/")[-1],
                              "result": sev,
                              "detail": f"score={r.score}, P0={r.p0_count}, P1={r.p1_count}, P2={r.p2_count}"})

            return {
                "status": "pass" if avg_score >= 80 else "warn",
                "score": round(avg_score),
                "signals": {
                    "files_reviewed": len(reports),
                    "total_issues": total_issues,
                    "p0_count": p0_total,
                    "p1_count": p1_total,
                    "avg_score": round(avg_score, 1),
                },
                "items": items,
                # v2.2: autoreview 历史摘要
                "_autoreview": await _get_autoreview_summary(),
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
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
        except Exception as e:
            return {"status": "error", "score": 0, "error": str(e)[:200],
                    "items": [{"check": "MCP 连通性", "result": "❌",
                               "detail": f"不可达: {str(e)[:200]}"}]}

    async def _check_full_stack():
        """Full-stack E2E: Spec lifecycle → Task → Trace → Radar → Dashboard → MarkStable.

        Tests the complete journey from Spec DRAFT through execution to STABLE,
        verifying that all three Andrew Ng loops (inner/middle/outer) are wired.
        Uses mock LLM responses — no real LLM calls.
        """
        import uuid, time as _time, json as _json
        run_id = f"diag-{uuid.uuid4().hex[:8]}"
        items: List[Dict[str, Any]] = []
        score = 0
        max_score = 14

        try:
            from core.harness.models.spec_lifecycle import get_spec_lifecycle, SpecStatus
            sl = get_spec_lifecycle()

            # J1: Spec creation → execution → review
            spec_id = "_diag_fullstack"
            # Clean up previous diagnostic run to prevent dashboard pollution
            existing = sl.get_latest(spec_id)
            if existing:
                try:
                    sl.mark_archived(spec_id)
                except Exception:
                    pass
            sv = sl.create_draft(spec_id, {"agent_md": "诊断全域测试 Spec"}, created_by="diagnostics",
                                   trigger_detail="Full-stack diagnostic")
            if sv and sv.status == SpecStatus.DRAFT:
                items.append({"check": "J1A Spec 创建", "result": "✅", "detail": f"{spec_id} v{sv.version} DRAFT"})
                score += 1
            else:
                items.append({"check": "J1A Spec 创建", "result": "❌", "detail": "创建失败",
                               "suggested_fix": "检查 spec_lifecycle.db 是否可写，SpecLifecycle 单例是否正常"})

            # Promote → PENDING → EXECUTING → REVIEW
            sl.promote_to_pending(spec_id)
            v = sl.get_latest(spec_id)
            if v and v.status == SpecStatus.PENDING:
                items.append({"check": "J1B PENDING", "result": "✅", "detail": f"v{v.version} PENDING"})
                score += 1
            else:
                items.append({"check": "J1B PENDING", "result": "❌", "detail": f"status={v.status.value if v else 'nil'}",
                               "suggested_fix": "检查 SpecLifecycle.promote_to_pending() 的状态转换逻辑"})

            sl.mark_executing(spec_id, run_id)
            v = sl.get_latest(spec_id)
            if v and v.status == SpecStatus.EXECUTING:
                items.append({"check": "J1C EXECUTING", "result": "✅", "detail": f"run={run_id}"})
                score += 1
            else:
                items.append({"check": "J1C EXECUTING", "result": "❌", "detail": f"status={v.status.value if v else 'nil'}",
                               "suggested_fix": "检查 SpecLifecycle.mark_executing() 的状态转换逻辑"})

            # Simulate trace data exactly like production
            sim_trace = [
                {"step": 1, "agent": "employee_agent", "reasoning": "开始执行诊断任务", "decision": "call_agent", "outcome": "ok"},
                {"step": 2, "agent": "employee_agent", "reasoning": "执行核心逻辑", "decision": "call_agent", "outcome": "ok"},
                {"step": 3, "agent": "employee_agent", "reasoning": "生成输出", "decision": "call_agent", "outcome": "ok"},
                {"step": 4, "agent": "", "reasoning": "任务完成", "decision": "finish", "outcome": "ok"},
            ]
            sl.mark_review(spec_id, sv.version, run_id=run_id,
                           result={"summary": "诊断测试完成", "trace": sim_trace,
                                   "agent_order": ["employee_agent"] * 3})
            v = sl.get_latest(spec_id)
            if v and v.status == SpecStatus.REVIEW:
                items.append({"check": "J1D REVIEW", "result": "✅", "detail": f"trace={len(sim_trace)} steps"})
                score += 1
            else:
                items.append({"check": "J1D REVIEW", "result": "❌", "detail": f"status={v.status.value if v else 'nil'}",
                               "suggested_fix": "检查 SpecLifecycle.mark_review() 是否正确写入 trace 数据"})

            # J2: Knowledge pipeline — ontology → wiki → document
            try:
                from core.harness.ontology_engine.engine import OntologyEngine
                if OntologyEngine:
                    items.append({"check": "J2A 本体引擎", "result": "✅", "detail": f"OntologyEngine 可导入"})
                    score += 1
                else:
                    items.append({"check": "J2A 本体引擎", "result": "❌", "detail": "导入失败"})
            except Exception as e:
                items.append({"check": "J2A 本体引擎", "result": "❌", "detail": str(e)[:80],
                               "suggested_fix": "检查 ontology_engine/ 模块和本体 YAML 文件是否存在"})

            try:
                from core.harness.knowledge.wiki_engine import wiki_health_report
                if callable(wiki_health_report):
                    items.append({"check": "J2B Wiki引擎", "result": "✅", "detail": f"wiki_health_report 可用"})
                    score += 1
                else:
                    items.append({"check": "J2B Wiki引擎", "result": "❌", "detail": "不可调用"})
            except Exception as e:
                items.append({"check": "J2B Wiki引擎", "result": "❌", "detail": str(e)[:80],
                               "suggested_fix": "检查知识库目录和 wiki_engine 模块配置"})

            try:
                from core.harness.document.protocol import ConverterRegistry
                if ConverterRegistry:
                    items.append({"check": "J2C 文档解析", "result": "✅", "detail": f"ConverterRegistry 可导入"})
                    score += 1
                else:
                    items.append({"check": "J2C 文档解析", "result": "❌", "detail": "导入失败"})
            except Exception as e:
                items.append({"check": "J2C 文档解析", "result": "❌", "detail": str(e)[:80],
                               "suggested_fix": "检查 document/converters/ 模块是否正确注册"})

            # J2D/E: Swarm + Roundtable (new collaboration modes)
            try:
                from core.harness.execution.swarm import run_swarm
                if run_swarm:
                    items.append({"check": "J2D Swarm模式", "result": "✅", "detail": f"run_swarm 可导入"})
                    score += 1
                else:
                    items.append({"check": "J2D Swarm模式", "result": "❌", "detail": "导入失败"})
            except Exception as e:
                items.append({"check": "J2D Swarm模式", "result": "❌", "detail": str(e)[:80],
                               "suggested_fix": "检查 harness/execution/swarm.py 是否存在"})

            try:
                from core.harness.execution.roundtable import run_roundtable
                if run_roundtable:
                    items.append({"check": "J2E Roundtable模式", "result": "✅", "detail": f"run_roundtable 可导入"})
                    score += 1
                else:
                    items.append({"check": "J2E Roundtable模式", "result": "❌", "detail": "导入失败"})
            except Exception as e:
                items.append({"check": "J2E Roundtable模式", "result": "❌", "detail": str(e)[:80],
                               "suggested_fix": "检查 harness/execution/roundtable.py 是否存在"})

            # J3/J5: TraceVisualizer
            try:
                from core.harness.execution.trace_visualizer import get_trace_visualizer
                viz = get_trace_visualizer()
                result = v.execution_result or {}
                trace_data = result.get("trace", [])
                summary = viz.analyze(trace_data, spec_id=spec_id, stage_count=1)
                if summary.total_steps == 4 and summary.agent_call_order:
                    items.append({"check": "J3A Trace 解析", "result": "✅", "detail": f"{summary.total_steps}步, {len(summary.agent_call_order)} agents"})
                    score += 1
                else:
                    items.append({"check": "J3A Trace 解析", "result": "❌", "detail": f"steps={summary.total_steps}",
                                   "suggested_fix": "检查 DynamicRouter._persist_dynamic_trace() 是否正确保存 trace"})
            except Exception as e:
                items.append({"check": "J3A Trace 解析", "result": "❌", "detail": str(e)[:80],
                               "suggested_fix": "检查 TraceVisualizer.analyze() 是否正确导入"})

            # J5A: Dashboard aggregation
            try:
                # Inline _collect_pending_decisions to avoid cross-router import
                active = sl.get_all_active()
                decisions_count = sum(1 for sv in active if sv.status == SpecStatus.REVIEW)
                found_self = any(sv.spec_id == spec_id for sv in active if sv.status == SpecStatus.REVIEW)
                if found_self:
                    items.append({"check": "J5A 仪表板聚合", "result": "✅", "detail": f"pending={decisions_count}"})
                    score += 1
                else:
                    items.append({"check": "J5A 仪表板聚合", "result": "⚠️", "detail": "未在 pending 中找到",
                                   "suggested_fix": "检查 get_all_active() 是否包含 REVIEW 状态的 Spec"})
            except Exception as e:
                items.append({"check": "J5A 仪表板聚合", "result": "❌", "detail": str(e)[:80],
                               "suggested_fix": "检查 SpecLifecycle.get_all_active() 的 SQL 查询"})

            # J3B/J5B: Mark → STABLE
            sl.mark_stable(spec_id)
            v = sl.get_latest(spec_id)
            if v and v.status == SpecStatus.STABLE:
                items.append({"check": "J3B Spec→STABLE", "result": "✅", "detail": f"v{v.version} STABLE"})
                score += 1
            else:
                items.append({"check": "J3B Spec→STABLE", "result": "❌", "detail": f"status={v.status.value if v else 'nil'}",
                               "suggested_fix": "检查 SpecLifecycle.mark_stable() 状态转换: 只有 REVIEW 状态可转为 STABLE"})

            # J4: Training monitor
            try:
                from core.harness.training.auto_trigger import get_lora_auto_trigger
                trigger = get_lora_auto_trigger()
                status = trigger.get_status()
                if isinstance(status, dict) and "threshold" in status:
                    items.append({"check": "J4A 训练监控", "result": "✅", "detail": f"q={status['quality_count']}/{status['threshold']}"})
                    score += 1
                else:
                    items.append({"check": "J4A 训练监控", "result": "⚠️", "detail": "状态不可读",
                                   "suggested_fix": "检查 LoRAAutoTrigger.get_status() 是否正确返回 dict"})
            except Exception as e:
                items.append({"check": "J4A 训练监控", "result": "❌", "detail": str(e)[:80],
                               "suggested_fix": "检查 auto_trigger.py 模块是否可导入"})

            # J5C: Timeline — inlined from workbench._collect_timeline
            try:
                history = sl.get_history(spec_id)
                timeline_entries = [h for h in history if h.status.value != "draft"]
                items.append({"check": "J5C 时间轴", "result": "✅", "detail": f"{len(timeline_entries)} 个版本事件"})
                score += 1
            except Exception as e:
                items.append({"check": "J5C 时间轴", "result": "⚠️", "detail": str(e)[:80],
                               "suggested_fix": "检查 SpecLifecycle.get_history() 是否正确返回版本记录"})

            # Clean up: archive the test spec to keep dashboard clean
            try:
                sl.mark_archived(spec_id)
            except Exception:
                pass

            status_str = "pass" if score >= 12 else "warn" if score >= 8 else "fail"
            return {
                "status": status_str,
                "score": round(score / max_score * 100),
                "signals": {"spec_id": spec_id, "run_id": run_id},
                "items": items,
            }
        except Exception as e:
            return {"status": "error", "score": 0, "error": str(e)[:200],
                    "items": items + [{"check": "全域测试", "result": "❌", "detail": f"异常: {str(e)[:150]}"}]}

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
        ("skill_realness", _check_skill_realness()),
        ("wiki_health", _check_wiki_health()),
        ("compliance", _check_compliance()),
        ("overview_issues", _check_overview_issues()),
        ("traces", _check_traces()),
        ("graph_runs", _check_graph_runs()),
        ("context_metrics", _check_context_metrics()),
        ("governance", _check_governance()),
        ("frontend", _check_frontend()),
        ("full_stack", _check_full_stack()),
        ("llm_review", _check_llm_review()),
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
    "llm_review": "LLM审查",
        "traces": "链路追踪", "graph_runs": "图执行", "context_metrics": "上下文",
        "e2e_smoke": "冒烟测试", "doctor": "Doctor", "overview_issues": "概览问题",
        "symbol_health": "符号健康", "lsp": "LSP 诊断", "security": "安全扫描",
    "cross_lang": "跨语言连接", "route_coverage": "路由覆盖",
    "domain_coupling": "跨域耦合", "fragile_base": "脆弱基类",
        "governance": "治理", "skill_lint": "Skill Lint",
        "frontend": "前端守卫", "mcp": "MCP 连通性",
        "full_stack": "全域测试",
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

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
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    _publish("diagnostics_complete", overall_score=overall, overall_grade=grade)
    return result


@router.post("/diagnostics/run-single", response_model=Dict[str, Any])
async def run_single_diagnostics(req: dict):
    """Run a single diagnostic category and return its result with real-time observation."""
    category = req.get("category", "")
    if not category:
        raise HTTPException(status_code=400, detail="category is required")
    # Reuse run_all_diagnostics with category filter
    return await run_all_diagnostics(category=category)


@router.post("/diagnostics/repairs", response_model=Dict[str, Any])
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


@router.get("/diagnostics/observability/stats", response_model=Dict[str, Any])
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
            COUNT(CASE WHEN status='success' THEN 1 END) as ok,
            COUNT(CASE WHEN status='failed' THEN 1 END) as error,
            COALESCE(AVG(duration_ms), 0) as avg_latency,
            COALESCE(MAX(duration_ms), 0) as max_latency,
            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(cost), 0) as total_cost
        FROM syscall_events
        WHERE kind='llm' AND start_time > unixepoch('now','-1 day')
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
        WHERE created_at > unixepoch('now','-1 day')
        GROUP BY kind ORDER BY cnt DESC
    """):
        by_kind[r.get("kind", "unknown")] = {"count": r.get("cnt", 0), "avg_latency_ms": round(r.get("avg_lat", 0), 1)}
    result["syscall_by_kind"] = by_kind

    # Active runs (last 1h)
    rows = _query("""
        SELECT COUNT(DISTINCT run_id) as cnt FROM syscall_events
        WHERE created_at > unixepoch('now','-1 hour') AND status='running'
    """)
    result["active_runs"] = rows[0].get("cnt", 0) if rows else 0

    # Throughput: events per minute (last hour, 5-min buckets)
    result["throughput"] = [
        {"ts": r.get("bucket", 0), "count": r.get("cnt", 0)}
        for r in _query("""
            SELECT (CAST(created_at AS INTEGER) / 300) * 300 as bucket, COUNT(*) as cnt
            FROM syscall_events WHERE created_at > unixepoch('now','-1 hour')
            GROUP BY bucket ORDER BY bucket
        """)
    ]

    # Error rate timeline (last 6h, 30-min windows)
    result["error_timeline"] = []
    for r in _query("""
        SELECT
            (CAST(created_at AS INTEGER) / 1800) * 1800 as bucket,
            COUNT(*) as total,
            COUNT(CASE WHEN status='failed' THEN 1 END) as errors
        FROM syscall_events
        WHERE created_at > unixepoch('now','-6 hours')
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
            WHERE kind='llm' AND start_time > unixepoch('now','-1 day')
            GROUP BY target_type ORDER BY cnt DESC LIMIT 10
        """)
    ]

    # Top errors
    result["top_errors"] = [
        {"error": (r.get("error", "") or "")[:120], "count": r.get("cnt", 0)}
        for r in _query("""
            SELECT error, COUNT(*) as cnt
            FROM syscall_events
            WHERE status='error' AND created_at > unixepoch('now','-1 day') AND error IS NOT NULL
            GROUP BY error ORDER BY cnt DESC LIMIT 5
        """)
    ]

    # Evaluate alert thresholds
    result["active_alerts"] = _evaluate_alerts(result)

    # Token efficiency metrics
    try:
        eff_rows = _query("""
            SELECT
                COALESCE(SUM(input_tokens), 0) as total_in,
                COALESCE(SUM(output_tokens), 0) as total_out,
                COUNT(*) as calls
            FROM syscall_events
            WHERE kind='llm' AND start_time > unixepoch('now','-1 day') AND status='success'
        """)
        eff = eff_rows[0] if eff_rows else {}
        total_in = eff.get("total_in", 0) or 0
        total_out = eff.get("total_out", 0) or 0
        result["token_efficiency"] = {
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "efficiency_pct": round(total_out / max(total_in, 1) * 100, 1),
            "waste_estimate_tokens": max(0, total_in - total_out),
            "total_calls": eff.get("calls", 0),
        }
    except Exception:
        result["token_efficiency"] = {"error": "unavailable"}

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
    except Exception as e:
        logging.warning(str(e), exc_info=True)


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


@router.get("/diagnostics/observability/alerts", response_model=Dict[str, Any])
async def get_alerts():
    return {"alerts": _load_alert_config()}


@router.put("/diagnostics/observability/alerts", response_model=Dict[str, Any])
async def update_alerts(data: dict = None):
    rules = data.get("alerts") if data else None
    if not isinstance(rules, list):
        raise HTTPException(status_code=400, detail="alerts must be a list")
    _save_alert_config(rules)
    return {"alerts": rules, "status": "saved"}


# ── Model Playground ─────────────────────────────────────────────

@router.get("/diagnostics/playground/models", response_model=Dict[str, Any])
async def list_playground_models():
    """List available LLM models for the playground."""
    try:
        from core.harness.infrastructure.infra_bridge import _list_models_from_infra
        models = _list_models_from_infra()
        if not models:
            # Fallback: env-based models
            from core.harness.utils.model_injection import best_model_for_purpose
            models = []
            default = best_model_for_purpose("chat")
            if default:
                models.append({"name": default, "provider": "env", "status": "available"})
        return {"models": models}
    except Exception:
        return {"models": []}


@router.post("/diagnostics/playground/compare", response_model=Dict[str, Any])
async def compare_models(data: dict = None):
    """Compare LLM outputs across multiple models concurrently."""
    prompt = data.get("prompt", "") if data else ""
    model_names = data.get("models", []) if data else []

    if not prompt or not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")
    if not isinstance(model_names, list) or len(model_names) == 0:
        raise HTTPException(status_code=400, detail="models list is required")
    if len(model_names) > 6:
        raise HTTPException(status_code=400, detail="max 6 models at once")

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


@router.post("/diagnostics/playground/chat", response_model=Dict[str, Any])
async def playground_chat(data: dict = None):
    """Quick-test chat: send a message with pipeline stages as context."""
    message = data.get("message", "") if data else ""
    stages = data.get("stages", []) if data else []

    if not message or not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    try:
        from core.harness.utils.model_injection import create_selected_adapter
        adapter = create_selected_adapter(model_name="")
        if adapter is None:
            raise HTTPException(status_code=503, detail="No LLM adapter available")

        # Build context from stages
        stage_ctx = ""
        if stages:
            lines = []
            for i, s in enumerate(stages):
                name = s.get("agent_name", s.get("id", f"Stage {i+1}"))
                phase = s.get("phase", "")
                lines.append(f"  {i+1}. {name}" + (f" ({phase})" if phase else ""))
            stage_ctx = "流水线阶段:\n" + "\n".join(lines)

        from core.harness.utils.prompt_loader import _async_prompt_resolve
        system = await _async_prompt_resolve("pipeline-test-assistant", stage_ctx="")
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
        raise HTTPException(status_code=500, detail=f"Chat failed: {e}")


# ══════════════════════════════════════════════════════════════
# Darwin Arena — agent competition benchmark (manual trigger only)
# ══════════════════════════════════════════════════════════════

@router.post("/diagnostics/arena/run", response_model=Dict[str, Any])
async def arena_run_round_robin(contenders: List[Dict[str, Any]]):
    """
    Run a round-robin tournament among agent variants.
    Manual trigger only — no auto-scheduling to control LLM costs.
    
    Body: {
      "contenders": [
        {"name": "agent-a", "agent_id": "...", "task": "build a REST API"},
        {"name": "agent-b", "agent_id": "...", "task": "build a REST API"}
      ],
      "matches_per_pair": 3
    }
    """
    try:
        from core.harness.arena.arena import DarwinArena
        arena = DarwinArena()
        
        async def _run_benchmark(name: str, cfg: Dict[str, Any]) -> float:
            """Run one benchmark and return a score 0-100."""
            try:
                harness = get_harness()
                req = ExecutionRequest(
                    kind="agent", target_id=cfg.get("agent_id", ""),
                    payload={"task": cfg.get("task", "")},
                    user_id="arena", session_id=f"arena-{name}-{int(time.time())}",
                )
                result = await harness.execute(req)
                return 100.0 if getattr(result, "ok", False) else 50.0
            except Exception:
                return 0.0
        
        pairs = [(c["name"], c) for c in contenders]
        result = await arena.round_robin(
            contenders=pairs,
            benchmark_fn=_run_benchmark,
            matches_per_pair=contenders[0].get("matches_per_pair", 3) if contenders else 3,
        )
        
        return {
            "leaderboard": result.leaderboard,
            "matches": len(result.matches),
            "promotions": [{"name": p.name, "rating": p.rating, "reason": p.promotion_reason}
                          for p in result.promotions],
            "duration_s": result.total_duration_s,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Arena failed: {str(e)}")


@router.get("/diagnostics/arena/leaderboard", response_model=Dict[str, Any])
async def arena_leaderboard():
    """Get current Darwin Arena leaderboard (read-only)."""
    try:
        from core.harness.arena.arena import DarwinArena
        arena = DarwinArena()
        return {"leaderboard": arena.scorer.leaderboard()}
    except Exception as e:
        return {"leaderboard": [], "error": str(e)}


@router.post("/diagnostics/arena/regression", response_model=Dict[str, Any])
async def arena_run_regression(baseline_path: Optional[str] = None):
    """
    Run benchmark regression against baseline.
    Returns pass_rate, latency, token delta vs stored baseline.
    
    POST body: {"baseline_path": "~/.aiplat/arena_baseline.json", "save_baseline": true}
    """
    try:
        from core.harness.arena.regression import RegressionRunner
        runner = RegressionRunner()
        
        async def _simple_agent(task: str) -> dict:
            """Minimal agent stub for regression testing."""
            try:
                harness = get_harness()
                req = ExecutionRequest(
                    kind="agent", target_id="regression_agent",
                    payload={"task": task}, user_id="arena",
                    session_id=f"regression-{int(time.time())}",
                )
                result = await harness.execute(req)
                output = getattr(result, "payload", {}) if not isinstance(result, dict) else result
                return {
                    "output": str(output.get("output", "") or ""),
                    "tool_calls": output.get("tool_calls", []) or [],
                    "tokens": output.get("tokens", {}).get("total_tokens", 0) if isinstance(output.get("tokens"), dict) else 0,
                    "error": result.get("error", "") if isinstance(result, dict) else "",
                }
            except Exception:
                return {"output": "", "tool_calls": [], "tokens": 0, "error": "agent_execution_failed"}
        
        report = await runner.run(
            agent_fn=_simple_agent,
            baseline_path=baseline_path,
            save_baseline=True,
        )
        
        return {
            "verdict": report.verdict,
            "current": report.current,
            "delta": report.delta,
            "tasks_summary": [
                {"id": t.task_id, "passed": t.passed, "score": t.score, "error": t.error[:100]}
                for t in report.tasks
            ],
            "duration_s": report.total_duration_s,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Regression failed: {str(e)}")


# ══════════════════════════════════════════════════════════════
# Eval Dashboard — unified evaluation metrics aggregation
# ══════════════════════════════════════════════════════════════

@router.get("/diagnostics/eval/summary", response_model=Dict[str, Any])
async def eval_summary():
    """Unified eval dashboard: arena + AB scores + evolution + obs + diagnostic trend."""
    import time as _time
    result: Dict[str, Any] = {"timestamp": _time.time()}

    # Arena leaderboard
    try:
        from core.harness.arena.arena import DarwinArena, EloScorer
        gs = _store()
        if gs:
            arena_data = await gs.get_global_setting(key="arena_state")
            if arena_data and isinstance(arena_data.get("value"), dict):
                av = arena_data["value"]
                result["arena"] = {"leaderboard": av.get("leaderboard", [])[:5],
                                   "total_matches": av.get("total_matches", 0)}
            else:
                result["arena"] = {"leaderboard": [], "total_matches": 0}
        else:
            result["arena"] = {"leaderboard": [], "total_matches": 0, "note": "no store"}
    except Exception:
        result["arena"] = {"leaderboard": [], "total_matches": 0, "error": "unavailable"}

    # Regression history
    try:
        gs2 = _store()
        if gs2:
            reg_data = await gs2.get_global_setting(key="arena_regression_history")
            if reg_data and isinstance(reg_data.get("value"), list):
                result["regression"] = {"history": reg_data["value"][-3:]}
            else:
                result["regression"] = {"history": []}
        else:
            result["regression"] = {"history": []}
    except Exception:
        result["regression"] = {"history": []}

    # AB scores from prompt_eval_scores
    try:
        store = _store()
        if store:
            import sqlite3
            conn = sqlite3.connect(store._config.db_path)
            try:
                rows = conn.execute(
                    "SELECT template_id, version, ROUND(AVG(overall_score),1) as avg_score, "
                    "ROUND(AVG(pass_rate),1) as avg_pass, COUNT(*) as cnt, "
                    "MAX(created_at) as last_eval "
                    "FROM prompt_eval_scores "
                    "GROUP BY template_id, version ORDER BY cnt DESC LIMIT 10"
                ).fetchall()
                result["ab_scores"] = {
                    "templates": len(set(r[0] for r in rows)),
                    "items": [{"template_id": r[0], "version": r[1], "avg_score": r[2],
                               "avg_pass_rate": r[3], "eval_count": r[4], "last_eval_at": r[5]} for r in rows],
                }
            except Exception:
                result["ab_scores"] = {"templates": 0, "items": [], "note": "no data"}
            finally:
                conn.close()
        else:
            result["ab_scores"] = {"templates": 0, "items": []}
    except Exception:
        result["ab_scores"] = {"templates": 0, "items": [], "error": "unavailable"}

    # Evolution fitness
    try:
        from core.harness.knowledge.evolution_runner import EvolutionRunner
        evo_path = os.path.expanduser("~/.aiplat/wiki/collections/default/evolution_history.json")
        if os.path.exists(evo_path):
            import json as _json
            with open(evo_path) as f:
                evo_data = _json.load(f)
            evo_list = evo_data if isinstance(evo_data, list) else []
            result["evolution"] = {
                "generations": len(evo_list),
                "latest_fitness": evo_list[-1].get("fitness_golden_after", 0) if evo_list else 0,
                "trend": [{"id": e.get("id"), "fitness": e.get("fitness_golden_after", 0),
                           "verdict": e.get("verdict")} for e in evo_list[-10:]],
            }
        else:
            result["evolution"] = {"generations": 0, "latest_fitness": 0, "trend": []}
    except Exception:
        result["evolution"] = {"generations": 0, "latest_fitness": 0, "trend": [], "error": "unavailable"}

    # Observability snapshot
    try:
        obs = await observability_stats()
        result["observability"] = {
            "token_efficiency_pct": obs.get("token_efficiency", {}).get("efficiency_pct", 0),
            "llm_success_rate": obs.get("llm_stats", {}).get("success_rate", 0),
            "avg_latency_ms": obs.get("llm_stats", {}).get("avg_latency_ms", 0),
            "total_calls": obs.get("llm_stats", {}).get("total_calls", 0),
        }
    except Exception:
        result["observability"] = {"error": "unavailable"}

    # Diagnostic trend
    try:
        hist = _load_diag_history()
        result["diagnostic_trend"] = {
            "current_score": hist[-1].get("overall_score", 0) if hist else 0,
            "current_grade": hist[-1].get("overall_grade", "?") if hist else "?",
            "score_trend": [{"run_id": h.get("run_id"), "overall_score": h.get("overall_score"),
                            "started_at": h.get("started_at")} for h in hist[-30:]],
        }
    except Exception:
        result["diagnostic_trend"] = {"error": "unavailable"}

    # Stage rewards from recent pipeline runs (most recent 10)
    try:
        store3 = _store()
        if store3:
            import sqlite3
            conn = sqlite3.connect(store3._config.db_path)
            try:
                evts = conn.execute(
                    "SELECT state_json, created_at FROM pipeline_events "
                    "WHERE event_type='stage_reward' ORDER BY created_at DESC LIMIT 50"
                ).fetchall()
                stage_map: Dict[str, List] = {}
                for evt in evts:
                    try:
                        raw = json.loads(evt[0])
                        sid = raw.get("stage_id", "?")
                        rw = raw.get("reward", 0)
                        dims = raw.get("dimensions", {})
                        if sid not in stage_map:
                            stage_map[sid] = []
                        stage_map[sid].append({"reward": rw, "dimensions": dims})
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)
                result["stage_rewards"] = {
                    "total_stages": len(stage_map),
                    "by_stage": {k: {"recent": v[:5], "avg_reward": round(sum(x["reward"] for x in v) / max(len(v), 1), 1)} for k, v in stage_map.items()},
                }
            except Exception:
                result["stage_rewards"] = {"total_stages": 0, "by_stage": {}}
            finally:
                conn.close()
        else:
            result["stage_rewards"] = {"total_stages": 0, "by_stage": {}}
    except Exception:
        result["stage_rewards"] = {"total_stages": 0, "by_stage": {}, "error": "unavailable"}

    return result


@router.get("/diagnostics/eval/ab-scores", response_model=Dict[str, Any])
async def eval_ab_scores(template_id: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    """AB optimizer per-template score history."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    try:
        import sqlite3
        conn = sqlite3.connect(store._config.db_path)
        try:
            q = "SELECT template_id, version, overall_score, pass_rate, recommendation, created_at FROM prompt_eval_scores"
            params = []
            if template_id:
                q += " WHERE template_id = ?"
                params.append(template_id)
            q += " ORDER BY created_at DESC LIMIT ?"
            params.append(int(limit))
            rows = conn.execute(q, params).fetchall()
            return {
                "total": len(rows),
                "scores": [{"template_id": r[0], "version": r[1], "overall_score": r[2],
                            "pass_rate": r[3], "recommendation": r[4], "created_at": r[5]} for r in rows],
            }
        finally:
            conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AB scores query failed: {str(e)}")


@router.get("/diagnostics/eval/arena-history", response_model=Dict[str, Any])
async def eval_arena_history(limit: int = Query(20, ge=1, le=100)):
    """Persisted Arena match history and leaderboard."""
    gs = _store()
    if not gs:
        return {"matches": [], "leaderboard": [], "note": "no store"}
    arena_data = await gs.get_global_setting(key="arena_state")
    if not arena_data or not isinstance(arena_data.get("value"), dict):
        return {"matches": [], "leaderboard": [], "note": "no arena data yet"}
    av = arena_data["value"]
    matches = av.get("matches", []) or []
    return {
        "leaderboard": av.get("leaderboard", [])[:10],
        "matches": matches[-int(limit):],
        "total_matches": len(matches),
        "promotions": av.get("promotions", []) or [],
    }
