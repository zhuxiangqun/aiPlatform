from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Annotated, Dict, List, Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from core.api.deps import actor_from_http, rbac_guard
from core.api.utils.governance import gate_error_envelope, ui_url
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.syscalls.llm import sys_llm_generate
from core.schemas_agents import AgentAutoFillBatchRequest, AgentAutoFillBatchResponse
from core.schemas_agents import AgentCreateRequest, AgentUpdateRequest, AgentAutoFillRequest, AgentAutoFillResponse, RoleDefinitionResponse
import asyncio as _asyncio

# LLM config for auto-fill endpoints — longer timeout for local CPU models
from core.adapters.llm.base import LLMConfig as _LlmConfig
kLlmConfig = _LlmConfig(model="", timeout=120)

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
                from core.harness.infrastructure.permissions import get_permission_manager
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
        resp = await model.generate(messages, config=kLlmConfig)
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


def _scan_skills_direct() -> List[Dict[str, Any]]:
    """Scan engine + workspace skill directories, return structured entries.
    
    Returns list of {name, display_name, category, description, triggers}.
    """
    import yaml as _yaml
    from pathlib import Path as _Py
    import os as _os
    entries = []
    
    # Engine skills
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
    
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
                entries.append({
                    "name": skill_id,
                    "display_name": str(fm.get("display_name") or fm.get("displayName") or skill_id),
                    "category": str(fm.get("category") or ""),
                    "description": str(fm.get("description") or ""),
                    "triggers": list(fm.get("triggers") or []),
                })
            except Exception:
                continue
    return entries


