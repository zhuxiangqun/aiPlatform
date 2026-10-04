"""
Workflow API router — CRUD + execute for workflow definitions.
"""
from __future__ import annotations

from api.schemas_response import StatusResponse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from auth.deps import require_auth
from builder.builder_workflow_service import WorkflowService

router = APIRouter(prefix="/platform/workflows", tags=["workflows"])
_svc = WorkflowService()
_log = logging.getLogger(__name__)


def _get_wf_mgr():
    try:
        from core.api.core_facade import WorkflowManager  # v2.5
        return WorkflowManager(scope="workspace")
    except Exception:
        return None


async def _record_workflow_changeset(name: str, workflow_id: str, status: str = "success", args: dict = None, error: str = None):
    """Best-effort: record a workflow mutation as a changeset for audit."""
    try:
        from core.api.core_facade import record_changeset
        await record_changeset(
            name=name,
            target_type="workflow",
            target_id=workflow_id,
            status=status,
            args=args or {},
            error=error,
            user_id="admin",
        )
    except Exception:
        _log.debug(f"Failed to record changeset for workflow {workflow_id}", exc_info=True)


@router.get("", response_model=StatusResponse)
async def list_workflows_endpoint(_auth: str = Depends(require_auth)):
    items = await _svc.list()
    return {"workflows": items, "total": len(items)}


@router.post("/dedupe", response_model=StatusResponse)
async def dedupe_workflows_endpoint(_auth: str = Depends(require_auth)):
    """Merge workflows that share the same name + node fingerprint; keep newest."""
    return await _svc.dedupe()


@router.get("/{workflow_id}", response_model=StatusResponse)
async def get_workflow_endpoint(workflow_id: str, _auth: str = Depends(require_auth)):
    item = await _svc.get(workflow_id)
    if not item:
        raise HTTPException(status_code=404, detail="workflow not found")
    return item


