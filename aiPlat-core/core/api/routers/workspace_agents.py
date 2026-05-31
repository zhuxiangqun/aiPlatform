from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any, Annotated, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from core.api.deps import actor_from_http, rbac_guard
from core.api.utils.governance import gate_error_envelope, ui_url
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas_agents import AgentCreateRequest, AgentUpdateRequest, AgentAutoFillRequest, AgentAutoFillResponse, RoleDefinitionResponse

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]

# Legacy in-memory fallback for dev-mode / no ExecutionStore scenarios.
_workspace_agent_history: Dict[str, List[Dict[str, Any]]] = {}


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _detect_shell_agent(agent) -> bool:
    """Detect if an agent is a 'shell' — no system_prompt, no skills, no tools."""
    system_prompt = (agent.config or {}).get("system_prompt", "") if isinstance(agent.config, dict) else ""
    has_prompt = bool(system_prompt and len(str(system_prompt).strip()) > 20)
    has_skills = bool(getattr(agent, "skills", None))
    has_tools = bool(getattr(agent, "tools", None))
    return not has_skills and not has_tools and not has_prompt


def _ws_agent_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "workspace_agent_manager", None) if rt else None


def _job_scheduler(rt: Optional[KernelRuntime]):
    return getattr(rt, "job_scheduler", None) if rt else None


def _inject_http_request_context(payload: Any, http_request: Request, *, entrypoint: str) -> Any:
    """
    Best-effort: inject tenant/actor/request identity from headers into payload.context.
    Used for tenant/actor propagation into harness/syscalls.
    """
    if not isinstance(payload, dict):
        return payload
    try:
        ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        ctx = dict(ctx) if isinstance(ctx, dict) else {}
        ctx.setdefault("entrypoint", str(entrypoint or "api"))

        tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID") or http_request.headers.get("x-aiplat-tenant-id")
        actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID") or http_request.headers.get("x-aiplat-actor-id")
        actor_role = http_request.headers.get("X-AIPLAT-ACTOR-ROLE") or http_request.headers.get("x-aiplat-actor-role")
        req_id = http_request.headers.get("X-AIPLAT-REQUEST-ID") or http_request.headers.get("x-aiplat-request-id")
        if tenant_id:
            ctx.setdefault("tenant_id", str(tenant_id))
        if actor_id:
            ctx.setdefault("actor_id", str(actor_id))
        if actor_role:
            ctx.setdefault("actor_role", str(actor_role))
        if req_id:
            ctx.setdefault("request_id", str(req_id))
        payload["context"] = ctx
    except Exception:
        return payload
    return payload


async def _audit_execute(
    rt: Optional[KernelRuntime],
    *,
    http_request: Request,
    payload: Optional[Dict[str, Any]],
    resource_type: str,
    resource_id: str,
    resp: Dict[str, Any],
    action: Optional[str] = None,
) -> None:
    """Enterprise audit for execute entrypoints (best-effort)."""
    store = _store(rt)
    if not store:
        return
    try:
        actor = actor_from_http(http_request, payload)
        await store.add_audit_log(
            action=action or f"execute_{resource_type}",
            status=str(resp.get("legacy_status") or resp.get("status") or ("ok" if resp.get("ok") else "failed")),
            tenant_id=str(actor.get("tenant_id") or "") or None,
            actor_id=str(actor.get("actor_id") or "") or None,
            actor_role=str(actor.get("actor_role") or "") or None,
            resource_type=str(resource_type),
            resource_id=str(resource_id),
            request_id=str(resp.get("request_id") or "") or (http_request.headers.get("X-AIPLAT-REQUEST-ID") or http_request.headers.get("x-aiplat-request-id")),
            run_id=str(resp.get("run_id") or resp.get("execution_id") or "") or None,
            trace_id=str(resp.get("trace_id") or "") or None,
            detail={"status": resp.get("status"), "legacy_status": resp.get("legacy_status"), "error": resp.get("error")},
        )
    except Exception:
        return


def _is_verified(meta: Dict[str, Any] | None) -> bool:
    if not isinstance(meta, dict):
        return False
    v = meta.get("verification")
    if isinstance(v, dict):
        return str(v.get("status") or "") == "verified"
    return False


def _autosmoke_gate_error(*, message: str) -> Dict[str, Any]:
    return gate_error_envelope(
        code="agent_unverified",
        message=message,
        next_actions=[{"type": "open_smoke", "label": "打开 Smoke", "url": ui_url("/diagnostics/smoke")}],
    )


# ==================== Workspace Agent Management ====================


@router.get("/workspace/agents")
async def list_workspace_agents(
    agent_type: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    rt: RuntimeDep = None,
):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        return {"agents": [], "total": 0, "limit": limit, "offset": offset}
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    agents = await mgr.list_agents(agent_type, status, category, tag_list, limit, offset)
    return {
        "agents": [
            {"id": a.id, "name": a.name,
             "display_name": a.metadata.get("display_name", a.name) if isinstance(a.metadata, dict) else a.name,
             "description": a.metadata.get("description", ""),
             "agent_type": a.type, "status": a.status,
             "runtime_state": getattr(a, "runtime_state", "stopped"),
             "is_shell": _detect_shell_agent(a),
             "category": a.category, "tags": a.tags, "phase": a.phase,
             "output_artifact": a.metadata.get("output_artifact", ""),
             "config": a.config,
             "skills": a.skills, "tools": a.tools, "metadata": a.metadata}
            for a in agents
        ],
        "total": mgr.get_agent_count().get("total", 0),
        "limit": limit,
        "offset": offset,
    }


