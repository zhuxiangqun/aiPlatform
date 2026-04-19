"""
Diagnostics API
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any, Optional

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


def _links_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    """将 links 聚合结果压缩为面板友好的摘要信息。"""
    resolved = payload.get("resolved") if isinstance(payload.get("resolved"), dict) else {}
    trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else None
    executions = payload.get("executions") if isinstance(payload.get("executions"), dict) else None
    graph_runs = payload.get("graph_runs") if isinstance(payload.get("graph_runs"), dict) else None
    run = payload.get("run") if isinstance(payload.get("run"), dict) else None
    lineage = payload.get("lineage") if isinstance(payload.get("lineage"), list) else []

    agent_execs = (executions.get("items", {}).get("agent_executions") if executions else None) or []
    skill_execs = (executions.get("items", {}).get("skill_executions") if executions else None) or []
    runs = (graph_runs.get("runs") if graph_runs else None) or []

    return {
        "trace_id": resolved.get("trace_id"),
        "run_id": resolved.get("run_id"),
        "trace_status": trace.get("status") if trace else None,
        "execution_counts": {
            "agents": len(agent_execs),
            "skills": len(skill_execs),
            "total": len(agent_execs) + len(skill_execs),
        },
        "graph_run_counts": {
            "total": int(graph_runs.get("total", 0) if graph_runs else 0),
            "returned": len(runs),
        },
        "lineage_depth": len(lineage),
        "lineage_root_run_id": (lineage[-1].get("run_id") if lineage and isinstance(lineage[-1], dict) else (run.get("run_id") if run else None)),
        "actions": {
            "can_resume": bool(run and run.get("run_id")),
            "has_trace": bool(resolved.get("trace_id")),
        },
    }


@router.get("/health/{layer}")
async def get_layer_health(layer: str, request: Request) -> Dict[str, Any]:
    """获取指定层级健康状态
    
    Args:
        layer: 层级名称 (infra, core, platform, app)
    
    Returns:
        健康状态
    """
    health_checkers = request.app.state.health_checkers
    if layer not in health_checkers:
        raise HTTPException(status_code=404, detail=f"Layer '{layer}' not found")
    
    checker = health_checkers[layer]
    health = await checker.get_health()
    
    return health


@router.get("/health/all")
async def get_all_health(request: Request) -> Dict[str, Dict[str, Any]]:
    """获取所有层级健康状态
    
    Returns:
        所有层级的健康状态
    """
    health_checkers = request.app.state.health_checkers
    all_health = {}
    
    for layer, checker in health_checkers.items():
        health = await checker.get_health()
        all_health[layer] = health
    
    return all_health


@router.get("/health")
async def list_available_checks(request: Request) -> Dict[str, Any]:
    """列出可用的健康检查
    
    Returns:
        可用的健康检查列表
    """
    health_checkers = request.app.state.health_checkers
    return {
        "layers": list(health_checkers.keys()),
        "description": {
            "infra": "Infrastructure layer health checks",
            "core": "Core AI layer health checks",
            "platform": "Platform services health checks",
            "app": "Application layer health checks"
        }
    }


@router.post("/check/{layer}")
async def run_layer_diagnosis(layer: str, request: Request) -> Dict[str, Any]:
    """运行层级诊断
    
    Args:
        layer: 层级名称 (infra, core, platform, app)
    
    Returns:
        诊断结果
    """
    health_checkers = request.app.state.health_checkers
    if layer not in health_checkers:
        raise HTTPException(status_code=404, detail=f"Layer '{layer}' not found")
    
    checker = health_checkers[layer]
    results = await checker.check()
    
    # 统计状态
    status_counts = {"healthy": 0, "degraded": 0, "unhealthy": 0}
    for result in results:
        status_counts[result.status.value] += 1
    
    # 整体状态
    if status_counts["unhealthy"] > 0:
        overall_status = "unhealthy"
    elif status_counts["degraded"] > 0:
        overall_status = "degraded"
    else:
        overall_status = "healthy"
    
    return {
        "layer": layer,
        "overall_status": overall_status,
        "status_counts": status_counts,
        "checks": [
            {
                "component": r.component,
                "status": r.status.value,
                "message": r.message,
                "details": r.details
            }
            for r in results
        ]
    }


@router.get("/trace/{layer}")
async def get_layer_trace(
    layer: str,
    request: Request,
    trace_id: Optional[str] = None,
    execution_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """获取层级链路追踪
    
    Args:
        layer: 层级名称 (infra, core, platform, app)
    
    Returns:
        链路追踪数据
    """
    health_checkers = request.app.state.health_checkers
    if layer not in health_checkers:
        raise HTTPException(status_code=404, detail=f"Layer '{layer}' not found")

    # 目前仅对 core 层提供可用闭环：ExecutionStore traces/spans/executions
    if layer != "core":
        return {"layer": layer, "supported": False, "message": "Tracing is supported for core layer only (for now)."}

    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")

    # Priority: execution_id -> trace, trace_id -> trace, else list traces
    if execution_id:
        trace = await core_client.get_trace_by_execution(execution_id)
        return {"layer": "core", "supported": True, "trace": trace, "mode": "by_execution_id", "execution_id": execution_id}

    if trace_id:
        trace = await core_client.get_trace(trace_id)
        executions = await core_client.list_executions_by_trace(trace_id, limit=limit, offset=offset)
        return {
            "layer": "core",
            "supported": True,
            "trace": trace,
            "executions": executions,
            "mode": "by_trace_id",
            "trace_id": trace_id,
            "limit": limit,
            "offset": offset,
        }

    traces = await core_client.list_traces(limit=limit, offset=offset)
    return {"layer": "core", "supported": True, "traces": traces, "mode": "list", "limit": limit, "offset": offset}


@router.get("/system")
async def get_system_overview(request: Request) -> Dict[str, Any]:
    """获取系统概览
    
    Returns:
        系统概览
    """
    health_checkers = request.app.state.health_checkers
    overview = {
        "overall_status": "healthy",
        "layers": {},
        "summary": {
            "total_layers": 4,
            "healthy_layers": 0,
            "degraded_layers": 0,
            "unhealthy_layers": 0
        }
    }
    
    for layer, checker in health_checkers.items():
        health = await checker.get_health()
        overview["layers"][layer] = health
        
        if health["status"] == "healthy":
            overview["summary"]["healthy_layers"] += 1
        elif health["status"] == "degraded":
            overview["summary"]["degraded_layers"] += 1
            overview["overall_status"] = "degraded"
        elif health["status"] == "unhealthy":
            overview["summary"]["unhealthy_layers"] += 1
            overview["overall_status"] = "unhealthy"
    
    return overview


# ==================== E2E Smoke (full-chain) ====================


@router.post("/e2e/smoke")
async def run_e2e_smoke(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trigger a production-grade full-chain smoke test.

    - For CI: call this endpoint and fail the pipeline if ok=false.
    - For ops: can be triggered manually; schedule is handled by core Jobs (kind=smoke_e2e).
    """
    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")
    return await core_client.run_e2e_smoke(body or {})


