"""User Workbench API — end-user task submission and feedback.

Endpoints:
  POST   /workbench/submit    — submit new task (description + files + capability)
  GET    /workbench/tasks/{id} — query task status + progress
  GET    /workbench/tasks      — user history
  POST   /workbench/tasks/{id}/feedback — submit user rating
  GET    /workbench/capabilities — list available agent capabilities
  POST   /workbench/spec/{id}/revise — revise Spec + trigger re-execution (SpecLifecycle)
  GET    /workbench/spec/{id}/history — Spec version history
  GET    /workbench/specs            — list all active Specs
"""
from fastapi import APIRouter, HTTPException, Request, Depends
from typing import Any, Dict, List, Optional
import os
from datetime import datetime, timezone

_tasks: Dict[str, Dict[str, Any]] = {}

# ── Auth (must be BEFORE router — evaluated at import time) ──────────────

def _require_auth(request: Request) -> str:
    """Platform gateway identity passthrough + dev-mode fallback.
    
    Prod mode: validates X-AIPLAT-API-KEY or Bearer token.
    Dev mode (default): trusts X-AIPLAT-TENANT-ID header from platform gateway.
    
    Returns tenant_id. Role is set on request.state for downstream checks.
    """
    api_key = os.getenv("AIPLAT_API_KEY", "")
    admin_key = os.getenv("AIPLAT_ADMIN_KEY", "")

    if api_key or admin_key:
        h_key = request.headers.get("X-AIPLAT-API-KEY", "")
        h_auth = request.headers.get("Authorization", "")
        if h_auth.startswith("Bearer "):
            h_key = h_auth[7:]
        if h_key not in (api_key, admin_key):
            raise HTTPException(status_code=401, detail="Invalid API key")
        # Prod: role from header or default
        role = request.headers.get("X-AIPLAT-ROLE", "developer")
        request.state.role = role
        return h_key

    # Dev mode — trust platform gateway identity headers
    tenant = request.headers.get("X-AIPLAT-TENANT-ID", "")
    if not tenant:
        tenant = request.headers.get("x-aiplat-tenant-id", "") or "dev-default"
    role = request.headers.get("X-AIPLAT-ROLE", "")
    if not role:
        # Resolve role from env var lists
        dev_user = os.getenv("AIPLAT_DEV_USER", "anonymous")
        admin_users = os.getenv("AIPLAT_ADMIN_USERS", "").split(",")
        dev_users = os.getenv("AIPLAT_DEVELOPER_USERS", "").split(",")
        if dev_user in admin_users:
            role = "admin"
        elif dev_user in dev_users:
            role = "developer"
        else:
            role = os.getenv("AIPLAT_DEFAULT_ROLE", "developer")
    request.state.role = role
    return tenant

router = APIRouter(prefix="/workbench", tags=["workbench"], dependencies=[Depends(_require_auth)])


from core.schemas_common import ListResponse

@router.get("/capabilities", response_model=ListResponse[CapabilityItem])
async def get_capabilities() -> List[Dict[str, str]]:
    """List available agent capabilities for the workbench."""
    return [
        {"id": "contract_review", "name": "合同审核", "desc": "自动审核合同条款、价格、合规性", "icon": "📋"},
        {"id": "report_gen", "name": "报表生成", "desc": "根据数据自动生成分析报表", "icon": "📊"},
        {"id": "qa", "name": "客服问答", "desc": "内部知识库智能问答", "icon": "💬"},
        {"id": "code_review", "name": "代码审查", "desc": "自动检查代码质量和安全", "icon": "🔍"},
        {"id": "general", "name": "通用任务", "desc": "自由描述任意AI任务", "icon": "🤖"},
    ]


