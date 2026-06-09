from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Annotated, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from core.api.deps import actor_from_http, rbac_guard
from core.api.utils.governance import gate_error_envelope, ui_url
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.syscalls.llm import sys_llm_generate
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
    import os as _os
    if _os.getenv("AIPLAT_APPROVALS_DISABLED", "").lower() in ("1", "true", "yes"):
        return True
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
    # Filter out engine agents (reserved IDs) — workspace page should only show workspace agents
    agents = [a for a in agents if a.id not in (mgr._reserved_ids or set())]
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
              "skills": a.skills, "tools": a.tools,
              "workflow_ids": a.workflow_ids, "agent_ids": a.agent_ids,
              "metadata": a.metadata}
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
        # If created from import (URL or file), materialize all source files into agent dir
        md = request.metadata or {}
        if md.get("source_url") or md.get("source_file_content"):
            try:
                import base64, io, zipfile
                import httpx as _httpx2
                base = mgr._resolve_agents_base_path()
                agent_dir = base / str(agent.id)
                zip_data = None
                if md.get("source_url"):
                    async with _httpx2.AsyncClient(timeout=30) as client:
                        r = await client.get(str(md["source_url"]), follow_redirects=True)
                        r.raise_for_status()
                    zip_data = r.content
                elif md.get("source_file_content"):
                    zip_data = base64.b64decode(str(md["source_file_content"]))
                if zip_data:
                    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                        for name in zf.namelist():
                            if name.endswith("/"):
                                continue
                            parts = name.split("/", 1)
                            if len(parts) < 2:
                                continue
                            rel = parts[1]
                            if rel == "AGENT.md":
                                continue
                            target = agent_dir / rel
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(name) as src:
                                target.write_bytes(src.read())
            except Exception:
                pass
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
        resp = await sys_llm_generate(model, messages)
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


def _extract_json_fallback(clean: str, raw_content: str, _re, _json, _log) -> dict | None:
    """Extract first JSON object from LLM output using bracket-matching fallback."""
    start = clean.find('{')
    if start == -1:
        _log.getLogger("auto-fill").warning(f"LLM response has no JSON: {raw_content[:500]}")
        return None
    depth = 0
    for i in range(start, len(clean)):
        if clean[i] == '{':
            depth += 1
        elif clean[i] == '}':
            depth -= 1
            if depth == 0:
                candidate = clean[start:i+1]
                for fix in [candidate,
                            _re.sub(r',\s*\}', '}', candidate),
                            _re.sub(r',\s*\]', ']', candidate),
                            _re.sub(r',\s*\}', '}', _re.sub(r',\s*\]', ']', candidate))]:
                    try:
                        return _json.loads(fix)
                    except _json.JSONDecodeError:
                        continue
                _log.getLogger("auto-fill").warning(f"LLM response unparseable: {candidate[:500]}")
                return None
    _log.getLogger("auto-fill").warning(f"LLM response has unclosed braces: {clean[:300]}")
    return None


def _scan_skills_direct() -> List[str]:
    """Scan engine + workspace skill directories directly (no capability graph).
    
    Fast path for auto-fill: reads SKILL.md frontmatter once, no SQLite, no graph.
    """
    import yaml as _yaml
    from pathlib import Path as _Py
    import os as _os
    entries = []
    
    # Engine skills: aiPlat-core/core/engine/skills/
    engine_root = None
    here = _Py(__file__).resolve()
    for _ in range(6):
        candidate = here.parent
        eng = candidate / "core" / "engine" / "skills"
        if eng.exists():
            engine_root = eng
            break
        here = here.parent
    if not engine_root:
        try:
            import core as _core
            if hasattr(_core, '__file__') and _core.__file__:
                engine_root = _Py(_os.path.dirname(_core.__file__)) / "engine" / "skills"
        except Exception:
            pass
    
    # Workspace skills: ~/.aiplat/skills/
    aiplat_home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    workspace_root = _Py(aiplat_home) / "skills"
    
    for root in (engine_root, workspace_root):
        if not root or not root.exists():
            continue
        for skill_dir in sorted(root.iterdir()):
            if not skill_dir.is_dir():
                continue
            md_file = skill_dir / "SKILL.md"
            if not md_file.exists():
                continue
            try:
                raw = md_file.read_text(encoding='utf-8', errors='ignore')
                if not raw.startswith('---'):
                    continue
                parts = raw.split('---', 2)
                if len(parts) < 3:
                    continue
                fm = _yaml.safe_load(parts[1]) or {}
                skill_id = str(fm.get("name") or skill_dir.name)
                label = str(fm.get("display_name") or fm.get("displayName") or skill_id)
                cat = str(fm.get("category") or "")
                desc = str(fm.get("description") or "")[:120]
                caps = fm.get("capabilities") or fm.get("capability") or []
                caps_str = ', '.join(str(c) for c in caps[:6]) if isinstance(caps, list) else ''
                ext = f" | {desc}" if desc else ""
                ext += f" | capabilities: {caps_str}" if caps_str else ""
                entries.append(f'  - {skill_id} | {label} | [{cat}]{ext}')
            except Exception:
                continue
    return entries