@router.post("/workspace/agents")
async def create_workspace_agent(request: AgentCreateRequest, http_request: Request, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    try:
        agent = await mgr.create_agent(
            name=request.name,
            agent_type=request.agent_type,
            config=request.config,
            skills=request.skills,
            tools=request.tools,
            mcp_ids=request.mcp_ids,
            workflow_ids=request.workflow_ids,
            agent_ids=request.agent_ids,
            memory_config=request.memory_config,
            metadata=request.metadata,
        )
        # Mark as pending verification (best-effort)
        try:
            await mgr.update_agent(
                str(agent.id),
                metadata={"verification": {"status": "pending", "updated_at": time.time(), "source": "autosmoke"}},
            )
        except Exception:
            pass

        # Auto-smoke (async, dedup): trigger on create/update to validate the full chain.
        try:
            store = _store(rt)
            sched = _job_scheduler(rt)
            if store is not None and sched is not None:
                from core.harness.smoke import enqueue_autosmoke

                tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
                actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
                agent_id = str(agent.id)

                async def _on_complete(job_run: Dict[str, Any]):
                    st = str(job_run.get("status") or "")
                    ver = {
                        "status": "verified" if st == "completed" else "failed",
                        "updated_at": time.time(),
                        "source": "autosmoke",
                        "job_id": f"autosmoke-agent:{agent_id}",
                        "job_run_id": str(job_run.get("id") or ""),
                        "reason": str(job_run.get("error") or ""),
                    }
                    try:
                        await mgr.update_agent(agent_id, metadata={"verification": ver})
                    except Exception:
                        pass

                await enqueue_autosmoke(
                    execution_store=store,
                    job_scheduler=sched,
                    resource_type="agent",
                    resource_id=agent_id,
                    tenant_id=tenant_id or "ops_smoke",
                    actor_id=actor_id or "admin",
                    detail={"op": "create", "name": agent.name},
                    on_complete=_on_complete,
                )
        except Exception:
            pass

        return {"id": agent.id, "status": "created", "name": agent.name}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/workspace/agents/generate-role-definition")
async def generate_role_definition(req: AgentAutoFillRequest) -> RoleDefinitionResponse:
    """基于功能描述生成角色定义，让用户确认后再进行下一步的技能/工具推荐。"""
    import json as _json, re as _re

    from core.harness.utils.prompt_loader import _async_prompt_resolve
    prompt = await _async_prompt_resolve("agent-role-definition",
        name=req.name or '(待填写)', description=req.description or '(无)',
    )

    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        model_name = best_model_for_purpose("agent_creation")
        model = create_selected_adapter(model_name=model_name)
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("agent-role-system")},
            {"role": "user", "content": prompt},
        ]
        resp = await model.generate(messages, config=None)
        content = resp.content if hasattr(resp, 'content') else str(resp)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")

    clean = content.strip()
    if clean.startswith("```"):
        clean = _re.sub(r'^```\w*\n?', '', clean)
        clean = _re.sub(r'\n?```$', '', clean)
    match = _re.search(r'\{[\s\S]*\}', clean)
    if match:
        try:
            data = _json.loads(match.group(0))
        except _json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="Failed to parse LLM response as JSON")
    else:
        raise HTTPException(status_code=422, detail="LLM response does not contain JSON")

    return RoleDefinitionResponse(
        role_name=str(data.get("role_name", ""))[:20],
        responsibilities=list(data.get("responsibilities", []))[:8],
        scenarios=list(data.get("scenarios", []))[:5],
        required_capabilities=list(data.get("required_capabilities", []))[:8],
        workflow_hint=str(data.get("workflow_hint", ""))[:500],
        reasoning=str(data.get("reasoning", ""))[:500],
    )


