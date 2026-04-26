from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from core.api.deps.rbac import actor_from_http
from core.harness.integration import get_harness
from core.harness.kernel.types import ExecutionRequest
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas import DiagnosticsPromptAssembleRequest
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
    from core.apps.exec_drivers.registry import get_exec_backend, healthcheck_backends

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
