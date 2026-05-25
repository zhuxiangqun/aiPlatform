"""
Dify → aiPlatform format adapter.

Handles:
- App config (agent) → AGENT.md
- Custom Tool (API/code) → SKILL.md or BaseTool Python
- Workflow/Chatflow → workflow.yaml
"""

from __future__ import annotations

import json as _json
import re
import yaml as _yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


class DifyAdapter:
    NAME = "dify"
    DESCRIPTION = "Dify (App + Custom Tool + Workflow/Chatflow)"

    def detect(self, root_dir: Path) -> bool:
        if (root_dir / "app.yml").is_file():
            return True
        if (root_dir / "app.yaml").is_file():
            return True
        if (root_dir / "dify").is_dir():
            d = root_dir / "dify"
            if (d / "app.yml").is_file():
                return True
        return False

    def convert(self, root_dir: Path, target_base: Path) -> Dict[str, Any]:
        converted: List[str] = []
        skipped: List[str] = []

        base = root_dir
        if (root_dir / "dify").is_dir():
            base = root_dir / "dify"

        agents_base = target_base.parent / "agents"
        tools_base = target_base.parent / "tools"

        # 1. Agent: app.yml → AGENT.md
        for yml_path in base.rglob("app.yml"):
            try:
                agent = _convert_dify_app(yml_path)
                if agent:
                    name = agent["name"]
                    dest = agents_base / name
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / "AGENT.md").write_text(agent["agenth_md"], encoding="utf-8")
                    converted.append(f"agent:{name}")
            except Exception:
                skipped.append(f"agent:{yml_path.name}")

        # 2. Tool: custom tool YAML → SKILL.md or BaseTool
        for tool_path in base.rglob("*.yml"):
            try:
                if tool_path.name in ("app.yml", "workflow.yml", "chatflow.yml"):
                    continue
                with open(tool_path, encoding="utf-8") as f:
                    data = _yaml.safe_load(f)
                if not isinstance(data, dict) or "provider" not in str(data.get("type", "")).lower():
                    continue
                result = _convert_dify_tool(tool_path, data)
                if not result:
                    continue
                name = result["name"]
                if result.get("tool_python"):
                    dest = tools_base / name
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / f"{name}.py").write_text(result["tool_python"], encoding="utf-8")
                    (dest / "manifest.json").write_text(_json.dumps({
                        "name": name, "type": "tool", "source": "dify_tool",
                        "description": result.get("description"),
                    }), encoding="utf-8")
                    converted.append(f"tool:{name}")
                elif result.get("skill_md"):
                    dest = target_base / name
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / "SKILL.md").write_text(result["skill_md"], encoding="utf-8")
                    converted.append(f"skill:{name}")
            except Exception:
                skipped.append(f"tool:{tool_path.name}")

        # 3. Workflow/Chatflow
        for wf_file in base.rglob("workflow.yml"):
            try:
                wf = _convert_dify_workflow(wf_file)
                if wf:
                    name = wf["name"]
                    dest = Path.home() / ".aiplat" / "workflow_templates"
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / f"{name}.json").write_text(_json.dumps(wf["stages"], indent=2, ensure_ascii=False), encoding="utf-8")
                    converted.append(f"workflow:{name}")
            except Exception:
                skipped.append(f"workflow:{wf_file.name}")

        return {"converted": converted, "skipped": skipped, "hints": []}


def _convert_dify_app(yml_path: Path) -> Optional[Dict[str, str]]:
    with open(yml_path, encoding="utf-8") as f:
        data = _yaml.safe_load(f)
    if not isinstance(data, dict):
        return None

    app = data.get("app") or data
    name = str(app.get("name") or "dify_app")
    desc = str(app.get("description") or "")
    mode = str(app.get("mode") or "chat")

    # Model
    model_cfg = app.get("model_config") or app.get("model") or {}
    if isinstance(model_cfg, str):
        model_name = model_cfg
    elif isinstance(model_cfg, dict):
        model_name = str(model_cfg.get("model") or model_cfg.get("name") or "auto")
    else:
        model_name = "auto"

    # Prompt
    prompt_cfg = app.get("prompt_template") or []
    persona = ""
    if isinstance(prompt_cfg, list):
        for p in prompt_cfg:
            if isinstance(p, dict) and str(p.get("role", "")).lower() == "system":
                persona = str(p.get("text", ""))
                break

    # Tools
    tools = app.get("tools") or []
    tool_names = [str(t.get("type", "")) for t in tools if isinstance(t, dict)]

    # Knowledge
    knowledge = app.get("knowledge_config") or {}
    ds_names = [str(d.get("name", "")) for d in (knowledge.get("datasets") or []) if isinstance(d, dict)]

    agent_type = "rag" if mode == "chat" and ds_names else "conversational"
    safe_name = re.sub(r"[^a-z0-9_]", "_", name.lower())[:32]

    sop_parts = []
    if persona:
        sop_parts.append(f"## Persona\n{persona}")
    if ds_names:
        sop_parts.append(f"## Knowledge Base\nDatasets: {', '.join(ds_names)}")
    if tool_names:
        sop_parts.append(f"## Available Tools\n{', '.join(tool_names)}")

    fm = {
        "name": safe_name,
        "display_name": name,
        "description": desc[:1024],
        "agent_type": agent_type,
        "version": "0.1.0",
        "status": "draft",
        "category": "general",
        "tags": ["dify", "imported"],
        "skills": ds_names[:10],
        "tools": tool_names[:10],
        "model": model_name,
    }

    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append("\n\n".join(sop_parts) if sop_parts else "## SOP\nImported from Dify app.")
    lines.append("")

    return {"name": safe_name, "agenth_md": "\n".join(lines)}