@router.post("/workspace/agents/auto-fill")
async def agent_auto_fill(req: AgentAutoFillRequest) -> AgentAutoFillResponse:
    """AI 智能填充：根据功能描述自动推荐 skills / tools / MCP / config / SOP 等。"""
    import json as _json
    import re as _re

    # ── Build skill catalog (enriched with display_name + description) ──
    skill_entries: List[str] = []
    try:
        from core.harness.knowledge.capability_graph import build_capability_graph
        import yaml as _yaml
        from pathlib import Path as _Py
        cg = build_capability_graph()
        for nid, n in cg.nodes.items():
            if n.get("type") == "skill":
                skill_id = n['raw_id']
                label = n.get('label', skill_id)
                cat = n.get('category', '')
                desc = ''
                # Read SKILL.md to get description
                skill_path = n.get('path', '')
                if skill_path:
                    md_file = _Py(skill_path) / 'SKILL.md'
                    if md_file.exists():
                        try:
                            raw = md_file.read_text(encoding='utf-8', errors='ignore')
                            if raw.startswith('---'):
                                parts = raw.split('---', 2)
                                if len(parts) >= 3:
                                    fm = _yaml.safe_load(parts[1]) or {}
                                    desc = str(fm.get('description', '') or '')[:120]
                        except Exception:
                            pass
                if desc:
                    skill_entries.append(f'  - {skill_id} | {label} | [{cat}] | {desc}')
                else:
                    skill_entries.append(f'  - {skill_id} | {label} | [{cat}]')
    except Exception:
        skill_entries = ["(unable to load skill catalog)"]

    # ── Build tool catalog ───────────────────────────────────────
    tool_entries: List[str] = []
    try:
        from core.apps.tools.base import get_tool_registry
        reg = get_tool_registry()
        for name in sorted(reg.list_tools() or []):
            tool = reg.get(name)
            desc = getattr(tool, 'description', '') if tool else ''
            tool_entries.append(f"  - {name}: {str(desc)[:200]}")
    except Exception:
        tool_entries = ["(unable to load tool catalog)"]

    # ── Build MCP catalog ────────────────────────────────────────
    mcp_entries: List[str] = []
    try:
        from core.management.mcp_manager import MCPManager as _Mgr
        mgr = _Mgr()
        for srv in mgr.list_servers() or []:
            mcp_entries.append(
                f"  - {srv.name}: enabled={getattr(srv,'enabled',True)} "
                f"transport={getattr(srv,'transport','')}"
            )
    except Exception:
        mcp_entries = ["(unable to load MCP catalog)"]

    # ── Build sub-agent catalog ───────────────────────────────────
    agent_catalog: List[str] = []
    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        rt = get_kernel_runtime()
        mgr = getattr(rt, "workspace_agent_manager", None) if rt else None
        if mgr:
            all_agents = await mgr.list_agents(limit=200)
            for a in all_agents:
                agent_catalog.append(
                    f"  - id={a.id} | name={a.name} | type={a.type}"
                )
        if not agent_catalog:
            agent_catalog = ["(no sub-agents available)"]
    except Exception:
        agent_catalog = ["(unable to load agent catalog)"]

    # ── Build workflow template catalog ────────────────────────────
    wf_catalog: List[str] = []
    try:
        import json as _wjson, os as _wos
        from pathlib import Path as _WPath
        wf_dir = _WPath(_wos.getenv("AIPLAT_HOME", _wos.path.expanduser("~/.aiplat"))) / "workflow_templates"
        if wf_dir.exists():
            for f in sorted(wf_dir.glob("*.json")):
                try:
                    data = _wjson.loads(f.read_text(encoding="utf-8"))
                    nm = data.get("name", f.stem)
                    sz = len(data.get("stages", []))
                    wf_catalog.append(f"  - {f.stem} | {nm} | stages={sz}")
                except Exception:
                    pass
        if not wf_catalog:
            wf_catalog = ["(no workflow templates available — create one in Workflow 页面)"]
    except Exception:
        wf_catalog = ["(unable to load workflow catalog)"]

    # ── Build prompt ────────────────────────────────────────────
    role_section = ""
    if req.role_definition and isinstance(req.role_definition, dict):
        rd = req.role_definition
        role_section = f"""
## 已确认的角色定义
- 角色名称: {rd.get('role_name', '')}
- 职责: {', '.join(rd.get('responsibilities', []))}
- 使用场景: {', '.join(rd.get('scenarios', []))}
- 需要的能力: {', '.join(rd.get('required_capabilities', []))}
- 协作关系: {rd.get('workflow_hint', '无')}
"""

    from core.harness.utils.prompt_loader import _async_prompt_resolve

    # Build app template catalog (for template recommendation)
    app_tpl_entries: List[str] = []
    try:
        store = getattr(rt, "execution_store", None) if rt else None
        if store:
            tpls = await store.list_prompt_app_templates(limit=100)
            for t in (tpls.get("items") or []):
                name = t.get("name", "")
                cat = t.get("category", "")
                sp = (t.get("system_prompt", "") or "")[:80]
                app_tpl_entries.append(f"- {t.get('id','')}: {name}（{cat}），系统提示：{sp}")
    except Exception:
        pass

    prompt = await _async_prompt_resolve("agent-auto-fill",
        name=req.name or '(待填写)',
        description=req.description or '(无)',
        role_section=role_section,
        skills_catalog=chr(10).join(skill_entries[:50]) or '(无)',
        tools_catalog=chr(10).join(tool_entries[:30]) or '(无)',
        mcp_catalog=chr(10).join(mcp_entries[:20]) or '(无)',
        agent_catalog=chr(10).join(agent_catalog[:40]) or '(无)',
        wf_catalog=chr(10).join(wf_catalog[:20]) or '(无)',
        app_template_catalog=chr(10).join(app_tpl_entries[:30]) or '(无)',
        role_phrase="和已确认的角色定义" if role_section else "",
    )

    # ── Call LLM ─────────────────────────────────────────────────
    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        model_name = best_model_for_purpose("agent_creation")
        model = create_selected_adapter(model_name=model_name)
        messages = [
            {"role": "system", "content": "你是一个 AI Agent 配置专家。只输出 JSON，不要加任何解释或 markdown 标记。"},
            {"role": "user", "content": prompt},
        ]
        resp = await model.generate(messages, config=None)
        content = resp.content if hasattr(resp, 'content') else str(resp)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")

    # ── Parse JSON response ──────────────────────────────────────
    clean = content.strip()
    if clean.startswith("```"):
        clean = _re.sub(r'^```\w*\n?', '', clean)
        clean = _re.sub(r'\n?```$', '', clean)
    match = _re.search(r'\{[\s\S]*\}', clean)
    if match:
        try:
            data = _json.loads(match.group(0))
        except _json.JSONDecodeError:
            cleaned = _re.sub(r',\s*\}', '}', match.group(0))
            try:
                data = _json.loads(cleaned)
            except _json.JSONDecodeError:
                raise HTTPException(status_code=422, detail="Failed to parse LLM response as JSON")
    else:
        raise HTTPException(status_code=422, detail="LLM response does not contain JSON")

    return AgentAutoFillResponse(
        agent_type=str(data.get("agent_type", "base"))[:20],
        config=data.get("config", {}) if isinstance(data.get("config"), dict) else {},
        skills=list(data.get("skills", []))[:20],
        tools=list(data.get("tools", []))[:20],
        mcp_ids=list(data.get("mcp_ids", []))[:10],
        agent_ids=list(data.get("agent_ids", []))[:10],
        memory_config=data.get("memory_config", {}) if isinstance(data.get("memory_config"), dict) else {},
        sop_text=str(data.get("sop_text", ""))[:8000],
        reasoning=str(data.get("reasoning", ""))[:500],
        workflow_ids=list(data.get("workflow_ids", []))[:10],
        template_id=str(data.get("template_id", ""))[:80],
    )


