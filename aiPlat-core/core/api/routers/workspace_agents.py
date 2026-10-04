from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Annotated, Dict, List, Optional
from pydantic import BaseModel

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from core.api.deps import actor_from_http, rbac_guard
from core.api.utils.governance import gate_error_envelope, ui_url
from core.api.core_facade import KernelRuntime  # P0-A2: 经 CoreFacade
from core.api.core_facade import get_kernel_runtime  # P0-A2: 经 CoreFacade
from core.api.core_facade import sys_llm_generate  # P0-A2: 经 CoreFacade
from core.schemas_agents import AgentAutoFillBatchRequest, AgentAutoFillBatchResponse
from core.schemas_agents import AgentCreateRequest, AgentUpdateRequest, AgentAutoFillRequest, AgentAutoFillResponse, RoleDefinitionResponse
import asyncio as _asyncio

# LLM config for auto-fill endpoints — longer timeout for local CPU models
from core.adapters.llm.base import LLMConfig as _LlmConfig
kLlmConfig = _LlmConfig(model="", timeout=120)

router = APIRouter()

# agent-role-system / agent-auto-fill* live in apps/builder/prompts; core server
# never imports that package, so register here before auto-fill resolves them.
def _ensure_builder_agent_prompts() -> None:
    try:
        from core.apps.builder.prompts import register_builder_prompts
        register_builder_prompts()
    except Exception:
        logging.getLogger(__name__).warning(
            "builder agent prompts not registered — auto-fill may 503",
            exc_info=True,
        )


_ensure_builder_agent_prompts()

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


@router.get("/workspace/agents", response_model=Dict[str, Any])
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


@router.post("/workspace/agents", response_model=Dict[str, Any])
async def create_workspace_agent(request: AgentCreateRequest, http_request: Request, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    try:
        md0 = request.metadata or {}
        # Imports may carry stale foreign IDs — keep for audit; normal create must bind known assets only.
        if not (md0.get("source_url") or md0.get("source_file_content")):
            _raise_if_unknown_bindings(
                skills=request.skills,
                tools=request.tools,
                mcp_ids=request.mcp_ids,
                agent_ids=request.agent_ids,
                workflow_ids=request.workflow_ids,
            )
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
            metadata={**(request.metadata or {}),
                      **({"trigger_conditions": getattr(request, "trigger_conditions", None)}
                         if getattr(request, "trigger_conditions", None) else {}),
                      **({"permissions": getattr(request, "permissions", None)}
                         if getattr(request, "permissions", None) else {}),},
            reuse_equivalent=bool(getattr(request, "reuse_equivalent", True)),
        )
        # If created from import (URL or file), materialize all source files into agent dir
        md = request.metadata or {}
        if md.get("source_url") or md.get("source_file_content"):
            try:
                import base64, io, shutil, tempfile, zipfile
                import httpx as _httpx2
                from pathlib import Path as _Path

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
                    with tempfile.TemporaryDirectory(prefix="aiplat-agent-create-") as td:
                        root = _Path(td) / "unzipped"
                        root.mkdir(parents=True, exist_ok=True)
                        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                            zf.extractall(str(root))
                        # Find agent dirs by searching for AGENT.md recursively
                        agent_dirs = sorted(root.rglob("AGENT.md"))
                        if agent_dirs:
                            sd = agent_dirs[0].parent
                            for item in sd.iterdir():
                                src = sd / item.name
                                dst = agent_dir / item.name
                                if dst.exists():
                                    if dst.is_dir():
                                        shutil.rmtree(dst)
                                    else:
                                        dst.unlink()
                                if src.is_dir():
                                    shutil.copytree(src, dst)
                                else:
                                    shutil.copy2(src, dst)
                            # Enrich frontmatter after extraction
                            try:
                                from core.management.asset_installer import AgentInstaller
                                inst = AgentInstaller(target_base_dir=base)
                                inst._enrich_asset_frontmatter(agent_dir)
                            except Exception as e:
                                logging.warning(str(e), exc_info=True)
                        else:
                            # Fallback: flat zip without AGENT.md wrapper dir
                            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                                for name in zf.namelist():
                                    if name.endswith("/"):
                                        continue
                                    rel = "/".join(name.split("/")[1:]) if "/" in name else name
                                    if not rel or rel == "AGENT.md":
                                        continue
                                    target = agent_dir / rel
                                    target.parent.mkdir(parents=True, exist_ok=True)
                                    with zf.open(name) as src:
                                        target.write_bytes(src.read())
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        # Mark as pending verification (best-effort)
        try:
            await mgr.update_agent(
                str(agent.id),
                metadata={"verification": {"status": "pending", "updated_at": time.time(), "source": "autosmoke"}},
            )
        except Exception as e:
            logging.warning(str(e), exc_info=True)

        # Auto-smoke (async, dedup): trigger on create/update to validate the full chain.
        try:
            store = _store(rt)
            sched = _job_scheduler(rt)
            if store is not None and sched is not None:
                from core.api.core_facade import enqueue_autosmoke  # P0-A2: 经 CoreFacade

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
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)

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
        except Exception as e:
            logging.warning(str(e), exc_info=True)

        # Auto-grant execute permission to the creating user
        try:
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "system")
            from core.apps.skills.registry import get_skill_registry
            # Get PermissionManager via the runtime's permission subsystem
            pm = getattr(rt, "permission_manager", None) if rt else None
            if pm is None:
                from core.api.core_facade import get_permission_manager  # via facade — fixed incorrect path
                pm = get_permission_manager()
            if pm and hasattr(pm, "grant_permission"):
                pm.grant_permission(str(actor_id), str(agent.id), "execute", granted_by="auto_create")
        except Exception as e:
            logging.warning(str(e), exc_info=True)

        return {"id": agent.id, "status": "created", "name": agent.name}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/workspace/agents/generate-role-definition", response_model=Dict[str, Any])
async def generate_role_definition(req: AgentAutoFillRequest) -> Any:
    """基于功能描述生成角色定义，让用户确认后再进行下一步的技能/工具推荐。
    
    支持 async_mode=true 参数：
      - async_mode=true: 立即返回 task_id，后台执行，前端轮询 GET /generate-role-definition/{task_id}
      - async_mode=false (默认): 同步等待 LLM 返回
    """
    async_mode = bool(getattr(req, "async_mode", False))
    if async_mode:
        tid = _create_role_def_task()
        _asyncio.create_task(_run_role_def_task(tid, req))
        return {"task_id": tid, "status": "processing", "role_name": "", "responsibilities": [], "scenarios": [], "required_capabilities": [], "workflow_hint": "", "reasoning": "后台处理中..."}

    import json as _json, re as _re

    from core.api.core_facade import _async_prompt_resolve  # P0-A2: 经 CoreFacade
    prompt = await _async_prompt_resolve("agent-role-definition",
        name=req.name or '(待填写)', description=req.description or '(无)',
    )

    try:
        from core.api.core_facade import best_model_for_purpose  # P0-A2: 经 CoreFacade
        from core.api.core_facade import sys_llm_generate  # P0-A2: 经 CoreFacade
        model_name = best_model_for_purpose("agent_creation")
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("agent-role-system")},
            {"role": "user", "content": prompt},
        ]
        resp = await sys_llm_generate(model=None, prompt=messages, model_name=model_name)
        content = resp.content if hasattr(resp, 'content') else str(resp)

        clean = content.strip()
        if clean.startswith("```"):
            clean = _re.sub(r'^```\w*\n?', '', clean)
            clean = _re.sub(r'\n?```$', '', clean)
        match = _re.search(r'\{[\s\S]*\}', clean)
        if match:
            try:
                data = _json.loads(match.group(0))
            except _json.JSONDecodeError:
                raise HTTPException(status_code=422, detail="LLM 返回格式异常，请重试。如持续失败，可手动绑定 skills/tools")
        else:
            raise HTTPException(status_code=422, detail="LLM 未返回有效的 JSON 格式，请重试")

        return RoleDefinitionResponse(
            role_name=str(data.get("role_name", ""))[:20],
            responsibilities=list(data.get("responsibilities", []))[:8],
            scenarios=list(data.get("scenarios", []))[:5],
            required_capabilities=list(data.get("required_capabilities", []))[:8],
            workflow_hint=str(data.get("workflow_hint", ""))[:500],
            reasoning=str(data.get("reasoning", ""))[:500],
        ).model_dump()
    except HTTPException:
        raise
    except Exception as e:
        import traceback, logging
        logging.getLogger("auto-fill").error("generate_role_definition crashed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


def _extract_json_fallback(clean: str, raw_content: str, _re, _json, _log) -> dict | None:
    """Extract first JSON object from LLM output using bracket-matching fallback.
    
    Handles common LLM JSON mistakes: trailing commas, Python bools (True/False/None),
    single quotes, and text preamble before JSON.
    """
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
                fixes = [
                    candidate,
                    _re.sub(r',\s*\}', '}', candidate),
                    _re.sub(r',\s*\]', ']', candidate),
                    _re.sub(r',\s*\}', '}', _re.sub(r',\s*\]', ']', candidate)),
                    # Python bool → JSON bool
                    candidate.replace(': True', ': true').replace(': False', ': false').replace(': None', ': null'),
                    # Single quotes → double quotes (for string values only)
                    _re.sub(r":\s*'([^']*)'", r': "\1"', candidate),
                ]
                for fix in fixes:
                    try:
                        return _json.loads(fix)
                    except _json.JSONDecodeError:
                        continue
                _log.getLogger("auto-fill").warning(f"LLM response unparseable (tried {len(fixes)} fixes): {candidate[:300]}")
                return None
    _log.getLogger("auto-fill").warning(f"LLM response has unclosed braces: {clean[:300]}")
    return None


# LLM often invents engine skill / tool names; map to workspace MultiSelect ids.
_SKILL_ALIAS_TO_WORKSPACE: Dict[str, str] = {
    "file_read": "knowledge_ingest_doc",
    "text_generation": "summarize",
    "summarization": "summarize",
    "summarize": "summarize",
    "doc_query": "knowledge_query_doc",
    "document_query": "knowledge_query_doc",
    "knowledge_query": "knowledge_query_doc",
    "knowledge_ingest": "knowledge_ingest_doc",
    "information_search": "knowledge_multi_query",
    "code_generation": "code",
    "code_gen": "code",
    "requirement_analysis": "requirement_analysis",
    "http_request": "http_request",
    "http": "http_request",
    "grilling": "requirement_analysis",
}

_TOOL_ALIAS_TO_NAME: Dict[str, str] = {
    "file_operations": "file_operations",
    "file_read": "file_operations",
    "file_write": "file_operations",
    "code_execution": "code",
    "code_execution_sandbox": "code",
    "http": "http",
    "http_request": "http",
    "search": "search",
    "web_search": "web_search",
    "information_search": "web_search",
    "webfetch": "webfetch",
    "browser": "browser",
}


def _scan_skills_direct(*, workspace_only: bool = False) -> List[Dict[str, Any]]:
    """Scan skill directories; return {id, name, display_name, category, description, triggers}.

    workspace_only=True: only ~/.aiplat/skills — same pool as 应用库 Agent MultiSelect.
    """
    import yaml as _yaml
    from pathlib import Path as _Py
    import os as _os
    entries: List[Dict[str, Any]] = []
    seen: set = set()

    engine_root = None
    if not workspace_only:
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)

    aiplat_home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    workspace_root = _Py(aiplat_home) / "skills"

    roots = (workspace_root,) if workspace_only else (workspace_root, engine_root)
    for root in roots:
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
                # Prefer directory name: matches workspace SkillManager id / frontend value
                skill_id = str(skill_dir.name).strip()
                skill_name = str(fm.get("name") or skill_id).strip()
                if skill_id in seen:
                    continue
                seen.add(skill_id)
                entries.append({
                    "id": skill_id,
                    "name": skill_name,
                    "display_name": str(fm.get("display_name") or fm.get("displayName") or skill_name or skill_id),
                    "category": str(fm.get("category") or ""),
                    "description": str(fm.get("description") or ""),
                    "triggers": list(fm.get("triggers") or []),
                })
            except Exception:
                continue
    return entries


def _scan_tools_direct() -> List[Dict[str, str]]:
    """List bindable tool names for auto-fill (same names frontend MultiSelect uses)."""
    known = [
        ("calculator", "执行数学计算"),
        ("search", "搜索互联网信息"),
        ("file_operations", "读写文件"),
        ("webfetch", "抓取网页内容"),
        ("http", "发送 HTTP 请求"),
        ("code", "沙箱执行代码"),
        ("database", "数据库查询"),
        ("browser", "浏览器自动化"),
        ("web_search", "统一 Web 搜索"),
        ("routed_retrieve", "意图路由检索"),
    ]
    return [{"id": n, "name": n, "description": d} for n, d in known]


def _scan_mcp_direct() -> List[Dict[str, str]]:
    """List bindable MCP server names (engine + workspace)."""
    entries: List[Dict[str, str]] = []
    seen = set()
    try:
        from core.management.mcp_manager import MCPManager as _Mgr

        for scope in (None, "workspace"):
            mgr = _Mgr() if scope is None else _Mgr(scope="workspace")
            for srv in list(mgr.list_servers() or []):
                name = str(getattr(srv, "name", "") or "").strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                meta = getattr(srv, "metadata", None) or {}
                desc = ""
                if isinstance(meta, dict):
                    desc = str(meta.get("description") or "")[:80]
                entries.append(
                    {
                        "id": name,
                        "name": name,
                        "description": desc
                        or f"transport={getattr(srv, 'transport', '')} enabled={getattr(srv, 'enabled', True)}",
                    }
                )
    except Exception:  # noqa: cleanup-best-effort
        pass
    return entries


def _resolve_skill_id(token: str, catalog_ids: set, name_to_id: Dict[str, str]) -> Optional[str]:
    """Map LLM token → workspace skill id, or None if unknown."""
    if not token or not isinstance(token, str):
        return None
    t = token.strip()
    if not t:
        return None
    if t in catalog_ids:
        return t
    if t in name_to_id and name_to_id[t] in catalog_ids:
        return name_to_id[t]
    alias = _SKILL_ALIAS_TO_WORKSPACE.get(t) or _SKILL_ALIAS_TO_WORKSPACE.get(t.lower())
    if alias and alias in catalog_ids:
        return alias
    # display-name / fuzzy: case-insensitive id match
    lower = {c.lower(): c for c in catalog_ids}
    if t.lower() in lower:
        return lower[t.lower()]
    return None


def _resolve_tool_names(tokens: List[str], text_blob: str = "") -> List[str]:
    """Map explicit tool tokens → real tool names. No free-text keyword expansion."""
    tool_ids = {t["id"] for t in _scan_tools_direct()}
    out: List[str] = []

    def _add(name: str) -> None:
        if name in tool_ids and name not in out:
            out.append(name)

    for tok in tokens or []:
        if not isinstance(tok, str):
            continue
        t = tok.strip()
        if t in tool_ids:
            _add(t)
            continue
        alias = _TOOL_ALIAS_TO_NAME.get(t) or _TOOL_ALIAS_TO_NAME.get(t.lower())
        if alias:
            _add(alias)
    # text_blob kept for call-site compat; intentionally unused (SOP-driven bind instead)
    _ = text_blob
    return out[:6]


# Soft SOP tokens must never auto-bind these unless explicitly backticked / needed_*.
_SOFT_BIND_DENY_SKILLS = frozenset({
    "app_page_generation", "webhook_trigger", "auth_agent", "parser_agent",
    "orchestrator_agent", "capability_scout", "refactor_flat_to_layered",
    "ponytail-lazy", "security-auditor", "skill_format_validate", "test-engineer",
    "web-perf-auditor", "output_style_adhd", "last30days",
})
_SOFT_BIND_DENY_TOOLS = frozenset({
    "search", "web_search", "webfetch", "browser", "database", "http",
    "calculator", "routed_retrieve",
})
_PPT_LIKE_HINTS = ("PPT", "ppt", "pptx", "幻灯", "演示文稿", "模版", "模板")
_PPT_MIN_TOOLS = ("file_operations", "code")
_PPT_MIN_SKILLS = ("requirement_analysis", "summarize", "code")


def _map_capabilities_to_skills(capabilities: list, skill_catalog: list) -> list:
    """Map role capabilities to skills via SKILL.md description + triggers overlap.
    
    No hardcoded keywords. Pure configuration-driven.
    Returns skill ids (frontend MultiSelect values).
    """
    scored = []
    for skill in skill_catalog:
        desc = (skill.get('description','') or '').lower()
        trigs = ' '.join(str(t) for t in (skill.get('triggers') or [])).lower()
        name = (skill.get('name','') or '').lower()
        disp = (skill.get('display_name','') or '').lower()
        sid = skill.get('id') or skill.get('name') or ''
        
        score = 0
        for cap in capabilities:
            cap_lower = cap.lower()
            if cap_lower in trigs:
                score += 6
            if cap_lower in name or cap_lower in disp:
                score += 5
            if cap_lower in desc:
                score += 4
            cap_bigrams = {cap_lower[i:i+2] for i in range(len(cap_lower)-1)} if len(cap_lower) >= 2 else set()
            trig_bigrams = {trigs[i:i+2] for i in range(len(trigs)-1)} if len(trigs) >= 2 else set()
            desc_bigrams = {desc[i:i+2] for i in range(len(desc)-1)} if len(desc) >= 2 else set()
            trig_hit = len(cap_bigrams & trig_bigrams)
            desc_hit = len(cap_bigrams & desc_bigrams)
            if trig_hit >= 1:
                score += trig_hit * 3
            elif desc_hit >= 2:
                score += desc_hit
        if score > 0 and sid:
            scored.append((sid, score))
    scored.sort(key=lambda x: -x[1])
    return [s[0] for s in scored[:3]]


def _generate_sop_from_role(role_def: dict, skills: list) -> str:
    """Generate SOP from role definition structure — no LLM, no hardcoding."""
    role_name = str(role_def.get("role_name", "") or "")
    resp = list(role_def.get("responsibilities", []) or [])[:4]
    
    persona = role_name or "Agent"
    resp_text = "；".join(resp) if resp else "处理相关任务"
    
    workflow_lines = ["1. 理解用户输入，澄清模糊需求"]
    for i, r in enumerate(resp[:3]):
        workflow_lines.append(f"{i+2}. {r}")
    workflow_lines.append(f"{len(workflow_lines)+1}. 综合信息生成准确回答，必要时引用知识库")
    
    skills_hint = f"- 可用技能: {', '.join(skills[:5])}" if skills else ""
    
    return f"""## Persona
{persona}，{resp_text}。

## Workflow
{chr(10).join(workflow_lines)}

## Knowledge Base
{skills_hint}

## Constraints
- 不回答超出职责范围的问题
- 保护用户隐私，不泄露敏感信息"""


def _ensure_memory_config(raw) -> dict:
    """Return memory config, filling short_term defaults if empty."""
    if isinstance(raw, dict) and raw:
        return raw
    return {"type": "short_term", "recall_count": 5}


def _suggest_skill_name(capability: str) -> str:
    """Suggest a Skill name for a given capability."""
    # Map common capability keywords to Chinese Skill names
    _name_map = {
        "诊断": "客户诊断", "分析": "数据分析", "检索": "知识检索",
        "文档": "文档处理", "代码": "代码生成", "测试": "测试执行",
        "审查": "内容审查", "监控": "监控告警", "报告": "报告生成",
        "安全": "安全检查", "合规": "合规审核", "检测": "异常检测",
        "图谱": "关联图谱", "问答": "智能问答", "摘要": "文本摘要",
    }
    for kw, name in _name_map.items():
        if kw in capability:
            return name
    return capability[:8]