@router.post("/{workflow_id}/audit", response_model=StatusResponse)
async def audit_workflow_endpoint(workflow_id: str, _auth: str = Depends(require_auth)):
    """AI 审核：Workflow 节点/描述完整性（规则驱动）。"""
    try:
        from core.management.asset_audit import issue, summarize_audit_issues
    except Exception:
        # Fallback if core import path differs in some envs
        def summarize_audit_issues(issues):  # type: ignore
            err = sum(1 for i in issues if i.get("severity") == "error")
            warn = sum(1 for i in issues if i.get("severity") == "warning")
            info = sum(1 for i in issues if i.get("severity") == "info")
            total = len(issues)
            health = "A" if total == 0 else "B" if err == 0 else "C" if err <= 2 else "D"
            return {"errors": err, "warnings": warn, "info": info, "total": total, "health": health}

        def issue(**kwargs):  # type: ignore
            fix = kwargs.pop("fix", None)
            out = dict(kwargs)
            if fix:
                out["fix_available"] = True
                out["fix"] = fix
            else:
                out["fix_available"] = False
            return out

    item = await _svc.get(workflow_id)
    if not item:
        raise HTTPException(status_code=404, detail="workflow not found")

    issues: List[Dict[str, Any]] = []
    name = str(item.get("name") or "").strip()
    if not name:
        issues.append(issue(
            severity="error", category="missing_name", field="name",
            message="缺少名称",
            suggestion="设置可读 Workflow 名称",
            fix={"type": "set_name", "name": f"workflow_{workflow_id[:8]}"},
        ))
    desc = str(item.get("description") or "").strip()
    if not desc:
        issues.append(issue(
            severity="warning", category="missing_description", field="description",
            message="缺少 description",
            suggestion="补充编排用途说明",
            fix={"type": "set_description", "description": f"{name or workflow_id} 编排流程"},
        ))
    nodes = item.get("nodes") or []
    if not isinstance(nodes, list) or len(nodes) == 0:
        issues.append(issue(
            severity="error", category="empty_nodes", field="nodes",
            message="节点为空——Workflow 无可执行步骤",
            suggestion="在画布中添加 Agent/Skill/Tool 节点",
        ))
    else:
        node_ids: List[str] = []
        for i, node in enumerate(nodes):
            if not isinstance(node, dict):
                issues.append(issue(
                    severity="error", category="invalid_node", field="nodes",
                    message=f"节点 [{i}] 不是对象",
                ))
                continue
            nid = str(node.get("id") or f"idx_{i}")
            node_ids.append(nid)
            data = node.get("data") if isinstance(node.get("data"), dict) else {}
            # Canvas nodes use type=stageNode; real kind lives in data.type
            ntype = str(
                data.get("type") or node.get("node_type") or node.get("type") or ""
            ).lower()
            if ntype in ("stagenode", "stage_node"):
                ntype = str(data.get("type") or "").lower()
            cfg = data.get("config") if isinstance(data.get("config"), dict) else {}
            label = str(data.get("label") or nid)

            agent_id = str(
                cfg.get("agentId")
                or cfg.get("agent_id")
                or data.get("agent_id")
                or node.get("agent_id")
                or data.get("agentId")
                or ""
            ).strip()
            if ntype in ("agent", "react") and not agent_id:
                guess = None
                try:
                    from core.management.asset_audit import (
                        infer_id_from_label,
                        list_workspace_agent_catalog,
                    )
                    cat = list_workspace_agent_catalog()
                    aliases = {v: k for k, v in cat.items()}
                    guess = infer_id_from_label(label, list(cat.keys()), aliases=aliases)
                except Exception:
                    guess = None
                issues.append(issue(
                    severity="warning", category="missing_agent_id", field="nodes",
                    message=f"Agent 节点「{label}」缺少 agentId",
                    suggestion=(
                        f"一键修复按节点标题匹配已有 Agent「{guess}」"
                        if guess
                        else "在画布中绑定已上架的 Agent（标题对不上已有 id 时不会编造）"
                    ),
                    fix=(
                        {"type": "set_node_config", "node_id": nid, "key": "agentId", "value": guess}
                        if guess
                        else None
                    ),
                ))
            elif ntype in ("agent", "react") and agent_id:
                # Existence + listed on disk
                from pathlib import Path as _P
                import os as _os
                ap = _P(_os.path.expanduser("~/.aiplat")) / "agents" / agent_id / "AGENT.md"
                if not ap.exists():
                    guess = None
                    try:
                        from core.management.asset_audit import (
                            infer_id_from_label,
                            list_workspace_agent_catalog,
                        )
                        cat = list_workspace_agent_catalog()
                        aliases = {v: k for k, v in cat.items()}
                        guess = infer_id_from_label(label, list(cat.keys()), aliases=aliases)
                        if guess == agent_id:
                            guess = None
                    except Exception:
                        guess = None
                    issues.append(issue(
                        severity="error", category="invalid_agent_binding", field="nodes",
                        message=f"Agent 节点「{label}」绑定的 '{agent_id}' 不存在",
                        suggestion=(
                            f"一键修复改绑标题匹配的 Agent「{guess}」"
                            if guess
                            else "改绑有效 Agent，或从画布删除该节点"
                        ),
                        fix=(
                            {"type": "set_node_config", "node_id": nid, "key": "agentId", "value": guess}
                            if guess
                            else None
                        ),
                    ))
                else:
                    try:
                        import yaml as _yaml
                        raw = ap.read_text(encoding="utf-8", errors="ignore")
                        sp = raw.split("---", 2)
                        afm = _yaml.safe_load(sp[1]) if len(sp) >= 2 else {}
                        st = str((afm or {}).get("status") or "draft").lower()
                        if st not in ("published", "listed"):
                            issues.append(issue(
                                severity="warning", category="agent_not_listed", field="nodes",
                                message=f"Agent 节点「{label}」绑定 '{agent_id}' 未上架（status={st}）",
                                suggestion=(
                                    f"请到应用库将 '{agent_id}' 提交审核并上架；"
                                    "上架需人工操作，一键修复不会代提"
                                ),
                            ))
                    except Exception:
                        pass  # noqa: best-effort status read

            if ntype in ("start",):
                si = data.get("start_inputs") or cfg.get("start_inputs") or []
                if not (isinstance(si, list) and si):
                    preview = ""
                    try:
                        from core.management.execution_examples import (
                            build_workflow_start_examples,
                            workflow_example_to_start_inputs,
                        )
                        sample = build_workflow_start_examples(
                            [], workflow_name=name or label
                        )
                        if sample:
                            preview = sample[0].get("content") or ""
                            workflow_example_to_start_inputs(preview)
                    except Exception:
                        preview = ""
                    issues.append(issue(
                        severity="info", category="missing_start_inputs", field="nodes",
                        message=f"Start 节点「{label}」未配置 start_inputs",
                        suggestion=(
                            "为主路径填写启动变量。"
                            + (f" 参考：{preview[:180]}" if preview else "")
                        ),
                    ))
            if ntype == "tool" and not str(cfg.get("tool_name") or "").strip():
                guess = None
                try:
                    from core.management.asset_audit import (
                        infer_id_from_label,
                        list_workspace_tool_names,
                    )
                    guess = infer_id_from_label(label, list_workspace_tool_names())
                except Exception:
                    guess = None
                issues.append(issue(
                    severity="warning", category="missing_tool_name", field="nodes",
                    message=f"Tool 节点「{label}」缺少 tool_name",
                    suggestion=(
                        f"一键修复按节点标题匹配工作区工具「{guess}」"
                        if guess
                        else "在节点配置中填写已注册工具名（标题对不上时不会编造）"
                    ),
                    fix=(
                        {"type": "set_node_config", "node_id": nid, "key": "tool_name", "value": guess}
                        if guess
                        else None
                    ),
                ))
            if ntype == "http" and not str(cfg.get("url") or "").strip():
                found_url = None
                try:
                    from core.management.asset_audit import infer_http_url_from_text
                    found_url = infer_http_url_from_text(
                        label,
                        item.get("description"),
                        data.get("description"),
                        data.get("notes"),
                        cfg.get("notes"),
                        cfg.get("endpoint"),
                    )
                except Exception:
                    found_url = None
                issues.append(issue(
                    severity="warning", category="missing_http_url", field="nodes",
                    message=f"HTTP 节点「{label}」缺少 url",
                    suggestion=(
                        "一键修复写入节点说明中已出现的真实 URL"
                        if found_url
                        else "填写可访问的请求 URL（说明里没有地址时不会编造）"
                    ),
                    fix=(
                        {"type": "set_node_config", "node_id": nid, "key": "url", "value": found_url}
                        if found_url
                        else None
                    ),
                ))
            if ntype == "llm" and not str(cfg.get("prompt") or "").strip():
                issues.append(issue(
                    severity="info", category="missing_llm_prompt", field="nodes",
                    message=f"LLM 节点「{label}」缺少 prompt",
                    suggestion="补充提示词或绑定上游变量",
                ))
            if ntype == "condition" and not str(cfg.get("expression") or "").strip():
                issues.append(issue(
                    severity="warning", category="missing_condition_expr", field="nodes",
                    message=f"Condition 节点「{label}」缺少 expression",
                    suggestion="填写分支条件表达式",
                ))
            if ntype == "knowledge" and not str(cfg.get("kb_name") or cfg.get("query") or "").strip():
                issues.append(issue(
                    severity="info", category="incomplete_knowledge_node", field="nodes",
                    message=f"Knowledge 节点「{label}」未配置 kb_name/query",
                    suggestion="指定知识库与查询表达式",
                ))

        edges = item.get("edges") or []
        if not isinstance(edges, list):
            edges = []
        if len(nodes) > 1 and len(edges) == 0:
            issues.append(issue(
                severity="info", category="no_edges", field="edges",
                message="有多个节点但无连线——执行顺序可能不明确",
                suggestion="在画布中连接节点以声明依赖顺序",
            ))
        else:
            # adjacency for isolation + cycle detection
            outs: Dict[str, List[str]] = {nid: [] for nid in node_ids}
            ins: Dict[str, int] = {nid: 0 for nid in node_ids}
            for e in edges:
                if not isinstance(e, dict):
                    continue
                src, tgt = str(e.get("source") or ""), str(e.get("target") or "")
                if src in outs and tgt in ins:
                    outs[src].append(tgt)
                    ins[tgt] = ins.get(tgt, 0) + 1
            # Isolated (no in/out), skip start/end kinds
            for i, node in enumerate(nodes):
                if not isinstance(node, dict):
                    continue
                nid = str(node.get("id") or f"idx_{i}")
                data = node.get("data") if isinstance(node.get("data"), dict) else {}
                ntype = str(data.get("type") or node.get("type") or "").lower()
                if ntype in ("start", "end"):
                    continue
                if ins.get(nid, 0) == 0 and not outs.get(nid):
                    label = str(data.get("label") or nid)
                    issues.append(issue(
                        severity="info", category="isolated_node", field="nodes",
                        message=f"节点「{label}」无入边也无出边（孤立）",
                        suggestion="连入主流程，或删除无用节点",
                    ))
            # Cycle detection (DFS): 0=unseen, 1=visiting, 2=done
            color = {nid: 0 for nid in node_ids}
            cycle_found = False

            def _dfs(u: str) -> bool:
                nonlocal cycle_found
                color[u] = 1
                for v in outs.get(u, []):
                    if color.get(v) == 1:
                        return True
                    if color.get(v) == 0 and _dfs(v):
                        return True
                color[u] = 2
                return False

            for nid in node_ids:
                if color[nid] == 0 and _dfs(nid):
                    cycle_found = True
                    break
            if cycle_found:
                issues.append(issue(
                    severity="warning", category="cycle_detected", field="edges",
                    message="画布存在环路——可能导致执行无法终止",
                    suggestion="检查连线方向，去掉回边或改用 Loop 节点",
                ))

    return {
        "workflow_id": workflow_id,
        "issues": issues,
        "summary": summarize_audit_issues(issues),
    }


