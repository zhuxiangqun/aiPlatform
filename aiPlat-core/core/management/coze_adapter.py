"""
Coze/扣子 → aiPlatform format adapter.

Handles:
- Bot config (agent) → AGENT.md
- Plugin manifest (skill/tool) → SKILL.md + BaseTool Python
- Workflow JSON → workflow.yaml
"""

from __future__ import annotations

import json as _json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class CozeAdapter:
    NAME = "coze"
    DESCRIPTION = "Coze/扣子 (Bot + Plugin + Workflow)"

    def detect(self, root_dir: Path) -> bool:
        """Detect Coze exports: bot_manifest.json, plugin_manifest.json, workflow.json"""
        if (root_dir / "bot_manifest.json").is_file():
            return True
        if (root_dir / "plugin_manifest.json").is_file():
            return True
        if (root_dir / "workflow.json").is_file():
            return True
        # Also check for nested coze/ directory
        for pattern in ["coze", ".coze", "bot", "plugin", "workflow"]:
            d = root_dir / pattern
            if d.is_dir():
                for f in d.iterdir():
                    if f.suffix == ".json" and "manifest" in f.stem.lower():
                        return True
        return False

    def convert(self, root_dir: Path, target_base: Path) -> Dict[str, Any]:
        converted: List[str] = []
        skipped: List[str] = []

        base = root_dir
        for pattern in ["coze", ".coze"]:
            if (root_dir / pattern).is_dir():
                base = root_dir / pattern
                break

        agents_base = target_base.parent / "agents"
        tools_base = target_base.parent / "tools"

        # 1. Agent: bot_manifest.json → AGENT.md
        bm = base / "bot_manifest.json"
        if bm.is_file():
            try:
                agent = _convert_coze_bot(bm)
                if agent:
                    name = agent["name"]
                    dest = agents_base / name
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / "AGENT.md").write_text(agent["agenth_md"], encoding="utf-8")
                    converted.append(f"agent:{name}")
                else:
                    skipped.append("agent: parse failed")
            except Exception:
                skipped.append("agent: error during conversion")

        # 2. Plugin → Skill or Tool
        for plugin_file in base.rglob("plugin_manifest.json"):
            try:
                result = _convert_coze_plugin(plugin_file)
                if not result:
                    continue
                if result.get("tool_python"):
                    name = result["name"]
                    dest = tools_base / name
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / f"{name}.py").write_text(result["tool_python"], encoding="utf-8")
                    (dest / "manifest.json").write_text(_json.dumps({
                        "name": name, "type": "tool", "source": "coze_plugin",
                        "description": result.get("description"),
                    }), encoding="utf-8")
                    converted.append(f"tool:{name}")
                elif result.get("skill_md"):
                    name = result["name"]
                    dest = target_base / name
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / "SKILL.md").write_text(result["skill_md"], encoding="utf-8")
                    converted.append(f"skill:{name}")
            except Exception:
                skipped.append(f"plugin:{plugin_file.name}")

        # 3. Workflow: workflow.json → workflow.yaml
        for wf_file in base.rglob("workflow.json"):
            try:
                wf = _convert_coze_workflow(wf_file)
                if wf:
                    name = wf["name"]
                    dest = Path.home() / ".aiplat" / "workflow_templates"
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / f"{name}.json").write_text(_json.dumps(wf["stages"], indent=2, ensure_ascii=False), encoding="utf-8")
                    converted.append(f"workflow:{name}")
            except Exception:
                skipped.append(f"workflow:{wf_file.name}")

        return {"converted": converted, "skipped": skipped, "hints": []}


