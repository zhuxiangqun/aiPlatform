"""
Workflow CRUD service — persists workflow definitions via WorkflowManager (directory-backed).

Backward-compatible: falls back to platform SQLite if WorkflowManager is unavailable.
"""
from __future__ import annotations

import logging
from storage.sqlite import list_workflow_runs
from typing import Any, Dict, List, Optional
from typing import Any, Dict, List, Optional

from core.utils.ids import new_prefixed_id

_logger = logging.getLogger("aiplat.platform.workflow_service")

# Lazy init — created on first use
_wf_mgr = None


def _get_wf_mgr():
    global _wf_mgr
    if _wf_mgr is None:
        try:
            from core.management.workflow_manager import WorkflowManager
            _wf_mgr = WorkflowManager(scope="workspace")
        except Exception as e:
            _logger.debug("WorkflowManager not available, falling back to SQLite: %s", e)
            _wf_mgr = False
    return _wf_mgr if _wf_mgr is not False else None


def _verify_workflow_signature(mgr, wf) -> None:
    """Best-effort signature verification for governed workflows (logs warning on failure)."""
    try:
        import asyncio
        from core.security.skill_signature_gate import get_trusted_skill_pubkeys_map
        from core.api.core_facade import get_kernel_runtime  # v2.5: canonical path
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
            trusted = _pool.submit(asyncio.run, get_trusted_skill_pubkeys_map(store)).result(timeout=10) if store else {}
        prov = mgr.compute_workflow_signature_verification(wf, trusted)
        if prov.get("signature") and not prov.get("signature_verified"):
            _logger.warning("Workflow %s signature verification failed: %s", wf.id, prov.get("signature_verified_reason", ""))
    except Exception:
        _logger.debug("Workflow %s signature verification skipped", wf.id, exc_info=True)