def _ensure_memory_config(raw) -> dict:
    """Return memory config, filling short_term defaults if empty."""
    if isinstance(raw, dict) and raw:
        return raw
    return {"type": "short_term", "recall_count": 5}


@router.post("/workspace/agents/auto-fill")
async def agent_auto_fill(req: AgentAutoFillRequest) -> AgentAutoFillResponse:
    """AI 智能填充：根据功能描述自动推荐 skills / tools / MCP / config / SOP 等。"""
    import json as _json
    import re as _re

    # ── Build skill catalog (direct disk scan — no capability graph) ──
    try:
        skill_entries = _scan_skills_direct()
    except Exception:
        skill_entries = []
    if not skill_entries:
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
        ws_mgr = _Mgr(scope="workspace")
        all_servers = list(mgr.list_servers() or []) + list(ws_mgr.list_servers() or [])
        for srv in all_servers:
            desc = str(getattr(srv, 'metadata', {}).get('description', '') or '')[:80]
            tools = ', '.join(str(t) for t in (getattr(srv, 'allowed_tools', []) or [])[:3])
            ext = f" | {desc}" if desc else ""
            ext += f" | tools: {tools}" if tools else ""
            mcp_entries.append(
                f"  - {srv.name}: enabled={getattr(srv,'enabled',True)} "
                f"transport={getattr(srv,'transport','')}{ext}"
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
                desc = str((getattr(a, 'metadata', {}) or {}).get('description', '') or '')[:80]
                ext = f" | {desc}" if desc else ""
                agent_catalog.append(
                    f"  - id={a.id} | name={a.name} | type={a.type}{ext}"
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
                    wdesc = str(data.get("description", "") or "")[:100]
                    ext = f" | {wdesc}" if wdesc else ""
                    wf_catalog.append(f"  - {f.stem} | {nm} | stages={sz}{ext}")
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

    prompt = await _async_prompt_resolve("agent-auto-fill",
        name=req.name or '(待填写)',
        description=req.description or '(无)',
        role_section=role_section,
        skills_catalog=chr(10).join(skill_entries[:50]) or '(无)',
        tools_catalog=chr(10).join(tool_entries[:30]) or '(无)',
        mcp_catalog=chr(10).join(mcp_entries[:20]) or '(无)',
        agent_catalog=chr(10).join(agent_catalog[:40]) or '(无)',
        wf_catalog=chr(10).join(wf_catalog[:20]) or '(无)',
        role_phrase="和已确认的角色定义" if role_section else "",
    )

    # ── Call LLM ─────────────────────────────────────────────────
    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        model_name = best_model_for_purpose("agent_creation")
        model = create_selected_adapter(model_name=model_name)
        from core.harness.utils.prompt_loader import _async_prompt_resolve
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("agent-auto-fill-system-role")},
            {"role": "user", "content": prompt},
        ]
        resp = await sys_llm_generate(model, messages)
        content = resp.content if hasattr(resp, 'content') else str(resp)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")

    # ── Parse JSON response ──────────────────────────────────────
    import logging as _log
    clean = content.strip()
    if clean.startswith("```"):
        clean = _re.sub(r'^```\w*\n?', '', clean)
        clean = _re.sub(r'\n?```$', '', clean)
    # Use JSONDecoder to extract first valid JSON object (handles nesting properly)
    try:
        decoder = _json.JSONDecoder()
        data, _end = decoder.raw_decode(clean)
    except _json.JSONDecodeError:
        # Fallback: find JSON between first { and matching }, then fix common LLM issues
        data = _extract_json_fallback(clean, content, _re, _json, _log)
    if data is None:
        raise HTTPException(status_code=422, detail="Failed to parse LLM response as JSON")

    # Resolve model via infra instead of trusting LLM choice
    agent_type = str(data.get("agent_type", "base"))[:20]
    config = data.get("config", {}) if isinstance(data.get("config"), dict) else {}
    try:
        from core.harness.utils.model_injection import best_model_for_agent_type
        config["model"] = best_model_for_agent_type(agent_type)
    except Exception:
        pass

    skills = list(data.get("skills", []))[:20]
    tools = list(data.get("tools", []))[:20]
    if not skills and not tools:
        _log.getLogger("auto-fill").warning(
            f"LLM returned empty skills+tools. agent_type={agent_type}, raw_response={content[:500]}"
        )

    return AgentAutoFillResponse(
        agent_type=agent_type,
        config=config,
        skills=skills,
        tools=tools,
        mcp_ids=list(data.get("mcp_ids", []))[:10],
        agent_ids=list(data.get("agent_ids", []))[:10],
        memory_config=_ensure_memory_config(data.get("memory_config")),
        sop_text=str(data.get("sop_text", ""))[:8000],
        reasoning=str(data.get("reasoning", ""))[:500],
        workflow_ids=list(data.get("workflow_ids", []))[:10],
        template_id="",
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
        resp = await sys_llm_generate(model, messages)
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
    entries = _scan_skills_direct()
    if not entries:
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
        ws_mgr = _Mgr(scope="workspace")
        all_servers = list(mgr.list_servers() or []) + list(ws_mgr.list_servers() or [])
        for srv in all_servers:
            desc = str(getattr(srv, 'metadata', {}).get('description', '') or '')[:80]
            tools = ', '.join(str(t) for t in (getattr(srv, 'allowed_tools', []) or [])[:3])
            ext = f" | {desc}" if desc else ""
            ext += f" | tools: {tools}" if tools else ""
            entries.append(
                f"  - {srv.name}: enabled={getattr(srv,'enabled',True)} "
                f"transport={getattr(srv,'transport','')}{ext}"
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
                desc = str((getattr(a, 'metadata', {}) or {}).get('description', '') or '')[:80]
                ext = f" | {desc}" if desc else ""
                entries.append(f"  - id={a.id} | name={a.name} | type={a.type}{ext}")
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
                    wdesc = str(data.get("description", "") or "")[:100]
                    ext = f" | {wdesc}" if wdesc else ""
                    entries.append(f"  - {f.stem} | {nm} | stages={sz}{ext}")
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
        "mcp_ids": agent.mcp_ids,
        "workflow_ids": agent.workflow_ids,
        "agent_ids": agent.agent_ids,
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


@router.post("/workspace/agents/{agent_id}/sign")
async def sign_workspace_agent(agent_id: str, request: Dict[str, Any], http_request: Request = None, rt: RuntimeDep = None):
    """
    Sign an agent with an Ed25519 private key, writing the signature to
    AGENT.manifest.json and updating provenance metadata.

    Body: { "private_key": "-----BEGIN PRIVATE KEY-----..." }
    """
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")

    if http_request is not None:
        deny = await rbac_guard(http_request=http_request, payload={}, action="sign", resource_type="agent", resource_id=str(agent_id))
        if deny:
            return deny

    private_key = str(request.get("private_key") or "").strip()
    private_key = private_key.replace("\\n", "\n")  # normalize escaped newlines from frontend
    if not private_key:
        raise HTTPException(status_code=400, detail="private_key is required")

    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        from core.harness.infrastructure.crypto.signature import sign_skill as sign_agent

        agent_dir = Path(agent.metadata.get("filesystem", {}).get("agent_dir") or agent.metadata.get("provenance", {}).get("agent_dir") or "")
        if not agent_dir or not agent_dir.exists():
            raise HTTPException(status_code=500, detail="Agent directory not found")

        # Ensure integrity is computed
        mgr._enrich_agent_provenance_and_integrity(agent.metadata, agent_dir=agent_dir)
        integ = agent.metadata.get("integrity", {})
        bundle_sha256 = integ.get("bundle_sha256", "")
        if not bundle_sha256:
            raise HTTPException(status_code=500, detail="Could not compute bundle_sha256")

        version = str(getattr(agent, "version", "0.1.0") or "0.1.0")

        signature = sign_agent(
            private_key=private_key,
            skill_id=agent_id,  # reuses the same canonical payload format
            version=version,
            bundle_sha256=bundle_sha256,
        )

        # Write AGENT.manifest.json with the signature
        manifest_path = agent_dir / "AGENT.manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        manifest["signature"] = signature
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        # Re-enrich provenance to pick up the new signature from the manifest
        mgr._enrich_agent_provenance_and_integrity(agent.metadata, agent_dir=agent_dir)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid private key: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Signing failed: {str(e)}")

    return {
        "status": "signed",
        "bundle_sha256": bundle_sha256,
        "version": version,
        "signature": signature,
    }


@router.post("/workspace/agents/{agent_id}/toggle-enabled")
async def toggle_agent_enabled(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=500, detail="agent manager not available")
    result = await mgr.toggle_enabled(agent_id)
    if result is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return {"agent_id": agent_id, "enabled": result}


@router.post("/workspace/agents/{agent_id}/enable")
async def enable_workspace_agent(agent_id: str, http_request: Request = None, rt: RuntimeDep = None):
    """
    Enable an agent with governance gates: autosmoke + signature verification + approval.

    On success, the agent is enabled and ready for execution.
    """
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")

    if http_request is not None:
        deny = await rbac_guard(http_request=http_request, payload={}, action="enable", resource_type="agent", resource_id=str(agent_id))
        if deny:
            return deny

    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.status == "deprecated":
        raise HTTPException(status_code=409, detail="Deprecated agent cannot be enabled — use restore first")

    store = _store(rt)
    from core.governance.gating import gate_with_change_control, autosmoke_enforce, require_targets_verified

    # 1. Autosmoke + change control gate
    if store:
        autosmoke_enforce(rt)
        change_id = await gate_with_change_control(
            store=store,
            operation=f"{mgr._scope}.agent.enable",
            user_id="admin",
            target_type="agent",
            target_id=agent_id,
        )
        await require_targets_verified(store=store, target_type="agent", targets=[agent_id])
    else:
        change_id = None

    # 2. Signature verification gate
    approval_request_id = None
    try:
        from core.security.skill_signature_gate import get_trusted_skill_pubkeys_map, signature_gate_eval

        trusted = await get_trusted_skill_pubkeys_map(store) if store else {}
        prov2 = mgr.compute_agent_signature_verification(agent, trusted) if hasattr(mgr, "compute_agent_signature_verification") else {}

        gate = signature_gate_eval(
            metadata=agent.metadata,
            trusted_keys_count=len(trusted),
        )
        if gate.get("required") is True:
            from core.security.skill_signature_gate import require_skill_signature_gate_approval, is_approval_resolved_approved
            approval_request_id = await require_skill_signature_gate_approval(
                skill_id=agent_id,
                verified=prov2.get("signature_verified", False),
                reason=prov2.get("signature_verified_reason") or gate.get("reason", ""),
                key_id=prov2.get("signature_verified_key_id", ""),
                user_id="admin",
                details=f"enable workspace agent {agent_id}",
            )
            approved = await is_approval_resolved_approved(approval_request_id)
            if not approved:
                raise HTTPException(
                    status_code=409,
                    detail=gate_error_envelope(
                        code="not_approved",
                        message="Agent signature verification requires approval",
                        approval_request_id=str(approval_request_id),
                        next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_request_id)}],
                    ),
                )

            if store:
                try:
                    from core.governance.changeset import record_changeset
                    await record_changeset(
                        store=store,
                        name="enable_workspace_agent",
                        target_type="agent",
                        target_id=agent_id,
                        status="approved",
                        approval_request_id=approval_request_id,
                        user_id="admin",
                    )
                except Exception:
                    pass
    except HTTPException:
        raise
    except Exception as e:
        logging.warning(f"Agent enable signature gate error (non-blocking): {e}")

    # 3. Actually enable
    agent.enabled = True
    agent.updated_at = datetime.now()

    # Audit
    if store:
        try:
            await store.add_audit_log(
                action="enable_agent",
                actor_id="admin",
                target_type="agent",
                target_id=agent_id,
                status="ok",
                metadata={"change_id": change_id, "approval_request_id": str(approval_request_id) if approval_request_id else None},
            )
        except Exception:
            pass

    return {
        "status": "enabled",
        "approval_request_id": str(approval_request_id) if approval_request_id else None,
        "change_id": change_id,
    }


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


