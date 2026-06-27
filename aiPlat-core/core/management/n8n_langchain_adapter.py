"""
n8n + LangChain → aiPlatform format adapters.
"""

from __future__ import annotations
import logging

import json as _json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════
# n8n
# ═══════════════════════════════════════════════════

class N8nAdapter:
    NAME = "n8n"
    DESCRIPTION = "n8n (Workflow JSON with 400+ nodes)"

    def detect(self, root_dir: Path) -> bool:
        if (root_dir / "workflow.json").is_file():
            return True
        for item in root_dir.iterdir():
            if item.suffix == ".json" and item.is_file():
                try:
                    data = _json.loads(item.read_text(encoding="utf-8", errors="replace"))
                    if isinstance(data, dict) and "nodes" in data and "connections" in data:
                        return True
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
        return False

    def convert(self, root_dir: Path, target_base: Path) -> Dict[str, Any]:
        converted: List[str] = []
        skipped: List[str] = []

        for json_file in root_dir.rglob("*.json"):
            try:
                data = _json.loads(json_file.read_text(encoding="utf-8", errors="replace"))
                if not isinstance(data, dict):
                    continue
                # n8n: {nodes: [...], connections: {...}}
                if "nodes" not in data or "connections" not in data:
                    continue

                name = str(data.get("name") or json_file.stem)
                safe = re.sub(r"[^a-z0-9_]", "_", name.lower())[:32]

                # Convert skills from HTTP/Webhook/Function nodes
                for node in data.get("nodes") or []:
                    if not isinstance(node, dict):
                        continue
                    ntype = str(node.get("type") or "").lower()
                    nname = str(node.get("name") or "")
                    params = node.get("parameters") or {}

                    if ntype in ("n8n-nodes-base.httprequest", "n8n-nodes-base.webhook"):
                        surl = str(params.get("url") or params.get("path") or "")
                        if surl:
                            _make_api_skill(nname, surl, params, target_base, converted)
                    elif ntype in ("n8n-nodes-base.function", "n8n-nodes-base.code", "n8n-nodes-base.pythonCode"):
                        code = str(params.get("code") or params.get("jsCode") or "")
                        if code:
                            _make_code_skill(nname, code, target_base, converted)

                # Convert workflow
                stages = []
                node_map = {str(n.get("id", "")): str(n.get("name", "")) for n in data.get("nodes") or [] if isinstance(n, dict)}

                for nid, conns in (data.get("connections") or {}).items():
                    if not isinstance(conns, dict):
                        continue
                    for output_port, targets in conns.items():
                        if not isinstance(targets, list):
                            continue
                        for t in targets:
                            if not isinstance(t, dict):
                                continue
                            tnid = str(t.get("node", ""))
                            if tnid:
                                stages.append({
                                    "id": nid,
                                    "kind": "tool",
                                    "tool_type": node_map.get(nid, nid),
                                    "depends_on": [tnid] if tnid != nid else [],
                                })

                if stages:
                    dest = Path.home() / ".aiplat" / "workflow_templates"
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / f"{safe}.json").write_text(_json.dumps({
                        "name": safe, "description": f"Imported from n8n: {name}", "stages": stages
                    }, indent=2, ensure_ascii=False), encoding="utf-8")
                    converted.append(f"workflow:{safe}")

            except Exception:
                skipped.append(f"n8n:{json_file.name}")

        return {"converted": converted, "skipped": skipped, "hints": []}


def _make_api_skill(name: str, url: str, params: dict, target: Path, converted: List[str]):
    safe = re.sub(r"[^a-z0-9_]", "_", (name or "n8n_api").lower())[:32]
    method = str(params.get("method") or "GET").upper()
    body = params.get("body") or {}
    lines = [
        "---",
        f"name: {safe}",
        f"display_name: {name}",
        f"description: API call to {url[:200]}",
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
        "input_schema: {'input': {'type': 'object', 'required': true}}",
        "output_schema: {'result': {'type': 'object', 'required': true}}",
        "---",
        "## SOP",
        f"Call {method} {url}",
        f"Body: {_json.dumps(body)[:500]}",
        "",
    ]
    dest = target / safe
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    converted.append(f"skill:{safe}")


def _make_code_skill(name: str, code: str, target: Path, converted: List[str]):
    safe = re.sub(r"[^a-z0-9_]", "_", (name or "n8n_code").lower())[:32]
    lines = [
        "---",
        f"name: {safe}",
        f"display_name: {name}",
        "description: Code execution node from n8n",
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
        "input_schema: {'input': {'type': 'object', 'required': true}}",
        "output_schema: {'result': {'type': 'object', 'required': true}}",
        "---",
        "## SOP",
        f"```\n{code[:3000]}\n```",
        "",
    ]
    dest = target / safe
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    converted.append(f"skill:{safe}")


# ═══════════════════════════════════════════════════
# LangChain
# ═══════════════════════════════════════════════════

