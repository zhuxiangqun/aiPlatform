"""
Workflow CRUD service — persists workflow definitions to platform SQLite.
Used by api/routers/workflows.py router.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.utils.ids import new_prefixed_id
from storage.sqlite import list_workflows, get_workflow, create_workflow, update_workflow, delete_workflow
from storage.sqlite import record_workflow_run, list_workflow_runs

_logger = logging.getLogger("aiplat.platform.workflow_service")


class WorkflowService:

    async def list(self) -> List[Dict[str, Any]]:
        wfs = list_workflows()
        for w in wfs:
            runs = list_workflow_runs(w["id"])
            w["last_run"] = runs[0] if runs else None
        return wfs

    async def get(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        return get_workflow(workflow_id)

    async def create(self, name: str, description: str = "", nodes: List[Any] = None, edges: List[Any] = None) -> Dict[str, Any]:
        if not name.strip():
            raise ValueError("name is required")
        wid = new_prefixed_id("wf")
        return create_workflow(wid, name.strip(), description.strip(), nodes or [], edges or [])

    async def update(self, workflow_id: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        result = update_workflow(workflow_id, **kwargs)
        if result is None:
            raise ValueError(f"workflow not found: {workflow_id}")
        return result

    async def delete(self, workflow_id: str) -> bool:
        return delete_workflow(workflow_id)

    async def list_runs(self, workflow_id: str) -> List[Dict[str, Any]]:
        return list_workflow_runs(workflow_id)

    async def execute(self, workflow_id: str, launch_name: str = "") -> Dict[str, Any]:
        wf = get_workflow(workflow_id)
        if not wf:
            raise ValueError(f"workflow not found: {workflow_id}")
        nodes = wf.get("nodes") or []
        edges = wf.get("edges") or []
        stages = []
        for i, n in enumerate(nodes):
            d = n.get("data", {}) or {}
            cfg = d.get("config", {}) or {}
            nt = d.get("type", "agent")
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
                "output_artifact": out_map.get(nt, "stage_output"),
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
        from builder.builder_project_service import BuilderProjectService
        from builder.builder_team_service import BuilderTeamService
        from core.schemas_builder import ProjectCreateRequest
        svc = BuilderProjectService(team_service=BuilderTeamService())
        proj = await svc.create_project(ProjectCreateRequest(
            name=launch_name or wf.get("name", "workflow"),
            description=wf.get("description", ""),
            stages=stages,
        ))
        record_workflow_run(workflow_id, proj.project_id, launch_name or wf.get("name", ""))
        # Background execution via dedicated thread — API returns immediately.
        # PipelineEventBus writes progress to SQLite pipeline_events → frontend polls.
        import threading
        def _run():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(svc.start_pipeline(proj.project_id))
            except Exception:
                pass
            finally:
                loop.close()
        threading.Thread(target=_run, daemon=True).start()
        return {"project_id": proj.project_id, "workflow_id": workflow_id, "run_id": proj.project_id}

    async def list_runs(self, workflow_id: str) -> list:
        return list_workflow_runs(workflow_id)