@router.post("/workspace/agents/auto-fill-batch")
async def agent_auto_fill_batch(req: "AgentAutoFillBatchRequest") -> "AgentAutoFillBatchResponse":
    u"""Batch AI auto-fill: single LLM call for multiple agents."""
    from core.schemas_agents import AgentAutoFillBatchResponse as _BatchResp, AgentAutoFillResponse as _FillResp
    import json as _json, re as _re

    names = req.names
    errors: List[str] = []
    results: Dict[str, Any] = {}

    # ── Build catalogs (once for all agents) ────────────────
    skill_entries = await _build_skill_catalog()
    tool_entries = await _build_tool_catalog()
    mcp_entries = await _build_mcp_catalog()
    agent_catalog = await _build_agent_catalog()
    wf_catalog = await _build_wf_catalog()

    # ── Build batch prompt ──────────────────────────────────
    agent_list_text = "\n".join(f"  - {n}" for n in names)
    from core.harness.utils.prompt_loader import _async_prompt_resolve
    prompt = await _async_prompt_resolve("agent-auto-fill-batch",
        count=str(len(names)),
        agent_list=agent_list_text,
        skills_catalog=chr(10).join(skill_entries[:50]) or '(无)',
        tools_catalog=chr(10).join(tool_entries[:30]) or '(无)',
        mcp_catalog=chr(10).join(mcp_entries[:20]) or '(无)',
        agent_catalog=chr(10).join(agent_catalog[:40]) or '(无)',
        wf_catalog=chr(10).join(wf_catalog[:20]) or '(无)',
    )

    # ── Call LLM ────────────────────────────────────────────
    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        model_name = best_model_for_purpose("agent_creation")
        model = create_selected_adapter(model_name=model_name)
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("agent-role-system")},
            {"role": "user", "content": prompt},
        ]
        resp = await model.generate(messages, config=None)
        content = resp.content if hasattr(resp, 'content') else str(resp)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")

    # ── Parse JSON ──────────────────────────────────────────
    clean = content.strip()
    if clean.startswith("```"):
        clean = _re.sub(r'^```\w*\n?', '', clean)
        clean = _re.sub(r'\n?```$', '', clean)
    match = _re.search(r'\{[\s\S]*\}', clean)
    if not match:
        raise HTTPException(status_code=422, detail="LLM response does not contain JSON")

    try:
        data = _json.loads(match.group(0))
    except _json.JSONDecodeError:
        cleaned = _re.sub(r',\s*\}', '}', match.group(0))
        try:
            data = _json.loads(cleaned)
        except _json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="Failed to parse LLM response")

    for name in names:
        entry = data.get(name, {})
        if not entry:
            errors.append(f"{name}: not in LLM response")
            continue
        try:
            results[name] = _FillResp(
                agent_type=str(entry.get("agent_type", "base"))[:20],
                config=entry.get("config", {}) if isinstance(entry.get("config"), dict) else {},
                skills=list(entry.get("skills", []))[:20],
                tools=list(entry.get("tools", []))[:20],
                mcp_ids=list(entry.get("mcp_ids", []))[:10],
                agent_ids=list(entry.get("agent_ids", []))[:10],
                memory_config=entry.get("memory_config", {}) if isinstance(entry.get("memory_config"), dict) else {},
                sop_text=str(entry.get("sop_text", ""))[:8000],
                reasoning=str(entry.get("reasoning", ""))[:500],
                workflow_ids=list(entry.get("workflow_ids", []))[:10],
            )
        except Exception as e:
            errors.append(f"{name}: {e}")

    return _BatchResp(results=results, errors=errors)


async def _build_skill_catalog() -> List[str]:
    import yaml as _yaml
    from pathlib import Path as _Py
    entries = []
    try:
        from core.harness.knowledge.capability_graph import build_capability_graph
        cg = build_capability_graph()
        for nid, n in cg.nodes.items():
            if n.get("type") == "skill":
                skill_id = n['raw_id']
                label = n.get('label', skill_id)
                cat = n.get('category', '')
                desc = ''
                skill_path = n.get('path', '')
                if skill_path:
                    md_file = _Py(skill_path) / 'SKILL.md'
                    if md_file.exists():
                        try:
                            raw = md_file.read_text(encoding='utf-8', errors='ignore')
                            if raw.startswith('---'):
                                parts = raw.split('---', 2)
                                if len(parts) >= 3:
                                    fm = _yaml.safe_load(parts[1]) or {}
                                    desc = str(fm.get('description', '') or '')[:120]
                        except Exception:
                            pass
                if desc:
                    entries.append(f'  - {skill_id} | {label} | [{cat}] | {desc}')
                else:
                    entries.append(f'  - {skill_id} | {label} | [{cat}]')
    except Exception:
        entries = ["(unable to load skill catalog)"]
    return entries