def _infer_missing_tools_for_skills(skills: list) -> list:
    """Infer tool needs from matched skills."""
    _skill_tool_map = {
        "field-assessment": [{"tool": "file_read", "reason": "诊断需要读取客户提供的配置文件或样例数据"}],
        "knowledge_retrieval": [{"tool": "database_query", "reason": "知识检索需要查询数据库获取文档"}],
        "document_analysis": [{"tool": "file_read", "reason": "文档分析需要读取PDF/Word文件"}],
        "code_generation": [{"tool": "code_execution", "reason": "代码生成后需要执行验证"}],
    }
    tools = []
    for skill in skills:
        for item in _skill_tool_map.get(skill, []):
            if item not in tools:
                tools.append(item)
    return tools

# ── Shared file-based async task store (workers=2 compatible) ──────────────

import uuid as _uuid, time as _time, json as _task_json
from pathlib import Path as _Path

_TASK_TTL = 300  # 5 minutes


def _tasks_dir() -> _Path:
    d = _Path(os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_task(tid: str) -> dict | None:
    p = _tasks_dir() / f"{tid}.json"
    if not p.exists():
        return None
    try:
        data = _task_json.loads(p.read_text())
        if _time.time() - data.get("created_at", 0) > _TASK_TTL:
            p.unlink(missing_ok=True)
            return None
        return data
    except Exception:
        return None


def _write_task(tid: str, data: dict) -> None:
    p = _tasks_dir() / f"{tid}.json"
    tmp = _tasks_dir() / f"{tid}.tmp"
    data["created_at"] = data.get("created_at", _time.time())
    tmp.write_text(_task_json.dumps(data, ensure_ascii=False))
    tmp.rename(p)


def _create_task() -> str:
    tid = _uuid.uuid4().hex[:12]
    _write_task(tid, {"status": "processing", "result": None, "error": None, "created_at": _time.time()})
    return tid


def _cleanup_expired_tasks() -> None:
    now = _time.time()
    d = _tasks_dir()
    for p in d.glob("*.json"):
        try:
            data = _task_json.loads(p.read_text())
            if now - data.get("created_at", 0) > _TASK_TTL:
                p.unlink(missing_ok=True)
        except Exception as e:
            logging.warning(str(e), exc_info=True)


@router.get("/workspace/agents/auto-fill/{task_id}", response_model=Dict[str, Any])
async def poll_auto_fill(task_id: str):
    u"""轮询异步智能填充任务状态。"""
    _cleanup_expired_tasks()
    task = _read_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在或已过期")
    return {
        "task_id": task_id,
        "status": task["status"],
        "result": task["result"] if task["status"] == "completed" else None,
        "error": task["error"],
    }


# ── Role-definition async task store ──────────────────────────────────────


def _create_role_def_task() -> str:
    return _create_task()  # same file-based store


async def _run_role_def_task(tid: str, req: "AgentAutoFillRequest"):
    """Execute role-definition generation in background and update task store."""
    try:
        import json as _json, re as _re
        from core.api.core_facade import _async_prompt_resolve  # P0-A2: 经 CoreFacade
        from core.api.core_facade import best_model_for_purpose  # P0-A2: 经 CoreFacade
        from core.api.core_facade import sys_llm_generate  # P0-A2: 经 CoreFacade

        prompt = await _async_prompt_resolve("agent-role-definition",
            name=req.name or '(待填写)', description=req.description or '(无)',
        )
        model_name = best_model_for_purpose("agent_creation")
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("agent-role-system")},
            {"role": "user", "content": prompt},
        ]
        resp = await sys_llm_generate(model=None, prompt=messages, model_name=model_name)
        content = resp.content if hasattr(resp, 'content') else str(resp)

        clean = content.strip()
        if clean.startswith("```"):
            clean = _re.sub(r'^```\w*\n?', '', clean)
            clean = _re.sub(r'\n?```$', '', clean)
        match = _re.search(r'\{[\s\S]*\}', clean)
        if not match:
            raise ValueError("LLM 未返回有效的 JSON 格式")
        data = _json.loads(match.group(0))
        result = {
            "role_name": str(data.get("role_name", ""))[:20],
            "responsibilities": list(data.get("responsibilities", []))[:8],
            "scenarios": list(data.get("scenarios", []))[:5],
            "required_capabilities": list(data.get("required_capabilities", []))[:8],
            "workflow_hint": str(data.get("workflow_hint", ""))[:500],
            "reasoning": str(data.get("reasoning", ""))[:500],
        }
        _write_task(tid, {"status": "completed", "result": result, "error": None, "created_at": _time.time()})
    except Exception as e:
        _write_task(tid, {"status": "failed", "result": None, "error": str(e), "created_at": _time.time()})


@router.get("/workspace/agents/generate-role-definition/{task_id}", response_model=Dict[str, Any])
async def poll_role_definition(task_id: str):
    """轮询异步角色定义生成任务状态。"""
    _cleanup_expired_tasks()
    task = _read_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在或已过期")
    return {
        "task_id": task_id,
        "status": task["status"],
        "result": task["result"] if task["status"] == "completed" else None,
        "error": task["error"],
    }


async def _run_auto_fill_task(tid: str, req: "AgentAutoFillRequest"):
    """Execute auto-fill in background and update task store."""
    try:
        result = await _do_auto_fill(req)
        _write_task(tid, {"status": "completed", "result": result.model_dump(), "error": None, "created_at": _time.time()})
    except Exception as e:
        _write_task(tid, {"status": "failed", "result": None, "error": str(e), "created_at": _time.time()})
    # Clean up the role-def task if one was created earlier (shared store)


@router.post("/workspace/agents/auto-fill", response_model=Dict[str, Any])
async def agent_auto_fill(req: AgentAutoFillRequest) -> AgentAutoFillResponse:
    """AI 智能填充：根据功能描述自动推荐 skills / tools / MCP / config / SOP 等。
    
    支持 async_mode=true 参数（通过请求体中的 metadata 字段）：
      - async_mode=true: 立即返回 task_id，后台执行，前端轮询 GET /auto-fill/{task_id}
      - async_mode=false (默认): 同步等待 LLM 返回
    """
    async_mode = bool(getattr(req, "async_mode", False))
    
    if async_mode:
        tid = _create_task()
        _asyncio.create_task(_run_auto_fill_task(tid, req))
        return {"task_id": tid, "status": "processing", "agent_type": "", "skills": [], "tools": [], "reasoning": "后台处理中..."}

    try:
        result = await _do_auto_fill(req)
        return result.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        import traceback, logging
        logging.getLogger("auto-fill").error("agent_auto_fill crashed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/workspace/agents/create-dialog", response_model=Dict[str, Any])
async def agent_create_dialog(request: Dict[str, Any], rt: RuntimeDep = None):
    """Conversational Agent creation: clarify → draft (auto-fill). Create still via POST /workspace/agents."""
    import logging as _logging

    text = str(request.get("text") or "").strip()
    history = request.get("history") if isinstance(request.get("history"), list) else []
    try:
        from core.apps.builder.service.agent_create_dialog import run_agent_create_dialog_turn

        return await run_agent_create_dialog_turn(text=text, history=history)
    except HTTPException:
        raise
    except Exception as e:
        _logging.getLogger("agent-create-dialog").exception("agent create dialog failed")
        raise HTTPException(status_code=500, detail=str(e)[:200])