# ==================== Doctor (one-shot report) ====================


@router.get("/doctor")
async def doctor_report(request: Request) -> Dict[str, Any]:
    """
    One-shot diagnostics report (MVP).

    Aggregates:
    - health (infra/core/platform/app)
    - core adapters summary
    - autosmoke env hints (best-effort)
    """
    import os
    import time

    # Health summary
    health_checkers = request.app.state.health_checkers
    health = {}
    for layer, checker in health_checkers.items():
        try:
            health[layer] = await checker.get_health()
        except Exception as e:
            health[layer] = {"status": "unhealthy", "message": str(e)}

    core_client = getattr(request.app.state, "core_client", None)

    # Core adapters summary
    adapters = {"adapters": [], "total": 0}
    try:
        if core_client:
            adapters = await core_client.list_adapters(limit=50, offset=0)
    except Exception:
        pass

    # Autosmoke config: env overrides first, otherwise fall back to core global_settings(key="autosmoke")
    core_autosmoke_cfg: Dict[str, Any] = {}
    try:
        if core_client:
            st = await core_client.get_onboarding_state()
            if isinstance(st, dict) and isinstance(st.get("autosmoke"), dict):
                core_autosmoke_cfg = st.get("autosmoke") or {}
    except Exception:
        core_autosmoke_cfg = {}

    env_enabled = os.getenv("AIPLAT_AUTOSMOKE_ENABLED")
    env_enforce = os.getenv("AIPLAT_AUTOSMOKE_ENFORCE")
    env_dedup = os.getenv("AIPLAT_AUTOSMOKE_DEDUP_SECONDS")
    env_webhook = os.getenv("AIPLAT_AUTOSMOKE_WEBHOOK_URL")

    autosmoke = {
        "enabled": env_enabled if env_enabled is not None else core_autosmoke_cfg.get("enabled"),
        "enforce": env_enforce if env_enforce is not None else core_autosmoke_cfg.get("enforce"),
        "dedup_seconds": env_dedup if env_dedup is not None else core_autosmoke_cfg.get("dedup_seconds"),
        "webhook_url_set": bool(env_webhook) or bool(core_autosmoke_cfg.get("webhook_url")),
        "source": {"env_override": bool(env_enabled or env_enforce or env_dedup or env_webhook), "core_setting": core_autosmoke_cfg},
    }
    # Secrets status (best-effort)
    secrets: Dict[str, Any] = {}
    try:
        if core_client:
            secrets = await core_client.get_secrets_status()
    except Exception:
        secrets = {}

    # Strong gate status (default tenant)
    strong_gate: Dict[str, Any] = {"tenant_id": "default", "enabled": False}
    try:
        if core_client:
            tp = await core_client.get_tenant_policy("default")
            policy = tp.get("policy") if isinstance(tp, dict) else None
            tool_policy = policy.get("tool_policy") if isinstance(policy, dict) else None
            approval_tools = (
                tool_policy.get("approval_required_tools")
                if isinstance(tool_policy, dict) and isinstance(tool_policy.get("approval_required_tools"), list)
                else []
            )
            enabled = "*" in [str(x) for x in approval_tools]
            strong_gate = {
                "tenant_id": "default",
                "enabled": bool(enabled),
                "policy_version": tp.get("version"),
                "approval_required_tools": approval_tools,
            }
    except Exception:
        pass

    links = {
        "onboarding_ui": "/onboarding",
        "diagnostics_smoke_ui": "/diagnostics/smoke",
        "tenant_policies_ui": "/diagnostics/policies",
        "doctor_api": "/api/diagnostics/doctor",
        "run_e2e_smoke_api": "/api/diagnostics/e2e/smoke",
    }
    # Doctor Actions: use action_type (frontend executes by allowlist).
    # Keep api_url for backward compatibility.
    actions = {
        "toggle_strong_gate": {
            "action_type": "onboarding.strong_gate",
            "method": "POST",
            "api_url": "/api/onboarding/strong-gate",
            "body_example": {"tenant_id": "default", "enabled": False, "require_approval": True},
        },
        "migrate_secrets": {
            "action_type": "onboarding.secrets_migrate",
            "method": "POST",
            "api_url": "/api/onboarding/secrets/migrate",
            "body_example": {"require_approval": True},
        },
        "enable_autosmoke": {
            "action_type": "onboarding.autosmoke",
            "method": "POST",
            "api_url": "/api/onboarding/autosmoke",
            "body_example": {"enabled": True, "enforce": True, "require_approval": True},
        },
    }
    config = {
        "management_public_url": os.getenv("AIPLAT_MANAGEMENT_PUBLIC_URL"),
        "autosmoke_webhook_url": os.getenv("AIPLAT_AUTOSMOKE_WEBHOOK_URL"),
    }

    recs = []
    if not autosmoke["enabled"]:
        recs.append({"severity": "warn", "code": "autosmoke_disabled", "message": "建议开启 AIPLAT_AUTOSMOKE_ENABLED=true 以获得自动验证闭环"})
    if autosmoke["enabled"] and not autosmoke["enforce"]:
        recs.append({"severity": "info", "code": "autosmoke_gate_off", "message": "如需强门禁，开启 AIPLAT_AUTOSMOKE_ENFORCE=true"})
    if autosmoke["enabled"] and not autosmoke["webhook_url_set"]:
        recs.append({"severity": "info", "code": "autosmoke_no_alerts", "message": "如需失败告警，设置 AIPLAT_AUTOSMOKE_WEBHOOK_URL"})

    layers = ["infra", "core", "platform", "app"]
    unhealthy = [k for k in layers if (health.get(k, {}).get("status") != "healthy")]
    if unhealthy:
        recs.append({"severity": "error", "code": "unhealthy_layers", "message": f"存在不健康层：{','.join(unhealthy)}；建议先修复 health 再跑 smoke"})

    if (adapters or {}).get("total", 0) <= 0:
        recs.append({"severity": "warn", "code": "no_adapters", "message": "尚未配置任何 LLM adapter；请先在初始化向导配置模型 Provider/API Key"})

    if not config["management_public_url"]:
        recs.append({"severity": "info", "code": "missing_public_url", "message": "建议设置 AIPLAT_MANAGEMENT_PUBLIC_URL，用于生成可点击诊断/重跑链接"})

    # If autosmoke is disabled, provide an action using config center (env still can override).
    if not autosmoke["enabled"]:
        recs.append(
            {
                "severity": "info",
                "code": "autosmoke_enable_action",
                "message": "可在配置中心开启 autosmoke（需审批）；若已使用 env 管理，也可忽略此项。",
                "links": {"onboarding_ui": "/onboarding"},
                "actions": {"enable_autosmoke": actions["enable_autosmoke"]},
            }
        )

    # If secrets still stored in plaintext, recommend migration.
    try:
        if isinstance(secrets, dict) and int(secrets.get("plaintext") or 0) > 0:
            if secrets.get("encryption_configured"):
                recs.append(
                    {
                        "severity": "warn",
                        "code": "plaintext_secrets_detected",
                        "message": "检测到 adapters.api_key 仍存在明文存储，建议执行一键迁移到加密列（需审批）。",
                        "links": {"onboarding_ui": "/onboarding"},
                        "actions": {"migrate_secrets": actions["migrate_secrets"]},
                    }
                )
            else:
                recs.append(
                    {
                        "severity": "warn",
                        "code": "plaintext_secrets_and_no_key",
                        "message": "检测到 adapters.api_key 存在明文且未配置 AIPLAT_SECRET_KEY；建议先配置密钥后再迁移。",
                        "links": {"onboarding_ui": "/onboarding"},
                    }
                )
    except Exception:
        pass

    if strong_gate.get("enabled"):
        recs.append(
            {
                "severity": "warn",
                "code": "strong_gate_enabled",
                "message": "default tenant 已启用强门禁（所有工具需审批）。如为误开启，可在 Onboarding 或 Tenant Policies 页面一键解除。",
                "links": {"onboarding_ui": "/onboarding", "tenant_policies_ui": "/diagnostics/policies"},
                "actions": {"disable_strong_gate": actions["toggle_strong_gate"]},
            }
        )

    return {
        "generated_at": time.time(),
        "health": health,
        "adapters": adapters,
        "autosmoke": autosmoke,
        "secrets": secrets,
        "strong_gate": strong_gate,
        "config": config,
        "links": links,
        "actions": actions,
        "recommendations": recs,
    }