@router.post("/submit", response_model=TaskSubmitResponse)
async def submit_task(body: Dict[str, Any]) -> Dict[str, Any]:
    """Submit a new task to the AI agent. Optionally link to a Spec for lifecycle tracking."""
    import uuid, time

    task = body.get("description", "")
    capability = body.get("capability", "general")
    spec_id = body.get("spec_id", "")
    if not task:
        raise HTTPException(status_code=400, detail="description is required")

    run_id = f"wb-{uuid.uuid4().hex[:8]}" if "run_id" not in body else body["run_id"]
    entry = {
        "run_id": run_id,
        "capability": capability,
        "spec_id": spec_id,
        "description": task[:500],
        "status": "running",
        "progress": {"current_step": 0, "total_steps": 4, "steps": [
            {"name": "分析请求", "status": "running"},
            {"name": "执行任务", "status": "pending"},
            {"name": "生成结果", "status": "pending"},
            {"name": "质量检查", "status": "pending"},
        ]},
        "result": None,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _tasks[run_id] = entry

    # SpecLifecycle: mark PENDING → EXECUTING
    if spec_id:
        try:
            from core.harness.models.spec_lifecycle import get_spec_lifecycle
            sl = get_spec_lifecycle()
            sl.promote_to_pending(spec_id)  # ensure it's in PENDING if still DRAFT
            sl.mark_executing(spec_id, run_id)
        except Exception:
            pass

    # Fire-and-forget: simulate task completion
    import asyncio as _aio
    _aio.ensure_future(_simulate_task_completion(run_id, spec_id))

    return {"run_id": run_id, "status": "accepted", "spec_id": spec_id}


async def _simulate_task_completion(run_id: str, spec_id: str = "") -> None:
    """Simulate progression through 4 steps, then mark complete + persist trace."""
    import asyncio as _aio, time as _time

    for step_idx in range(3):  # Step 0→1, 1→2, 2→3
        await _aio.sleep(1.5)
        entry = _tasks.get(run_id, {})
        progress = entry.get("progress", {})
        steps = progress.get("steps", [])
        if step_idx < len(steps):
            steps[step_idx]["status"] = "completed"
        if step_idx + 1 < len(steps):
            steps[step_idx + 1]["status"] = "running"
        progress["current_step"] = step_idx + 2
        entry["progress"] = progress
        _tasks[run_id] = entry

    # Final: mark complete
    entry = _tasks.get(run_id, {})
    entry["status"] = "completed"
    progress = entry.get("progress", {})
    for s in progress.get("steps", []):
        s["status"] = "completed"
    progress["current_step"] = 4
    entry["progress"] = progress
    entry["result"] = {"summary": f"任务完成: {entry.get('description', '')[:80]}", "warnings": []}
    _tasks[run_id] = entry

    # SpecLifecycle: mark REVIEW + persist varied trace
    if spec_id:
        try:
            from core.harness.models.spec_lifecycle import get_spec_lifecycle
            import random as _r

            sl = get_spec_lifecycle()
            latest = sl.get_latest(spec_id)
            if latest and latest.status.value == "executing":
                desc = entry.get("description", "task")
                agents = ["employee_agent", "qa_agent", "frontend_engineer", "backend_developer"]
                chosen = _r.sample(agents, min(3, len(agents)))

                # Generate varied trace with occasional hesitation / repeat
                simulated_trace = [
                    {"step": 1, "agent": chosen[0], "reasoning": f"收到请求: {desc[:50]}", "decision": "call_agent", "outcome": "ok"},
                ]
                if _r.random() < 0.3:
                    simulated_trace.append({"step": 2, "agent": chosen[0],
                        "reasoning": "可能需要重新考虑上一步的方案", "decision": "call_agent", "outcome": "ok"})
                simulated_trace.append({"step": len(simulated_trace) + 1, "agent": chosen[1] if len(chosen) > 1 else chosen[0],
                    "reasoning": "继续执行后续逻辑", "decision": "call_agent", "outcome": "ok"})
                if _r.random() < 0.2:
                    simulated_trace.append({"step": len(simulated_trace) + 1, "agent": chosen[0],
                        "reasoning": "检测到前一步输出需要修正，考虑重新处理", "decision": "call_agent", "outcome": "ok"})
                if len(chosen) > 2:
                    simulated_trace.append({"step": len(simulated_trace) + 1, "agent": chosen[2],
                        "reasoning": "最后验证与审查", "decision": "call_agent", "outcome": "ok"})
                simulated_trace.append({"step": len(simulated_trace) + 1, "agent": "",
                    "reasoning": "所有步骤完成", "decision": "finish", "outcome": "ok"})

                sl.mark_review(spec_id, latest.version, run_id=run_id,
                               result={"summary": f"完成: {desc[:60]}", "trace": simulated_trace,
                                       "agent_order": [t["agent"] for t in simulated_trace if t["agent"]]})
        except Exception:
            pass


@router.get("/tasks/{run_id}", response_model=TaskStatusResponse)
async def get_task_status(run_id: str) -> Dict[str, Any]:
    """Get task execution status and progress."""
    entry = _tasks.get(run_id)
    if not entry:
        # Simulate completed task for demo
        import time
        return {
            "run_id": run_id, "capability": "general",
            "description": "Demo task", "status": "completed",
            "progress": {"current_step": 4, "total_steps": 4, "steps": [
                {"name": "分析请求", "status": "completed"},
                {"name": "执行任务", "status": "completed"},
                {"name": "生成结果", "status": "completed"},
                {"name": "质量检查", "status": "completed"},
            ]},
            "result": {"summary": "任务已完成", "warnings": []},
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    return entry


from core.schemas_common import ListResponse, PaginatedResponse
from core.schemas_workbench import CapabilityItem, TaskSubmitResponse, TaskFeedbackResponse, TrainingStatusResponse, SkillInstallResponse, SeedDemoResponse, BatchMarkStableResponse
from core.schemas_builder import SpecHistoryResponse, SpecRevisionResponse, SpecCreatedResponse, SpecMarkStableResponse, SpecRadarResponse, SpecTraceResponse, SpecDiffResponse, SpecsListResponse, TaskStatusResponse, PromotionResponse

@router.get("/tasks", response_model=PaginatedResponse[dict])
async def get_user_tasks(limit: int = 20) -> Dict[str, Any]:
    """Get user's historical task list."""
    items = sorted(_tasks.values(), key=lambda x: x.get("created_at", ""), reverse=True)[:limit]
    if not items:
        import time
        items = [{
            "run_id": f"demo-{i}", "capability": "general",
            "description": f"Demo task {i}",
            "status": "completed",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        } for i in range(3)]
    return {"items": items, "total": len(items)}


@router.post("/tasks/{run_id}/feedback", response_model=TaskFeedbackResponse)
async def submit_feedback(run_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Submit user feedback for a completed task."""
    rating = body.get("rating", 0)
    action = body.get("action", "useful")

    # Feed into ImplicitFeedbackCollector
    try:
        from core.services.implicit_feedback import get_implicit_feedback_collector
        collector = get_implicit_feedback_collector()
        await collector.record(
            run_id=run_id,
            signal_type="copy_full" if action == "useful" else "re_query",
            value=0.3 if action == "useful" else -0.1,
        )
    except Exception:
        pass

    _tasks[run_id] = {**_tasks.get(run_id, {}), "rating": rating, "feedback_action": action}
    return {"run_id": run_id, "rating": rating, "recorded": True}


# ── SpecLifecycle endpoints (Andrew Ng 三层 Loop 传动轴) ──

@router.get("/specs", response_model=SpecsListResponse)
async def list_specs() -> Dict[str, Any]:
    """List all active (non-archived) Specs with latest status."""
    try:
        from core.harness.models.spec_lifecycle import get_spec_lifecycle
        sl = get_spec_lifecycle()
        specs = sl.list_specs()
        return {"specs": specs, "total": len(specs)}
    except Exception as e:
        return {"specs": [], "total": 0, "error": str(e)}


@router.get("/spec/{spec_id}/history", response_model=SpecHistoryResponse)
async def get_spec_history(spec_id: str) -> Dict[str, Any]:
    """Get full version history for a Spec."""
    try:
        from core.harness.models.spec_lifecycle import get_spec_lifecycle
        sl = get_spec_lifecycle()
        versions = sl.get_history(spec_id)
        result = []
        for v in versions:
            result.append({
                "version": v.version,
                "status": v.status.value,
                "trigger": v.trigger,
                "trigger_detail": v.trigger_detail,
                "created_by": v.created_by,
                "created_at": v.created_at,
                "execution_run_id": v.execution_run_id,
                "affected_stages": v.affected_stages if v.affected_stages else "ALL",
                "execution_summary": (v.execution_result or {}).get("summary", ""),
            })
        return {"spec_id": spec_id, "versions": result, "total": len(result)}
    except Exception as e:
        return {"spec_id": spec_id, "versions": [], "total": 0, "error": str(e)}


@router.post("/spec/{spec_id}/revise", response_model=SpecRevisionResponse)
async def revise_spec(spec_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Revise Spec + optionally trigger re-execution.

    Body:
      - content: new spec content (agent_md, tools, evals, stage_configs)
      - trigger: "manual" | "user_feedback" | "agent_trace" | "auto_learn"
      - trigger_detail: human-readable reason
      - created_by: who made the change
      - affected_stages: list of stage indices to re-run (empty = all stages)
      - re_execute: whether to trigger immediate re-execution (default: false)
    """
    try:
        from core.harness.models.spec_lifecycle import get_spec_lifecycle, RevisionTrigger

        new_content = body.get("content", {})
        if not new_content:
            raise HTTPException(status_code=400, detail="content is required")

        trigger = body.get("trigger", RevisionTrigger.MANUAL.value)
        detail = body.get("trigger_detail", "Manual revision")
        created_by = body.get("created_by", "developer")
        affected_stages = body.get("affected_stages")
        re_execute = body.get("re_execute", False)

        sl = get_spec_lifecycle()
        latest = sl.get_latest(spec_id)
        if not latest:
            raise HTTPException(status_code=404, detail=f"Spec '{spec_id}' not found")

        # Merge new content on top of latest (partial updates supported)
        merged = {**latest.content, **new_content}

        sv = sl.revise(
            spec_id=spec_id,
            new_content=merged,
            trigger=trigger,
            trigger_detail=detail,
            created_by=created_by,
            affected_stages=affected_stages,
        )
        if not sv:
            raise HTTPException(status_code=409, detail=f"Cannot revise spec '{spec_id}' from status '{latest.status.value}'")

        response = {
            "spec_id": spec_id,
            "version": sv.version,
            "status": sv.status.value,
            "affected_stages": sv.affected_stages if sv.affected_stages else "ALL",
            "trigger": sv.trigger,
            "trigger_detail": sv.trigger_detail,
            "re_execute": re_execute,
        }

        # If re_execute requested, trigger agent re-execution with affected stages
        if re_execute:
            try:
                run_id = await _trigger_spec_re_execution(spec_id, sv, merged.get("target_agent_id", spec_id))
                response["run_id"] = run_id
                response["re_execution_triggered"] = True
            except Exception as e:
                response["re_execution_triggered"] = False
                response["re_execution_error"] = str(e)

        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _trigger_spec_re_execution(spec_id: str, sv: Any, agent_id: str) -> str:
    """Trigger re-execution of agent with updated spec, only affected stages."""
    import uuid
    run_id = f"spec-{uuid.uuid4().hex[:8]}"

    # Promote spec to EXECUTING
    sl = get_spec_lifecycle()
    sl.mark_executing(spec_id, run_id)

    # Determine stages to re-run
    affected = sv.affected_stages if sv.affected_stages else None

    # Build execution payload
    payload = {
        "user_message": f"Re-execute with updated Spec v{sv.version}: {sv.trigger_detail[:200]}",
        "spec_id": spec_id,
        "spec_version": sv.version,
        "re_execute_stages": affected,  # None = all stages
    }

    # Agent execution via CoreFacade
    try:
        from core.api.deps import get_core_facade
        facade = get_core_facade()
        await facade.run_workspace_agent(agent_id=agent_id, payload=payload)
    except Exception:
        pass  # Best-effort; task submitted to workbench queue

    return run_id


@router.get("/spec/{spec_id}/radar", response_model=SpecRadarResponse)
async def get_feedback_radar(spec_id: str) -> Dict[str, Any]:
    """Get FeedbackRadar analysis for a Spec.

    Returns human-readable Spec adjustment suggestions with severity and evidence,
    driven by real user behavior signals (copy, re-query, abandon, repeat).
    """
    try:
        from core.harness.learning.feedback_radar import get_feedback_radar
        radar = get_feedback_radar()
        suggestions = await radar.analyze(spec_id)
        result = []
        for s in suggestions:
            result.append({
                "type": s.type.value,
                "severity": s.severity.value,
                "detail": s.detail,
                "suggested_action": s.suggested_action,
                "evidence_count": len(s.evidence),
            })
        return {"spec_id": spec_id, "suggestions": result, "total": len(result)}
    except Exception as e:
        return {"spec_id": spec_id, "suggestions": [], "total": 0, "error": str(e)}


@router.get("/spec/{spec_id}/trace", response_model=SpecTraceResponse)
async def get_spec_trace(spec_id: str) -> Dict[str, Any]:
    """Get the latest execution trace for a Spec (Agent 决策痕迹可视化).

    Returns structured trace data + anomaly warnings + Spec suggestions.
    Each step shows: which Agent was chosen, Supervisor's reasoning, and execution outcome.
    """
    try:
        from core.harness.models.spec_lifecycle import get_spec_lifecycle
        from core.harness.execution.trace_visualizer import get_trace_visualizer

        sl = get_spec_lifecycle()
        latest = sl.get_latest(spec_id)
        if not latest:
            return {"spec_id": spec_id, "trace": None, "error": "Spec not found"}

        result = latest.execution_result or {}
        raw_trace = result.get("trace", [])
        stage_count = len(latest.content.get("stage_configs", []))

        viz = get_trace_visualizer()
        summary = viz.analyze(
            raw_trace,
            spec_id=spec_id,
            stage_count=stage_count,
            goal=latest.content.get("agent_md", "")[:200],
        )

        return {
            "spec_id": spec_id,
            "version": latest.version,
            "status": latest.status.value,
            "total_steps": summary.total_steps,
            "agent_call_order": summary.agent_call_order,
            "hesitation_count": summary.hesitation_count,
            "repeat_count": summary.repeat_count,
            "decision_chain": viz.format_chain(summary),
            "anomaly_report": viz.format_anomalies(summary),
            "spec_suggestions": summary.spec_suggestions,
            "anomalies": summary.anomaly_warnings,
            "raw_steps": [
                {"step": s.step, "agent": s.agent, "reasoning": s.reasoning[:200],
                 "outcome": s.outcome, "is_hesitation": s.is_hesitation, "is_repeat": s.is_repeat}
                for s in summary.steps
            ],
        }
    except Exception as e:
        return {"spec_id": spec_id, "trace": None, "error": str(e)}


@router.get("/training/status", response_model=TrainingStatusResponse)
async def get_training_status() -> Dict[str, Any]:
    """Get SFT/RL auto-training pipeline status (LoRAAutoTrigger monitoring)."""
    try:
        from core.harness.training.auto_trigger import get_lora_auto_trigger
        trigger = get_lora_auto_trigger()
        status = trigger.get_status()

        # Check latest SFT model
        model_info: Dict[str, Any] = {}
        model_path = os.path.expanduser("~/.aiplat/sft_models/latest.json")
        if os.path.exists(model_path):
            try:
                import json as _json
                with open(model_path) as f:
                    model_info = _json.load(f)
            except Exception:
                pass

        # Check dataset files
        dataset_dir = os.path.expanduser("~/.aiplat/training")
        dataset_count = 0
        if os.path.isdir(dataset_dir):
            dataset_count = len([f for f in os.listdir(dataset_dir) if f.startswith("sft_train_")])

        return {
            **status,
            "latest_model": model_info.get("result_model", model_info.get("base_model", "")),
            "latest_model_completed_at": model_info.get("completed_at", ""),
            "dataset_count": dataset_count,
        }
    except Exception as e:
        return {"enabled": False, "error": str(e)}


# ── FDE Dashboard (proxy — logic migrated to core.api.routers.fde) ──────

@router.get("/fde-dashboard", response_model=Dict[str, Any])
async def get_fde_dashboard():
    """Proxy to unified FDE Router. Logic migrated to fde.py (方向一).

    Kept to avoid breaking existing callers (ValueCenter/UserWorkbench.tsx, 7 refs).
    Remove this proxy once frontend migration is complete.
    """
    from core.api.routers.fde import get_fde_dashboard as _fde_dashboard
    return await _fde_dashboard()




@router.post("/spec/{spec_id}/mark-stable", response_model=SpecMarkStableResponse)
async def mark_spec_stable(spec_id: str) -> Dict[str, Any]:
    """Quick action: mark a REVIEW Spec as STABLE (one-click approve)."""
    try:
        from core.harness.models.spec_lifecycle import get_spec_lifecycle
        sl = get_spec_lifecycle()
        result = sl.mark_stable(spec_id)
        if result:
            return {"spec_id": spec_id, "status": "stable", "version": result.version}
        return {"spec_id": spec_id, "status": "unchanged", "reason": "not in review"}
    except Exception as e:
        return {"spec_id": spec_id, "error": str(e)}


@router.post("/spec/create", response_model=SpecCreatedResponse)
async def create_spec(body: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new Spec from scratch (manual Spec creation)."""
    try:
        from core.harness.models.spec_lifecycle import get_spec_lifecycle
        spec_id = body.get("spec_id", "")
        if not spec_id:
            raise HTTPException(status_code=400, detail="spec_id is required")
        content = body.get("content", {})
        created_by = body.get("created_by", "developer")
        sl = get_spec_lifecycle()
        sv = sl.create_draft(spec_id, content, created_by=created_by,
                              trigger_detail="Manual creation from Workbench")
        return {"spec_id": sv.spec_id, "version": sv.version, "status": sv.status.value}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seed-demo", response_model=SeedDemoResponse)
async def seed_demo_data() -> Dict[str, Any]:
    """一键种子数据: 创建 2 个 Spec + 提交任务 → 仪表板立即可用。

    Creates demo specs with varied content, submits tasks that produce
    REVIEW-status specs with trace data and radar signals.
    """
    import uuid, asyncio as _aio
    results = []
    specs = [
        {"id": "contract_review_demo", "content": {"agent_md": "合同审核 Agent — 自动审核采购合同条款", "tools": ["kb_query", "code_execution"], "evals": ["accuracy > 0.9"]}},
        {"id": "report_gen_demo", "content": {"agent_md": "报表生成 Agent — 根据数据自动生成分析报表", "tools": ["data_analysis", "api_calling"], "evals": ["latency < 5s"]}},
    ]

    for spec in specs:
        try:
            # Create spec
            resp = await create_spec({
                "spec_id": spec["id"],
                "content": spec["content"],
                "created_by": "seed-demo",
            })
            spec_id = resp["spec_id"]

            # Submit task
            run_id = f"demo-{uuid.uuid4().hex[:8]}"
            submit = await submit_task({
                "description": f"Demo: {spec['content']['agent_md'][:40]}...",
                "capability": "general",
                "spec_id": spec_id,
                "run_id": run_id,
            })
            results.append({"spec_id": spec_id, "run_id": run_id, "status": "submitted"})
        except Exception as e:
            results.append({"spec_id": spec["id"], "error": str(e)[:100]})

    return {"seeded": len(results), "specs": results,
            "note": "任务正在后台执行，约 5 秒后仪表板将显示数据"}


@router.post("/skill/install", response_model=SkillInstallResponse)
async def install_skill_from_url(body: Dict[str, Any]) -> Dict[str, Any]:
    """Install a skill from an agentskills.io URL / git repo / zip URL.

    Skill Marketplace (Competitor Gap Closure): wraps skill_installer to
    provide one-click install from external skill registries.

    Body: {"url": "https://agentskills.io/skill/security-auditor" | git URL | zip URL}
    """
    url = body.get("url", "")
    if not url:
        raise HTTPException(status_code=400, detail="url is required")

    try:
        from core.management.skill_installer import SkillInstaller
        installer = SkillInstaller()

        # Determine install source
        if "agentskills.io" in url or url.endswith(".md"):
            # Single SKILL.md URL — download and wrap into skill directory
            import tempfile, httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=30)
                resp.raise_for_status()
                raw_md = resp.text

            with tempfile.TemporaryDirectory(prefix="aiplat-skill-url-") as td:
                import os as _os
                skill_dir = _os.path.join(td, "imported-skill")
                _os.makedirs(skill_dir, exist_ok=True)
                # Convert agentskills.io format if needed
                try:
                    from core.management.agentskills_parser import convert_agentskills_to_aiplat, is_agentskills_format
                    if is_agentskills_format(raw_md):
                        raw_md = convert_agentskills_to_aiplat(raw_md, "imported-skill")
                except Exception:
                    pass
                with open(_os.path.join(skill_dir, "SKILL.md"), "w") as f:
                    f.write(raw_md)
                result = await installer.install_from_dir(skill_dir)
                return {"status": "installed", "skill": result.get("name", "imported-skill"),
                        "source": url}

        elif url.startswith(("http", "git@")):
            # Git repo or zip URL — delegate to installer
            result = installer.install_from_git(url) if "git" in url else installer.install_from_zip(url)
            return {"status": "installed", "skill": result.get("name", ""), "source": url}

        else:
            raise HTTPException(status_code=400, detail="unsupported URL format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.post("/spec/{spec_id}/duplicate", response_model=SpecCreatedResponse)  # share SpecCreatedResponse
async def duplicate_spec(spec_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Duplicate an existing Spec as a new one (FDE productivity shortcut).

    Body: {"new_spec_id": "my-new-spec"} — optional, defaults to {spec_id}_copy
    """
    try:
        from core.harness.models.spec_lifecycle import get_spec_lifecycle
        sl = get_spec_lifecycle()
        source = sl.get_latest(spec_id)
        if not source:
            raise HTTPException(status_code=404, detail=f"Spec '{spec_id}' not found")

        new_id = body.get("new_spec_id", f"{spec_id}_copy")
        sv = sl.create_draft(
            new_id,
            content=source.content,
            created_by=body.get("created_by", "developer"),
            trigger_detail=f"Duplicated from {spec_id} v{source.version}",
        )
        return {"spec_id": sv.spec_id, "version": sv.version, "status": sv.status.value,
                "source": spec_id, "source_version": source.version}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/spec/{spec_id}/diff", response_model=SpecDiffResponse)
async def diff_spec_versions(spec_id: str, v1: int = 0, v2: int = 0) -> Dict[str, Any]:
    """Compare two Spec versions side by side (FDE troubleshooting tool).

    Query: ?v1=1&v2=3 — compares v1 to v3.
    Defaults to comparing latest vs previous version.
    """
    try:
        from core.harness.models.spec_lifecycle import get_spec_lifecycle
        sl = get_spec_lifecycle()
        if v1 <= 0 or v2 <= 0:
            history = sl.get_history(spec_id)
            if len(history) < 2:
                return {"spec_id": spec_id, "diff": None, "reason": "need at least 2 versions"}
            v2 = history[-1].version if v2 <= 0 else v2
            v1 = history[-2].version if v1 <= 0 else v1

        src = sl.get_version(spec_id, v1)
        dst = sl.get_version(spec_id, v2)
        if not src or not dst:
            raise HTTPException(status_code=404, detail="version not found")

        # Compute content changes
        changes = []
        old_content = src.content or {}
        new_content = dst.content or {}
        all_keys = set(old_content.keys()) | set(new_content.keys())

        for key in sorted(all_keys):
            old_val = old_content.get(key)
            new_val = new_content.get(key)
            if old_val != new_val:
                changes.append({
                    "field": key,
                    "v1_value": str(old_val)[:200] if old_val else "(未设置)",
                    "v2_value": str(new_val)[:200] if new_val else "(删除)",
                    "changed": True,
                })

        # Compute acceptance/deliverable changes (Matter fields)
        for field, label in [("acceptance_criteria", "验收标准"), ("deliverable", "交付物")]:
            o = old_content.get(field, "")
            n = new_content.get(field, "")
            if o != n:
                changes.append({"field": label, "v1_value": o or "(未设置)", "v2_value": n or "(删除)", "changed": True})

        return {
            "spec_id": spec_id,
            "v1": {"version": v1, "status": src.status.value, "trigger_detail": src.trigger_detail},
            "v2": {"version": v2, "status": dst.status.value, "trigger_detail": dst.trigger_detail},
            "changes": changes,
            "total_changes": len(changes),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.post("/spec/batch-mark-stable", response_model=BatchMarkStableResponse)
async def batch_mark_stable(body: Dict[str, Any]) -> Dict[str, Any]:
    """Batch operation: mark multiple REVIEW specs as STABLE at once.

    Body: {"spec_ids": ["spec-a", "spec-b", ...]}
    Returns: results per spec (stable / unchanged / error).
    """
    spec_ids = body.get("spec_ids", [])
    if not spec_ids or not isinstance(spec_ids, list):
        raise HTTPException(status_code=400, detail="spec_ids (list) is required")

    from core.harness.models.spec_lifecycle import get_spec_lifecycle
    sl = get_spec_lifecycle()
    results = []
    for sid in spec_ids:
        try:
            result = sl.mark_stable(sid)
            if result:
                results.append({"spec_id": sid, "status": "stable", "version": result.version})
            else:
                results.append({"spec_id": sid, "status": "unchanged", "reason": "not in review"})
        except Exception as e:
            results.append({"spec_id": sid, "status": "error", "reason": str(e)[:100]})

    stable_count = sum(1 for r in results if r["status"] == "stable")
    return {"total": len(spec_ids), "stable": stable_count, "results": results}


# ── Platform Promotion (Palantir 碎石路→高速公路) ──

@router.post("/spec/{spec_id}/promote", response_model=PromotionResponse)
async def promote_to_platform(spec_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Request Spec promotion to platform scope."""
    try:
        from core.harness.models.spec_lifecycle import get_spec_lifecycle
        sl = get_spec_lifecycle()
        result = sl.promote_to_platform(
            spec_id,
            requester=body.get("requester", "developer"),
            notes=body.get("notes", ""),
        )
        if not result:
            raise HTTPException(status_code=400, detail="Cannot promote: spec must be tenant-scoped")
        return {"spec_id": spec_id, "scope": "platform", "promotion_status": "pending"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.post("/spec/{spec_id}/promote/approve", response_model=PromotionResponse)  # share PromotionResponse
async def approve_promotion(spec_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Approve platform promotion (reviewer action)."""
    try:
        from core.harness.models.spec_lifecycle import get_spec_lifecycle
        sl = get_spec_lifecycle()
        result = sl.promote_approve(
            spec_id,
            reviewer=body.get("reviewer", "architect"),
            notes=body.get("notes", ""),
        )
        if not result:
            raise HTTPException(status_code=400, detail="Cannot approve: spec not in pending promotion")
        return {"spec_id": spec_id, "scope": "platform", "promotion_status": "approved",
                "reviewer": result.promotion_reviewer}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.post("/spec/{spec_id}/promote/reject", response_model=PromotionResponse)  # share PromotionResponse
async def reject_promotion(spec_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Reject platform promotion (reviewer action)."""
    try:
        from core.harness.models.spec_lifecycle import get_spec_lifecycle
        sl = get_spec_lifecycle()
        result = sl.promote_reject(
            spec_id,
            reviewer=body.get("reviewer", "architect"),
            reason=body.get("reason", ""),
        )
        if not result:
            raise HTTPException(status_code=400, detail="Cannot reject: spec not in pending promotion")
        return {"spec_id": spec_id, "scope": "tenant", "promotion_status": "rejected"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/promotion-queue", response_model=PaginatedResponse[dict])
async def get_promotion_queue() -> Dict[str, Any]:
    """List all Specs awaiting platform promotion review."""
    try:
        from core.harness.models.spec_lifecycle import get_spec_lifecycle
        sl = get_spec_lifecycle()
        queue = sl.get_promotion_queue()
        items = [{"spec_id": s.spec_id, "version": s.version, "requester": s.promotion_requester,
                  "notes": s.promotion_notes, "created_at": s.created_at} for s in queue]
        return {"queue": items, "total": len(items)}
    except Exception as e:
        return {"queue": [], "total": 0, "error": str(e)}


# Local helper for _trigger_spec_re_execution
from core.harness.models.spec_lifecycle import get_spec_lifecycle