def _extract_tokens_from_sop(sop: str) -> Dict[str, List[str]]:
    """Pull SOP refs. intentional = backticks / [[need:]]; soft = bare snake_case (bind only if whitelisted)."""
    import re as _re
    intentional: List[str] = []
    soft: List[str] = []
    if not sop:
        return {"intentional": [], "soft": []}
    for m in _re.finditer(r"\[\[\s*need\s*:\s*([^\]]+?)\s*\]\]", sop, flags=_re.IGNORECASE):
        intentional.append(m.group(1).strip())
    for m in _re.finditer(r"`([a-zA-Z][\w\-]{1,64})`", sop):
        intentional.append(m.group(1).strip())
    for m in _re.finditer(r"\b([a-z][a-z0-9_]{2,48})\b", sop):
        soft.append(m.group(1).strip())
    def _dedupe(items: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        skip = {
            "the", "and", "for", "with", "from", "that", "this", "then", "when",
            "user", "page", "file", "files", "step", "steps", "using", "use",
            "output", "input", "return", "path", "default", "template", "content",
            "python", "pptx", "html", "json", "markdown", "title", "outline",
        }
        for t in items:
            key = t.lower()
            if key in seen or len(t) < 3 or key in skip:
                continue
            seen.add(key)
            out.append(t)
        return out
    return {"intentional": _dedupe(intentional), "soft": _dedupe(soft)}


def _bind_from_sop(
    sop_text: str,
    *,
    skill_catalog: List[Dict[str, Any]],
    tool_catalog: List[Dict[str, Any]],
    name_to_id: Dict[str, str],
    llm_needed_skills: Optional[List[str]] = None,
    llm_needed_tools: Optional[List[str]] = None,
    llm_needed_mcps: Optional[List[str]] = None,
    mcp_catalog: Optional[List[Dict[str, Any]]] = None,
    agent_blob: str = "",
) -> Dict[str, Any]:
    """Bind only whitelist hits referenced by SOP (+ intentional needed_*); rest → suggestions."""
    catalog_ids = {str(s.get("id") or s.get("name")) for s in skill_catalog if s.get("id") or s.get("name")}
    display_to_id: Dict[str, str] = {}
    for s in skill_catalog:
        sid = str(s.get("id") or s.get("name") or "")
        if not sid:
            continue
        for key in (s.get("display_name"), s.get("name"), sid):
            if key:
                display_to_id[str(key).strip().lower()] = sid
    tool_ids = {t["id"] for t in tool_catalog}
    tool_alias = dict(_TOOL_ALIAS_TO_NAME)
    mcp_ids_set = {
        str(m.get("id") or m.get("name") or "").strip()
        for m in (mcp_catalog or [])
        if m.get("id") or m.get("name")
    }
    mcp_ids_set.discard("")
    mcp_norm = {x.lower(): x for x in mcp_ids_set}

    extracted = _extract_tokens_from_sop(sop_text)
    intentional = list(extracted.get("intentional") or [])
    soft = list(extracted.get("soft") or [])
    sop_explicit = {t.lower() for t in intentional}
    soft_keys = {t.lower() for t in soft}
    sop_l = sop_text or ""
    catalog_ids_early = catalog_ids
    tool_ids_early = tool_ids

    for lst in (llm_needed_skills or [], llm_needed_tools or [], llm_needed_mcps or []):
        for x in lst:
            if not isinstance(x, str) or not x.strip():
                continue
            tok = x.strip()
            if tok.lower().startswith("mcp:"):
                tok = tok.split(":", 1)[1].strip() or tok
            key = tok.lower()
            in_sop = key in sop_explicit or f"`{tok}`" in sop_l
            if not in_sop and key in soft_keys:
                if tok not in _SOFT_BIND_DENY_SKILLS and key not in _SOFT_BIND_DENY_TOOLS:
                    in_sop = True
            in_whitelist = (
                tok in catalog_ids_early
                or tok in tool_ids_early
                or key in mcp_norm
                or key in {a.lower() for a in _TOOL_ALIAS_TO_NAME}
                or key in {a.lower() for a in _SKILL_ALIAS_TO_WORKSPACE}
            )
            if in_sop or not in_whitelist:
                intentional.append(tok)

    skills: List[str] = []
    tools: List[str] = []
    mcp_ids: List[str] = []
    missing_skills: List[Dict[str, str]] = []
    missing_tools: List[Dict[str, str]] = []
    missing_mcps: List[Dict[str, str]] = []
    seen_miss_s, seen_miss_t, seen_miss_m = set(), set(), set()

    def _add_skill(sid: str) -> None:
        if sid in catalog_ids and sid not in skills:
            skills.append(sid)

    def _add_tool(name: str) -> None:
        if name in tool_ids and name not in tools:
            tools.append(name)

    def _add_mcp(name: str) -> None:
        real = mcp_norm.get(name.lower()) or (name if name in mcp_ids_set else "")
        if real and real not in mcp_ids:
            mcp_ids.append(real)

    for tok in soft:
        key = tok.lower()
        if tok in tool_ids and key not in _SOFT_BIND_DENY_TOOLS:
            _add_tool(tok)
            continue
        if key in mcp_norm:
            _add_mcp(tok)
            continue
        if tok in catalog_ids and tok not in _SOFT_BIND_DENY_SKILLS:
            _add_skill(tok)

    for disp, sid in display_to_id.items():
        if len(disp) < 2 or sid not in catalog_ids or sid in skills:
            continue
        if not any("\u4e00" <= ch <= "\u9fff" for ch in disp):
            continue
        if disp not in sop_l:
            continue
        if sid in _SOFT_BIND_DENY_SKILLS and sid.lower() not in sop_explicit and disp.lower() not in sop_explicit:
            continue
        _add_skill(sid)

    for tok in intentional:
        raw = tok
        if tok.lower().startswith("mcp:"):
            tok = tok.split(":", 1)[1].strip() or tok
        t_alias = tool_alias.get(tok) or tool_alias.get(tok.lower())
        if tok in tool_ids or (t_alias and t_alias in tool_ids):
            _add_tool(tok if tok in tool_ids else t_alias)  # type: ignore[arg-type]
            continue

        if tok.lower() in mcp_norm or tok in mcp_ids_set:
            _add_mcp(tok)
            continue

        sid = _resolve_skill_id(tok, catalog_ids, name_to_id)
        if not sid:
            sid = display_to_id.get(tok.lower())
        if sid and sid in catalog_ids:
            _add_skill(sid)
            continue

        looks_mcp = (
            raw.lower().startswith("mcp:")
            or tok.lower().startswith("mcp_")
            or tok.lower().endswith("_mcp")
        )
        looks_tool = (
            tok.lower() in tool_alias
            or tok.endswith("_tool")
            or tok in ("browser", "webfetch", "calculator", "database", "repo", "search", "http")
        )
        if looks_mcp:
            if tok.lower() not in seen_miss_m:
                seen_miss_m.add(tok.lower())
                missing_mcps.append(
                    {
                        "capability": tok,
                        "how_to_create": (
                            f"应用能力层 → MCP 库 → 对话创建/创建「{tok}」→ 启用并测试 → 回到 Agent 重新填充"
                        ),
                    }
                )
        elif looks_tool:
            if tok.lower() not in seen_miss_t:
                seen_miss_t.add(tok.lower())
                missing_tools.append(_describe_tool_gap(tok))
        else:
            if tok.lower() not in seen_miss_s:
                seen_miss_s.add(tok.lower())
                missing_skills.append(
                    _describe_skill_gap(tok, sop_text=sop_text, agent_blob=agent_blob)
                )

    blob = f"{agent_blob} {sop_text}"
    if any(h in blob for h in _PPT_LIKE_HINTS):
        tools = [
            t for t in tools
            if t in _PPT_MIN_TOOLS or t.lower() in sop_explicit
        ]
        for t in _PPT_MIN_TOOLS:
            if t in tool_ids and t not in tools:
                tools.append(t)
        skills = [
            s for s in skills
            if s not in _SOFT_BIND_DENY_SKILLS or s.lower() in sop_explicit
        ]
        for sid in _PPT_MIN_SKILLS:
            if sid in catalog_ids and sid not in skills:
                skills.append(sid)
        skills = list(dict.fromkeys(skills))[:6]
        tools = list(dict.fromkeys(tools))[:6]
        mcp_ids = [m for m in mcp_ids if m.lower() in sop_explicit]

    return {
        "skills": skills[:8],
        "tools": tools[:8],
        "mcp_ids": mcp_ids[:8],
        "missing_skills": missing_skills[:8],
        "missing_tools": missing_tools[:8],
        "missing_mcps": missing_mcps[:8],
    }



def _describe_skill_gap(capability: str, *, sop_text: str = "", agent_blob: str = "") -> Dict[str, str]:
    """Explain what a missing skill must do + how to create it (user-facing)."""
    cap = (capability or "").strip()
    key = cap.lower().replace("-", "_")
    blob = f"{agent_blob}\n{sop_text}"

    # Known capability blueprints
    if key in ("ppt_generation", "pptx_generation", "powerpoint", "slide_generation"):
        must = (
            "1) 输入：结构化大纲（标题/章节/每页要点）+ 可选模版路径(.pptx/.potx)或默认模版名；"
            "2) 按模版母版/占位符逐页填充，控制单页字数；"
            "3) 输出：生成的 .pptx 文件路径 + 页数/所用模版等元信息；"
            "4) 不联网找素材、不编造用户未提供的事实。"
        )
        how = (
            "创建步骤：\n"
            "① 打开 应用能力层 → Skill 库 → 新建 Skill\n"
            "② id/目录名填 ppt_generation；display_name 可用「PPT生成」\n"
            "③ execution_type 建议 handler（真实生成文件）；若暂时用 prompt，须在 SOP 中明确调用 code+file_operations 写出 pptx\n"
            "④ 粘贴下方「建议 SOP」到 SKILL.md 正文后保存\n"
            "⑤ 回到本页再点「AI 智能填充」，将自动绑定该 Skill\n"
            "临时绕过：把 Agent SOP 第 5 步改成调用已有 `code`（python-pptx）+ `file_operations`，删掉 [[need:ppt_generation]]。"
        )
        draft = (
            "## 输入\n"
            "- outline: 结构化大纲（标题、章节、每页要点）\n"
            "- template_path: 可选，用户模版 .pptx/.potx；空则用默认商务模版\n"
            "- output_dir: 输出目录\n\n"
            "## 步骤\n"
            "1. 校验 outline；模版存在则解析版式，否则加载默认模版\n"
            "2. 按页填充占位符（标题≤20字，正文≤6条×20字）\n"
            "3. 写出 .pptx 到 output_dir\n"
            "4. 返回 {path, page_count, template_used}\n\n"
            "## 约束\n"
            "- 忠实用户内容，不编造数据\n"
            "- 有用户模版时不擅自改母版/配色"
        )
        return {
            "capability": cap,
            "suggested_name": "ppt_generation",
            "must_have": must,
            "draft_sop": draft,
            "how_to_create": f"应具备：{must}\n\n{how}\n\n建议 SOP：\n{draft}",
        }

    # Generic: pull nearby SOP line for context
    hint = ""
    for line in (sop_text or "").splitlines():
        if cap in line or f"need:{cap}" in line.replace(" ", ""):
            hint = line.strip()
            break
    must = (
        f"实现 SOP 中对该能力的调用（上下文：{hint or '见 Agent SOP'}）。"
        f"明确输入/输出 schema，能被 ReAct 通过 sys_skill_call 调用并返回可验收结果。"
    )
    if any(h in blob for h in _PPT_LIKE_HINTS) and "ppt" in key:
        must += " 就本 Agent 而言，核心是「大纲+模版 → .pptx 文件」。"
    how = (
        f"创建步骤：应用能力层 → Skill 库 → 新建 → id 用「{cap}」→ "
        f"写清输入/输出与步骤 SOP → 保存 → 回到本页重新智能填充。\n"
        f"或：改写 Agent SOP，删掉 [[need:{cap}]]，改用已有白名单 Skill/Tool。"
    )
    return {
        "capability": cap,
        "suggested_name": cap,
        "must_have": must,
        "draft_sop": "",
        "how_to_create": f"应具备：{must}\n\n{how}",
    }


def _describe_tool_gap(capability: str) -> Dict[str, str]:
    cap = (capability or "").strip()
    how = (
        f"SOP 需要工具「{cap}」，当前工具白名单没有。\n"
        f"请到 能力组装 → Tool 确认是否已注册；或改写 SOP 使用已有工具"
        f"（常用：file_operations / code / http / web_search）。"
    )
    return {
        "capability": cap,
        "suggested_name": cap,
        "how_to_create": how,
    }


def _binding_catalogs() -> Dict[str, set]:
    """Known workspace/engine asset IDs for bind-time validation."""
    from pathlib import Path as _P
    import yaml as _yaml

    skills: set = set()
    tools: set = set()
    mcps: set = set()
    agents: set = set()
    workflows: set = set()

    home = _P(os.path.expanduser("~/.aiplat"))
    for root in (home / "skills",):
        if not root.exists():
            continue
        for d in root.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                skills.add(d.name)
                try:
                    sp = (d / "SKILL.md").read_text(encoding="utf-8", errors="ignore").split("---", 2)
                    if len(sp) >= 2:
                        fm = _yaml.safe_load(sp[1]) or {}
                        nm = str(fm.get("name") or "").strip()
                        if nm:
                            skills.add(nm)
                except Exception:
                    pass  # noqa: best-effort catalog
    try:
        eng = _P(__file__).resolve().parents[3] / "core" / "engine" / "skills"
        if eng.exists():
            for d in eng.iterdir():
                if d.is_dir() and (d / "SKILL.md").exists():
                    skills.add(d.name)
                    try:
                        sp = (d / "SKILL.md").read_text(encoding="utf-8", errors="ignore").split("---", 2)
                        if len(sp) >= 2:
                            fm = _yaml.safe_load(sp[1]) or {}
                            nm = str(fm.get("name") or "").strip()
                            if nm:
                                skills.add(nm)
                    except Exception:
                        pass  # noqa  # noqa: cleanup-best-effort
    except Exception:
        pass  # noqa  # noqa: cleanup-best-effort

    try:
        from core.apps.tools.base import get_tool_registry
        for tn in (get_tool_registry().list_tools() or []):
            tools.add(str(tn))
    except Exception:
        pass  # noqa  # noqa: cleanup-best-effort

    try:
        from core.management.mcp_manager import MCPManager
        for s in (MCPManager(scope="workspace").list_servers() or []):
            nm = str(getattr(s, "name", "") or "").strip()
            if nm:
                mcps.add(nm)
    except Exception:
        pass  # noqa  # noqa: cleanup-best-effort

    agents_dir = home / "agents"
    if agents_dir.exists():
        for d in agents_dir.iterdir():
            if d.is_dir() and (d / "AGENT.md").exists():
                agents.add(d.name)

    wf_dir = home / "workflows"
    if wf_dir.exists():
        for d in wf_dir.iterdir():
            if d.is_dir():
                workflows.add(d.name)
            elif d.suffix in (".json", ".yaml", ".yml"):
                workflows.add(d.stem)
    try:
        from core.api.core_facade import WorkflowManager
        for w in (WorkflowManager(scope="workspace").list_workflows() or []):
            for key in (getattr(w, "id", None), getattr(w, "name", None)):
                wid = str(key or "").strip()
                if wid:
                    workflows.add(wid)
    except Exception:
        pass  # noqa  # noqa: cleanup-best-effort

    return {
        "skills": skills,
        "tools": tools,
        "mcp": mcps,
        "agents": agents,
        "workflows": workflows,
    }


def _raise_if_unknown_bindings(
    *,
    skills: Optional[List[str]] = None,
    tools: Optional[List[str]] = None,
    mcp_ids: Optional[List[str]] = None,
    agent_ids: Optional[List[str]] = None,
    workflow_ids: Optional[List[str]] = None,
    self_agent_id: str = "",
) -> None:
    """Reject bind/update that references assets not present in catalogs."""
    cat = _binding_catalogs()
    unknown: List[Dict[str, str]] = []
    for s in skills or []:
        sid = str(s or "").strip()
        if sid and sid not in cat["skills"]:
            unknown.append({"kind": "skill", "id": sid})
    for t in tools or []:
        tid = str(t or "").strip()
        if tid and tid not in cat["tools"]:
            unknown.append({"kind": "tool", "id": tid})
    for m in mcp_ids or []:
        mid = str(m or "").strip()
        if mid and mid not in cat["mcp"]:
            unknown.append({"kind": "mcp", "id": mid})
    for a in agent_ids or []:
        aid = str(a or "").strip()
        if not aid or aid == self_agent_id:
            continue
        if aid not in cat["agents"]:
            unknown.append({"kind": "agent", "id": aid})
    for w in workflow_ids or []:
        wid = str(w or "").strip()
        if wid and wid not in cat["workflows"]:
            unknown.append({"kind": "workflow", "id": wid})
    if not unknown:
        return
    lines = [f"{u['kind']}:{u['id']}" for u in unknown]
    raise HTTPException(
        status_code=400,
        detail={
            "error": "unknown_bindings",
            "message": (
                "绑定失败：以下资产不存在，请先在对应库中创建后再绑定——"
                + "、".join(lines)
            ),
            "unknown": unknown,
        },
    )


def _missing_binding_create_issue(
    *,
    kind: str,
    name: str,
    agent_display: str,
    description: str,
    sop_text: str,
) -> Dict[str, Any]:
    """Audit issue for a missing binding: recommend create (no auto-remove)."""
    name = str(name or "").strip()
    agent_display = str(agent_display or "本 Agent").strip() or "本 Agent"
    desc = str(description or "").strip()
    sop_hint = ""
    for line in (sop_text or "").splitlines():
        if name and name in line:
            sop_hint = line.strip()
            break
    if not sop_hint:
        for line in (sop_text or "").splitlines():
            s = line.strip()
            if s.startswith("-") or s.startswith("1.") or "调用" in s:
                sop_hint = s
                break
    sop_hint = (sop_hint or "见 AGENT.md Persona/Workflow")[:160]

    if kind == "skill":
        gap = _describe_skill_gap(name, sop_text=sop_text, agent_blob=desc)
        must = gap.get("must_have") or (
            f"支撑「{agent_display}」完成：{desc or '其 SOP 中声明的任务'}。"
            f"须可被 ReAct 通过 sys_skill_call 调用，输入/输出可验收。"
        )
        how = gap.get("how_to_create") or (
            f"到 应用能力层 → Skill 库 → 新建，id 用「{name}」，写清输入/输出与步骤后保存，再回到本 Agent 绑定。"
        )
        category = "invalid_skill"
        field = "skills"
        label = "技能"
        where = "技能库"
    elif kind == "tool":
        gap = _describe_tool_gap(name)
        must = (
            f"为「{agent_display}」提供可调用能力「{name}」。"
            f"上下文：{sop_hint}。"
            f"须在 TOOL_DEF 声明 name/description/parameters，execute 返回结构化结果。"
        )
        how = gap.get("how_to_create") or (
            f"到 能力组装 → Tool → 新建「{name}」，补全 TOOL_DEF 后保存重载，再绑定到本 Agent。"
        )
        category = "invalid_tool"
        field = "tools"
        label = "工具"
        where = "工具库"
    elif kind == "mcp":
        must = (
            f"对接外部系统/服务，供「{agent_display}」调用。"
            f"Agent 描述：{desc or '（无）'}；SOP 线索：{sop_hint}。"
            f"Server 应暴露最小工具集（allowed_tools），transport/url 或 stdio command 可用。"
        )
        how = (
            f"到 MCP 库 → 新建 Server，name=「{name}」→ 选 transport 并填 url/command → "
            f"发现工具并勾选最小权限 → 保存后回到本 Agent 绑定。"
        )
        category = "invalid_mcp"
        field = "mcp_servers"
        label = "MCP"
        where = "MCP 库"
    elif kind == "agent":
        must = (
            f"作为「{agent_display}」的子 Agent 承接委派任务。"
            f"父 Agent 描述：{desc or '（无）'}；SOP 线索：{sop_hint}。"
            f"须有清晰 Persona/Workflow，以及可验收的 output_artifact。"
        )
        how = (
            f"到 应用库 → 新建 Agent，id=「{name}」→ 写描述与 SOP → 保存后回到本 Agent 绑定为子 Agent。"
        )
        category = "invalid_sub_agent"
        field = "agent_ids"
        label = "子 Agent"
        where = "应用库"
    else:  # workflow
        must = (
            f"编排「{agent_display}」相关多步流程。"
            f"Agent 描述：{desc or '（无）'}；SOP 线索：{sop_hint}。"
            f"画布应含可执行节点与明确连线顺序。"
        )
        how = (
            f"到 编排/Workflow → 新建「{name}」→ 添加节点并连线 → 保存后回到本 Agent 绑定。"
        )
        category = "invalid_workflow"
        field = "workflows"
        label = "Workflow"
        where = "编排库"

    suggestion = (
        f"{label}「{name}」不存在——绑定本应在创建时从目录选择。\n"
        f"· 若仍需要该能力：到{where}按下列说明新建后再绑定（一键修复不会代建）。\n"
        f"· 若确认不需要：可用一键修复解绑。\n\n"
        f"【应具备】\n{must}\n\n【如何创建】\n{how}"
    )
    fix_by_kind = {
        "skill": {"type": "remove_skill", "skill": name},
        "tool": {"type": "remove_tool", "tool": name},
        "mcp": {"type": "remove_mcp", "mcp": name},
        "agent": {"type": "remove_agent", "agent": name},
        "workflow": {"type": "remove_workflow", "workflow": name},
    }
    return {
        "severity": "error",
        "category": category,
        "field": field,
        "current": name,
        "message": f"{label} '{name}' 在系统中不存在",
        "suggestion": suggestion,
        "fix_available": True,
        "fix": fix_by_kind.get(kind) or {"type": "remove_skill", "skill": name},
        "create_brief": {
            "kind": kind,
            "suggested_id": name,
            "must_have": must,
            "how_to_create": how,
            "where": where,
        },
    }


def _not_listed_unbind_issue(
    *,
    category: str,
    field: str,
    name: str,
    kind: str,
    message: str,
    list_where: str,
    severity: str = "error",
) -> Dict[str, Any]:
    """Asset exists but is not listed: never auto-publish; optional per-issue unbind."""
    name = str(name or "").strip()
    fix_by_kind = {
        "skill": {"type": "remove_skill", "skill": name},
        "tool": {"type": "remove_tool", "tool": name},
        "mcp": {"type": "remove_mcp", "mcp": name},
        "agent": {"type": "remove_agent", "agent": name},
        "workflow": {"type": "remove_workflow", "workflow": name},
    }
    fix = dict(fix_by_kind.get(kind) or {"type": "remove_skill", "skill": name})
    fix["apply_all"] = False
    return {
        "severity": severity,
        "category": category,
        "field": field,
        "current": name,
        "message": message,
        "suggestion": (
            f"{list_where}上架需人工操作，一键修复不会代提。"
            f"若本 Agent 暂不需要该绑定，可对该条点修复以解绑。"
        ),
        "fix_available": True,
        "fix": fix,
    }


def _strip_resolved_need_markers(sop: str, resolved_ids: List[str]) -> str:
    """Replace [[need:X]] with `X` when X is already bound."""
    import re as _re

    if not sop:
        return sop
    resolved = {str(x).strip() for x in (resolved_ids or []) if str(x).strip()}
    resolved_norm = {x.lower().replace("-", "_") for x in resolved}

    def _repl(m):
        name = (m.group(1) or "").strip()
        key = name.lower().replace("-", "_")
        if name in resolved or key in resolved_norm:
            return f"`{name}`"
        return m.group(0)

    return _re.sub(r"\[\[\s*need\s*:\s*([^\]]+?)\s*\]\]", _repl, sop, flags=_re.IGNORECASE)


def _wants_outbound_network(*, tools: List[str], blob: str) -> bool:
    from core.apps.common.boundary_hints import wants_outbound_network

    return wants_outbound_network(tools=tools, text=blob)


def _mentions_external_system(text: str) -> bool:
    """Real external SaaS/API integration — not「外部内容」/「不引入外部」negations."""
    from core.apps.common.boundary_hints import mentions_external_system

    return mentions_external_system(text)


def _derive_agent_permissions(
    *,
    tools: Optional[List[str]] = None,
    skills: Optional[List[str]] = None,
    mcp_ids: Optional[List[str]] = None,
    description: str = "",
    sop_text: str = "",
) -> List[str]:
    """Minimal permissions from bindings + description (least privilege)."""
    tools = [str(t) for t in (tools or []) if str(t).strip()]
    skills = [str(s) for s in (skills or []) if str(s).strip()]
    mcp_ids = [str(m) for m in (mcp_ids or []) if str(m).strip()]
    blob = f"{description}\n{sop_text}\n{' '.join(tools)}\n{' '.join(skills)}".lower()
    perms: List[str] = ["llm:generate"]

    if _wants_outbound_network(tools=tools, blob=blob):
        if "network:outbound" not in perms:
            perms.append("network:outbound")

    write_hints = (
        "file_operations" in tools
        or "code" in tools
        or any(k in blob for k in ("写文件", "保存", "pptx", "落盘", "workspace_fs", "下载", "导出"))
    )
    if write_hints and "tool:workspace_fs_write" not in perms:
        perms.append("tool:workspace_fs_write")

    if "code" in tools and "tool:run_command" not in perms:
        # code sandbox often needs run; keep optional — only if SOP mentions 执行/脚本
        if any(k in blob for k in ("执行脚本", "bash", "shell", "run_command", "沙箱")):
            perms.append("tool:run_command")

    if mcp_ids and "mcp:invoke" not in perms:
        perms.append("mcp:invoke")

    # de-dupe preserve order
    out: List[str] = []
    seen = set()
    for p in perms:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _append_gap_section(
    sop: str,
    missing_skills: list,
    missing_tools: list,
    missing_mcps: Optional[list] = None,
) -> str:
    miss_m = missing_mcps or []
    if not missing_skills and not missing_tools and not miss_m:
        return sop
    lines = [sop.rstrip(), "", "## 能力缺口（需新建或改写 SOP）"]
    for m in missing_skills:
        must = (m.get("must_have") or "").strip()
        how = (m.get("how_to_create") or "").strip()
        cap = m.get("capability") or ""
        if must:
            lines.append(f"- Skill 缺失: {cap}")
            lines.append(f"  - 应具备: {must}")
            if how:
                first = how.split("\n", 1)[0]
                lines.append(f"  - 创建: {first}")
        else:
            lines.append(f"- Skill 缺失: {cap} — {how}")
    for m in missing_tools:
        lines.append(f"- Tool 缺失: {m.get('capability')} — {m.get('how_to_create')}")
    for m in miss_m:
        if not isinstance(m, dict):
            continue
        cap = m.get("capability") or m.get("type") or "mcp"
        how = m.get("how_to_create") or m.get("description") or ""
        lines.append(f"- MCP 缺失: {cap} — {how}")
    return "\n".join(lines)[:8000]


async def _do_auto_fill(req: AgentAutoFillRequest) -> AgentAutoFillResponse:
    """SOP-first auto-fill: generate SOP → bind whitelist refs → suggest gaps."""
    import json as _json, re as _re

    rd = None
    if hasattr(req, "role_definition") and isinstance(req.role_definition, dict):
        rd = req.role_definition

    skill_catalog = _scan_skills_direct(workspace_only=True)
    tool_catalog = _scan_tools_direct()
    mcp_catalog = _scan_mcp_direct()
    _name_to_id: Dict[str, str] = {}
    skills_text_lines = []
    for s in skill_catalog:
        sid = str(s.get("id") or s.get("name") or "")
        if not sid:
            continue
        _name_to_id[str(s.get("name") or "")] = sid
        _name_to_id[str(s.get("display_name") or "")] = sid
        _name_to_id[sid] = sid
        skills_text_lines.append(
            f"- {sid}: {s.get('display_name') or s.get('name') or sid} — {(s.get('description') or '')[:60]}"
        )
    skills_text = "\n".join(skills_text_lines) or "(无可用技能)"
    tools_text = "\n".join(
        f"- {t['id']}: {t.get('description') or t['id']}" for t in tool_catalog
    ) or "(无可用工具)"
    mcps_text = "\n".join(
        f"- {m['id']}: {m.get('description') or m['id']}" for m in mcp_catalog
    ) or "(无可用 MCP；需要外部系统时写 [[need:mcp:名称]])"

    role_hint = ""
    if rd and isinstance(rd, dict):
        role_hint = (
            f"\n角色: {rd.get('role_name','')}."
            f" 职责: {', '.join(rd.get('responsibilities',[])[:3])}"
        )

    # Pass 1: SOP-first. Do NOT ask LLM to pick final bind lists as source of truth.
    inline_prompt = (
        f"你是 AI Agent 流程设计师。先写出可执行的 SOP，再给出配置元数据。只输出 JSON。\n\n"
        f"Agent名称: {req.name or '(待填写)'}\n"
        f"功能描述: {req.description or '(无)'}\n"
        f"{role_hint}\n\n"
        f"## 可用 Skill 白名单（SOP 步骤里尽量用这些 id，写成 `id` 反引号）\n{skills_text}\n\n"
        f"## 可用 Tool 白名单（同上）\n{tools_text}\n\n"
        f"## 可用 MCP 白名单（外部系统对接时引用，写成 `server_name`）\n{mcps_text}\n\n"
        f"规则：\n"
        f"1. 先写 sop_text：4~8 个编号步骤，可执行、可验收。\n"
        f"2. 步骤需要调用能力时，优先引用白名单 id（Skill/Tool/MCP）。\n"
        f"3. 若白名单没有必需能力，不要假装已有；Skill/Tool 写 [[need:能力名]]，MCP 写 [[need:mcp:名称]]，并分别列入 needed_skills/needed_tools/needed_mcps。\n"
        f"4. 不要为了塞满而引用无关 id（例如做 PPT 不要引用 search/webfetch/无关 MCP，除非描述明确要求联网或外部对接）。\n"
        f"5. PPT/文档生成类：白名单已有 `ppt_generation` 时必须写成 `ppt_generation`；没有时才写 [[need:ppt_generation]]。可辅以 `summarize`/`requirement_analysis`/`file_operations`。\n"
        f"6. system_prompt 写角色与边界（≠ SOP 第一行）。\n\n"
        f"输出JSON："
        f'{{"agent_type":"react",'
        f'"sop_text":"1. ...\\n2. ...",'
        f'"system_prompt":"你是…",'
        f'"memory_config":{{"type":"conversation","max_turns":20,"persist":true}},'
        f'"trigger_conditions":["触发短语"],'
        f'"needed_skills":["白名单id或缺口名"],'
        f'"needed_tools":["白名单id或缺口名"],'
        f'"needed_mcps":["白名单MCP名或缺口名"],'
        f'"reasoning":"说明SOP设计与缺口"}}'
    )

    try:
        from core.api.core_facade import best_model_for_purpose
        from core.api.core_facade import sys_llm_generate
        from core.api.core_facade import _async_prompt_resolve
        model_name = best_model_for_purpose("agent_creation")
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("agent-role-system")},
            {"role": "user", "content": inline_prompt},
        ]
        resp = await sys_llm_generate(model=None, prompt=messages, model_name=model_name)
        content = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")

    import logging as _log
    clean = content.strip()
    if clean.startswith("```"):
        clean = _re.sub(r"^```\w*\n?", "", clean)
        clean = _re.sub(r"\n?```$", "", clean)
    if "{" in clean and clean.index("{") > 0 and clean.index("{") < 200:
        clean = clean[clean.index("{"):]
    try:
        data, _end = _json.JSONDecoder().raw_decode(clean)
    except _json.JSONDecodeError:
        data = _extract_json_fallback(clean, content, _re, _json, _log)
    if data is None:
        raise HTTPException(status_code=422, detail="LLM 返回格式异常，请重试")

    agent_type = str(data.get("agent_type", "react"))[:20]
    config = data.get("config", {}) if isinstance(data.get("config"), dict) else {}
    if data.get("system_prompt") and not config.get("system_prompt"):
        config["system_prompt"] = str(data.get("system_prompt"))[:500]

    sop_text = str(data.get("sop_text") or "").strip()
    if not sop_text and rd and isinstance(rd, dict):
        sop_text = _generate_sop_from_role(rd, [])

    needed_skills = data.get("needed_skills") if isinstance(data.get("needed_skills"), list) else []
    needed_tools = data.get("needed_tools") if isinstance(data.get("needed_tools"), list) else []
    needed_mcps = data.get("needed_mcps") if isinstance(data.get("needed_mcps"), list) else []

    bound = _bind_from_sop(
        sop_text,
        skill_catalog=skill_catalog,
        tool_catalog=tool_catalog,
        name_to_id=_name_to_id,
        llm_needed_skills=[x for x in needed_skills if isinstance(x, str)],
        llm_needed_tools=[x for x in needed_tools if isinstance(x, str)],
        llm_needed_mcps=[x for x in needed_mcps if isinstance(x, str)],
        mcp_catalog=mcp_catalog,
        agent_blob=f"{getattr(req, 'name', '')} {getattr(req, 'description', '')}",
    )
    skills = bound["skills"]
    tools = bound["tools"]
    mcp_ids = list(bound.get("mcp_ids") or [])
    missing_skills = bound["missing_skills"]
    missing_tools = bound["missing_tools"]
    missing_mcps = list(bound.get("missing_mcps") or [])

    # Already-bound capabilities should not remain as [[need:...]] in SOP
    sop_text = _strip_resolved_need_markers(
        sop_text,
        list(skills) + list(tools) + list(mcp_ids) + [f"mcp:{m}" for m in mcp_ids],
    )
    sop_text = _append_gap_section(sop_text, missing_skills, missing_tools, missing_mcps)

    desc = getattr(req, "description", "") or ""
    if not mcp_ids and not missing_mcps and desc and _mentions_external_system(str(desc)):
        missing_mcps = [{
            "capability": "external_integration",
            "how_to_create": "描述涉及外部系统对接，建议在 MCP 库创建并启用对应 Server，再重新智能填充绑定",
        }]
        sop_text = _append_gap_section(sop_text, [], [], missing_mcps)

    sp = str(config.get("system_prompt") or "").strip()
    if not sp or (sp[:1].isdigit() and "." in sp[:4]):
        nm = (getattr(req, "name", None) or "Agent").strip() or "Agent"
        ds = (getattr(req, "description", None) or "").strip()
        config["system_prompt"] = (
            f"你是“{nm}”。{('职责：' + ds) if ds else ''}"
            " 严格按 SOP 执行；只使用已绑定的 Skill/Tool/MCP；缺口能力需提示用户补齐。"
        )[:500]

    gap_note = ""
    if missing_skills or missing_tools or missing_mcps:
        gap_note = (
            f" 另有 Skill缺口{len(missing_skills)} / Tool缺口{len(missing_tools)} / "
            f"MCP缺口{len(missing_mcps)}，已写入 SOP「能力缺口」并返回建议，未强行绑定。"
        )
    reasoning = (str(data.get("reasoning", ""))[:420] + gap_note).strip()

    permissions = _derive_agent_permissions(
        tools=tools,
        skills=skills,
        mcp_ids=mcp_ids,
        description=str(getattr(req, "description", "") or ""),
        sop_text=sop_text,
    )

    return AgentAutoFillResponse(
        agent_type=agent_type,
        config=config,
        skills=skills,
        tools=tools,
        mcp_ids=mcp_ids,
        missing_skills=missing_skills,
        missing_tools=missing_tools,
        missing_mcps=missing_mcps,
        agent_ids=[],
        memory_config=_ensure_memory_config(data.get("memory_config")),
        sop_text=sop_text,
        reasoning=reasoning[:500],
        workflow_ids=[],
        trigger_conditions=list(data.get("trigger_conditions", []))[:20],
        permissions=permissions,
        template_id="",
        stages=list(data.get("stages", []))[:20] if isinstance(data.get("stages"), list) else [],
    )