@router.post("", response_model=StatusResponse)
async def create_workflow_endpoint(req: Dict[str, Any], _auth: str = Depends(require_auth)):
    try:
        reuse = req.get("reuse_equivalent", True)
        item = await _svc.create(
            name=str(req.get("name") or "未命名工作流"),
            description=str(req.get("description") or ""),
            nodes=req.get("nodes") or [],
            edges=req.get("edges") or [],
            reuse_equivalent=bool(reuse),
        )
        await _record_workflow_changeset("create_workflow", item["id"], args={"name": item.get("name", "")})
        return item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{workflow_id}", response_model=StatusResponse)
async def update_workflow_endpoint(workflow_id: str, req: Dict[str, Any], _auth: str = Depends(require_auth)):
    kwargs: Dict[str, Any] = {}
    if "name" in req:
        kwargs["name"] = str(req["name"])
    if "description" in req:
        kwargs["description"] = str(req["description"])
    if "nodes" in req:
        kwargs["nodes"] = req["nodes"]
    if "edges" in req:
        kwargs["edges"] = req["edges"]
    try:
        result = await _svc.update(workflow_id, **kwargs)
        await _record_workflow_changeset("update_workflow", workflow_id, args=kwargs)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{workflow_id}", response_model=StatusResponse)
async def delete_workflow_endpoint(workflow_id: str, _auth: str = Depends(require_auth)):
    await _svc.delete(workflow_id)
    await _record_workflow_changeset("delete_workflow", workflow_id)
    return {"status": "deleted", "id": workflow_id}