def _convert_coze_bot(bot_path: Path) -> Optional[Dict[str, str]]:
    data = _json.loads(bot_path.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(data, dict):
        return None

    name = str(data.get("name") or data.get("bot_name") or "coze_bot")
    display = str(data.get("display_name") or data.get("name") or name)
    desc = str(data.get("description") or "")
    persona = str(data.get("persona") or data.get("prompt") or "")

    # Model config
    model_cfg = data.get("model") or data.get("model_config") or {}
    if isinstance(model_cfg, str):
        model_name = model_cfg
    elif isinstance(model_cfg, dict):
        model_name = str(model_cfg.get("model") or model_cfg.get("name") or "auto")
    else:
        model_name = "auto"

    # Skills from plugins
    plugins = data.get("plugins") or []
    if isinstance(plugins, list):
        plugin_ids = [str(p.get("id") or p.get("name") or "") for p in plugins if isinstance(p, dict)]
    else:
        plugin_ids = []

    # Knowledge base
    knowledge = data.get("knowledge") or {}
    datasets = knowledge.get("datasets") if isinstance(knowledge, dict) else []

    safe_name = re.sub(r"[^\w\u4e00-\u9fff]", "_", name.lower())[:32]

    sop_parts = []
    if persona:
        sop_parts.append(f"## Persona\n{persona}")
    if datasets:
        ds_names = ", ".join(d.get("name", "") for d in datasets if isinstance(d, dict))
        if ds_names:
            sop_parts.append(f"## Knowledge Base\nDatasets: {ds_names}")
    if plugin_ids:
        sop_parts.append(f"## Available Plugins\n{', '.join(plugin_ids)}")

    fm = {
        "name": safe_name,
        "display_name": display,
        "description": desc[:1024],
        "agent_type": "conversational",
        "version": "0.1.0",
        "status": "draft",
        "category": "general",
        "tags": ["coze", "imported"],
        "skills": plugin_ids[:10],
        "tools": [],
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
    lines.append("\n\n".join(sop_parts) if sop_parts else "## SOP\nImported from Coze bot.")
    lines.append("")

    return {"name": safe_name, "agenth_md": "\n".join(lines)}


def _convert_coze_plugin(plugin_path: Path) -> Optional[Dict[str, str]]:
    data = _json.loads(plugin_path.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(data, dict):
        return None

    name = str(data.get("name") or data.get("id") or "coze_plugin")
    desc = str(data.get("description") or "")
    api = data.get("api") or {}
    if not isinstance(api, dict):
        return None

    url = str(api.get("url") or "")
    method = str(api.get("method") or "GET").upper()
    params = api.get("parameters") or {}
    auth = api.get("auth") or {}

    safe_name = re.sub(r"[^\w\u4e00-\u9fff]", "_", name.lower())[:32]

    if not url:
        # Pure function plugin → SKILL.md
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
            f"input_schema: {{'input': {{'type': 'object', 'description': 'Plugin input', 'required': true}}}}",
            f"output_schema: {{'result': {{'type': 'object', 'description': 'Plugin output', 'required': true}}}}",
            "---",
            "## SOP",
            f"{desc}",
            "",
        ]
        return {"name": safe_name, "skill_md": "\n".join(skill_lines)}

    # API plugin → BaseTool Python
    param_props = {}
    for pk, pv in params.items() if isinstance(params, dict) else []:
        if isinstance(pv, dict):
            param_props[pk] = {"type": str(pv.get("type", "string")), "description": str(pv.get("description", ""))}
        else:
            param_props[pk] = {"type": "string"}

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
        f'        resp = requests.{method.lower()}("{url}", params=locals())',
        "        return resp.json()",
        "",
    ]

    return {"name": safe_name, "tool_python": "\n".join(tool_lines),
            "description": desc[:200]}


def _convert_coze_workflow(wf_path: Path) -> Optional[Dict[str, Any]]:
    data = _json.loads(wf_path.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(data, dict):
        return None

    name = str(data.get("name") or "coze_workflow")
    nodes = data.get("nodes") or []
    if not isinstance(nodes, list):
        return None
    edges = data.get("edges") or []

    safe_name = re.sub(r"[^\w\u4e00-\u9fff]", "_", name.lower())[:32]
    stages = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id", ""))
        ntype = str(node.get("type", "")).lower()

        stage: Dict[str, Any] = {"id": nid}

        if ntype == "start":
            stage["kind"] = "start"
        elif ntype == "end":
            stage["kind"] = "end"
        elif ntype in ("llm", "model"):
            stage["kind"] = "agent"
            stage["agent_type"] = "conversational"
            model = node.get("model") or {}
            stage["model"] = model.get("model") if isinstance(model, dict) else str(model)
            prompt = node.get("prompt") or node.get("prompt_template") or ""
            if isinstance(prompt, list):
                prompt = "\n".join(str(p.get("text", "")) for p in prompt if isinstance(p, dict))
            stage["prompt_extra"] = str(prompt)[:2000]
        elif ntype in ("code", "function"):
            stage["kind"] = "tool"
            stage["tool_type"] = "code_execution"
            code = node.get("code") or node.get("script") or ""
            stage["code_snippet"] = str(code)[:5000]
        elif ntype in ("knowledge", "retrieval"):
            stage["kind"] = "skill"
            stage["skill_id"] = "knowledge_retrieval"
            datasets = node.get("dataset_ids") or []
            stage["dataset_ids"] = list(datasets) if isinstance(datasets, list) else []
        elif ntype in ("condition", "branch", "if"):
            stage["kind"] = "condition"
            branches = node.get("branches") or []
            stage["conditions"] = [
                {"label": str(b.get("name", "")), "predicate": str(b.get("condition", ""))[:500]}
                for b in branches if isinstance(b, dict)
            ]
        else:
            stage["kind"] = "tool"
            stage["tool_type"] = ntype

        # Map edges
        deps = [str(e.get("from", "")) for e in edges if isinstance(e, dict) and str(e.get("to", "")) == nid]
        if deps:
            stage["depends_on"] = deps

        stages.append(stage)

    return {"name": safe_name, "stages": {"name": safe_name, "description": f"Imported from Coze workflow: {name}", "stages": stages}}


__all__ = ["CozeAdapter"]