@router.get("/graphs/{layer}")
async def list_layer_graph_runs(
    layer: str,
    request: Request,
    graph_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    获取图执行列表（管理面聚合入口）。

    目前仅支持 core 层（aiPlat-core ExecutionStore）。
    """
    health_checkers = request.app.state.health_checkers
    if layer not in health_checkers:
        raise HTTPException(status_code=404, detail=f"Layer '{layer}' not found")

    if layer != "core":
        return {"layer": layer, "supported": False, "message": "Graph runs are supported for core layer only (for now)."}

    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")

    runs = await core_client.list_graph_runs(limit=limit, offset=offset, graph_name=graph_name, status=status)
    return {"layer": "core", "supported": True, "runs": runs}


@router.get("/syscalls/{layer}")
async def list_layer_syscalls(
    layer: str,
    request: Request,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    kind: Optional[str] = None,
    name: Optional[str] = None,
    status: Optional[str] = None,
    error_contains: Optional[str] = None,
    approval_request_id: Optional[str] = None,
    span_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """List syscall events (core layer only for now)."""
    health_checkers = request.app.state.health_checkers
    if layer not in health_checkers:
        raise HTTPException(status_code=404, detail=f"Layer '{layer}' not found")

    if layer != "core":
        return {"layer": layer, "supported": False, "message": "Syscall events are supported for core layer only (for now)."}

    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")

    items = await core_client.list_syscall_events(
        limit=limit,
        offset=offset,
        trace_id=trace_id,
        run_id=run_id,
        kind=kind,
        name=name,
        status=status,
        error_contains=error_contains,
        approval_request_id=approval_request_id,
        span_id=span_id,
    )
    return {"layer": "core", "supported": True, "syscalls": items, "limit": limit, "offset": offset}


@router.get("/syscalls/{layer}/stats")
async def get_layer_syscall_stats(
    layer: str,
    request: Request,
    window_hours: int = 24,
    top_n: int = 10,
    kind: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregated syscall stats (core layer only for now)."""
    health_checkers = request.app.state.health_checkers
    if layer not in health_checkers:
        raise HTTPException(status_code=404, detail=f"Layer '{layer}' not found")

    if layer != "core":
        return {"layer": layer, "supported": False, "message": "Syscall stats are supported for core layer only (for now)."}

    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")

    stats = await core_client.get_syscall_stats(window_hours=window_hours, top_n=top_n, kind=kind)
    return {"layer": "core", "supported": True, "stats": stats}


@router.get("/graphs/{layer}/{run_id}")
async def get_layer_graph_run(
    layer: str,
    run_id: str,
    request: Request,
    include_checkpoints: bool = True,
    checkpoints_limit: int = 50,
    checkpoints_offset: int = 0,
) -> Dict[str, Any]:
    """
    获取单次图执行与 checkpoints（管理面聚合入口）。
    """
    health_checkers = request.app.state.health_checkers
    if layer not in health_checkers:
        raise HTTPException(status_code=404, detail=f"Layer '{layer}' not found")

    if layer != "core":
        return {"layer": layer, "supported": False, "message": "Graph run details are supported for core layer only (for now)."}

    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")

    run = await core_client.get_graph_run(run_id)
    if not include_checkpoints:
        return {"layer": "core", "supported": True, "run": run}

    checkpoints = await core_client.list_graph_checkpoints(run_id, limit=checkpoints_limit, offset=checkpoints_offset)
    return {
        "layer": "core",
        "supported": True,
        "run": run,
        "checkpoints": checkpoints,
        "checkpoints_limit": checkpoints_limit,
        "checkpoints_offset": checkpoints_offset,
    }


@router.post("/graphs/{layer}/{run_id}/resume")
async def resume_layer_graph_run(layer: str, run_id: str, request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    从 checkpoint 恢复（仅建档，不继续执行）。

    目前仅支持 core 层，透传到：
    POST /api/core/graphs/runs/{run_id}/resume
    """
    health_checkers = request.app.state.health_checkers
    if layer not in health_checkers:
        raise HTTPException(status_code=404, detail=f"Layer '{layer}' not found")

    if layer != "core":
        return {"layer": layer, "supported": False, "message": "Resume is supported for core layer only (for now)."}

    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")

    payload = body or {}
    resumed = await core_client.resume_graph_run(run_id, payload)
    return {"layer": "core", "supported": True, "resumed": resumed}


@router.post("/graphs/{layer}/{run_id}/resume/execute")
async def resume_and_execute_layer_graph_run(layer: str, run_id: str, request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    从 checkpoint 恢复并继续执行（闭环）。

    目前仅支持 core 层，透传到：
    POST /api/core/graphs/runs/{run_id}/resume/execute
    """
    health_checkers = request.app.state.health_checkers
    if layer not in health_checkers:
        raise HTTPException(status_code=404, detail=f"Layer '{layer}' not found")

    if layer != "core":
        return {"layer": layer, "supported": False, "message": "Resume/execute is supported for core layer only (for now)."}

    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")

    payload = body or {}
    result = await core_client.resume_and_execute_graph_run(run_id, payload)
    return {"layer": "core", "supported": True, "result": result}


@router.get("/links/{layer}")
async def get_layer_links(
    layer: str,
    request: Request,
    trace_id: Optional[str] = None,
    execution_id: Optional[str] = None,
    run_id: Optional[str] = None,
    graph_run_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    lineage_depth: int = 3,
    include_spans: bool = False,
) -> Dict[str, Any]:
    """
    联动查询入口（设计正确：management 聚合展示）。

    core 支持：
    - execution_id -> trace -> executions -> graph_runs(trace_id)（若存在）
    - trace_id -> trace -> executions -> graph_runs(trace_id)
    - run_id -> graph_run(trace_id) -> trace -> executions
    """
    health_checkers = request.app.state.health_checkers
    if layer not in health_checkers:
        raise HTTPException(status_code=404, detail=f"Layer '{layer}' not found")
    if layer != "core":
        return {"layer": layer, "supported": False, "message": "Links are supported for core layer only (for now)."}

    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")

    resolved_trace_id = trace_id
    resolved_run_id = run_id or graph_run_id

    if execution_id:
        t = await core_client.get_trace_by_execution(execution_id)
        resolved_trace_id = t.get("trace_id") if isinstance(t, dict) else resolved_trace_id

    run = None
    lineage = []
    if resolved_run_id:
        run = await core_client.get_graph_run(resolved_run_id)
        # Prefer explicit column trace_id, fallback to metadata.trace_id
        resolved_trace_id = run.get("trace_id") or ((run.get("initial_state") or {}).get("metadata") or {}).get("trace_id") or resolved_trace_id
        # lineage chain (best effort)
        cur = run
        for _ in range(max(0, int(lineage_depth))):
            parent = cur.get("parent_run_id") if isinstance(cur, dict) else None
            if not parent:
                break
            try:
                parent_run = await core_client.get_graph_run(parent)
                lineage.append(parent_run)
                cur = parent_run
            except Exception:
                break

    trace = None
    executions = None
    graph_runs = None
    if resolved_trace_id:
        try:
            trace = await core_client.get_trace(resolved_trace_id)
            if not include_spans and isinstance(trace, dict) and "spans" in trace:
                # 默认不返回 spans，避免 payload 过大；需要时由 include_spans=true 打开
                trace = {**trace}
                trace.pop("spans", None)
        except Exception:
            trace = None
        try:
            executions = await core_client.list_executions_by_trace(resolved_trace_id, limit=limit, offset=offset)
        except Exception:
            executions = None
        try:
            graph_runs = await core_client.list_graph_runs(limit=limit, offset=offset, trace_id=resolved_trace_id)
        except Exception:
            graph_runs = None

    return {
        "layer": "core",
        "supported": True,
        "query": {"trace_id": trace_id, "execution_id": execution_id, "run_id": run_id, "graph_run_id": graph_run_id, "include_spans": include_spans},
        "resolved": {"trace_id": resolved_trace_id, "run_id": resolved_run_id},
        "trace": trace,
        "executions": executions,
        "graph_runs": graph_runs,
        "run": run,
        "lineage": lineage,
        "limit": limit,
        "offset": offset,
    }


@router.get("/links/{layer}/ui")
async def get_layer_links_ui(
    layer: str,
    request: Request,
    trace_id: Optional[str] = None,
    execution_id: Optional[str] = None,
    run_id: Optional[str] = None,
    graph_run_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    lineage_depth: int = 3,
    include_spans: bool = False,
) -> Dict[str, Any]:
    """
    Frontend/UI 友好版本：字段裁剪 + 汇总 + 行为提示。
    - 仍保持设计原则：management 仅做聚合/转发，不实现业务逻辑。
    """
    full = await get_layer_links(  # type: ignore[misc]
        layer=layer,
        request=request,
        trace_id=trace_id,
        execution_id=execution_id,
        run_id=run_id,
        graph_run_id=graph_run_id,
        limit=limit,
        offset=offset,
        lineage_depth=lineage_depth,
        include_spans=include_spans,
    )
    if not full.get("supported"):
        return full

    return {
        "layer": full.get("layer"),
        "supported": True,
        "summary": _links_summary(full),
        # minimal payload for UI list rendering
        "trace": full.get("trace"),
        "executions": full.get("executions"),
        "graph_runs": full.get("graph_runs"),
        "run": full.get("run"),
        "lineage": full.get("lineage"),
    }