@router.post("/{workflow_id}/execute", response_model=StatusResponse)
async def execute_workflow_endpoint(workflow_id: str, req: Dict[str, Any] = {}, _auth: str = Depends(require_auth)):
    try:
        result = await _svc.execute(workflow_id, launch_name=str(req.get("name") or ""))
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{workflow_id}/runs", response_model=StatusResponse)
async def list_workflow_runs_endpoint(workflow_id: str, _auth: str = Depends(require_auth)):
    runs = await _svc.list_runs(workflow_id)
    return {"runs": runs, "total": len(runs)}


@router.post("/{workflow_id}/toggle-enabled", response_model=StatusResponse)
async def toggle_workflow_enabled_endpoint(workflow_id: str, _auth: str = Depends(require_auth)):
    # Try directory-based manager first, fall back to SQLite
    mgr = _get_wf_mgr()
    if mgr:
        result = mgr.toggle_enabled(workflow_id)
        if result is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        await _record_workflow_changeset("toggle_workflow", workflow_id, args={"enabled": result})
        return {"enabled": result, "workflow_id": workflow_id}

    from storage.sqlite import toggle_workflow_enabled
    result = toggle_workflow_enabled(workflow_id)
    if result is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    await _record_workflow_changeset("toggle_workflow", workflow_id, args={"enabled": result})
    return {"enabled": result, "workflow_id": workflow_id}


@router.get("/runs/{run_id}/events/latest", response_model=StatusResponse)
async def get_latest_event_endpoint(run_id: str, _auth: str = Depends(require_auth)):
    from storage.sqlite import get_latest_event
    event = get_latest_event(run_id)
    if not event:
        return {"event": None}
    return {"event": event}