async def _build_tool_catalog() -> List[str]:
    entries = []
    try:
        from core.apps.tools.base import get_tool_registry
        reg = get_tool_registry()
        for name in sorted(reg.list_tools() or []):
            tool = reg.get(name)
            desc = getattr(tool, 'description', '') if tool else ''
            entries.append(f"  - {name}: {str(desc)[:200]}")
    except Exception:
        entries = ["(unable to load tool catalog)"]
    return entries


async def _build_mcp_catalog() -> List[str]:
    entries = []
    try:
        from core.management.mcp_manager import MCPManager as _Mgr
        mgr = _Mgr()
        for srv in mgr.list_servers() or []:
            entries.append(
                f"  - {srv.name}: enabled={getattr(srv,'enabled',True)} "
                f"transport={getattr(srv,'transport','')}"
            )
    except Exception:
        entries = ["(unable to load MCP catalog)"]
    return entries


async def _build_agent_catalog() -> List[str]:
    entries = []
    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        rt = get_kernel_runtime()
        mgr = getattr(rt, "workspace_agent_manager", None) if rt else None
        if mgr:
            all_agents = await mgr.list_agents(limit=200)
            for a in all_agents:
                entries.append(f"  - id={a.id} | name={a.name} | type={a.type}")
        if not entries:
            entries = ["(no sub-agents available)"]
    except Exception:
        entries = ["(unable to load agent catalog)"]
    return entries


async def _build_wf_catalog() -> List[str]:
    import json as _wjson, os as _wos
    from pathlib import Path as _WPath
    entries = []
    try:
        wf_dir = _WPath(_wos.getenv("AIPLAT_HOME", _wos.path.expanduser("~/.aiplat"))) / "workflow_templates"
        if wf_dir.exists():
            for f in sorted(wf_dir.glob("*.json")):
                try:
                    data = _wjson.loads(f.read_text(encoding="utf-8"))
                    nm = data.get("name", f.stem)
                    sz = len(data.get("stages", []))
                    entries.append(f"  - {f.stem} | {nm} | stages={sz}")
                except Exception:
                    pass
        if not entries:
            entries = ["(no workflow templates available)"]
    except Exception:
        entries = ["(unable to load workflow catalog)"]
    return entries


@router.get("/workspace/agents/{agent_id}")
async def get_workspace_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {
        "id": agent.id,
        "name": agent.name,
        "agent_type": agent.type,
        "status": agent.status,
        "config": agent.config,
        "skills": agent.skills,
        "tools": agent.tools,
        "memory_config": agent.memory_config,
        "metadata": agent.metadata,
    }


@router.get("/workspace/agents/{agent_id}/sop")
async def get_workspace_agent_sop(agent_id: str, rt: RuntimeDep = None):
    """Get agent SOP (markdown) from AGENT.md '## SOP' section."""
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    data = await mgr.get_agent_sop(agent_id)  # type: ignore[attr-defined]
    if not data:
        raise HTTPException(status_code=404, detail="SOP not found")
    return data


@router.put("/workspace/agents/{agent_id}/sop")
async def update_workspace_agent_sop(agent_id: str, request: dict, rt: RuntimeDep = None):
    """Update agent SOP section in AGENT.md."""
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    sop = (request or {}).get("sop")
    if sop is None:
        raise HTTPException(status_code=400, detail="Missing field: sop")
    try:
        ok = await mgr.update_agent_sop(agent_id, str(sop))  # type: ignore[attr-defined]
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update SOP")
    return {"status": "updated", "id": agent_id}


@router.get("/workspace/agents/{agent_id}/execution-help")
async def get_workspace_agent_execution_help(agent_id: str, rt: RuntimeDep = None):
    """Get execution input help/examples for agent."""
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    data = await mgr.get_agent_execution_help(agent_id)  # type: ignore[attr-defined]
    if not data:
        raise HTTPException(status_code=404, detail="Execution help not found")
    return data


@router.delete("/workspace/agents/{agent_id}")
async def delete_workspace_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    ok = await mgr.delete_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "deleted", "id": agent_id}


@router.post("/workspace/agents/{agent_id}/start")
async def start_workspace_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    try:
        from core.governance.gating import autosmoke_enforce
    except Exception:
        autosmoke_enforce = None  # type: ignore

    if autosmoke_enforce and autosmoke_enforce(store=_store(rt)):
        a = await mgr.get_agent(agent_id)
        if not a:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        if not _is_verified(getattr(a, "metadata", None)):
            raise HTTPException(status_code=403, detail=_autosmoke_gate_error(message="smoke must pass before start"))
    ok = await mgr.start_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "started", "id": agent_id}


@router.post("/workspace/agents/{agent_id}/stop")
async def stop_workspace_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    ok = await mgr.stop_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "stopped", "id": agent_id}