class LangChainAdapter:
    NAME = "langchain"
    DESCRIPTION = "LangChain (agent JSON, @tool decorator, LangGraph)"

    def detect(self, root_dir: Path) -> bool:
        for item in root_dir.iterdir():
            if item.suffix == ".json" and item.is_file():
                try:
                    data = _json.loads(item.read_text(encoding="utf-8", errors="replace"))
                    if isinstance(data, dict):
                        if "agent_type" in data or "executor" in data or "tools" in data:
                            return True
                        if "nodes" in data and "edges" in data and data.get("type") in ("graph", "langgraph"):
                            return True
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
            if item.suffix == ".py" and item.is_file():
                try:
                    text = item.read_text(encoding="utf-8", errors="replace")
                    if "@tool" in text or "create_react_agent" in text or "LangGraph" in text or "StateGraph" in text:
                        return True
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
        return False

    def convert(self, root_dir: Path, target_base: Path) -> Dict[str, Any]:
        converted: List[str] = []
        skipped: List[str] = []
        agents_base = target_base.parent / "agents"
        tools_base = target_base.parent / "tools"

        for item in root_dir.rglob("*"):
            if item.name.startswith(".") or item.name.endswith(".pyc"):
                continue

            # Agent JSON
            if item.suffix == ".json":
                try:
                    data = _json.loads(item.read_text(encoding="utf-8", errors="replace"))
                    if isinstance(data, dict) and "agent_type" in data:
                        agent = _convert_lc_agent(item, data)
                        if agent:
                            name = agent["name"]
                            dest = agents_base / name
                            dest.mkdir(parents=True, exist_ok=True)
                            (dest / "AGENT.md").write_text(agent["agenth_md"], encoding="utf-8")
                            converted.append(f"agent:{name}")
                except Exception:
                    skipped.append(f"langchain:{item.name}")

            # Tool: @tool decorated Python functions
            if item.suffix == ".py":
                try:
                    text = item.read_text(encoding="utf-8", errors="replace")
                    if "@tool" in text:
                        tools = _extract_lc_tools(item, text)
                        for t in tools:
                            name = t["name"]
                            dest = target_base / name
                            dest.mkdir(parents=True, exist_ok=True)
                            (dest / "SKILL.md").write_text(t["skill_md"], encoding="utf-8")
                            converted.append(f"skill:{name}")
                    if "StateGraph" in text or "langgraph" in text.lower():
                        wf = _extract_langgraph(item, text)
                        if wf:
                            dest = Path.home() / ".aiplat" / "workflow_templates"
                            dest.mkdir(parents=True, exist_ok=True)
                            (dest / f"{wf['name']}.json").write_text(_json.dumps(wf["stages"], indent=2, ensure_ascii=False), encoding="utf-8")
                            converted.append(f"workflow:{wf['name']}")
                except Exception:
                    skipped.append(f"langchain:{item.name}")

        return {"converted": converted, "skipped": skipped, "hints": []}


def _convert_lc_agent(json_path: Path, data: Dict[str, Any]) -> Optional[Dict[str, str]]:
    name = str(data.get("name") or json_path.stem)
    agent_type = str(data.get("agent_type") or "react")
    desc = str(data.get("description") or "")
    model = str(data.get("model") or data.get("llm") or "auto")
    tools = data.get("tools") or []
    tool_names = [str(t.get("name", t)) for t in tools] if isinstance(tools, list) else []

    lc_agent_type = "conversational"
    if "react" in agent_type.lower():
        lc_agent_type = "react"
    elif "plan" in agent_type.lower():
        lc_agent_type = "plan_execute"
    elif "rag" in agent_type.lower():
        lc_agent_type = "rag"

    safe = re.sub(r"[^a-z0-9_]", "_", name.lower())[:32]

    fm = {
        "name": safe,
        "display_name": name,
        "description": desc[:1024],
        "agent_type": lc_agent_type,
        "version": "0.1.0",
        "status": "draft",
        "category": "general",
        "tags": ["langchain", "imported"],
        "skills": [],
        "tools": [],
        "model": model,
    }

    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(f"## SOP\nImported from LangChain {agent_type} agent.")
    if tool_names:
        lines.append(f"Available tools: {', '.join(tool_names)}")
    lines.append("")

    return {"name": safe, "agenth_md": "\n".join(lines)}


def _extract_lc_tools(py_path: Path, text: str) -> List[Dict[str, str]]:
    tools = []
    # Simple extraction of @tool decorated functions
    pattern = r"@tool\s*\n\s*def\s+(\w+)\s*\((.*?)\)[^:]*:?\s*\"{3}(.*?)\"{3}"
    for m in re.finditer(pattern, text, re.DOTALL):
        func_name = m.group(1)
        args = m.group(2).strip()
        doc = m.group(3).strip() if m.group(3) else f"LangChain tool: {func_name}"

        safe = re.sub(r"[^a-z0-9_]", "_", func_name.lower())[:32]
        skill_lines = [
            "---",
            f"name: {safe}",
            f"display_name: {func_name}",
            f"description: {doc[:1024]}",
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
            f"{doc}",
            f"Parameters: {args}",
            "",
        ]
        tools.append({"name": safe, "skill_md": "\n".join(skill_lines)})
    return tools


def _extract_langgraph(py_path: Path, text: str) -> Optional[Dict[str, Any]]:
    name = re.sub(r"[^a-z0-9_]", "_", py_path.stem.lower())[:32]
    # Extract node names from StateGraph.add_node() calls
    nodes = re.findall(r'\.add_node\s*\(\s*["\'](\w+)["\']', text)
    # Extract edge definitions
    edges = re.findall(r'\.add_edge\s*\(\s*["\'](\w+)["\']\s*,\s*["\'](\w+)["\']', text)

    if not nodes:
        return None

    stages = []
    for n in nodes:
        stage: Dict[str, Any] = {"id": n, "kind": "agent", "agent_type": "conversational"}
        stage["depends_on"] = [e[0] for e in edges if e[1] == n]
        stages.append(stage)

    return {"name": name, "stages": {"name": name, "description": f"Imported from LangGraph: {py_path.name}", "stages": stages}}


__all__ = ["N8nAdapter", "LangChainAdapter"]