def _map_capabilities_to_skills(capabilities: list, skill_catalog: list) -> list:
    """Map role capabilities to skills via SKILL.md description + triggers overlap.
    
    No hardcoded keywords. Pure configuration-driven.
    """
    import re as _re
    scored = []
    for skill in skill_catalog:
        desc = (skill.get('description','') or '').lower()
        trigs = ' '.join(str(t) for t in (skill.get('triggers') or [])).lower()
        cat = (skill.get('category','') or '').lower()
        name = (skill.get('name','') or '').lower()
        disp = (skill.get('display_name','') or '').lower()
        
        score = 0
        for cap in capabilities:
            cap_lower = cap.lower()
            # Triggers match = strongest signal (3x)
            if cap_lower in trigs:
                score += 6
            # Display name / skill name direct match
            if cap_lower in name or cap_lower in disp:
                score += 5
            # Description contains capability
            if cap_lower in desc:
                score += 4
            # Character bigram overlap (Chinese word-like matching)
            cap_bigrams = {cap_lower[i:i+2] for i in range(len(cap_lower)-1)} if len(cap_lower) >= 2 else set()
            trig_bigrams = {trigs[i:i+2] for i in range(len(trigs)-1)} if len(trigs) >= 2 else set()
            desc_bigrams = {desc[i:i+2] for i in range(len(desc)-1)} if len(desc) >= 2 else set()
            trig_hit = len(cap_bigrams & trig_bigrams)  # Matches against triggers (higher weight)
            desc_hit = len(cap_bigrams & desc_bigrams)
            if trig_hit >= 1:
                score += trig_hit * 3
            elif desc_hit >= 2:
                score += desc_hit
        if score > 0:
            scored.append((skill["name"], score))
    scored.sort(key=lambda x: -x[1])
    return [s[0] for s in scored[:3]]  # Top 3 matches


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
        from core.harness.utils.prompt_loader import _async_prompt_resolve
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose

        prompt = await _async_prompt_resolve("agent-role-definition",
            name=req.name or '(待填写)', description=req.description or '(无)',
        )
        model_name = best_model_for_purpose("agent_creation")
        model = create_selected_adapter(model_name=model_name)
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("agent-role-system")},
            {"role": "user", "content": prompt},
        ]
        resp = await model.generate(messages, config=kLlmConfig)
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
async def _do_auto_fill(req: AgentAutoFillRequest) -> AgentAutoFillResponse:
    """Sync auto-fill — LLM generates role, backend maps skills/tools/SOP."""
    import json as _json, re as _re

    # ── Build role section for prompt ──────────────────────────────
    role_section = ""
    rd = None
    if hasattr(req, "role_definition") and isinstance(req.role_definition, dict):
        rd = req.role_definition
        role_section = f"""
## 已确认的角色定义
- 角色名称: {rd.get('role_name', '')}
- 职责: {', '.join(rd.get('responsibilities', []))}
- 使用场景: {', '.join(rd.get('scenarios', []))}
- 需要的能力: {', '.join(rd.get('required_capabilities', []))}
- 协作关系: {rd.get('workflow_hint', '无')}
"""

    # ── Call LLM (simplified: only agent_type + system_prompt + memory + triggers) ──
    from core.harness.utils.prompt_loader import _async_prompt_resolve
    # Build skill catalog summary for LLM to directly suggest matching skill names
    # (P1: include id so LLM returns the id the frontend MultiSelect expects)
    skill_catalog = _scan_skills_direct()
    _name_to_id = {}
    skills_text_lines = []
    for s in skill_catalog:
        sid = s.get("id", s["name"])
        _name_to_id[s["name"]] = sid
        skills_text_lines.append(f"- {sid}: {s.get('description','')[:60]}")
    skills_text = "\n".join(skills_text_lines)

    # Build inline prompt — LLM generates skills + config + SOP in one pass
    role_hint = ""
    if rd and isinstance(rd, dict):
        role_hint = f"\n角色: {rd.get('role_name','')}. 职责: {', '.join(rd.get('responsibilities',[])[:3])}"
    inline_prompt = (
        f"你是AI平台配置专家。为以下Agent推荐最佳配置。只输出JSON。\n\n"
        f"Agent名称: {req.name or '(待填写)'}\n"
        f"描述: {req.description or '(无)'}\n"
        f"{role_hint}\n\n"
        f"可用技能列表（必须从中选择，禁止使用不存在于列表中的id）:\n{skills_text}\n\n"
        f'输出JSON: {{"agent_type":"react",'
        f'"skills":["skill-id1","skill-id2"],"sop_text":"1. x\\n2. y\\n3. z",'
        f'"memory_config":{{}},"reasoning":"..."}}\n'
        f"skills必须严格从以上列表选取。若无匹配项skills留空[]。sop_text中禁止引用你未选的技能。"
    )
    prompt = inline_prompt

    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        model_name = best_model_for_purpose("agent_creation")
        model = create_selected_adapter(model_name=model_name)
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("agent-auto-fill-system-role")},
            {"role": "user", "content": prompt},
        ]
        resp = await model.generate(messages, config=kLlmConfig)
        content = resp.content if hasattr(resp, 'content') else str(resp)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")

    # ── Parse JSON response (only agent_type + config + memory + triggers + reasoning) ──
    import logging as _log
    clean = content.strip()
    if clean.startswith("```"):
        clean = _re.sub(r'^```\w*\n?', '', clean)
        clean = _re.sub(r'\n?```$', '', clean)
    if '{' in clean and clean.index('{') > 0 and clean.index('{') < 200:
        clean = clean[clean.index('{'):]
    try:
        data, _end = _json.JSONDecoder().raw_decode(clean)
    except _json.JSONDecodeError:
        data = _extract_json_fallback(clean, content, _re, _json, _log)
    if data is None:
        raise HTTPException(status_code=422, detail="LLM 返回格式异常，请重试")

    agent_type = str(data.get("agent_type", "react"))[:20]
    config = data.get("config", {}) if isinstance(data.get("config"), dict) else {}

    # ── Skill matching: LLM ids > LLM names→ids > capability map > empty ──
    skill_catalog = _scan_skills_direct()
    catalog_ids = {s.get("id", s["name"]) for s in skill_catalog}
    # Rebuild name→id map (P1 fix: return IDs, not names)
    _name_to_id = {}
    for s in skill_catalog:
        _name_to_id[s["name"]] = s.get("id", s["name"])
    skills = []
    missing_skills = []
    llm_skills = data.get("skills", [])
    if isinstance(llm_skills, list) and llm_skills:
        unknown_skills = []
        mapped = []
        for s in llm_skills:
            if not isinstance(s, str): continue
            sid = _name_to_id.get(s, s)
            if sid in catalog_ids:
                mapped.append(sid)
            else:
                unknown_skills.append(s)
        skills = mapped[:5]
        for s in unknown_skills[:5]:
            missing_skills.append({
                "capability": s,
                "suggested_name": s,
                "how_to_create": f"Skill库 → 新建 → 名称'{s}' → 编辑SOP → 保存 → 回到本页重新AI填充",
            })
    tools = []

    # ── Detect missing assets and provide actionable guidance ──
    capabilities = list((rd or {}).get("required_capabilities", []) or [])
    # If no role definition, infer capabilities from description keywords
    if not capabilities:
        desc = str(getattr(req, "description", "") or "").strip()
        _desc_caps = []
        for kw, cap in [("诊断", "诊断分析"), ("检测", "异常检测"), ("分析", "数据分析"),
                         ("文档", "文档处理"), ("检索", "知识检索"), ("图谱", "关联图谱"),
                         ("代码", "代码生成"), ("安全", "安全检查"), ("监控", "监控告警")]:
            if kw in desc: _desc_caps.append(cap)
        capabilities = _desc_caps[:5]
    if not skills:
        skills = _map_capabilities_to_skills(capabilities, skill_catalog) if capabilities else []
    else:
        # Supplement: also map capabilities to skills (LLM may miss some)
        extra = _map_capabilities_to_skills(capabilities, skill_catalog) if capabilities else []
        for s in extra:
            if s not in skills:
                skills.append(s)
    if not skills and capabilities:
        for cap in capabilities[:5]:
            missing_skills.append({
                "capability": cap,
                "suggested_name": _suggest_skill_name(cap),
                "how_to_create": f"Skill库 → 新建 → 名称'{_suggest_skill_name(cap)}' → 编辑SOP → 保存 → 回到本页重新AI填充",
            })

    # If everything is empty, provide a generic guidance
    if not skills and not missing_skills:
        missing_skills.append({
            "capability": "诊断分析",
            "suggested_name": "field-assessment",
            "how_to_create": "Skill库 → 新建 → 名称'field-assessment' → 粘贴下方SOP → 保存 → 回到本页重新AI填充",
        })

    missing_tools = []
    if not tools and skills:
        missing_tools = _infer_missing_tools_for_skills(skills)

    missing_mcps: list = []
    desc = getattr(req, "description", "") or ""
    if desc and any(kw in str(desc) for kw in ("对接", "外部", "API", "数据库", "IM", "飞书", "企微")):
        missing_mcps = [{
            "type": "external_api",
            "description": "Agent描述涉及外部系统对接，建议配置MCP连接",
            "how_to_create": "应用能力层 → MCP库 → 新建 → 配置连接参数 → 测试连通 → 回到本页重新AI填充",
        }]

    # ── SOP: LLM-generated > role-definition-derived > empty ──
    sop_text = data.get("sop_text", "")
    if not sop_text and rd and isinstance(rd, dict):
        sop_text = _generate_sop_from_role(rd, skills)

    # Auto-sync system_prompt from sop_text if missing
    if (not config.get("system_prompt") or not str(config.get("system_prompt", "")).strip()) and sop_text:
        lines = sop_text.strip().split('\n')
        first = [l.strip() for l in lines if l.strip() and not l.strip().startswith('#')]
        if first:
            config["system_prompt"] = first[0][:200]

    return AgentAutoFillResponse(
        agent_type=agent_type,
        config=config,
        skills=skills,
        tools=tools,
        mcp_ids=[],
        missing_skills=missing_skills,
        missing_tools=missing_tools,
        missing_mcps=missing_mcps,
        agent_ids=[],
        memory_config=_ensure_memory_config(data.get("memory_config")),
        sop_text=sop_text,
        reasoning=str(data.get("reasoning", ""))[:500],
        workflow_ids=[],
        trigger_conditions=list(data.get("trigger_conditions", []))[:20],
        template_id="",
        stages=list(data.get("stages", []))[:20],
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
        resp = await model.generate(messages, config=kLlmConfig)
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
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
        if not entries:
            entries = ["(no workflow templates available)"]
    except Exception:
        entries = ["(unable to load workflow catalog)"]
    return entries




# ── Seed templates (must be before {agent_id} to avoid route conflict) ──

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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

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
    stream_mode = str(opts.get("stream", "")).lower() in ("1", "true", "yes")
    resp = await run_workspace_agent(
        agent_info=agent,
        user_message=user_message,
        max_steps=int(user_config.get("max_steps", 10)),
        toolset=str(opts.get("toolset", "")),
        session_id=str(payload.get("session_id", "") or f"ws-{agent_id}"),
        stream=stream_mode,
    )

    try:
        await _audit_execute(rt, http_request=http_request, payload=payload, resource_type="agent", resource_id=str(agent_id), resp=resp)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return JSONResponse(status_code=200 if resp.get("ok") else 500, content=resp)


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
    except Exception as e:
        return {"error": f"AI detection failed: {str(e)}"}


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

    from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
    from core.harness.utils.prompt_loader import _async_prompt_resolve
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

    from core.harness.syscalls.llm import sys_llm_generate
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"upload_install_failed: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


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


# ── Agent Configuration Audit ──────────────────────────────────────────────

class AgentAuditResponse(BaseModel):
    agent_id: str
    issues: List[Dict[str, Any]]
    summary: Dict[str, Any]


@router.post("/workspace/agents/{agent_id}/audit", response_model=AgentAuditResponse)
async def audit_agent_config(agent_id: str) -> AgentAuditResponse:
    u"""AI 审核：检查 Agent 配置的问题点及建议。规则驱动，毫秒返回，无需 LLM。

    检查项包括：工具有效性/技能有效性/字段格式/Coze残留/必填字段/
    system_prompt/status规范/SOP干净度。
    """
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

    # ── Tool catalog ──
    valid_tools: set = set()
    try:
        from core.apps.tools.base import get_tool_registry
        reg = get_tool_registry()
        for tn in (reg.list_tools() or []):
            valid_tools.add(str(tn))
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # ── Skill catalog ──
    valid_skills: set = set()
    skill_dir = _P(os.path.expanduser("~/.aiplat")) / "skills"
    if skill_dir.exists():
        for d in skill_dir.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                try:
                    sk_raw = (d / "SKILL.md").read_text(encoding="utf-8", errors="ignore")
                    sp = sk_raw.split("---", 2)
                    if len(sp) >= 2:
                        sk_fm = _yaml.safe_load(sp[1]) or {}
                        name = sk_fm.get("name", d.name)
                        valid_skills.add(name)
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
    # Also engine skills
    engine_skill_dir = _P(__file__).resolve().parents[3] / "core" / "engine" / "skills"
    if engine_skill_dir.exists():
        for d in engine_skill_dir.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                try:
                    sk_raw = (d / "SKILL.md").read_text(encoding="utf-8", errors="ignore")
                    sp = sk_raw.split("---", 2)
                    if len(sp) >= 2:
                        sk_fm = _yaml.safe_load(sp[1]) or {}
                        name = sk_fm.get("name", d.name)
                        valid_skills.add(name)
                except Exception as e:
                    logging.warning(str(e), exc_info=True)

    # ── Check tools ──
    tools = fm.get("required_tools") or fm.get("tools") or []
    for t in tools:
        t_str = str(t).strip()
        if t_str in valid_tools:
            continue
        # Check if it's a syscall
        is_syscall = t_str.startswith("sys_")
        suggestion = ""
        fix = None
        if t_str == "sys_file_read":
            suggestion = "替换为 file_operations（sys_file_read 是内核级 syscall，非用户层 tool）"
            fix = {"type": "replace_tool", "from": "sys_file_read", "to": "file_operations"}
        elif is_syscall:
            suggestion = f"'{t_str}' 是 syscall，不是 tool——从 tools 列表中移除"
            fix = {"type": "remove_tool", "tool": t_str}
        else:
            suggestion = f"工具 '{t_str}' 在系统中不存在——检查是否为拼写错误或未安装的 MCP 工具"
            fix = {"type": "remove_tool", "tool": t_str}
        issues.append({
            "severity": "error", "category": "invalid_tool", "field": "tools",
            "current": t_str, "message": suggestion, "suggestion": suggestion,
            "fix_available": fix is not None,
            "fix": fix,
        })

    # ── Old format tools field ──
    if fm.get("tools") and not fm.get("required_tools"):
        issues.append({
            "severity": "warning", "category": "old_format", "field": "tools",
            "message": "使用了旧格式 'tools:' 字段，应迁移到 'required_tools:'",
            "suggestion": "将 tools: 中的有效条目迁移到 required_tools: 中",
            "fix": {"type": "migrate_field", "from": "tools", "to": "required_tools", "keep": [t for t in tools if str(t).strip() in valid_tools]},
        })

    # ── Coze import artifacts ──
    tags = fm.get("tags") or []
    if "coze" in tags or "imported" in tags:
        has_coze_issues = any(
            i["category"] in ("invalid_tool", "invalid_skill", "old_format")
            for i in issues
        )
        if has_coze_issues:
            bad_tools = [i["current"] for i in issues if i["category"] == "invalid_tool"]
            bad_skills = [i["current"] for i in issues if i["category"] == "invalid_skill"]
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

    # ── Skills validity ──
    skills = fm.get("required_skills") or fm.get("skills") or []
    for s in skills:
        s_str = str(s).strip()
        if s_str not in valid_skills and s_str not in ("", "[]", "null"):
            issues.append({
                "severity": "warning", "category": "invalid_skill", "field": "skills",
                "current": s_str, "message": f"技能 '{s_str}' 在系统中未找到",
                "suggestion": "检查名称或从绑定列表中移除",
            })

    # ── Required fields ──
    for field in ["name", "agent_type"]:
        if not fm.get(field):
            issues.append({
                "severity": "error", "category": "missing_required", "field": field,
                "message": f"缺少必填字段 '{field}'",
                "suggestion": f"添加 {field}: '{agent_id}' → name, 'react' → agent_type",
            })

    # ── system_prompt ──
    config = fm.get("config") or {}
    if isinstance(config, dict) and not config.get("system_prompt"):
        issues.append({
            "severity": "warning", "category": "missing_system_prompt", "field": "config.system_prompt",
            "message": "缺少 system_prompt——运行时将使用 CLAUDE.md 作为回退",
            "suggestion": "添加 config.system_prompt 字段或在编辑页使用 AI 优化 System Prompt",
        })

    # ── Status validity ──
    status = fm.get("status", "")
    if status and status not in ("ready", "published", "initializing", "disabled", "deprecated"):
        issues.append({
            "severity": "error", "category": "invalid_status", "field": "status",
            "current": status, "message": f"status 值 '{status}' 不合法",
            "suggestion": "使用 ready / published / deprecated / disabled 之一",
        })

    # ── SOP cleanliness ──
    body_lower = body.lower()
    if _audit_re.search(r'^\s*,\s*$', body, _audit_re.MULTILINE):
        issues.append({
            "severity": "info", "category": "sop_cleanup", "field": "sop_body",
            "message": "SOP 正文包含残留空行或裸逗号",
            "suggestion": "清理 SOP 中空的 'Available Plugins' 或残留标点",
        })
    if '## persona' not in body_lower and '## 角色' not in body_lower and body.strip():
        issues.append({
            "severity": "info", "category": "sop_structure", "field": "sop_body",
            "message": "SOP 建议包含 ## Persona 和 ## Workflow 章节",
            "suggestion": "使用 AI 生成角色定义来创建结构化 SOP",
        })
    if body.strip() and len(body.strip()) < 50:
        issues.append({
            "severity": "info", "category": "sop_short", "field": "sop_body",
            "message": f"SOP 正文过短 ({len(body.strip())} 字符)",
            "suggestion": "建议至少 200 字符的 SOP，包含角色定义和工作流",
        })

    # ── Semantic rules: role-tool mismatch (capability-driven) ──
    agent_name_lower = (fm.get("name") or agent_id).lower()
    agent_type = str(fm.get("agent_type") or "").lower()
    tools_list = fm.get("required_tools") or fm.get("tools") or []
    skills_list = fm.get("required_skills") or fm.get("skills") or []

    # Infer capabilities from SOP Knowledge Base + system_prompt context
    _caps_text = (body + " " + str(config.get("system_prompt", ""))).lower() if isinstance(config, dict) else body.lower()
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

    # ── Summary ──
    severity_count = {"error": 0, "warning": 0, "info": 0}
    for i in issues:
        severity_count[i["severity"]] = severity_count.get(i["severity"], 0) + 1

    errors = severity_count["error"]
    warnings = severity_count["warning"]
    total_issues = len(issues)
    health = "A" if total_issues == 0 else "B" if errors == 0 else "C" if errors <= 2 else "D"

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
        summary={
            "errors": errors, "warnings": warnings, "info": severity_count["info"],
            "total": total_issues, "health": health,
        },
    )