@router.put("/workspace/agents/{agent_id}")
async def update_workspace_agent(agent_id: str, request: AgentUpdateRequest, http_request: Request, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.update_agent(
        agent_id,
        name=request.name,
        status=request.status,
        config=request.config,
        skills=request.skills,
        tools=request.tools,
        mcp_ids=request.mcp_ids,
        workflow_ids=request.workflow_ids,
        agent_ids=request.agent_ids,
        memory_config=request.memory_config,
        metadata=request.metadata,
    )
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # Mark as pending verification (best-effort)
    try:
        await mgr.update_agent(str(agent_id), metadata={"verification": {"status": "pending", "updated_at": time.time(), "source": "autosmoke"}})
    except Exception:
        pass

    # Auto-smoke (async, dedup)
    try:
        store = _store(rt)
        sched = _job_scheduler(rt)
        if store is not None and sched is not None:
            from core.harness.smoke import enqueue_autosmoke

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
            aid = str(agent_id)

            async def _on_complete(job_run: Dict[str, Any]):
                st = str(job_run.get("status") or "")
                ver = {
                    "status": "verified" if st == "completed" else "failed",
                    "updated_at": time.time(),
                    "source": "autosmoke",
                    "job_id": f"autosmoke-agent:{aid}",
                    "job_run_id": str(job_run.get("id") or ""),
                    "reason": str(job_run.get("error") or ""),
                }
                try:
                    await mgr.update_agent(aid, metadata={"verification": ver})
                except Exception:
                    pass

            await enqueue_autosmoke(
                execution_store=store,
                job_scheduler=sched,
                resource_type="agent",
                resource_id=aid,
                tenant_id=tenant_id or "ops_smoke",
                actor_id=actor_id or "admin",
                detail={"op": "update"},
                on_complete=_on_complete,
            )
    except Exception:
        pass
    return {"status": "updated", "id": agent_id}


# ==================== skills/tools bindings ====================


@router.get("/workspace/agents/{agent_id}/skills")
async def get_workspace_agent_skills(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    bindings = await mgr.get_skill_bindings(agent_id)
    return {
        "skills": [
            {"skill_id": b.skill_id, "skill_name": b.skill_name, "skill_type": b.skill_type, "call_count": b.call_count, "success_rate": b.success_rate}
            for b in bindings
        ],
        "skill_ids": agent.skills,
        "total": len(agent.skills),
    }


@router.post("/workspace/agents/{agent_id}/skills")
async def bind_workspace_agent_skills(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    skill_ids = (request or {}).get("skill_ids", [])
    if skill_ids:
        await mgr.bind_skills(agent_id, skill_ids)
    return {"status": "bound", "skill_ids": skill_ids}


@router.delete("/workspace/agents/{agent_id}/skills/{skill_id}")
async def unbind_workspace_agent_skill(agent_id: str, skill_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    await mgr.unbind_skill(agent_id, skill_id)
    return {"status": "unbound"}


@router.get("/workspace/agents/{agent_id}/tools")
async def get_workspace_agent_tools(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    bindings = await mgr.get_tool_bindings(agent_id)
    return {
        "tools": [
            {"tool_id": b.tool_id, "tool_name": b.tool_name, "tool_type": b.tool_type, "call_count": b.call_count, "success_rate": b.success_rate}
            for b in bindings
        ],
        "tool_ids": agent.tools,
        "total": len(agent.tools),
    }


@router.post("/workspace/agents/{agent_id}/tools")
async def bind_workspace_agent_tools(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    tool_ids = (request or {}).get("tool_ids", [])
    if tool_ids:
        await mgr.bind_tools(agent_id, tool_ids)
    return {"status": "bound", "tool_ids": tool_ids}


@router.delete("/workspace/agents/{agent_id}/tools/{tool_id}")
async def unbind_workspace_agent_tool(agent_id: str, tool_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    await mgr.unbind_tool(agent_id, tool_id)
    return {"status": "unbound"}


# ── MCP server bindings ──

@router.get("/workspace/agents/{agent_id}/mcp")
async def get_workspace_agent_mcp(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"mcp_ids": agent.mcp_ids, "total": len(agent.mcp_ids)}


@router.post("/workspace/agents/{agent_id}/mcp")
async def bind_workspace_agent_mcp(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    mcp_ids = (request or {}).get("mcp_ids", [])
    await mgr.update_agent(agent_id, mcp_ids=mcp_ids)
    return {"status": "bound", "mcp_ids": mcp_ids}


@router.delete("/workspace/agents/{agent_id}/mcp/{mcp_id}")
async def unbind_workspace_agent_mcp(agent_id: str, mcp_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    new_mcp = [m for m in agent.mcp_ids if m != mcp_id]
    await mgr.update_agent(agent_id, mcp_ids=new_mcp)
    return {"status": "unbound"}


# ── Workflow bindings ──

@router.get("/workspace/agents/{agent_id}/workflows")
async def get_workspace_agent_workflows(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"workflow_ids": agent.workflow_ids, "total": len(agent.workflow_ids)}


@router.post("/workspace/agents/{agent_id}/workflows")
async def bind_workspace_agent_workflows(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    workflow_ids = (request or {}).get("workflow_ids", [])
    await mgr.update_agent(agent_id, workflow_ids=workflow_ids)
    return {"status": "bound", "workflow_ids": workflow_ids}


@router.delete("/workspace/agents/{agent_id}/workflows/{workflow_id}")
async def unbind_workspace_agent_workflow(agent_id: str, workflow_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    new_wf = [w for w in agent.workflow_ids if w != workflow_id]
    await mgr.update_agent(agent_id, workflow_ids=new_wf)
    return {"status": "unbound"}


# ── Sub-agent bindings ──

@router.get("/workspace/agents/{agent_id}/agents")
async def get_workspace_agent_sub_agents(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"agent_ids": agent.agent_ids, "total": len(agent.agent_ids)}


@router.post("/workspace/agents/{agent_id}/agents")
async def bind_workspace_agent_sub_agents(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    agent_ids = (request or {}).get("agent_ids", [])
    await mgr.update_agent(agent_id, agent_ids=agent_ids)
    return {"status": "bound", "agent_ids": agent_ids}


@router.delete("/workspace/agents/{agent_id}/agents/{sub_agent_id}")
async def unbind_workspace_agent_sub_agent(agent_id: str, sub_agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    new_ids = [a for a in agent.agent_ids if a != sub_agent_id]
    await mgr.update_agent(agent_id, agent_ids=new_ids)
    return {"status": "unbound"}


# ==================== execute / history / versions ====================


@router.post("/workspace/agents/{agent_id}/execute")
async def execute_workspace_agent(agent_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    payload = _inject_http_request_context(dict(request or {}), http_request, entrypoint="api")
    deny = await rbac_guard(http_request=http_request, payload=payload, action="execute", resource_type="agent", resource_id=str(agent_id))
    if deny:
        return deny

    try:
        from core.governance.gating import autosmoke_enforce
    except Exception:
        autosmoke_enforce = None

    if autosmoke_enforce and autosmoke_enforce(store=_store(rt)):
        if not _is_verified(getattr(agent, "metadata", None)):
            raise HTTPException(status_code=403, detail=_autosmoke_gate_error(message="smoke must pass before execute"))

    # Extract user message and config from payload
    inp = payload.get("input") if isinstance(payload, dict) else None
    if isinstance(inp, str) and inp.strip():
        user_message = inp.strip()
    elif isinstance(inp, dict):
        user_message = str(inp.get("message") or inp.get("prompt") or inp.get("task") or "")
    else:
        user_message = str(payload.get("message") or payload.get("prompt") or payload.get("task") or "")

    user_config: dict = {}
    if isinstance(inp, dict):
        user_config = dict(inp.get("config") or {})
    if isinstance(payload.get("config"), dict):
        user_config.update(payload["config"])
    opts = payload.get("options") if isinstance(payload.get("options"), dict) else {}

    # Delegate to CoreFacade
    from core.api.core_facade import run_workspace_agent
    resp = await run_workspace_agent(
        agent_info=agent,
        user_message=user_message,
        max_steps=int(user_config.get("max_steps", 10)),
        toolset=str(opts.get("toolset", "")),
        session_id=str(payload.get("session_id", "") or f"ws-{agent_id}"),
    )

    try:
        await _audit_execute(rt, http_request=http_request, payload=payload, resource_type="agent", resource_id=str(agent_id), resp=resp)
    except Exception:
        pass
    return JSONResponse(status_code=200 if resp.get("ok") else 500, content=resp)


@router.post("/workspace/agents/{agent_id}/toggle-enabled")
async def toggle_agent_enabled(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=500, detail="agent manager not available")
    result = await mgr.toggle_enabled(agent_id)
    if result is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return {"agent_id": agent_id, "enabled": result}


@router.get("/workspace/agents/{agent_id}/history")
async def get_workspace_agent_history(agent_id: str, limit: int = 100, offset: int = 0, rt: RuntimeDep = None):
    store = _store(rt)
    if store:
        history, total = await store.list_agent_history(agent_id, limit=limit, offset=offset)
        return {"history": history, "total": total}
    history = _workspace_agent_history.get(agent_id, [])[offset : offset + limit]
    return {"history": history, "total": len(_workspace_agent_history.get(agent_id, []))}


@router.get("/workspace/agents/{agent_id}/versions")
async def get_workspace_agent_versions(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    versions = await mgr.get_versions(agent_id)
    return {"agent_id": agent_id, "versions": [{"version": v.version, "status": v.status, "created_at": v.created_at.isoformat(), "changes": v.changes} for v in versions]}


@router.post("/workspace/agents/{agent_id}/versions")
async def create_workspace_agent_version(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    changes = (request or {}).get("changes", "")
    version = await mgr.create_version(agent_id, changes)
    if not version:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"version": version.version, "status": version.status, "created_at": version.created_at.isoformat(), "changes": version.changes}


@router.post("/workspace/agents/{agent_id}/versions/{version}/rollback")
async def rollback_workspace_agent_version(agent_id: str, version: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    ok = await mgr.rollback_version(agent_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent or version {version} not found")
    return {"status": "rolled_back", "version": version}


# ── reload ──


def _reload_workspace_managers(rt: Optional[KernelRuntime]) -> None:
    try:
        from core.workspace.reload import rebuild_workspace_managers

        out = rebuild_workspace_managers(
            engine_agent_manager=getattr(rt, "agent_manager", None) if rt else None,
            engine_skill_manager=getattr(rt, "skill_manager", None) if rt else None,
            engine_mcp_manager=getattr(rt, "mcp_manager", None) if rt else None,
        )
        if rt is not None:
            setattr(rt, "workspace_agent_manager", out.get("workspace_agent_manager"))
            setattr(rt, "workspace_skill_manager", out.get("workspace_skill_manager"))
            setattr(rt, "workspace_mcp_manager", out.get("workspace_mcp_manager"))
    except Exception:
        return


@router.post("/workspace/agents/{agent_id}/reload")
async def reload_workspace_agent(agent_id: str, rt: RuntimeDep = None):
    _reload_workspace_managers(rt)
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    a = await mgr.get_agent(agent_id)
    if not a:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "reloaded", "agent_id": agent_id}


# ── Agent Installer endpoints (workspace scope) ──────────────────────

@router.post("/workspace/agents/installer/plan")
async def workspace_agents_installer_plan(request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    try:
        return await mgr.installer_plan(
            source_type=str(request.get("source_type", "")),
            url=request.get("url"),
            ref=request.get("ref"),
            path=request.get("path"),
            agent_id=request.get("agent_id"),
            subdir=request.get("subdir"),
            auto_detect_subdir=bool(request.get("auto_detect_subdir", True)),
            metadata=request.get("metadata"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/workspace/agents/installer/install")
async def workspace_agents_installer_install(request: dict, http_request: Request, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    try:
        return await mgr.installer_install(
            source_type=str(request.get("source_type", "")),
            url=request.get("url"),
            ref=request.get("ref"),
            path=request.get("path"),
            agent_id=request.get("agent_id"),
            subdir=request.get("subdir"),
            auto_detect_subdir=bool(request.get("auto_detect_subdir", True)),
            allow_overwrite=bool(request.get("allow_overwrite", False)),
            metadata=request.get("metadata"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/workspace/agents/installer/resolve-head")
async def workspace_agents_installer_resolve_head(request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    try:
        return await mgr.installer_resolve_head(url=str(request.get("url", "")))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/workspace/agents/{agent_id}/submit-for-review")
async def submit_agent_for_review(agent_id: str, rt: RuntimeDep = None):
    """提交 Agent 进入审批流水线。

    1. 获取 Agent 当前状态（仅 draft/enabled 可提交）
    2. 运行 AGENT.md 配置校验
    3. 有 error → 拒绝提交，返回校验报告
    4. 无 error → status → ready, governance → pending
    """
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")

    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    current_status = str(getattr(agent, "status", "") or "draft")
    if current_status not in ("draft", "enabled", ""):
        raise HTTPException(status_code=409, detail=f"Agent status is '{current_status}', must be draft or enabled")

    # ── Run Config Validation ─────────────────────────────────────
    import time as _time
    from pathlib import Path as _Path

    lint_errors = 0
    lint_warnings = 0
    lint_messages: list = []

    agent_path = None
    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        rt2 = get_kernel_runtime()
        agent_mgr = getattr(rt2, "workspace_agent_manager", None) if rt2 else None
        if agent_mgr and hasattr(agent_mgr, "_agents_dir"):
            ws_agents = _Path(str(agent_mgr._agents_dir)) / agent_id / "AGENT.md"
            if ws_agents.exists():
                agent_path = ws_agents
        if not agent_path:
            engine_agents = _Path(__file__).resolve().parent.parent.parent.parent / "engine" / "agents" / agent_id / "AGENT.md"
            if engine_agents.exists():
                agent_path = engine_agents
    except Exception:
        pass

    if agent_path:
        try:
            from core.management.agent_config_validator import validate_agent_file
            issues = validate_agent_file(agent_path)
            for iss in issues:
                lint_messages.append(f"{'ERROR' if iss.severity == 'error' else 'WARN'}: {iss.message}")
                if iss.severity == "error":
                    lint_errors += 1
                else:
                    lint_warnings += 1
        except Exception as e:
            lint_messages.append(f"Validate failed: {e}")
            lint_errors += 1

    lint_result = {
        "risk_level": "high" if lint_errors > 0 else "low",
        "blocked": lint_errors > 0,
        "error_count": lint_errors,
        "warning_count": lint_warnings,
        "messages": lint_messages,
    }

    if lint_errors > 0:
        try:
            await mgr.update_agent(agent_id, metadata={
                "governance": {
                    "status": "failed",
                    "lint_result": lint_result,
                    "submitted_at": _time.time(),
                    "last_op": "submit_for_review",
                },
                "verification": {
                    "status": "failed",
                    "source": "config_validator",
                },
            })
        except Exception:
            pass
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"配置校验未通过：{lint_errors} 个错误，{lint_warnings} 个警告",
                "lint": lint_result,
            },
        )

    try:
        await mgr.update_agent(agent_id,
            status="ready",
            metadata={
                "governance": {
                    "status": "pending",
                    "lint_result": lint_result,
                    "submitted_at": _time.time(),
                    "last_op": "submit_for_review",
                },
                "verification": {
                    "status": "pending",
                    "source": "config_validator",
                },
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update agent status: {e}")

    return {
        "status": "ok",
        "agent_id": agent_id,
        "new_status": "ready",
        "governance": "pending",
        "lint": {
            "risk_level": lint_result["risk_level"],
            "error_count": lint_errors,
            "warning_count": lint_warnings,
        },
    }


@router.post("/workspace/agents/{agent_id}/invoke")
async def invoke_agent(agent_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """Standardized invoke endpoint — external systems call this to run an agent.
    Body: { input: "your message", config?: {}, options?: {} }
    Returns: { run_id, output, tokens, status }
    """
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    inp = request.get("input") if isinstance(request, dict) else None
    if isinstance(inp, str):
        user_message = inp.strip()
    elif isinstance(inp, dict):
        user_message = str(inp.get("message") or inp.get("prompt") or "")
    else:
        user_message = str(request.get("message") or request.get("prompt") or "")

    from core.api.core_facade import run_workspace_agent
    resp = await run_workspace_agent(
        agent_info=agent,
        user_message=user_message,
        max_steps=int(request.get("config", {}).get("max_steps", 10) if isinstance(request.get("config"), dict) else 10),
        session_id=str(request.get("session_id", "") or f"invoke-{agent_id}"),
    )
    return {
        "run_id": resp.get("run_id", ""),
        "output": resp.get("output", ""),
        "tokens": resp.get("tokens", {}),
        "status": resp.get("status", "completed"),
        "error": resp.get("error"),
    }