class WorkflowService:

    async def list(self) -> List[Dict[str, Any]]:
        mgr = _get_wf_mgr()
        if mgr:
            return mgr.list_workflow_dicts()
        from storage.sqlite import list_workflows, list_workflow_runs
        wfs = list_workflows()
        for w in wfs:
            runs = list_workflow_runs(w["id"])
            w["last_run"] = runs[0] if runs else None
        return wfs

    async def get(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        mgr = _get_wf_mgr()
        if mgr:
            return mgr.get_workflow_dict(workflow_id)
        from storage.sqlite import get_workflow
        return get_workflow(workflow_id)

    async def create(self, name: str, description: str = "", nodes: List[Any] = None, edges: List[Any] = None) -> Dict[str, Any]:
        mgr = _get_wf_mgr()
        if mgr:
            wf = mgr.create_workflow(name, description.strip(), nodes or [], edges or [])
            return mgr.get_workflow_dict(wf.id) or {}
        from storage.sqlite import create_workflow
        wid = new_prefixed_id("wf")
        return create_workflow(wid, name.strip(), description.strip(), nodes or [], edges or [])

    async def update(self, workflow_id: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        mgr = _get_wf_mgr()
        if mgr:
            result = mgr.update_workflow(workflow_id, **kwargs)
            if result is None:
                raise ValueError(f"workflow not found: {workflow_id}")
            return mgr.get_workflow_dict(workflow_id) or {}
        from storage.sqlite import update_workflow
        result = update_workflow(workflow_id, **kwargs)
        if result is None:
            raise ValueError(f"workflow not found: {workflow_id}")
        return result

    async def delete(self, workflow_id: str) -> bool:
        mgr = _get_wf_mgr()
        if mgr:
            return mgr.delete_workflow(workflow_id)
        from storage.sqlite import delete_workflow
        return delete_workflow(workflow_id)

    async def list_runs(self, workflow_id: str) -> List[Dict[str, Any]]:
        from storage.sqlite import list_workflow_runs
        return list_workflow_runs(workflow_id)

    async def execute(self, workflow_id: str, launch_name: str = "") -> Dict[str, Any]:
        # Resolve workflow from manager or SQLite
        mgr = _get_wf_mgr()
        if mgr:
            wf = mgr.get_workflow(workflow_id)
            wf_dict = mgr.get_workflow_dict(workflow_id) if wf else None
        else:
            from storage.sqlite import get_workflow
            wf_dict = get_workflow(workflow_id)
        if not wf_dict:
            raise ValueError(f"workflow not found: {workflow_id}")

        # Signature verification best-effort on governed workflows
        if mgr and wf:
            _verify_workflow_signature(mgr, wf)

        nodes = wf_dict.get("nodes") or []
        edges = wf_dict.get("edges") or []
        stages = []
        for i, n in enumerate(nodes):
            d = n.get("data", {}) or {}
            cfg = d.get("config", {}) or {}
            nt = d.get("type", "agent")
            # Load agent frontmatter for model/agent_type
            agent_fm = {}
            agent_id = cfg.get("agentId", "")
            if agent_id:
                try:
                    from core.api.core_facade import get_agent_frontmatter
                    agent_fm = get_agent_frontmatter(agent_id) or {}
                except Exception:
                    pass
            # Inject Start node's test inputs into stage config
            if nt == 'start':
                inputs = d.get("start_inputs", [])
                if inputs:
                    cfg["inputs"] = {si.get("key", ""): si.get("value", "") for si in inputs if si.get("key")}
            # Set meaningful output_artifact per node type (Dify/Coze: each node declares its output)
            out_map = {'llm': 'llm_output', 'code': 'code_result', 'http': 'http_response',
                       'knowledge': 'kb_chunks', 'tool': 'tool_result', 'loop': 'loop_results',
                       'template': 'rendered_text', 'condition': 'branch_result',
                       'assigner': 'assigned_var', 'aggregator': 'aggregated', 'list': 'list_result',
                       'agent': 'agent_output', 'human': 'human_input'}
            stages.append({
                "id": n.get("id", f"n_{i}"),
                "agent_id": cfg.get("agentId", nt),
                "agent_name": d.get("label", "Node"),
                "type": nt,
                "order": i,
                "depends_on": [e.get("source") for e in edges if e.get("target") == n.get("id")],
                "config": cfg,
                "node_type": nt,
                "node_config": cfg,
                "output_artifact": cfg.get("outputArtifact") or out_map.get(nt, "stage_output"),
                "input_artifacts": cfg.get("inputArtifacts", []),
                "hitl": cfg.get("hitl", False),
                "hitl_phase": cfg.get("hitlPhase", ""),
                "model": agent_fm.get("model", ""),
                "agent_type": agent_fm.get("agent_type", "react"),
                "review_gate": cfg.get("reviewGate", "quick"),
                "required_skills": cfg.get("requiredSkills", []),
                # v2.5: LLM nodes with agentId use Agent→ReActLoop→Skill (via _execute_agent_node)  # noqa: boundary
                # StageRunner._resolve_skills() picks up required_skills from PipelineStageConfig.
            })
        # Attach per-node input_variables to node_config so the engine can resolve them
        for s in stages:
            n_orig = next((n for n in nodes if n.get("id") == s["id"]), None)
            if n_orig:
                iv = (n_orig.get("data", {}) or {}).get("input_variables", [])
                if iv:
                    nc = dict(s.get("node_config") or {})
                    nc["input_variables"] = iv
                    s["node_config"] = nc
        # Topological sort stages by depends_on (edges define DAG)
        if stages:
            node_ids = {s["id"] for s in stages}
            in_degree = {sid: 0 for sid in node_ids}
            adjacency: dict = {sid: [] for sid in node_ids}
            for s in stages:
                for dep in s.get("depends_on", []):
                    if dep in node_ids:
                        adjacency[dep].append(s["id"])
                        in_degree[s["id"]] = in_degree.get(s["id"], 0) + 1
            queue = [sid for sid, deg in in_degree.items() if deg == 0]
            ordered = []
            while queue:
                sid = queue.pop(0)
                ordered.append(sid)
                for nb in adjacency.get(sid, []):
                    in_degree[nb] -= 1
                    if in_degree[nb] == 0:
                        queue.append(nb)
            if len(ordered) == len(stages):
                stage_map = {s["id"]: s for s in stages}
                stages = [stage_map[sid] for sid in ordered]
                for i, s in enumerate(stages):
                    s["order"] = i
        from builder.builder_project_service import _get_project_service
        from core.schemas_builder import ProjectCreateRequest
        svc = _get_project_service()
        proj = await svc.create_project(ProjectCreateRequest(
            name=launch_name or wf_dict.get("name", "workflow"),
            description=wf_dict.get("description", ""),
            stages=stages,
        ))
        from storage.sqlite import record_workflow_run
        record_workflow_run(workflow_id, proj.project_id, launch_name or wf_dict.get("name", ""))
        # Fire pipeline in background — API returns immediately, frontend polls /runs
        import sys
        print("### start_pipeline_background called for", proj.project_id, file=sys.stderr)
        svc.start_pipeline_background(proj.project_id)
        return {"project_id": proj.project_id, "workflow_id": workflow_id, "run_id": proj.project_id}

    async def list_runs(self, workflow_id: str) -> list:
        return list_workflow_runs(workflow_id)  # noqa: F821


async def _execute_agent_node(node_config: dict, pipeline_state: dict) -> Optional[dict]:
    """Execute a workflow node as an Agent (ReActLoop→Skill) instead of direct LLM.  # noqa: boundary
    
    Only fires for type="llm" nodes that have an agentId and requiredSkills.
    Returns None if Agent system is unavailable → caller falls back to direct LLM.
    """
    agent_id = node_config.get("agentId", "") or node_config.get("agent_id", "")
    skills = node_config.get("requiredSkills", []) or node_config.get("required_skills", [])
    
    if not agent_id or not skills:
        return None
    
    try:
        from core.apps.fde.agent import run_fde_agent_one_shot
        
        return await run_fde_agent_one_shot(
            agent_id=agent_id,
            skill_filter=list(skills),
            user_message="\n".join(summary_parts),
        )
    except Exception:
        return None