@router.get("/runs/{run_id}/events", response_model=StatusResponse)
async def list_events_endpoint(run_id: str, _auth: str = Depends(require_auth)):
    from storage.sqlite import list_pipeline_events
    events = list_pipeline_events(run_id)
    return {"events": events, "total": len(events)}


@router.post("/{workflow_id}/stop", response_model=StatusResponse)
async def stop_workflow_run(workflow_id: str, req: Dict[str, Any] = {}, _auth: str = Depends(require_auth)):
    """Cancel a running pipeline by project_id."""
    project_id = str(req.get("project_id", ""))
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    from core.api.core_facade import cancel_pipeline
    cancel_pipeline(project_id)
    return {"status": "cancelled", "project_id": project_id}


@router.post("/{workflow_id}/sign", response_model=StatusResponse)
async def sign_workflow(workflow_id: str, req: Dict[str, Any] = {}, _auth: str = Depends(require_auth)):
    """Sign a workflow directory with an Ed25519 private key. Writes WORKFLOW.manifest.json."""
    mgr = _get_wf_mgr()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workflow manager not available (not migrated to directory storage yet)")

    wf = mgr.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="workflow not found")

    private_key = str(req.get("private_key") or "").strip()
    private_key = private_key.replace("\\n", "\n")  # normalize escaped newlines from frontend
    if not private_key:
        raise HTTPException(status_code=400, detail="private_key is required")

    try:
        from core.api.core_facade import sign_skill as sign_wf  # v2.5: canonical path

        wf_dir = Path(wf.metadata.get("filesystem", {}).get("server_dir") or "")
        if not wf_dir or not wf_dir.exists():
            raise HTTPException(status_code=500, detail="Workflow directory not found")

        mgr._enrich_workflow_provenance_and_integrity(wf.metadata, workflow_dir=wf_dir)
        integ = wf.metadata.get("integrity", {})
        bundle_sha256 = integ.get("bundle_sha256", "")
        if not bundle_sha256:
            raise HTTPException(status_code=500, detail="Could not compute bundle_sha256")

        version = req.get("version") or wf.version or "0.1.0"
        signature = sign_wf(private_key=private_key, skill_id=workflow_id, version=str(version), bundle_sha256=bundle_sha256)

        manifest_path = wf_dir / "WORKFLOW.manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        manifest["signature"] = signature
        manifest["version"] = str(version)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        mgr._enrich_workflow_provenance_and_integrity(wf.metadata, workflow_dir=wf_dir)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid private key: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Signing failed: {str(e)}")

    return {"status": "signed", "bundle_sha256": bundle_sha256, "version": str(version), "signature": signature}


@router.post("/{workflow_id}/publish", response_model=StatusResponse)
async def publish_version_endpoint(workflow_id: str, req: Dict[str, Any] = {}, _auth: str = Depends(require_auth)):
    # Try directory-based manager first
    mgr = _get_wf_mgr()
    if mgr:
        ver = mgr.publish(workflow_id)
        await _record_workflow_changeset("publish_workflow", workflow_id, args={"version": ver.get("status")})
        return ver

    from storage.sqlite import get_workflow, publish_workflow_version
    wf = get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="workflow not found")
    ver = publish_workflow_version(
        workflow_id,
        name=str(req.get("name") or wf.get("name", "")),
        nodes=wf.get("nodes") or [],
        edges=wf.get("edges") or [],
    )
    await _record_workflow_changeset("publish_workflow", workflow_id, args={"version": ver.get("version")})
    return ver


@router.get("/{workflow_id}/versions", response_model=StatusResponse)
async def list_versions_endpoint(workflow_id: str, _auth: str = Depends(require_auth)):
    from storage.sqlite import list_workflow_versions
    versions = list_workflow_versions(workflow_id)
    return {"versions": versions, "total": len(versions), "latest_version": versions[0]["version"] if versions else 0}


@router.post("/{workflow_id}/restore/{version_id:path}", response_model=StatusResponse)
async def restore_version_endpoint(workflow_id: str, version_id: str, _auth: str = Depends(require_auth)):
    from storage.sqlite import get_workflow_version, update_workflow
    ver = get_workflow_version(version_id)
    if not ver:
        raise HTTPException(status_code=404, detail="version not found")
    result = update_workflow(workflow_id, nodes=ver.get("nodes"), edges=ver.get("edges"))
    if not result:
        raise HTTPException(status_code=404, detail="workflow not found")
    return {"status": "restored", "from_version": ver["version"]}