def _convert_dify_tool(tool_path: Path, data: Dict[str, Any]) -> Optional[Dict[str, str]]:
    name = str(data.get("name") or tool_path.stem)
    desc = str(data.get("description") or "")
    tool_type = str(data.get("type") or "").lower()
    params = data.get("parameters") or data.get("input_schema") or {}

    safe_name = re.sub(r"[^a-z0-9_]", "_", name.lower())[:32]

    if "api" in tool_type:
        url = str(data.get("url") or "")
        method = str(data.get("method") or "GET").upper()
        headers = data.get("headers") or {}

        param_props = {}
        for pk, pv in (params if isinstance(params, dict) else {}).items():
            param_props[pk] = {"type": str(pv.get("type", "string")), "description": str(pv.get("description", ""))}


        tool_lines = [
            "from core.apps.tools.base import BaseTool",
            "import requests",
            "",
            "",
            f"class {safe_name.title().replace('_', '')}Tool(BaseTool):",
            f'    name = "{safe_name}"',
            f'    description = """{desc[:500]}"""',
            "    parameters = {",
            '        "type": "object",',
            f'        "properties": {_json.dumps(param_props, indent=12)},',
            f'        "required": {_json.dumps(list(param_props.keys()))}',
            "    }",
            "",
            f"    def execute(self, **kwargs) -> dict:",
            f'        resp = requests.{method.lower()}("{url}", json=kwargs)',
            "        return resp.json()",
            "",
        ]
        return {"name": safe_name, "tool_python": "\n".join(tool_lines), "description": desc[:200]}

    # Code tool → SKILL.md
    code = str(data.get("code") or data.get("script") or "")
    skill_lines = [
        "---",
        f"name: {safe_name}",
        f"display_name: {name}",
        f"description: {desc[:1024]}",
        "category: tool",
        "version: 0.1.0",
        "status: draft",
        "execution_mode: prompt",
        "permissions: []",
        "effects:",
        "  - type: read",
        "    resources: [filesystem:~/.aiplat]",
        "    idempotent: true",
        "    rollback_available: false",
        f"input_schema: {{'input': {{'type': 'object', 'required': true}}}}",
        f"output_schema: {{'result': {{'type': 'object', 'required': true}}}}",
        "---",
        "## SOP",
        f"{desc}",
        "",
        f"```python\n{code[:3000]}\n```" if code else "",
        "",
    ]
    return {"name": safe_name, "skill_md": "\n".join(skill_lines)}


def _convert_dify_workflow(yml_path: Path) -> Optional[Dict[str, Any]]:
    with open(yml_path, encoding="utf-8") as f:
        data = _yaml.safe_load(f)
    if not isinstance(data, dict):
        return None

    wf = data.get("workflow") or data.get("chatflow") or data
    name = str(wf.get("name") or "dify_workflow")
    graph = wf.get("graph") or wf
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []

    safe_name = re.sub(r"[^a-z0-9_]", "_", name.lower())[:32]
    stages = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id", ""))
        ntype = str(node.get("type") or node.get("data", {}).get("type", "")).lower()

        stage: Dict[str, Any] = {"id": nid}

        ndata = node.get("data") or {}
        if not isinstance(ndata, dict):
            ndata = {}

        if ntype in ("start", "begin"):
            stage["kind"] = "start"
        elif ntype in ("end", "finish"):
            stage["kind"] = "end"
        elif ntype in ("llm", "chat-model"):
            stage["kind"] = "agent"
            stage["agent_type"] = "conversational"
            model = ndata.get("model") or ndata.get("provider") or ""
            stage["model"] = str(model)
            prompt = ndata.get("prompt_template") or ndata.get("sys_prompt") or ""
            if isinstance(prompt, list):
                prompt = "\n".join(str(p.get("text", "")) for p in prompt if isinstance(p, dict))
            stage["prompt_extra"] = str(prompt)[:2000]
        elif ntype in ("code", "python", "javascript"):
            stage["kind"] = "tool"
            stage["tool_type"] = "code_execution"
        elif ntype in ("retrieval", "dataset", "knowledge-retrieval"):
            stage["kind"] = "skill"
            stage["skill_id"] = "knowledge_retrieval"
            ds = ndata.get("dataset_ids") or []
            stage["dataset_ids"] = list(ds) if isinstance(ds, list) else []
        elif ntype in ("condition", "question-classifier", "if-else"):
            stage["kind"] = "condition"
            branches = ndata.get("branches") or ndata.get("cases") or []
            stage["conditions"] = [
                {"label": str(b.get("name", "")),
                 "predicate": str(b.get("condition", "") or b.get("case_id", ""))[:500]}
                for b in branches if isinstance(b, dict)
            ]
        elif ntype in ("template-transform", "parameter-extractor"):
            stage["kind"] = "tool"
            stage["tool_type"] = "template_transform"
        else:
            stage["kind"] = "tool"
            stage["tool_type"] = ntype

        deps = [str(e.get("from", "")) for e in edges if isinstance(e, dict) and str(e.get("to", "")) == nid]
        if deps:
            stage["depends_on"] = deps

        stages.append(stage)

    return {"name": safe_name, "stages": {"name": safe_name,
              "description": f"Imported from Dify: {name}", "stages": stages}}


__all__ = ["DifyAdapter"]