# ── Agent Import Detection (analogous to workspace_skills import-detect) ──

@router.post("/workspace/agents/import-detect")
async def detect_agent_import(request: Dict[str, Any], rt: RuntimeDep = None):
    """AI 检测导入的 agent 配置。接收 URL 或 zip 文件，返回推荐配置。"""
    import yaml as _yaml
    import io
    import zipfile
    
    agmd_body = ""
    url = str(request.get("url") or "").strip()
    file_content = str(request.get("file_content") or "").strip()
    
    if url:
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                for name in zf.namelist():
                    if name.endswith("AGENT.md"):
                        agmd_body = zf.read(name).decode("utf-8", errors="ignore")
                        break
                if not agmd_body:
                    for name in zf.namelist():
                        if name.endswith(".md"):
                            agmd_body = zf.read(name).decode("utf-8", errors="ignore")
                            break
        except Exception as e:
            return {"error": f"Failed to download/parse URL: {str(e)}"}
    elif file_content:
        try:
            import base64
            data = base64.b64decode(file_content)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for name in zf.namelist():
                    if name.endswith("AGENT.md"):
                        agmd_body = zf.read(name).decode("utf-8", errors="ignore")
                        break
        except Exception:
            agmd_body = file_content[:20000]
    
    if not agmd_body:
        return {"error": "No AGENT.md found in import source. Provide url or file_content."}
    
    # Extract YAML frontmatter
    existing = {}
    sop_body = agmd_body
    if agmd_body.startswith("---"):
        parts = agmd_body.split("---", 2)
        if len(parts) >= 3:
            try:
                existing = _yaml.safe_load(parts[1]) or {}
            except Exception:
                pass
            sop_body = parts[2].strip() if len(parts) > 2 else agmd_body
    
    name = str(existing.get("name") or "")
    desc = str(existing.get("description") or "")
    
    try:
        config = await _ai_recommend_agent_config(
            agmd_body=sop_body,
            name=name,
            description=desc,
        )
        config["detected_name"] = name or config.get("detected_name", "")
        config["detected_description"] = desc
        config["sop_body"] = sop_body
        config["display_name"] = str(existing.get("display_name") or existing.get("displayName") or name)
        return config
    except Exception as e:
        return {"error": f"AI detection failed: {str(e)}"}