@router.post("/workspace/agents/auto-fill-batch", response_model=Dict[str, Any])
async def agent_auto_fill_batch(req: AgentAutoFillBatchRequest) -> AgentAutoFillBatchResponse:
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
    from core.api.core_facade import _async_prompt_resolve  # P0-A2: 经 CoreFacade
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
        from core.api.core_facade import best_model_for_purpose  # P0-A2: 经 CoreFacade
        from core.api.core_facade import sys_llm_generate  # P0-A2: 经 CoreFacade
        model_name = best_model_for_purpose("agent_creation")
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("agent-role-system")},
            {"role": "user", "content": prompt},
        ]
        resp = await sys_llm_generate(model=None, prompt=messages, model_name=model_name)
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
        raise HTTPException(status_code=422, detail="LLM 未返回有效的 JSON 格式，请重试")

    try:
        data = _json.loads(match.group(0))
    except _json.JSONDecodeError:
        cleaned = _re.sub(r',\s*\}', '}', match.group(0))
        try:
            data = _json.loads(cleaned)
        except _json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="LLM 返回解析失败，请重试")

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
    raw = _scan_skills_direct(workspace_only=True)
    if not raw:
        return ["(unable to load skill catalog)"]
    return [
        f"  - {s.get('id') or s.get('name')}: {s.get('display_name') or s.get('name')} — {(s.get('description') or '')[:80]}"
        for s in raw
    ]


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
        from core.api.core_facade import get_kernel_runtime  # P0-A2: 经 CoreFacade
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
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
        if not entries:
            entries = ["(no workflow templates available)"]
    except Exception:
        entries = ["(unable to load workflow catalog)"]
    return entries




# ── Seed templates (must be before {agent_id} to avoid route conflict) ──

@router.post("/workspace/agents/dedupe", response_model=Dict[str, Any])
async def dedupe_workspace_agents(rt: RuntimeDep = None):
    """Merge agents that share the same display_name + skills/tools fingerprint; keep newest."""
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    return await mgr.dedupe_agents()


@router.get("/workspace/agents/seeds", response_model=Dict[str, Any])
async def list_agent_seeds():
    """List available agent seed templates from workspace_seeds/agents/."""
    from pathlib import Path as _P
    import yaml as _yaml

    seeds_dir = _P(__file__).resolve().parents[2] / "workspace_seeds" / "agents"
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


@router.post("/workspace/agents/seeds/{seed_id}/install", response_model=Dict[str, Any])
async def install_agent_seed(seed_id: str):
    """Install a workspace agent seed template into ~/.aiplat/agents/."""
    import shutil as _shutil
    from pathlib import Path as _P

    seeds_dir = _P(__file__).resolve().parents[2] / "workspace_seeds" / "agents"
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to install seed: {str(e)}")

    return {"status": "installed", "id": seed_id}


@router.get("/workspace/agents/{agent_id}", response_model=Dict[str, Any])
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


@router.get("/workspace/agents/{agent_id}/sop", response_model=Dict[str, Any])
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


@router.put("/workspace/agents/{agent_id}/sop", response_model=Dict[str, Any])
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


@router.get("/workspace/agents/{agent_id}/execution-help", response_model=Dict[str, Any])
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


def _agent_sop_excerpt(info) -> str:
    try:
        from core.management.execution_examples import sop_excerpt_from_markdown
        if not isinstance(info, dict):
            return ""
        body = str(info.get("body") or "").strip()
        if body:
            return sop_excerpt_from_markdown(body)
        path = info.get("path")
        if path:
            from pathlib import Path as _P
            p = _P(str(path))
            if p.exists():
                return sop_excerpt_from_markdown(p.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return ""
    return ""


@router.post("/workspace/agents/{agent_id}/generate-execution-examples", response_model=Dict[str, Any])
async def generate_workspace_agent_execution_examples(
    agent_id: str,
    request: Dict[str, Any] = None,
    http_request: Request = None,
    rt: RuntimeDep = None,
):
    """Optional LLM generation of smoke test cases for Execute Agent UI.

    Body:
      persist: bool — write into AGENT.md frontmatter execution_examples
      refine_hint: str — optional extra instruction
    """
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    body = request if isinstance(request, dict) else {}
    persist = bool(body.get("persist"))
    refine_hint = str(body.get("refine_hint") or "").strip()

    if persist and http_request is not None:
        deny = await rbac_guard(
            http_request=http_request,
            payload=body,
            action="update",
            resource_type="agent",
            resource_id=str(agent_id),
        )
        if deny:
            return deny

    skill_ids = list(getattr(agent, "skills", []) or [])
    info = None
    try:
        info = mgr._read_agent_md(agent_id)  # type: ignore[attr-defined]
    except Exception:
        info = None
    fm = (info or {}).get("frontmatter") if isinstance(info, dict) else {}
    if isinstance(fm, dict):
        for s in fm.get("required_skills") or []:
            sid = str(s).strip()
            if sid and sid not in skill_ids:
                skill_ids.append(sid)
    tool_ids = list(getattr(agent, "tools", []) or [])
    display = str(
        (getattr(agent, "metadata", None) or {}).get("display_name")
        or getattr(agent, "name", None)
        or agent_id
    )
    desc = str((getattr(agent, "metadata", None) or {}).get("description") or "")
    meta = getattr(agent, "metadata", None) or {}
    schema: Dict[str, Any] = {}
    from core.management.execution_examples import resolve_skill_example_schema
    schema = resolve_skill_example_schema(
        live=(meta.get("execution_input_schema") if isinstance(meta, dict) else None)
        or (meta.get("input_schema") if isinstance(meta, dict) else None),
        frontmatter=fm if isinstance(fm, dict) else {},
    )

    try:
        from core.apps.agents.service.agent_execution_examples_llm import (
            generate_agent_execution_examples_llm,
        )

        result = await generate_agent_execution_examples_llm(
            agent_id=str(agent_id),
            agent_name=display,
            description=desc,
            skill_ids=skill_ids,
            tool_ids=tool_ids,
            input_schema=schema if isinstance(schema, dict) else {},
            refine_hint=refine_hint,
            sop_excerpt=_agent_sop_excerpt(info),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)[:200])
    except Exception as e:
        logging.exception("generate agent execution examples failed")
        raise HTTPException(status_code=500, detail=str(e)[:200])

    examples = result.get("examples") if isinstance(result, dict) else None
    if not isinstance(examples, list) or not examples:
        raise HTTPException(status_code=502, detail="LLM did not return usable examples")

    saved = False
    if persist and str(result.get("source") or "") == "llm":
        try:
            saved = bool(mgr.persist_execution_examples(str(agent_id), examples))  # type: ignore[attr-defined]
        except Exception as e:
            logging.warning("persist agent execution examples failed: %s", e, exc_info=True)
            saved = False
    elif persist:
        extra = str(result.get("warning") or "").strip()
        result["warning"] = (extra + "；" if extra else "") + "启发式回退未写入 AGENT.md（避免覆盖已有用例）"

    return {
        "status": "ok",
        "agent_id": agent_id,
        "examples": examples,
        "model": result.get("model"),
        "source": result.get("source"),
        "warning": result.get("warning"),
        "persisted": saved,
    }


@router.post("/workspace/routing/classify", response_model=Dict[str, Any])
async def classify_user_request(request: Request, rt: RuntimeDep = None):
    """Agent 路由：根据用户输入自动推荐最合适的 Agent。
    
    请求体: {"message": "用户输入", "agent_name": "(可选)", "agent_type": "(可选)",
             "available_skills": [...], "available_tools": [...]}
    返回: RoutingResult (intent, confidence, primary_route, suggested_routes, entities, skills, tools)
    """
    import json as _json
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = str(body.get("message") or body.get("name") or "")

    from core.harness.routing.classifier import classify
    from core.schemas_routing import RoutingContext as _Rctx

    # ── Fast path: use agent context from request body (zero disk I/O) ──
    agent_type = str(body.get("agent_type") or "")
    agent_name = str(body.get("agent_name") or "")
    agent_desc = str(body.get("agent_description") or "")
    agent_skills: list = [s for s in (body.get("available_skills") or []) if s]
    agent_tools: list = [t for t in (body.get("available_tools") or []) if t]

    # ── Fallback: load from disk if frontend didn't send context ──
    if not agent_name and not agent_type:
        agent_id = str(body.get("agent_id") or "")
        if agent_id:
            mgr = _ws_agent_mgr(rt)
            if mgr:
                try:
                    agent = await mgr.get_agent(agent_id)
                    if agent:
                        agent_type = getattr(agent, "type", "") or ""
                        agent_name = getattr(agent, "name", "") or ""
                        agent_desc = str((getattr(agent, "metadata", {}) or {}).get("description", ""))
                        agent_skills = list(getattr(agent, "skills", []) or [])
                        agent_tools = list(getattr(agent, "tools", []) or [])
                except Exception as e:
                    logging.warning(str(e), exc_info=True)

    ctx = _Rctx(
        user_message=message,
        agent_id=str(body.get("agent_id") or ""),
        agent_type=agent_type,
        agent_name=agent_name,
        agent_description=agent_desc,
        available_agents=[],
        available_skills=agent_skills,
        available_tools=agent_tools,
    )

    result = classify(ctx)
    return result.model_dump()


@router.delete("/workspace/agents/{agent_id}", response_model=Dict[str, Any])
async def delete_workspace_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    ok = await mgr.delete_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "deleted", "id": agent_id}


@router.post("/workspace/agents/{agent_id}/start", response_model=Dict[str, Any])
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


@router.post("/workspace/agents/{agent_id}/stop", response_model=Dict[str, Any])
async def stop_workspace_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    ok = await mgr.stop_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "stopped", "id": agent_id}


@router.put("/workspace/agents/{agent_id}", response_model=Dict[str, Any])
async def update_workspace_agent(agent_id: str, request: AgentUpdateRequest, http_request: Request, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    # Align with create_workspace_agent: top-level permissions / trigger_conditions
    # must land in metadata so AGENT.md persist writes them (UI sends them at top-level).
    meta = dict(request.metadata or {})
    if getattr(request, "permissions", None) is not None:
        meta["permissions"] = list(request.permissions or [])
    if getattr(request, "trigger_conditions", None) is not None:
        meta["trigger_conditions"] = list(request.trigger_conditions or [])
    # Bind-time gate: only validate fields explicitly provided on this update.
    _raise_if_unknown_bindings(
        skills=request.skills,
        tools=request.tools,
        mcp_ids=request.mcp_ids,
        agent_ids=request.agent_ids,
        workflow_ids=request.workflow_ids,
        self_agent_id=str(agent_id),
    )
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
        metadata=meta or None,
    )
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # Mark as pending verification (best-effort)
    try:
        await mgr.update_agent(str(agent_id), metadata={"verification": {"status": "pending", "updated_at": time.time(), "source": "autosmoke"}})
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # Auto-smoke (async, dedup)
    try:
        store = _store(rt)
        sched = _job_scheduler(rt)
        if store is not None and sched is not None:
            from core.api.core_facade import enqueue_autosmoke  # P0-A2: 经 CoreFacade

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
                except Exception as e:
                    logging.warning(str(e), exc_info=True)

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
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return {"status": "updated", "id": agent_id}


# ==================== skills/tools bindings ====================


@router.get("/workspace/agents/{agent_id}/skills", response_model=Dict[str, Any])
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