async def _ai_recommend_agent_config(
    agmd_body: str, name: str = "", description: str = "",
) -> dict:
    """LLM 分析 AGENT.md 正文，返回推荐的 agent 配置。"""
    from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
    from core.harness.utils.prompt_loader import _async_prompt_resolve
    
    model_name = best_model_for_purpose("agent_creation")
    model = create_selected_adapter(model_name=model_name)
    system_prompt = await _async_prompt_resolve("agent-import-detect")
    user_content = f"Agent 名称: {name or '(未命名)'}\n描述: {description or '(无)'}\n\nAGENT.md:\n{agmd_body[:8000]}"
    
    from core.harness.syscalls.llm import sys_llm_generate
    response = await sys_llm_generate(
        model,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    
    text = str(getattr(response, "content", "") or "")
    from core.utils.json_utils import parse_json
    return parse_json(text) or {}


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


@router.post("/workspace/agents/installer/upload-plan")
async def workspace_agents_installer_upload_plan(
    file: UploadFile = File(...),
    subdir: str = Form(""),
    asset_id: str = Form(""),
    auto_detect_subdir: str = Form("true"),
    rt: RuntimeDep = None,
):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        plan = await mgr.installer_plan(
            source_type="zip", path=tmp_path,
            subdir=subdir or None, asset_id=asset_id or None,
            auto_detect_subdir=auto_detect_subdir.lower() in ("true", "1", "yes"),
        )
        return {"status": "ok", **plan}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"upload_plan_failed: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/workspace/agents/installer/upload-install")