@router.post("/workspace/agents/{agent_id}/skills", response_model=Dict[str, Any])
async def bind_workspace_agent_skills(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    skill_ids = (request or {}).get("skill_ids", [])
    if skill_ids:
        _raise_if_unknown_bindings(skills=[str(x) for x in skill_ids])
        await mgr.bind_skills(agent_id, skill_ids)
    return {"status": "bound", "skill_ids": skill_ids}


@router.delete("/workspace/agents/{agent_id}/skills/{skill_id}", response_model=Dict[str, Any])
async def unbind_workspace_agent_skill(agent_id: str, skill_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    await mgr.unbind_skill(agent_id, skill_id)
    return {"status": "unbound"}


@router.get("/workspace/agents/{agent_id}/tools", response_model=Dict[str, Any])
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


@router.post("/workspace/agents/{agent_id}/tools", response_model=Dict[str, Any])
async def bind_workspace_agent_tools(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    tool_ids = (request or {}).get("tool_ids", [])
    if tool_ids:
        _raise_if_unknown_bindings(tools=[str(x) for x in tool_ids])
        await mgr.bind_tools(agent_id, tool_ids)
    return {"status": "bound", "tool_ids": tool_ids}


@router.delete("/workspace/agents/{agent_id}/tools/{tool_id}", response_model=Dict[str, Any])
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

@router.get("/workspace/agents/{agent_id}/mcp", response_model=Dict[str, Any])
async def get_workspace_agent_mcp(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"mcp_ids": agent.mcp_ids, "total": len(agent.mcp_ids)}


@router.post("/workspace/agents/{agent_id}/mcp", response_model=Dict[str, Any])
async def bind_workspace_agent_mcp(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    mcp_ids = (request or {}).get("mcp_ids", [])
    if mcp_ids:
        _raise_if_unknown_bindings(mcp_ids=[str(x) for x in mcp_ids])
    await mgr.update_agent(agent_id, mcp_ids=mcp_ids)
    return {"status": "bound", "mcp_ids": mcp_ids}


@router.delete("/workspace/agents/{agent_id}/mcp/{mcp_id}", response_model=Dict[str, Any])
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

@router.get("/workspace/agents/{agent_id}/workflows", response_model=Dict[str, Any])
async def get_workspace_agent_workflows(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"workflow_ids": agent.workflow_ids, "total": len(agent.workflow_ids)}


@router.post("/workspace/agents/{agent_id}/workflows", response_model=Dict[str, Any])
async def bind_workspace_agent_workflows(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    workflow_ids = (request or {}).get("workflow_ids", [])
    if workflow_ids:
        _raise_if_unknown_bindings(workflow_ids=[str(x) for x in workflow_ids])
    await mgr.update_agent(agent_id, workflow_ids=workflow_ids)
    return {"status": "bound", "workflow_ids": workflow_ids}


@router.delete("/workspace/agents/{agent_id}/workflows/{workflow_id}", response_model=Dict[str, Any])
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

@router.get("/workspace/agents/{agent_id}/agents", response_model=Dict[str, Any])
async def get_workspace_agent_sub_agents(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"agent_ids": agent.agent_ids, "total": len(agent.agent_ids)}


@router.post("/workspace/agents/{agent_id}/agents", response_model=Dict[str, Any])
async def bind_workspace_agent_sub_agents(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    agent_ids = (request or {}).get("agent_ids", [])
    if agent_ids:
        _raise_if_unknown_bindings(
            agent_ids=[str(x) for x in agent_ids],
            self_agent_id=str(agent_id),
        )
    await mgr.update_agent(agent_id, agent_ids=agent_ids)
    return {"status": "bound", "agent_ids": agent_ids}


@router.delete("/workspace/agents/{agent_id}/agents/{sub_agent_id}", response_model=Dict[str, Any])
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


@router.post("/workspace/agents/{agent_id}/execute", response_model=Dict[str, Any])
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
        if not user_message and inp:
            user_message = json.dumps(inp, ensure_ascii=False)
    else:
        user_message = str(payload.get("message") or payload.get("prompt") or payload.get("task") or "")

    user_config: dict = {}
    if isinstance(inp, dict):
        user_config = dict(inp.get("config") or {})
    if isinstance(payload.get("config"), dict):
        user_config.update(payload["config"])
    opts = payload.get("options") if isinstance(payload.get("options"), dict) else {}

    # AGENT.md config.max_steps is the default; request config may override.
    default_steps = 10
    try:
        acfg = getattr(agent, "config", None)
        if isinstance(acfg, dict) and acfg.get("max_steps") is not None:
            default_steps = max(1, int(acfg.get("max_steps")))
    except Exception:
        default_steps = 10

    # Delegate to CoreFacade
    from core.api.core_facade import run_workspace_agent
    from core.harness.utils.execute_session import mint_execute_session_id

    # Accept stream from options or config (UI often uses options; smoke scripts
    # may put it under config — both must flip stream mode).
    _stream_raw = opts.get("stream", None)
    if _stream_raw is None:
        _stream_raw = user_config.get("stream", False)
    stream_mode = str(_stream_raw).lower() in ("1", "true", "yes")
    resp = await run_workspace_agent(
        agent_info=agent,
        user_message=user_message,
        max_steps=int(user_config.get("max_steps", default_steps)),
        toolset=str(opts.get("toolset", "")),
        session_id=mint_execute_session_id(
            kind="agent",
            target_id=str(agent_id),
            session_id=payload.get("session_id") or None,
        ),
        stream=stream_mode,
        input_payload=inp if inp is not None else user_message,
    )

    try:
        st = str((resp or {}).get("status") or "").lower()
        if st in ("completed", "ok", "success") and isinstance(resp, dict):
            from core.management.execution_quality_review import (
                review_execution_output,
                quality_review_blocks_success,
            )

            skills = list(getattr(agent, "required_skills", None) or getattr(agent, "skills", None) or [])
            skill_hint = " ".join(str(s) for s in skills[:8])
            _qr = review_execution_output(
                kind="agent",
                asset_id=str(agent_id),
                asset_name=str(getattr(agent, "display_name", None) or getattr(agent, "name", None) or agent_id),
                input_payload=user_message or inp,
                output=resp.get("output"),
                status=st,
                hints=f"{skill_hint} {getattr(agent, 'name', '')}",
            )
            resp["quality_review"] = _qr
            if quality_review_blocks_success(_qr):
                resp["status"] = "failed"
                resp["ok"] = False
                resp["error"] = str(
                    (_qr.get("headline") if isinstance(_qr, dict) else None)
                    or resp.get("error")
                    or "coding deliverable failed quality review"
                )
                resp["quality_block_completed"] = True
    except Exception as e:
        logging.warning("agent execute quality_review skipped: %s", e, exc_info=True)

    try:
        await _audit_execute(rt, http_request=http_request, payload=payload, resource_type="agent", resource_id=str(agent_id), resp=resp)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return JSONResponse(status_code=200 if resp.get("ok") else 500, content=resp)


@router.post("/workspace/agents/{agent_id}/review-output", response_model=Dict[str, Any])
async def review_workspace_agent_output(agent_id: str, request: dict, rt: RuntimeDep = None):
    """Post-run product-quality review for Agent execute (stream path / re-check).

    When body.input is empty, restores from execution store via execution_id.
    """
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    body = request if isinstance(request, dict) else {}
    from core.management.execution_quality_review import (
        pick_embedded_quality_review,
        resolve_review_io_from_store,
        review_execution_output,
    )

    eid = body.get("execution_id") or body.get("run_id")
    inp, out, st, embedded = await resolve_review_io_from_store(
        execution_id=str(eid) if eid else None,
        kind="agent",
        body_input=body.get("input"),
        body_output=body.get("output"),
        body_status=body.get("status"),
    )
    chosen = pick_embedded_quality_review(
        embedded=embedded,
        body_output=body.get("output"),
        resolved_output=out,
        prefer_embedded=bool(body.get("prefer_embedded")),
    )
    if chosen is not None:
        return chosen
    skills = list(getattr(agent, "required_skills", None) or getattr(agent, "skills", None) or [])
    skill_hint = " ".join(str(s) for s in skills[:8])
    return review_execution_output(
        kind="agent",
        asset_id=str(agent_id),
        asset_name=str(getattr(agent, "display_name", None) or getattr(agent, "name", None) or agent_id),
        input_payload=inp,
        output=out,
        status=st,
        hints=f"{skill_hint} {getattr(agent, 'name', '')}",
        execution_id=str(eid or ""),
    )


@router.post("/workspace/agents/{agent_id}/apply-quality-fix", response_model=Dict[str, Any])
async def apply_workspace_agent_quality_fix(
    agent_id: str, request: dict, rt: RuntimeDep = None
):
    """Append quality SOP into AGENT.md and bound Skill SKILL.md mirrors."""
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    body = request if isinstance(request, dict) else {}
    primary = None
    try:
        info = mgr._read_agent_md(agent_id) if hasattr(mgr, "_read_agent_md") else None
        if isinstance(info, dict) and info.get("path"):
            from pathlib import Path as _P

            primary = _P(str(info["path"]))
    except Exception as e:
        logging.warning("read AGENT.md for apply-quality-fix: %s", e, exc_info=True)
    bound = list(getattr(agent, "required_skills", None) or getattr(agent, "skills", None) or [])
    from core.management.execution_quality_review import apply_quality_sop_for_agent_id

    result = apply_quality_sop_for_agent_id(
        str(agent_id),
        primary_path=primary,
        issue_codes=body.get("issue_codes") or [],
        fix_ids=body.get("fix_ids") or [],
        bound_skill_ids=bound,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=str(result.get("error") or "apply failed"))
    return result


@router.post("/workspace/agents/{agent_id}/sign", response_model=Dict[str, Any])
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
        from core.api.core_facade import sign_skill as sign_agent  # P0-A2: 经 CoreFacade

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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        manifest["signature"] = signature
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        # Re-enrich provenance to pick up the new signature from the manifest
        mgr._enrich_agent_provenance_and_integrity(agent.metadata, agent_dir=agent_dir)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid private key: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Signing failed: {str(e)}")

    return {
        "status": "signed",
        "bundle_sha256": bundle_sha256,
        "version": version,
        "signature": signature,
    }


@router.post("/workspace/agents/{agent_id}/toggle-enabled", response_model=Dict[str, Any])
async def toggle_agent_enabled(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=500, detail="agent manager not available")
    result = await mgr.toggle_enabled(agent_id)
    if result is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return {"agent_id": agent_id, "enabled": result}


@router.post("/workspace/agents/{agent_id}/enable", response_model=Dict[str, Any])
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
                raise HTTPException(  # noqa: error-structured
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
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
    except HTTPException:
        raise
    except Exception as e:
        logging.warning(f"Agent enable signature gate error (non-blocking): {e}")

    # 3. Actually enable
    agent.enabled = True
    agent.updated_at = datetime.now(timezone.utc)

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
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    return {
        "status": "enabled",
        "approval_request_id": str(approval_request_id) if approval_request_id else None,
        "change_id": change_id,
    }


@router.get("/workspace/agents/{agent_id}/history", response_model=Dict[str, Any])
async def get_workspace_agent_history(agent_id: str, limit: int = 100, offset: int = 0, rt: RuntimeDep = None):
    store = _store(rt)
    if store:
        history, total = await store.list_agent_history(agent_id, limit=limit, offset=offset)
        return {"history": history, "total": total}
    history = _workspace_agent_history.get(agent_id, [])[offset : offset + limit]
    return {"history": history, "total": len(_workspace_agent_history.get(agent_id, []))}


@router.get("/workspace/agents/{agent_id}/versions", response_model=Dict[str, Any])
async def get_workspace_agent_versions(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    versions = await mgr.get_versions(agent_id)
    return {"agent_id": agent_id, "versions": [{"version": v.version, "status": v.status, "created_at": v.created_at.isoformat(), "changes": v.changes} for v in versions]}


@router.post("/workspace/agents/{agent_id}/versions", response_model=Dict[str, Any])
async def create_workspace_agent_version(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    changes = (request or {}).get("changes", "")
    version = await mgr.create_version(agent_id, changes)
    if not version:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"version": version.version, "status": version.status, "created_at": version.created_at.isoformat(), "changes": version.changes}


@router.post("/workspace/agents/{agent_id}/versions/{version}/rollback", response_model=Dict[str, Any])
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


@router.post("/workspace/agents/{agent_id}/reload", response_model=Dict[str, Any])
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

@router.post("/workspace/agents/import-detect", response_model=Dict[str, Any])
async def detect_agent_import(request: Dict[str, Any], rt: RuntimeDep = None):
    """AI 检测导入的 agent 配置。接收 URL 或 zip 文件，返回推荐配置。"""
    import yaml as _yaml
    import io
    import zipfile
    from .workspace_skills import _load_tool_mapping

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
        except HTTPException:
            raise
            raise HTTPException(status_code=500, detail=str(e)[:200])
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            sop_body = parts[2].strip() if len(parts) > 2 else agmd_body

    name = str(existing.get("name") or "")
    desc = str(existing.get("description") or "")

    # Determine tools from frontmatter declarations (config-driven mapping)
    tool_map = _load_tool_mapping()
    declared_tools = None
    for key in ("tools", "allowed-tools", "allowedTools"):
        val = existing.get(key)
        if val:
            if isinstance(val, str):
                declared_tools = [t.strip().lower() for t in val.split(",") if t.strip()]
            elif isinstance(val, list):
                declared_tools = [str(t).strip().lower() for t in val if str(t).strip()]
            break

    if declared_tools:
        mapped = set()
        for t in declared_tools:
            mapped.update(tool_map.get(t, [t]))
        declared_tools = sorted(mapped)

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
        # Use frontmatter-declared trigger_conditions if present
        config["trigger_conditions"] = (
            existing.get("trigger_conditions")
            or existing.get("trigger_keywords")
            or []
        )
        # Use frontmatter-declared permissions if present
        config["permissions"] = existing.get("permissions") or []
        # Override AI-inferred tools with deterministic frontmatter mapping
        if declared_tools:
            config["tools"] = declared_tools
        # Cross-validate tools against ToolRegistry
        try:
            from core.apps.tools.base import get_tool_registry
            registry = get_tool_registry()
            registered = set(registry.list_tools() or [])
            recommended = config.get("tools", [])
            config["tools_available"] = [t for t in recommended if t in registered]
            config["tools_missing"] = [t for t in recommended if t not in registered]
        except Exception:
            config["tools_available"] = config.get("tools", [])
            config["tools_missing"] = []
        # Cross-validate skills against SkillRegistry
        try:
            from core.apps.skills import get_skill_registry
            reg = get_skill_registry()
            rec = config.get("skills", [])
            config["skills_available"] = [s for s in rec if reg.get(s)]
            config["skills_missing"] = [s for s in rec if not reg.get(s)]
        except Exception:
            config["skills_available"] = config.get("skills", [])
            config["skills_missing"] = []
        # Cross-validate MCP servers
        try:
            from core.management.mcp_manager import MCPManager
            mgr = MCPManager()
            servers = {getattr(s, "name", ""): True for s in (mgr.list_servers() or [])}
            rec = config.get("mcp_ids", [])
            config["mcp_available"] = [m for m in rec if m in servers]
            config["mcp_missing"] = [m for m in rec if m not in servers]
        except Exception:
            config["mcp_available"] = config.get("mcp_ids", [])
            config["mcp_missing"] = []
        # Cross-validate sub-agents
        try:
            from core.management.agent_manager import WorkspaceAgentManager
            wam = WorkspaceAgentManager()
            agents = {getattr(a, "name", ""): True for a in (wam.list_agents() or [])}
            rec = config.get("agent_ids", [])
            config["agents_available"] = [a for a in rec if a in agents]
            config["agents_missing"] = [a for a in rec if a not in agents]
        except Exception:
            config["agents_available"] = config.get("agent_ids", [])
            config["agents_missing"] = []
        return config
    except HTTPException:
        raise
        raise HTTPException(status_code=500, detail=str(e)[:200])


def _build_skills_catalog() -> str:
    """Build a catalog string of available skills for AI prompt injection."""
    try:
        from core.apps.skills.registry import _scan_skills_direct
        entries = _scan_skills_direct()
        return "\n".join(entries[:30]) if entries else "(no skills registered)"
    except Exception:
        return "(unable to load skill catalog)"


def _build_mcp_catalog() -> str:
    """Build a catalog string of available MCP servers."""
    try:
        from core.management.mcp_manager import MCPManager
        mgr = MCPManager()
        servers = mgr.list_servers() or []
        lines = []
        for s in servers[:20]:
            name = getattr(s, "name", "") or s.get("name", "")
            desc = getattr(s, "description", "") or s.get("description", "") if isinstance(s, dict) else (getattr(s, "description", "") or "")
            lines.append(f"- {name}: {str(desc)[:100]}" if desc else f"- {name}")
        return "\n".join(lines) if lines else "(no MCP servers registered)"
    except Exception:
        return "(unable to load MCP catalog)"


def _build_agent_catalog() -> str:
    """Build a catalog string of available sub-agents."""
    try:
        from core.management.agent_manager import WorkspaceAgentManager
        mgr = WorkspaceAgentManager()
        agents = mgr.list_agents() if hasattr(mgr, "list_agents") else []
        lines = []
        for a in (agents or [])[:20]:
            name = getattr(a, "name", "") or a.get("name", "") if isinstance(a, dict) else ""
            lines.append(f"- {name}")
        return "\n".join(lines) if lines else "(no sub-agents registered)"
    except Exception:
        return "(unable to load agent catalog)"


async def _ai_recommend_agent_config(
    agmd_body: str, name: str = "", description: str = "",
) -> dict:
    """分析 AGENT.md 正文，返回推荐的 agent 配置。

    首次调用走 LLM，后续被 SOP 哈希缓存命中（秒级返回）。
    """
    import hashlib
    from core.utils.json_utils import parse_json

    cache_key = hashlib.sha256(agmd_body[:8000].encode()).hexdigest()

    # ── 确定性推断（agent_type） ──
    combined = f"{name} {description} {agmd_body[:2000]}".lower()
    agent_type = "react"  # default
    if any(k in combined for k in ("base", "simple", "basic", "conversation")):
        agent_type = "base"
    elif any(k in combined for k in ("plan", "task", "decompose", "分解", "规划")):
        agent_type = "plan"
    elif any(k in combined for k in ("tool", "execute", "exec", "run")):
        agent_type = "tool"

    # ── 缓存命中 ──
    if cache_key in _AGENT_IMPORT_CACHE:
        return _AGENT_IMPORT_CACHE[cache_key]

    from core.api.core_facade import create_selected_adapter  # P0-A2: 经 CoreFacade
    from core.api.core_facade import best_model_for_purpose  # P0-A2: 经 CoreFacade
    from core.api.core_facade import _async_prompt_resolve  # P0-A2: 经 CoreFacade
    from .workspace_skills import _build_available_tools_list

    model_name = best_model_for_purpose("agent_creation")
    model = create_selected_adapter(model_name=model_name)
    system_prompt = await _async_prompt_resolve("agent-import-detect",
        available_tools_list=_build_available_tools_list(),
        skills_catalog=_build_skills_catalog(),
        mcp_catalog=_build_mcp_catalog(),
        agent_catalog=_build_agent_catalog(),
    )
    user_content = f"Agent 名称: {name or '(未命名)'}\n描述: {description or '(无)'}\n\nAGENT.md:\n{agmd_body[:8000]}"

    from core.api.core_facade import sys_llm_generate  # P0-A2: 经 CoreFacade
    response = await sys_llm_generate(
        model,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )

    text = str(getattr(response, "content", "") or "")
    config = parse_json(text) or {}
    if not config.get("agent_type"):
        config["agent_type"] = agent_type
    _AGENT_IMPORT_CACHE[cache_key] = config
    return config


_AGENT_IMPORT_CACHE: dict = {}

# ── Agent Installer endpoints (workspace scope) ──────────────────────

@router.post("/workspace/agents/installer/plan", response_model=Dict[str, Any])
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


@router.post("/workspace/agents/installer/install", response_model=Dict[str, Any])
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


@router.post("/workspace/agents/installer/resolve-head", response_model=Dict[str, Any])
async def workspace_agents_installer_resolve_head(request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    try:
        return await mgr.installer_resolve_head(url=str(request.get("url", "")))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/workspace/agents/installer/upload-plan", response_model=Dict[str, Any])
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"upload_plan_failed: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/workspace/agents/installer/upload-install", response_model=Dict[str, Any])
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"upload_install_failed: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/workspace/templates/upload", response_model=Dict[str, Any])
async def upload_workspace_template(
    file: UploadFile = File(...),
    http_request: Request = None,
    rt: RuntimeDep = None,
):
    """Upload a .pptx/.potx into ~/.aiplat/templates for PPT agents (方案 B confirm step)."""
    import re as _re
    from pathlib import Path as _Path

    if http_request is not None:
        deny = await rbac_guard(
            http_request=http_request,
            payload={},
            action="write",
            resource_type="template",
            resource_id="upload",
        )
        if deny:
            return deny

    raw_name = (file.filename or "upload.pptx").strip()
    base = _Path(raw_name).name
    if not _re.search(r"\.(pptx|potx)$", base, _re.I):
        raise HTTPException(status_code=400, detail="only .pptx / .potx templates are accepted")
    safe = _re.sub(r"[^\w.\-一-龥]+", "_", base).strip("._") or "upload.pptx"
    if not _re.search(r"\.(pptx|potx)$", safe, _re.I):
        safe = f"{safe}.pptx"

    home = _Path(os.environ.get("AIPLAT_HOME") or _Path.home() / ".aiplat")
    dest_dir = home / "templates"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="template too large (>50MB)")
    dest.write_bytes(content)

    return {
        "ok": True,
        "path": str(dest.resolve()),
        "filename": safe,
        "size": len(content),
    }


@router.get("/workspace/templates", response_model=Dict[str, Any])
async def list_workspace_templates(http_request: Request = None, rt: RuntimeDep = None):
    """List .pptx/.potx files under ~/.aiplat/templates for confirm-step pickers."""
    from pathlib import Path as _Path

    if http_request is not None:
        deny = await rbac_guard(
            http_request=http_request,
            payload={},
            action="read",
            resource_type="template",
            resource_id="list",
        )
        if deny:
            return deny

    home = _Path(os.environ.get("AIPLAT_HOME") or _Path.home() / ".aiplat")
    dest_dir = home / "templates"
    items = []
    if dest_dir.is_dir():
        for p in sorted(dest_dir.iterdir(), key=lambda x: x.name.lower()):
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".pptx", ".potx"):
                continue
            try:
                st = p.stat()
                items.append({
                    "filename": p.name,
                    "path": str(p.resolve()),
                    "size": int(st.st_size),
                    "mtime": float(st.st_mtime),
                    "is_default": p.name.lower() == "default.pptx",
                })
            except Exception:
                continue
    return {"ok": True, "templates": items, "dir": str(dest_dir)}


@router.post("/workspace/agents/{agent_id}/submit-for-review", response_model=Dict[str, Any])
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
        from core.api.core_facade import get_kernel_runtime  # P0-A2: 经 CoreFacade
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        raise HTTPException(  # noqa: error-structured
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
    except HTTPException:
        raise
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


@router.post("/workspace/agents/{agent_id}/invoke", response_model=Dict[str, Any])
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
        if not user_message and inp:
            user_message = json.dumps(inp, ensure_ascii=False)
    else:
        user_message = str(request.get("message") or request.get("prompt") or "")

    from core.api.core_facade import run_workspace_agent
    from core.harness.utils.execute_session import mint_execute_session_id

    resp = await run_workspace_agent(
        agent_info=agent,
        user_message=user_message,
        max_steps=int(request.get("config", {}).get("max_steps", 10) if isinstance(request.get("config"), dict) else 10),
        session_id=mint_execute_session_id(
            kind="agent",
            target_id=str(agent_id),
            session_id=request.get("session_id") if isinstance(request, dict) else None,
        ),
    )
    return {
        "run_id": resp.get("run_id", ""),
        "output": resp.get("output", ""),
        "tokens": resp.get("tokens", {}),
        "status": resp.get("status", "completed"),
        "error": resp.get("error"),
    }


# ── Agent Configuration Audit ──────────────────────────────────────────────

class AgentAuditRequest(BaseModel):
    """Optional draft overrides so Edit UI can audit unsaved SOP / system_prompt."""

    sop_body: Optional[str] = None
    system_prompt: Optional[str] = None


class AgentAuditResponse(BaseModel):
    agent_id: str
    issues: List[Dict[str, Any]]
    summary: Dict[str, Any]


def _audit_agent_sop_content(
    body: str,
    *,
    skills: list,
    tools: list,
    system_prompt: str = "",
) -> list:
    """Rule-based Agent SOP content checks (generic — not role-specific).

    Aligns with Skill lint signals (goal / flow / acceptance) but applied to
    AGENT.md body. Kept deterministic / no LLM (same as rest of audit_agent_config).
    """
    import re as _re

    out: list = []
    text = (body or "").strip()
    lower = text.lower()

    if _re.search(r"^\s*,\s*$", text, _re.MULTILINE):
        out.append({
            "severity": "info",
            "category": "sop_cleanup",
            "field": "sop_body",
            "message": "SOP 正文包含残留空行或裸逗号",
            "suggestion": "清理 SOP 中空的 'Available Plugins' 或残留标点",
        })

    n = len(text)
    # Empty SOP: fall through so role/flow/goal/quality one-click appendices apply.
    # Short body is informational once structure warnings exist.
    if 0 < n < 80:
        out.append({
            "severity": "info",
            "category": "sop_short",
            "field": "sop_body",
            "message": f"SOP 正文过短（{n} 字符）——难以约束决策与产物",
            "suggestion": "一键修复可先补角色/流程/目标/质量骨架，再按真实职责改写至约 200 字",
        })
    elif n < 200:
        out.append({
            "severity": "info",
            "category": "sop_short",
            "field": "sop_body",
            "message": f"SOP 正文偏短（{n} 字符）",
            "suggestion": "补充工作步骤与输出/验收要求，便于执行与审核对齐",
        })

    has_role = any(
        m in lower
        for m in (
            "## persona",
            "## 角色",
            "# 角色",
            "角色：",
            "你是",
            "## role",
        )
    )
    if not has_role:
        from core.management.asset_audit import fix_append_sop_role

        out.append({
            "severity": "warning",
            "category": "sop_missing_role",
            "field": "sop_body",
            "message": "SOP 缺少角色/Persona 说明",
            "suggestion": (
                "增加「# 角色」或「## Persona」段落，写清职责与边界。"
                "一键修复可追加角色骨架，请再按真实职责改写。"
            ),
            "fix_available": True,
            "fix": fix_append_sop_role(),
        })

    has_flow = any(
        m in lower
        for m in (
            "## workflow",
            "## 工作流",
            "## 工作流程",
            "工作流程",
            "步骤",
            "## sop",
            "1.",
            "1、",
        )
    ) or bool(_re.search(r"(?m)^\s*\d+[\.\、\)]\s+\S", text))
    if not has_flow:
        from core.management.asset_audit import fix_append_sop_flow

        out.append({
            "severity": "warning",
            "category": "sop_missing_flow",
            "field": "sop_body",
            "message": "SOP 缺少可执行的工作流程/步骤",
            "suggestion": (
                "增加编号步骤（输入→分析→调用 Skill/Tool→产出→验收）。"
                "一键修复可追加流程骨架，请再按真实步骤改写。"
            ),
            "fix_available": True,
            "fix": fix_append_sop_flow(),
        })

    has_goal = any(
        m in text
        for m in (
            "## 目标",
            "# 目标",
            "目标：",
            "## 目的",
            "## Goal",
            "## Objective",
            "输出格式",
            "输出要求",
            "产出",
            "output",
        )
    )
    if not has_goal:
        from core.management.asset_audit import fix_append_sop_goal

        out.append({
            "severity": "warning",
            "category": "sop_missing_goal",
            "field": "sop_body",
            "message": "SOP 缺少目标/产出说明",
            "suggestion": (
                "写明要交付什么（例如结构化 JSON 字段、文档章节、验收结果）。"
                "一键修复可追加目标/输出骨架，请再按真实产物改写。"
            ),
            "fix_available": True,
            "fix": fix_append_sop_goal(),
        })

    has_quality = any(
        m in text
        for m in (
            "验收",
            "验证",
            "Checklist",
            "质量要求",
            "输出铁律",
            "禁止",
            "强制",
            "completion_criterion",
            "- [ ]",
            "不得",
            "必须",
            "不要",
            "## 规则",
            "## 约束",
            "## 反模式",
        )
    )
    if not has_quality:
        from core.management.asset_audit import fix_append_sop_quality

        out.append({
            "severity": "warning",
            "category": "sop_missing_quality",
            "field": "sop_body",
            "message": "SOP 缺少验收/质量约束（铁律、禁止项或 Checklist）",
            "suggestion": (
                "补充可验证要求（必须/禁止/验收标准），避免「跑通即合格」。"
                "一键修复可追加标准骨架，请再按本 Agent 真实产物改写。"
            ),
            "fix_available": True,
            "fix": fix_append_sop_quality(),
        })

    bound_skills = [str(s).strip() for s in (skills or []) if str(s).strip()]
    bound_tools = [str(t).strip() for t in (tools or []) if str(t).strip()]
    if bound_skills:
        mentioned = 0
        for sid in bound_skills:
            if sid in text or f"`{sid}`" in text or sid.replace("_", "-") in text:
                mentioned += 1
        if mentioned == 0 and len(bound_skills) >= 1:
            from core.management.asset_audit import (
                SOP_SKILL_REFS_HEADING,
                upsert_sop_skill_refs_appendix,
            )

            appendix = upsert_sop_skill_refs_appendix("", bound_skills)
            out.append({
                "severity": "warning",
                "category": "sop_skills_unreferenced",
                "field": "sop_body",
                "message": (
                    f"已绑定 {len(bound_skills)} 个 Skill，但 SOP 正文未引用任一 id"
                    f"（如 {', '.join(bound_skills[:3])}）"
                ),
                "suggestion": (
                    "更佳：在步骤中用反引号写出要调用的 Skill id。"
                    "一键修复可安全追加「已绑定 Skill」附录（只列 id，不改步骤语义）。"
                ),
                "fix_available": True,
                "fix": {
                    "type": "append_sop_skill_refs",
                    "skills": bound_skills,
                    "section_heading": SOP_SKILL_REFS_HEADING,
                    "appendix": appendix,
                },
            })

    if bound_tools:
        mentioned_t = 0
        for tid in bound_tools:
            if tid in text or f"`{tid}`" in text:
                mentioned_t += 1
        if mentioned_t == 0 and len(bound_tools) >= 2:
            out.append({
                "severity": "info",
                "category": "sop_tools_unreferenced",
                "field": "sop_body",
                "message": (
                    f"已绑定 {len(bound_tools)} 个 Tool，SOP 未点名引用"
                    f"（{', '.join(bound_tools[:4])}）"
                ),
                "suggestion": "若步骤依赖某工具，建议在 SOP 中显式写出工具 id",
            })

    sp = (system_prompt or "").strip()
    if sp and len(sp) > 400 and len(text) < len(sp):
        out.append({
            "severity": "info",
            "category": "sop_prompt_imbalance",
            "field": "sop_body",
            "message": "System Prompt 长于 SOP 正文——细节宜放 SOP，prompt 保持短边界",
            "suggestion": "把长流程/输出格式挪到 SOP Markdown，System Prompt 只留角色与硬边界",
        })

    # Pass-visible summary (same pattern as tool_binding_ok)
    has_sop_warning = any(
        i.get("severity") == "warning" and str(i.get("category") or "").startswith("sop_")
        for i in out
    )
    if not has_sop_warning:
        checks = ["角色", "流程", "产出/目标", "验收/质量"]
        out.append({
            "severity": "info",
            "category": "sop_content_ok",
            "field": "sop_body",
            "message": (
                f"已检查 SOP 内容（{len(text)} 字）："
                + "、".join(checks)
                + "结构齐全"
            ),
            "suggestion": (
                "SOP 内容门禁通过（规则驱动，非 LLM 评分）。"
                "产物质量仍由执行后 review_execution_output 复核。"
            ),
            "fix_available": False,
        })

    return out


@router.post("/workspace/agents/{agent_id}/audit", response_model=AgentAuditResponse)
async def audit_agent_config(
    agent_id: str,
    req: Annotated[Optional[AgentAuditRequest], Body()] = None,
) -> AgentAuditResponse:
    u"""AI 审核：检查 Agent 配置的问题点及建议。规则驱动，毫秒返回，无需 LLM。

    检查项包括：工具/技能上架门禁、字段格式、Coze 残留、必填字段、
    system_prompt/status、**SOP 结构**（角色/流程/目标/验收/绑定引用对齐）、
    **AGENT.md 正文质量**（``prompt_auditor``：模糊形容词、流水线交接/frontmatter、正文长度）、
    以及模型（infra unified_pipeline 策略）、Toolset、loop_type、permissions/triggers、流水线字段。

    请求体可选 ``sop_body`` / ``system_prompt``：编辑页传入未保存草稿，避免只审磁盘旧正文。
    """
    if req is None:
        req = AgentAuditRequest()
    issues = []
    # Load AGENT.md
    from pathlib import Path as _P
    md_path = _P(os.path.expanduser("~/.aiplat")) / "agents" / agent_id / "AGENT.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 的 AGENT.md 不存在")

    raw = md_path.read_text(encoding="utf-8", errors="ignore")
    parts = raw.split("---", 2)
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="AGENT.md YAML frontmatter 解析失败")

    import re as _audit_re, yaml as _yaml
    try:
        fm = _yaml.safe_load(parts[1]) or {}
    except Exception:
        raise HTTPException(status_code=400, detail="AGENT.md frontmatter YAML 非法")

    body = parts[2] if len(parts) > 2 else ""
    # Edit-screen draft: prefer form SOP / system_prompt over disk when provided
    _draft_sop = False
    disk_body = str(body)
    if req.sop_body is not None:
        body = str(req.sop_body)
        # Same text as disk (e.g. 一键修复刚写入) is not an unsaved draft.
        if body.strip() != disk_body.strip():
            _draft_sop = True
    if not isinstance(fm, dict):
        fm = {}
    config = fm.get("config") if isinstance(fm.get("config"), dict) else {}
    if not isinstance(config, dict):
        config = {}
    else:
        config = dict(config)
    if req.system_prompt is not None:
        config["system_prompt"] = str(req.system_prompt)
        fm = dict(fm)
        fm["config"] = config
    if _draft_sop:
        issues.append({
            "severity": "info",
            "category": "audit_draft_sop",
            "field": "sop_body",
            "message": "本次审核使用了编辑框中的 SOP 草稿（尚未点保存也会审）",
            "suggestion": "通过后请点「保存」写入 AGENT.md，否则下次打开仍是磁盘旧正文",
            "fix_available": False,
        })

    # ── Tool catalog ──
    valid_tools: set = set()
    try:
        from core.apps.tools.base import get_tool_registry
        reg = get_tool_registry()
        for tn in (reg.list_tools() or []):
            valid_tools.add(str(tn))
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # ── Skill catalog (+ lifecycle for Agent 上架门禁) ──
    # Engine skills are first-class (runtime-resolvable). Workspace skills need
    # published|listed. Binding an engine-only skill is OK — do NOT require a
    # workspace copy. Lifecycle gate applies only to workspace catalog entries.
    _OK_SKILL_LIFECYCLE = frozenset({"published", "listed"})
    valid_skills: set = set()
    skill_statuses: Dict[str, str] = {}
    workspace_skill_ids: set = set()
    engine_skill_ids: set = set()
    skill_dir = _P(os.path.expanduser("~/.aiplat")) / "skills"
    if skill_dir.exists():
        for d in skill_dir.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                try:
                    sk_raw = (d / "SKILL.md").read_text(encoding="utf-8", errors="ignore")
                    sp = sk_raw.split("---", 2)
                    if len(sp) >= 2:
                        sk_fm = _yaml.safe_load(sp[1]) or {}
                        name = str(sk_fm.get("name") or d.name).strip()
                        if not name:
                            continue
                        st = str(sk_fm.get("status") or "draft").strip().lower() or "draft"
                        valid_skills.add(name)
                        workspace_skill_ids.add(name)
                        workspace_skill_ids.add(d.name)
                        skill_statuses[name] = st
                        skill_statuses[d.name] = st
                        dn = str(sk_fm.get("display_name") or "").strip()
                        if dn:
                            valid_skills.add(dn)
                            skill_statuses[dn] = st
                            workspace_skill_ids.add(dn)
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
    # Engine skills (runtime-resolvable; optional workspace mirror not required)
    engine_skill_dir = _P(__file__).resolve().parents[3] / "core" / "engine" / "skills"
    if engine_skill_dir.exists():
        for d in engine_skill_dir.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                try:
                    sk_raw = (d / "SKILL.md").read_text(encoding="utf-8", errors="ignore")
                    sp = sk_raw.split("---", 2)
                    if len(sp) >= 2:
                        sk_fm = _yaml.safe_load(sp[1]) or {}
                        name = str(sk_fm.get("name") or d.name).strip()
                        if not name:
                            continue
                        valid_skills.add(name)
                        engine_skill_ids.add(name)
                        engine_skill_ids.add(d.name)
                        dn = str(sk_fm.get("display_name") or "").strip()
                        if dn:
                            valid_skills.add(dn)
                            engine_skill_ids.add(dn)
                        # Engine-only: treat as always available (no workspace lifecycle)
                        if name not in workspace_skill_ids:
                            skill_statuses.setdefault(name, "listed")
                            skill_statuses.setdefault(d.name, "listed")
                            if dn:
                                skill_statuses.setdefault(dn, "listed")
                except Exception as e:
                    logging.warning(str(e), exc_info=True)

    # ── Check tools ──
    # Align with Agent 上架硬门禁 (approval.py): tool must be published|listed.
    # Registry membership alone is not enough — draft tools look "missing" in 资产库.
    _OK_TOOL_LIFECYCLE = frozenset({"published", "listed"})
    _TOOL_ALIASES = {
        "knowledge_retrieve": "routed_retrieve",
        "knowledge_retrieval": "routed_retrieve",
        "kb_retrieve": "routed_retrieve",
        "sys_file_read": "file_operations",
        "sys_file_write": "file_operations",
    }
    tools = fm.get("required_tools") or fm.get("tools") or []
    tools_ok: list = []
    for t in tools:
        t_str = str(t).strip()
        if not t_str:
            continue
        if t_str in valid_tools:
            try:
                from core.apps.tools.lifecycle import get_tool_status
                tool_st = get_tool_status(t_str)
            except Exception:
                tool_st = "draft"
            if tool_st not in _OK_TOOL_LIFECYCLE:
                issues.append(_not_listed_unbind_issue(
                    category="tool_not_listed",
                    field="tools",
                    name=t_str,
                    kind="tool",
                    message=(
                        f"工具 '{t_str}' 已在引擎注册表中，但未上架"
                        f"（status={tool_st}）——资产库/Agent 上架会视为不可用"
                    ),
                    list_where="请到工具库提交审核并完成「已发布/已上架」。",
                ))
            else:
                tools_ok.append(t_str)
            # Known tool (listed or not) — never fall through to "不存在"
            continue
        is_syscall = t_str.startswith("sys_")
        alias = _TOOL_ALIASES.get(t_str)
        if alias and (alias in valid_tools or alias == "file_operations"):
            issues.append({
                "severity": "error",
                "category": "invalid_tool",
                "field": "tools",
                "current": t_str,
                "message": f"工具 '{t_str}' 已废弃/未注册",
                "suggestion": f"替换为已注册工具 '{alias}'",
                "fix_available": True,
                "fix": {"type": "replace_tool", "from": t_str, "to": alias},
            })
        elif is_syscall:
            issues.append({
                "severity": "error",
                "category": "invalid_tool",
                "field": "tools",
                "current": t_str,
                "message": f"'{t_str}' 是 syscall，不是 tool",
                "suggestion": "从 tools / required_tools 列表中移除（syscall 不能当 Tool 绑定）",
                "fix_available": True,
                "fix": {"type": "remove_tool", "tool": t_str},
            })
        else:
            issues.append(_missing_binding_create_issue(
                kind="tool",
                name=t_str,
                agent_display=str(fm.get("display_name") or fm.get("name") or agent_id),
                description=str(fm.get("description") or ""),
                sop_text=body,
            ))
    if tools_ok:
        issues.append({
            "severity": "info",
            "category": "tool_binding_ok",
            "field": "tools",
            "current": ", ".join(tools_ok),
            "message": (
                f"已检查 {len(tools_ok)} 个绑定工具（已注册且上架）："
                + "、".join(tools_ok)
            ),
            "suggestion": "工具绑定通过；仍会结合默认 Toolset 校验是否允许调用",
            "fix_available": False,
        })
    # ── Old format tools field ──
    if fm.get("tools") and not fm.get("required_tools"):
        keep = []
        for t in tools:
            t_str = str(t).strip()
            alias = _TOOL_ALIASES.get(t_str, t_str)
            if alias in valid_tools:
                keep.append(alias)
        issues.append({
            "severity": "warning",
            "category": "old_format",
            "field": "tools",
            "message": "使用了旧格式 'tools:' 字段，应迁移到 'required_tools:'",
            "suggestion": "将有效条目写入 required_tools，并删除旧 tools 字段",
            "fix_available": True,
            "fix": {
                "type": "migrate_field",
                "from": "tools",
                "to": "required_tools",
                "keep": keep,
            },
        })

    # ── Coze import artifacts ──
    tags = fm.get("tags") or []
    if "coze" in tags or "imported" in tags:
        has_coze_issues = any(
            i["category"] in (
                "invalid_tool",
                "tool_not_listed",
                "invalid_skill",
                "skill_not_listed",
                "old_format",
            )
            for i in issues
        )
        if has_coze_issues:
            bad_tools = [i["current"] for i in issues if i["category"] in ("invalid_tool", "tool_not_listed")]
            bad_skills = [
                i["current"]
                for i in issues
                if i["category"] in ("invalid_skill", "skill_not_listed")
            ]
            detail = []
            if bad_tools: detail.append(f"工具: {', '.join(bad_tools)}")
            if bad_skills: detail.append(f"技能: {', '.join(bad_skills)}")
            issues.append({
                "severity": "warning", "category": "coze_artifact", "field": "tags",
                "message": f"从 Coze 导入，以下配置需要检查: {'; '.join(detail)}",
                "suggestion": "建议执行 AI 智能填充更新绑定，或手动修正上述工具/技能名",
            })
        else:
            issues.append({
                "severity": "info", "category": "coze_artifact", "field": "tags",
                "message": "从 Coze 导入 — 所有配置项已修正 ✓",
            })

    # ── Skills validity (+ workspace lifecycle; engine skills are first-class) ──
    skills = fm.get("required_skills") or fm.get("skills") or []
    engine_bound: list = []
    for s in skills:
        s_str = str(s).strip()
        if not s_str or s_str in ("[]", "null"):
            continue
        if s_str not in valid_skills:
            issues.append(_missing_binding_create_issue(
                kind="skill",
                name=s_str,
                agent_display=str(fm.get("display_name") or fm.get("name") or agent_id),
                description=str(fm.get("description") or ""),
                sop_text=body,
            ))
            continue
        in_workspace = s_str in workspace_skill_ids
        in_engine = s_str in engine_skill_ids
        # Engine-only: runtime OK — collect for one summary info (not N× tips)
        if in_engine and not in_workspace:
            engine_bound.append(s_str)
            continue
        skill_st = str(skill_statuses.get(s_str) or "unknown").strip().lower() or "unknown"
        if skill_st not in _OK_SKILL_LIFECYCLE:
            issues.append(_not_listed_unbind_issue(
                category="skill_not_listed",
                field="skills",
                name=s_str,
                kind="skill",
                message=(
                    f"技能 '{s_str}' 在工作区库中，但未上架（status={skill_st}）"
                    "——Agent 上架会视为不可用"
                ),
                list_where="请到 Skill 库提交审核并完成「已发布/已上架」。",
            ))
            continue
    if engine_bound:
        issues.append({
            "severity": "info",
            "category": "engine_skill_binding",
            "field": "skills",
            "current": ", ".join(engine_bound),
            "message": (
                f"已绑定 {len(engine_bound)} 个引擎内置 Skill（可直接执行）："
                + "、".join(engine_bound)
            ),
            "suggestion": (
                "引擎 Skill 为平台核心能力，无需同步到工作区库。"
                "若需单独改 SOP/上架态，可再安装工作区副本（同名禁止覆盖引擎）。"
            ),
            "fix_available": False,
        })

    # ── Required fields ──
    if not fm.get("name"):
        issues.append({
            "severity": "error",
            "category": "missing_required",
            "field": "name",
            "message": "缺少必填字段 'name'",
            "suggestion": f"写入目录 id「{agent_id}」（保存 AGENT.md 时也会自动补）",
            "fix_available": True,
            "fix": {"type": "set_name", "name": agent_id},
        })
    if not fm.get("agent_type"):
        loop_hint = str(fm.get("loop_type") or "").strip().lower()
        type_val = loop_hint if loop_hint in (
            "react", "plan", "plan_execute", "function_call", "conversational", "base", "tool",
        ) else "react"
        issues.append({
            "severity": "error",
            "category": "missing_required",
            "field": "agent_type",
            "message": "缺少必填字段 'agent_type'",
            "suggestion": f"写入 agent_type: {type_val}（与 loop_type / 默认 react 对齐，不编造业务角色）",
            "fix_available": True,
            "fix": {"type": "set_agent_type", "agent_type": type_val},
        })

    # ── system_prompt ──
    config = fm.get("config") or {}
    if isinstance(config, dict) and not config.get("system_prompt"):
        issues.append({
            "severity": "warning",
            "category": "missing_system_prompt",
            "field": "config.system_prompt",
            "message": "缺少 system_prompt——运行时将使用 CLAUDE.md 作为回退",
            "suggestion": "添加 config.system_prompt，或在「SOP / 高级」页用 AI 优化 System Prompt",
            "fix_available": True,
            "fix": {
                "type": "set_system_prompt",
                "system_prompt": (
                    f"你是{(fm.get('display_name') or fm.get('name') or agent_id)}。"
                    f"{str(fm.get('description') or '').strip() or '按 AGENT.md 的 Persona/Workflow 执行任务。'}"
                ),
            },
        })

    # ── Status validity ──
    status = str(fm.get("status") or "").strip()
    _STATUS_ALIASES = {
        "enabled": "ready",
        "active": "ready",
        "ok": "ready",
        "online": "ready",
        "listed": "published",
    }
    if status and status not in ("ready", "published", "initializing", "disabled", "deprecated", "draft"):
        mapped = _STATUS_ALIASES.get(status)
        issues.append({
            "severity": "error",
            "category": "invalid_status",
            "field": "status",
            "current": status,
            "message": f"status 值 '{status}' 不合法",
            "suggestion": (
                f"改为 '{mapped}'" if mapped else "使用 ready / published / deprecated / disabled / draft 之一"
            ),
            "fix_available": bool(mapped),
            "fix": {"type": "set_status", "status": mapped} if mapped else None,
        })

    # ── Semantic rules: role-tool mismatch (capability-driven) ──
    agent_name_lower = (fm.get("name") or agent_id).lower()
    agent_type = str(fm.get("agent_type") or "").lower()
    tools_list = fm.get("required_tools") or fm.get("tools") or []
    skills_list = fm.get("required_skills") or fm.get("skills") or []

    # ── SOP content (generic structure + binding alignment; no LLM) ──
    _sp_for_sop = ""
    if isinstance(config, dict):
        _sp_for_sop = str(config.get("system_prompt") or "")
    issues.extend(
        _audit_agent_sop_content(
            body,
            skills=list(skills_list or []),
            tools=list(tools_list or []),
            system_prompt=_sp_for_sop,
        )
    )

    # Deep AGENT.md quality (CLAUDE.md §5.27) — was implemented but unwired.
    try:
        from core.harness.audit import audit_agent_md, prompt_audit_to_issues

        _prompt_rec = audit_agent_md(agent_id, body, frontmatter=fm if isinstance(fm, dict) else {})
        issues.extend(
            prompt_audit_to_issues(
                _prompt_rec,
                frontmatter=fm if isinstance(fm, dict) else {},
            )
        )
    except Exception:
        logging.getLogger(__name__).debug(
            "prompt_auditor skipped for %s", agent_id, exc_info=True
        )

    # Infer capabilities from SOP Knowledge Base + system_prompt context
    _caps_text = (body + " " + _sp_for_sop).lower()
    # Check if SOP has actual knowledge base references (Product Manual, Pricing Guide, etc.)
    _sop_has_kb_content = bool(_audit_re.search(
        r'(?:Product Manual|Pricing Guide|FAQ|知识库|产品手册|定价指南|售后政策|Datasets?:?\s*\S)',
        body, _audit_re.IGNORECASE))
    _has_knowledge = _sop_has_kb_content  # Only from SOP content, no guessing
    _has_conversation = any(kw in _caps_text or kw in agent_name_lower for kw in
        ["对话", "沟通", "回复", "闲聊", "咨询", "接待", "客服", "chitchat",
         "顾问", "秘书", "代表", "助手", "接待员"])
    _has_code = any(kw in _caps_text or kw in agent_name_lower for kw in
        ["代码", "编程", "开发", "生成", "bug", "code", "programm"])
    _has_security = any(kw in _caps_text or kw in agent_name_lower for kw in
        ["安全", "审计", "审查", "合规", "security"])

    _inappropriate_for_knowledge_agent = {"search", "code_execution", "browser", "file_operations", "http", "calculator"}
    if _has_knowledge or _has_conversation:
        for t in tools_list:
            if str(t).strip() in _inappropriate_for_knowledge_agent:
                issues.append({
                    "severity": "warning", "category": "role_tool_mismatch", "field": "tools",
                    "current": t, "message": f"知识/对话型 Agent 不应绑定 '{t}' 工具——它需要网络/代码执行，不匹配当前角色能力",
                    "suggestion": f"解绑 '{t}'，改为绑定 knowledge_query 技能来实现知识库查询",
                    "fix_available": True,
                    "fix": {"type": "remove_tool", "tool": str(t).strip()},
                })

    # ── Semantic rules: missing knowledge base ──
    has_rag_skills = any(s in skills_list for s in ["knowledge_query", "doc_query", "multi_doc_query", "knowledge_retrieve"])
    kb_collections = fm.get("kb_collections") or fm.get("knowledge_bases") or []
    kb_cfg = (fm.get("config") or {})
    if isinstance(kb_cfg, dict):
        kb_collections = kb_collections or kb_cfg.get("kb_collections") or kb_cfg.get("knowledge_bases") or []

    if has_rag_skills and not kb_collections:
        issues.append({
            "severity": "warning", "category": "missing_knowledge_base", "field": "kb_collections",
            "message": "Agent 绑定了 RAG 技能但未选择知识库集合——检索时无数据可查",
            "suggestion": "在知识库集合中选择一个集合（如 default），确保其中有对应的产品手册/FAQ",
        })
    if _has_knowledge and not has_rag_skills:
        issues.append({
            "severity": "info", "category": "no_rag_skill", "field": "skills",
            "message": "Agent 需要知识查询能力，但未绑定 RAG 技能（如 knowledge_query）",
            "suggestion": "添加 knowledge_query 技能，并配置知识库集合",
            "fix_available": True,
            "fix": {"type": "add_skill", "skill": "knowledge_query"},
        })

    # ── Semantic rules: SOP references unbound knowledge ──
    sop_datasets = _audit_re.findall(r'(?:Product Manual|Pricing Guide|FAQ|知识库|产品手册|定价指南|售后政策|Datasets?:?\s*)([^\n]+)', body, _audit_re.IGNORECASE)
    if sop_datasets and not kb_collections:
        issues.append({
            "severity": "info", "category": "sop_kb_unbound", "field": "sop_body",
            "message": f"SOP 中引用了知识库资料（{', '.join(s[:30] for s in sop_datasets[:3])}），但未绑定知识库集合",
            "suggestion": "在知识库集合中选择对应资料集（如 default），或在 KB 中导入这些资料",
            "fix_available": True,
            "fix": {"type": "set_kb_collection", "collection": "default"},
        })

    # ── Model strategy (infra unified_pipeline / best_model_for_purpose) ──
    # Not just "is the model registered": evaluate against purpose requirements.
    # Prefer skill_model_purpose; else loop_type (ReAct⇒agent); else agent_type.
    # (conversational + loop_type=react must NOT silently audit as weak "chat".)
    _AGENT_TYPE_PURPOSE = {
        "rag": "chat",
        "react": "agent",
        "conversational": "chat",
        "wiki_curator": "chat",
        "materials_chat": "chat",
        "plan_execute": "agent",
        "function_call": "agent",
    }
    _LOOP_PURPOSE = {
        "react": "agent",
        "plan": "agent",
        "plan_execute": "agent",
        "function_call": "agent",
    }
    purpose_explicit = str(fm.get("skill_model_purpose") or "").strip()
    agent_type = str(fm.get("agent_type") or "").strip().lower()
    loop_type_early = str(fm.get("loop_type") or "").strip().lower()
    if purpose_explicit:
        model_purpose = purpose_explicit
    elif loop_type_early in _LOOP_PURPOSE:
        model_purpose = _LOOP_PURPOSE[loop_type_early]
    else:
        model_purpose = _AGENT_TYPE_PURPOSE.get(agent_type, "chat")
    configured_model = ""
    if isinstance(config, dict):
        configured_model = str(config.get("model") or "").strip()

    _should_declare_purpose = (
        agent_type in ("react", "plan_execute", "function_call")
        or loop_type_early in ("react", "plan", "plan_execute", "function_call")
    )
    if not purpose_explicit and _should_declare_purpose:
        issues.append({
            "severity": "info",
            "category": "missing_skill_model_purpose",
            "field": "skill_model_purpose",
            "message": (
                f"未声明 skill_model_purpose，将按 "
                f"loop_type={loop_type_early or '—'} / agent_type={agent_type or '—'} "
                f"推断 purpose={model_purpose}"
            ),
            "suggestion": (
                f"建议显式设置 skill_model_purpose: {model_purpose} "
                "（与产品经理等 Agent 对齐），以便审核/流水线走同一套 infra 选型"
            ),
            "fix_available": True,
            "fix": {"type": "set_skill_model_purpose", "purpose": model_purpose},
        })

    try:
        from core.harness.utils.model_injection import (
            best_model_for_purpose_with_meta,
            _load_llm_profile,
            _get_cached_model_manager,
        )
        profile_data = _load_llm_profile() or {}
        known_purposes = set((profile_data.get("purpose_profiles") or {}).keys())
        if purpose_explicit and known_purposes and purpose_explicit not in known_purposes:
            issues.append({
                "severity": "warning",
                "category": "invalid_skill_model_purpose",
                "field": "skill_model_purpose",
                "current": purpose_explicit,
                "message": f"skill_model_purpose '{purpose_explicit}' 不在 llm_profile.purpose_profiles 中",
                "suggestion": (
                    f"改为已知 purpose 之一（如 {', '.join(sorted(known_purposes)[:8])}），"
                    "或补齐工作区 llm_profile 覆盖"
                ),
                "fix_available": True,
                "fix": {
                    "type": "set_skill_model_purpose",
                    "purpose": _AGENT_TYPE_PURPOSE.get(agent_type, "chat"),
                },
            })
            model_purpose = _AGENT_TYPE_PURPOSE.get(agent_type, "chat")

        recommended_meta = best_model_for_purpose_with_meta(model_purpose)
        recommended_model = str(recommended_meta.get("model") or "").strip()
        recommended_tier = str(recommended_meta.get("model_tier") or "unknown")

        if not configured_model or configured_model.lower() == "auto":
            issues.append({
                "severity": "info",
                "category": "model_auto",
                "field": "config.model",
                "message": (
                    f"模型未固定（auto）——运行时将按 purpose={model_purpose} "
                    f"走 infra 自动选择；当前推荐 {recommended_model or '（无）'}"
                    f"（tier={recommended_tier}）"
                ),
                "suggestion": (
                    "可保持 auto 以跟随策略；若需固定，一键写入当前推荐模型"
                ),
                "fix_available": bool(recommended_model),
                "fix": (
                    {"type": "set_model", "model": recommended_model}
                    if recommended_model else None
                ),
            })
        else:
            mgr = _get_cached_model_manager()
            mi = mgr.select(model_name=configured_model) if mgr else None
            if not mi:
                issues.append({
                    "severity": "error",
                    "category": "model_unavailable",
                    "field": "config.model",
                    "current": configured_model,
                    "message": (
                        f"模型 '{configured_model}' 不在 infra ModelManager 注册表中"
                        f"（purpose={model_purpose} 推荐 {recommended_model or 'auto'}）"
                    ),
                    "suggestion": (
                        f"改为 infra 策略推荐的 '{recommended_model}'，或设为 auto"
                        if recommended_model else "检查模型是否已启用/健康，或改为 auto"
                    ),
                    "fix_available": True,
                    "fix": {
                        "type": "set_model",
                        "model": recommended_model or "auto",
                    },
                })
            else:
                purpose_profile = (profile_data.get("purpose_profiles") or {}).get(
                    model_purpose, {}
                )
                fits_cap = True
                try:
                    from infra.management.model.manager import _filter_capability
                    fits_cap = bool(
                        _filter_capability(mi, model_purpose, purpose_profile, profile_data)
                    )
                except Exception:
                    fits_cap = True  # noqa: audit best-effort

                # Local Ollama RAM budget (same hard filter as unified_pipeline).
                # Capability-only audit previously let gemma4:12b pass as "usable"
                # on 16GB Macs while runtime selection already rejects it.
                fits_ram = True
                ram_reason = ""
                try:
                    from infra.management.model.manager import (
                        _hard_filter,
                        collect_platform_resources,
                    )
                    _res = collect_platform_resources()
                    fits_ram, ram_reason = _hard_filter(mi, _res, profile_data)
                except Exception:
                    fits_ram = True  # noqa: audit best-effort

                configured_tier = "unknown"
                try:
                    configured_tier = str(mgr.get_model_tier(configured_model, profile_data))
                except Exception:
                    configured_tier = "unknown"

                if not fits_ram:
                    issues.append({
                        "severity": "warning",
                        "category": "model_local_ram_exceeded",
                        "field": "config.model",
                        "current": configured_model,
                        "message": (
                            f"模型 '{configured_model}' 超过本机本地模型 RAM 预算，"
                            f"容易楔死 Ollama：{ram_reason or 'exceeds local_max_ram_ratio'}"
                        ),
                        "suggestion": (
                            f"改为 auto（当前策略推荐 '{recommended_model}'），"
                            "或换更小的本地模型 / 使用远程 API"
                            if recommended_model
                            else "改为 auto，或换更小的本地模型 / 使用远程 API"
                        ),
                        "fix_available": True,
                        "fix": {
                            "type": "set_model",
                            "model": recommended_model or "auto",
                        },
                    })
                elif not fits_cap:
                    issues.append({
                        "severity": "warning",
                        "category": "model_unsuitable",
                        "field": "config.model",
                        "current": configured_model,
                        "message": (
                            f"模型 '{configured_model}'（tier={configured_tier}）"
                            f"不满足 purpose={model_purpose} 的能力要求"
                            f"（infra unified_pipeline 会优先选 {recommended_model or '其他合格模型'}）"
                        ),
                        "suggestion": (
                            f"按策略改为 '{recommended_model}'，或将 config.model 设为 auto"
                            if recommended_model else "改为 auto，交由 infra 自动选择"
                        ),
                        "fix_available": True,
                        "fix": {
                            "type": "set_model",
                            "model": recommended_model or "auto",
                        },
                    })
                elif (
                    recommended_model
                    and configured_model != recommended_model
                ):
                    # 同 tier 也可能次优（例：gemma4:12b 与 qwen2.5-coder:7b 同为 T4，
                    # 但 unified_pipeline 因时延/楔死风险仍推荐后者）。不得再要求 tier 不同。
                    tier_note = (
                        f"；当前 tier={configured_tier}，推荐 tier={recommended_tier}"
                        if recommended_tier not in ("unknown", "")
                        and configured_tier != recommended_tier
                        else f"（tier={configured_tier}）"
                    )
                    issues.append({
                        "severity": "warning",
                        "category": "model_suboptimal",
                        "field": "config.model",
                        "current": configured_model,
                        "message": (
                            f"当前模型 '{configured_model}'{tier_note}可用，"
                            f"但 purpose={model_purpose} 的 infra 自动选型更推荐 "
                            f"'{recommended_model}'"
                            + (
                                f"（tier={recommended_tier}）"
                                if recommended_tier not in ("unknown", "")
                                else ""
                            )
                        ),
                        "suggestion": (
                            "一键切换到策略推荐模型，或改回 auto；"
                            "大本地模型在长 prompt 下可能楔死 Ollama"
                        ),
                        "fix_available": True,
                        "fix": {"type": "set_model", "model": recommended_model},
                    })
                else:
                    issues.append({
                        "severity": "info",
                        "category": "model_binding_ok",
                        "field": "config.model",
                        "current": configured_model,
                        "message": (
                            f"已固定模型 '{configured_model}'（tier={configured_tier}），"
                            f"与 purpose={model_purpose} 策略一致"
                            + (
                                f"（推荐 {recommended_model}）"
                                if recommended_model else ""
                            )
                        ),
                        "suggestion": "可保持固定；若希望跟随 infra 策略变化，改为 auto",
                    })
    except Exception as e:
        logging.warning("model strategy audit skipped: %s", e, exc_info=True)
        if configured_model and configured_model.lower() != "auto":
            issues.append({
                "severity": "info",
                "category": "model_audit_skipped",
                "field": "config.model",
                "current": configured_model,
                "message": f"无法完成 infra 模型策略审核：{e}",
                "suggestion": "确认 infra ModelManager / llm_profile 可用后重试审核",
            })

    # ── Toolset ──
    toolset_name = str(fm.get("toolset") or "").strip() or "workspace_default"
    try:
        from core.harness.tools.toolsets import DEFAULT_TOOLSETS, resolve_toolset, is_tool_allowed
        if toolset_name not in DEFAULT_TOOLSETS:
            issues.append({
                "severity": "warning",
                "category": "invalid_toolset",
                "field": "toolset",
                "current": toolset_name,
                "message": f"Toolset '{toolset_name}' 未定义，运行时会回退到 workspace_default",
                "suggestion": (
                    f"改为已知值：{', '.join(sorted(DEFAULT_TOOLSETS.keys()))}"
                ),
                "fix_available": True,
                "fix": {"type": "set_toolset", "toolset": "workspace_default"},
            })
            toolset_policy = resolve_toolset("workspace_default")
        else:
            toolset_policy = resolve_toolset(toolset_name)

        # Only gate tools that toolsets actually govern (packs cover file/web/browser/…).
        # Engine tools like routed_retrieve sit outside packs — skip to avoid false positives.
        _toolset_governed = set()
        for _pol in DEFAULT_TOOLSETS.values():
            _toolset_governed |= set(_pol.allowed_tools or set())
        for t in tools_list:
            t_str = str(t).strip()
            if not t_str:
                continue
            if t_str not in valid_tools and not t_str.startswith("mcp."):
                continue
            if not t_str.startswith("mcp.") and t_str not in _toolset_governed:
                continue
            allowed, reason = is_tool_allowed(toolset_policy, t_str, None)
            if not allowed:
                issues.append({
                    "severity": "warning",
                    "category": "toolset_tool_mismatch",
                    "field": "toolset",
                    "current": t_str,
                    "message": (
                        f"工具 '{t_str}' 不在 toolset '{toolset_policy.name}' 允许列表中"
                        f"{f'（{reason}）' if reason else ''}"
                    ),
                    "suggestion": (
                        "换用包含该工具的 toolset（如 full/browser），或从 required_tools 解绑"
                    ),
                })

        if toolset_name == "mcp_readonly":
            if skills_list:
                issues.append({
                    "severity": "warning",
                    "category": "toolset_blocks_skills",
                    "field": "toolset",
                    "message": "toolset=mcp_readonly 禁止调用 Skill，但 Agent 已绑定技能",
                    "suggestion": "改用 workspace_default，或解绑技能仅走 MCP 工具",
                    "fix_available": True,
                    "fix": {"type": "set_toolset", "toolset": "workspace_default"},
                })
            mcp_bound = fm.get("mcp_servers") or fm.get("mcp_ids") or []
            if not mcp_bound:
                issues.append({
                    "severity": "warning",
                    "category": "toolset_mcp_unbound",
                    "field": "toolset",
                    "message": "toolset=mcp_readonly 但未绑定 MCP 服务器",
                    "suggestion": "在 Agent 中绑定 MCP，或改用其他 toolset",
                })

        if toolset_name == "full":
            high_risk = {"http", "browser", "database", "code"}
            bound_risk = {str(t).strip() for t in tools_list} & high_risk
            if not bound_risk:
                issues.append({
                    "severity": "info",
                    "category": "toolset_overprivileged",
                    "field": "toolset",
                    "message": "使用了高风险 toolset=full，但未绑定 http/browser/database/code",
                    "suggestion": "若无需高风险能力，改为 workspace_default 降低暴露面",
                    "fix_available": True,
                    "fix": {"type": "set_toolset", "toolset": "workspace_default"},
                })
    except Exception as e:
        logging.warning("toolset audit skipped: %s", e, exc_info=True)

    # ── Loop type / Agent policy ──
    # Runtime + UI default is react; missing is fine — only flag illegal values.
    loop_type = str(fm.get("loop_type") or "").strip().lower()
    _VALID_LOOPS = frozenset({"react", "function_call"})
    if loop_type and loop_type not in _VALID_LOOPS:
        issues.append({
            "severity": "warning",
            "category": "invalid_loop_type",
            "field": "loop_type",
            "current": loop_type,
            "message": f"loop_type '{loop_type}' 非法",
            "suggestion": "使用 react 或 function_call",
            "fix_available": True,
            "fix": {"type": "set_loop_type", "loop_type": "react"},
        })

    # ── Permissions / triggers ──
    # UI/runtime default is ["llm:generate"] when omitted — don't nag "未声明".
    perms_raw = fm.get("permissions")
    if perms_raw is None:
        perms = ["llm:generate"]
        derived = _derive_agent_permissions(
            tools=[str(t) for t in tools_list],
            skills=[str(s) for s in skills_list],
            mcp_ids=[str(m) for m in (fm.get("mcp_servers") or fm.get("mcp_ids") or [])],
            description=str(fm.get("description") or ""),
            sop_text=body,
        )
        missing_perms = [p for p in derived if p not in perms]
        if missing_perms:
            issues.append({
                "severity": "info",
                "category": "permissions_incomplete",
                "field": "permissions",
                "message": (
                    f"未显式声明 permissions（默认 llm:generate），"
                    f"按绑定能力建议补充：{', '.join(missing_perms)}"
                ),
                "suggestion": "一键写入最小权限集到 AGENT.md",
                "fix_available": True,
                "fix": {
                    "type": "set_permissions",
                    "permissions": list(dict.fromkeys([*perms, *missing_perms])),
                },
            })
    elif not isinstance(perms_raw, list) or any(not isinstance(p, str) for p in perms_raw):
        issues.append({
            "severity": "error",
            "category": "invalid_permissions",
            "field": "permissions",
            "message": "permissions 必须是字符串数组",
            "suggestion": '例如 ["llm:generate"]',
            "fix_available": True,
            "fix": {"type": "set_permissions", "permissions": ["llm:generate"]},
        })
    else:
        perms = [str(p).strip() for p in perms_raw if str(p).strip()]
        if "llm:generate" not in perms:
            issues.append({
                "severity": "warning",
                "category": "permissions_missing_llm",
                "field": "permissions",
                "message": "permissions 缺少 llm:generate，Agent 对话/生成可能被拒",
                "suggestion": "加入 llm:generate",
                "fix_available": True,
                "fix": {
                    "type": "set_permissions",
                    "permissions": ["llm:generate", *perms],
                },
            })
        derived = _derive_agent_permissions(
            tools=[str(t) for t in tools_list],
            skills=[str(s) for s in skills_list],
            mcp_ids=[str(m) for m in (fm.get("mcp_servers") or fm.get("mcp_ids") or [])],
            description=str(fm.get("description") or ""),
            sop_text=body,
        )
        missing_perms = [p for p in derived if p not in perms]
        if missing_perms:
            issues.append({
                "severity": "info",
                "category": "permissions_incomplete",
                "field": "permissions",
                "message": f"按绑定能力建议补充权限：{', '.join(missing_perms)}",
                "suggestion": "一键合并最小权限集（最小特权推导）",
                "fix_available": True,
                "fix": {
                    "type": "set_permissions",
                    "permissions": list(dict.fromkeys([*perms, *missing_perms])),
                },
            })

    triggers_raw = fm.get("trigger_conditions")
    if triggers_raw is not None:
        if not isinstance(triggers_raw, list):
            issues.append({
                "severity": "warning",
                "category": "invalid_triggers",
                "field": "trigger_conditions",
                "message": "trigger_conditions 应为字符串数组（每行一条触发词）",
                "suggestion": "改为 YAML 列表，或在编辑器中按行填写",
            })
        elif any(not str(t).strip() for t in triggers_raw):
            issues.append({
                "severity": "info",
                "category": "empty_trigger",
                "field": "trigger_conditions",
                "message": "trigger_conditions 含空条目",
                "suggestion": "删除空行，保留有效触发短语",
            })

    # ── Pipeline fields ──
    phase = str(fm.get("phase") or "").strip()
    phase_desc = str(fm.get("phase_description") or "").strip()
    hitl_after = bool(fm.get("hitl_after_execute"))
    hitl_phase = str(fm.get("hitl_after_phase") or "").strip()
    output_artifact = str(fm.get("output_artifact") or "").strip()
    scoring = fm.get("scoring_dimensions")

    if hitl_after and not hitl_phase:
        issues.append({
            "severity": "warning",
            "category": "hitl_phase_missing",
            "field": "hitl_after_phase",
            "message": "已启用 hitl_after_execute 但未填写 hitl_after_phase",
            "suggestion": "填写暂停阶段名，或关闭「执行后暂停」",
            "fix_available": True,
            "fix": {
                "type": "set_hitl_after_phase",
                "phase": phase or phase_desc or "review",
            },
        })

    if phase and not phase_desc:
        issues.append({
            "severity": "info",
            "category": "missing_phase_description",
            "field": "phase_description",
            "message": f"已声明 phase={phase} 但缺少 phase_description",
            "suggestion": "补充阶段描述，便于流水线 UI / 交接说明",
            "fix_available": True,
            "fix": {
                "type": "set_phase_description",
                "phase_description": f"{phase} 阶段",
            },
        })

    if phase and not output_artifact:
        issues.append({
            "severity": "info",
            "category": "missing_output_artifact",
            "field": "output_artifact",
            "message": f"流水线阶段 phase={phase} 未声明 output_artifact",
            "suggestion": "设置产物 key（如 prd / architecture），便于下游 depends_on",
        })

    if scoring is not None:
        if not isinstance(scoring, list):
            issues.append({
                "severity": "warning",
                "category": "invalid_scoring_dimensions",
                "field": "scoring_dimensions",
                "message": "scoring_dimensions 应为对象数组",
                "suggestion": "每项含 name/weight/threshold/description",
            })
        else:
            for idx, dim in enumerate(scoring):
                if not isinstance(dim, dict) or not dim.get("name"):
                    issues.append({
                        "severity": "warning",
                        "category": "invalid_scoring_dimensions",
                        "field": "scoring_dimensions",
                        "message": f"scoring_dimensions[{idx}] 缺少 name",
                        "suggestion": "每项至少包含 name 与 weight",
                    })
                    break

    depends_on = fm.get("depends_on")
    if depends_on is not None and not isinstance(depends_on, list):
        issues.append({
            "severity": "warning",
            "category": "invalid_depends_on",
            "field": "depends_on",
            "message": "depends_on 应为字符串数组（上游 artifact key）",
            "suggestion": "例如 depends_on: [prd]",
        })

    # ── Bound assets: MCP / sub-agents / workflows（存在性 + 上架态）──
    _OK_ASSET = frozenset({"published", "listed"})
    agents_home = _P(os.path.expanduser("~/.aiplat")) / "agents"

    def _agent_status_on_disk(aid: str) -> Optional[str]:
        p = agents_home / aid / "AGENT.md"
        if not p.exists():
            return None
        try:
            raw_a = p.read_text(encoding="utf-8", errors="ignore")
            sp = raw_a.split("---", 2)
            if len(sp) < 2:
                return "unknown"
            afm = _yaml.safe_load(sp[1]) or {}
            return str(afm.get("status") or "draft").strip().lower() or "draft"
        except Exception:
            return "unknown"

    mcp_bound = [
        str(m).strip()
        for m in (fm.get("mcp_servers") or fm.get("mcp_ids") or [])
        if str(m).strip()
    ]
    mcp_ok: list = []
    if mcp_bound:
        mcp_mgr = None
        try:
            from core.management.mcp_manager import MCPManager
            mcp_mgr = MCPManager(scope="workspace")
        except Exception as e:
            logging.warning("mcp binding audit: %s", e, exc_info=True)
        for mid in mcp_bound:
            srv = mcp_mgr.get_server(mid) if mcp_mgr else None
            if not srv:
                issues.append(_missing_binding_create_issue(
                    kind="mcp",
                    name=mid,
                    agent_display=str(fm.get("display_name") or fm.get("name") or agent_id),
                    description=str(fm.get("description") or ""),
                    sop_text=body,
                ))
                continue
            st = str(getattr(srv, "status", "") or "draft").strip().lower() or "draft"
            if st not in _OK_ASSET:
                issues.append(_not_listed_unbind_issue(
                    category="mcp_not_listed",
                    field="mcp_servers",
                    name=mid,
                    kind="mcp",
                    message=f"MCP '{mid}' 未上架（status={st}）——Agent 上架硬门禁会拒绝",
                    list_where="请到 MCP 库提交审核并上架到 published/listed。",
                ))
            else:
                mcp_ok.append(mid)
            if not getattr(srv, "enabled", True):
                issues.append(_not_listed_unbind_issue(
                    category="mcp_disabled",
                    field="mcp_servers",
                    name=mid,
                    kind="mcp",
                    message=f"MCP '{mid}' 已绑定但未启用（enabled=false）",
                    list_where="请在 MCP 编辑页开启 enabled。",
                    severity="warning",
                ))
    if mcp_ok:
        issues.append({
            "severity": "info",
            "category": "mcp_binding_ok",
            "field": "mcp_servers",
            "current": ", ".join(mcp_ok),
            "message": (
                f"已检查 {len(mcp_ok)} 个绑定 MCP（已存在且上架）："
                + "、".join(mcp_ok)
            ),
            "suggestion": "MCP 绑定通过；若某服务 enabled=false 仍会单独告警",
            "fix_available": False,
        })

    sub_agents = [
        str(a).strip()
        for a in (fm.get("agent_ids") or [])
        if str(a).strip() and str(a).strip() != agent_id
    ]
    sub_agent_ok: list = []
    for sid in sub_agents:
        st = _agent_status_on_disk(sid)
        if st is None:
            issues.append(_missing_binding_create_issue(
                kind="agent",
                name=sid,
                agent_display=str(fm.get("display_name") or fm.get("name") or agent_id),
                description=str(fm.get("description") or ""),
                sop_text=body,
            ))
        elif st not in _OK_ASSET and st not in ("ready",):
            # ready = 待审核，仍不可给生产 Agent 委派；与上架门禁对齐用 published|listed
            issues.append(_not_listed_unbind_issue(
                category="sub_agent_not_listed",
                field="agent_ids",
                name=sid,
                kind="agent",
                message=f"子 Agent '{sid}' 未上架（status={st}）",
                list_where="请到应用库提交审核并上架到 published/listed。",
                severity="error" if st in ("draft", "deprecated", "disabled") else "warning",
            ))
        elif st == "ready":
            issues.append(_not_listed_unbind_issue(
                category="sub_agent_not_listed",
                field="agent_ids",
                name=sid,
                kind="agent",
                message=f"子 Agent '{sid}' 仍为待审核（status=ready）",
                list_where="请在审批中心完成功能审核与上架后再委派。",
                severity="warning",
            ))
        elif st in _OK_ASSET:
            sub_agent_ok.append(sid)
    if sub_agent_ok:
        issues.append({
            "severity": "info",
            "category": "sub_agent_binding_ok",
            "field": "agent_ids",
            "current": ", ".join(sub_agent_ok),
            "message": (
                f"已检查 {len(sub_agent_ok)} 个子 Agent（已存在且上架）："
                + "、".join(sub_agent_ok)
            ),
            "suggestion": "子 Agent 绑定通过",
            "fix_available": False,
        })

    wf_bound = [
        str(w).strip()
        for w in (fm.get("workflows") or fm.get("workflow_ids") or [])
        if str(w).strip()
    ]
    workflow_ok: list = []
    if wf_bound:
        known_wf: dict = {}  # id/name -> status
        try:
            wf_dir = _P(os.path.expanduser("~/.aiplat")) / "workflows"
            if wf_dir.exists():
                for d in wf_dir.iterdir():
                    if d.is_dir():
                        known_wf.setdefault(d.name, "ready")
                    elif d.suffix in (".json", ".yaml", ".yml"):
                        known_wf.setdefault(d.stem, "ready")
        except Exception as e:
            logging.warning("workflow dir scan: %s", e, exc_info=True)
        try:
            from core.api.core_facade import WorkflowManager
            wmgr = WorkflowManager(scope="workspace")
            for w in (wmgr.list_workflows() or []):
                st = str(getattr(w, "status", "") or "ready").lower()
                for key in (getattr(w, "id", None), getattr(w, "name", None)):
                    wid = str(key or "").strip()
                    if wid:
                        known_wf[wid] = st
        except Exception:
            pass  # noqa: optional
        for wid in wf_bound:
            if known_wf and wid not in known_wf:
                issues.append(_missing_binding_create_issue(
                    kind="workflow",
                    name=wid,
                    agent_display=str(fm.get("display_name") or fm.get("name") or agent_id),
                    description=str(fm.get("description") or ""),
                    sop_text=body,
                ))
            elif wid in known_wf:
                st = known_wf[wid]
                if st not in _OK_ASSET and st != "ready":
                    issues.append(_not_listed_unbind_issue(
                        category="workflow_not_listed",
                        field="workflows",
                        name=wid,
                        kind="workflow",
                        message=f"Workflow '{wid}' 未上架（status={st}）",
                        list_where="请到编排库提交审核并上架。",
                        severity="warning",
                    ))
                else:
                    # published|listed|ready（编排侧 ready 视为可用关联）
                    workflow_ok.append(wid)
    if workflow_ok:
        issues.append({
            "severity": "info",
            "category": "workflow_binding_ok",
            "field": "workflows",
            "current": ", ".join(workflow_ok),
            "message": (
                f"已检查 {len(workflow_ok)} 个关联 Workflow（已存在且可用）："
                + "、".join(workflow_ok)
            ),
            "suggestion": "Workflow 关联通过（编排模板可选绑定）",
            "fix_available": False,
        })

    # ── Summary ──
    from core.management.asset_audit import summarize_audit_issues

    summary = summarize_audit_issues(issues)

    # ── Model quality feedback: audit result → model scoring ──
    try:
        from core.harness.routing.model_feedback import record_model_quality
        _model_name = (fm.get("config") or {}).get("model") if isinstance(fm, dict) else ""
        if _model_name:
            import asyncio
            asyncio.create_task(asyncio.to_thread(record_model_quality, _model_name, "agent_creation", issues))
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    return AgentAuditResponse(
        agent_id=agent_id,
        issues=issues,
        summary=summary,
    )