async def workspace_agents_installer_upload_install(
    file: UploadFile = File(...),
    subdir: str = Form(""),
    asset_id: str = Form(""),
    auto_detect_subdir: str = Form("true"),
    allow_overwrite: str = Form("false"),
    plan_id: str = Form(""),
    http_request: Request = None,
    rt: RuntimeDep = None,
):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        result = await mgr.installer_install(
            source_type="zip", path=tmp_path,
            subdir=subdir or None, asset_id=asset_id or None,
            auto_detect_subdir=auto_detect_subdir.lower() in ("true", "1", "yes"),
            allow_overwrite=allow_overwrite.lower() in ("true", "1", "yes"),
        )
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"upload_install_failed: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


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


@router.get("/workspace/agents/seeds")
async def list_agent_seeds(rt: RuntimeDep = None):
    """List available agent seed templates from workspace_seeds/agents/.
    These are read-only templates that the user can optionally install.
    """
    from pathlib import Path as _P
    import yaml as _yaml

    seeds_dir = _P(__file__).resolve().parents[3] / "core" / "workspace_seeds" / "agents"
    if not seeds_dir.exists():
        return {"seeds": [], "total": 0}

    seeds = []
    for item in sorted(seeds_dir.iterdir()):
        if not item.is_dir():
            continue
        agent_md = item / "AGENT.md"
        if not agent_md.exists():
            continue
        try:
            raw = agent_md.read_text(encoding="utf-8")
            fm = {}
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    fm = _yaml.safe_load(parts[1]) or {}
            installed = (_P.home() / ".aiplat" / "agents" / item.name).exists()
            seeds.append({
                "id": item.name,
                "name": str(fm.get("display_name") or fm.get("name") or item.name),
                "description": str(fm.get("description") or ""),
                "category": str(fm.get("category") or ""),
                "tags": fm.get("tags") or [],
                "installed": installed,
            })
        except Exception:
            continue
    return {"seeds": seeds, "total": len(seeds)}


@router.post("/workspace/agents/seeds/{seed_id}/install")
async def install_agent_seed(seed_id: str, rt: RuntimeDep = None):
    """Install a workspace agent seed template into ~/.aiplat/agents/."""
    import shutil as _shutil
    from pathlib import Path as _P

    seeds_dir = _P(__file__).resolve().parents[3] / "core" / "workspace_seeds" / "agents"
    seed_dir = seeds_dir / seed_id
    if not seed_dir.exists():
        raise HTTPException(status_code=404, detail=f"Seed template '{seed_id}' not found")

    workspace_dir = _P.home() / ".aiplat" / "agents"
    dst = workspace_dir / seed_id
    if dst.exists():
        raise HTTPException(status_code=409, detail=f"Agent '{seed_id}' already installed")

    try:
        workspace_dir.mkdir(parents=True, exist_ok=True)
        _shutil.copytree(seed_dir, dst)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to install seed: {str(e)}")

    # Reload workspace agent manager so the new agent appears
    mgr = _ws_agent_mgr(rt)
    if mgr and hasattr(mgr, 'reload'):
        try:
            mgr.reload()
        except Exception:
            pass

    return {"status": "installed", "id": seed_id}
