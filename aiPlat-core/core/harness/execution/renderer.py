"""
Stage Output Renderer — Pydantic schema → unified Markdown for downstream agents.

Inspired by TradingAgents' render_research_plan / render_trader_proposal pattern.
Ensures structured output flows downstream as readable, consistent markdown.

Caller: PipelineEngine._exec_stage → render_stage_output → inject into next stage's prompt.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def render_stage_output(
    artifact: Any,
    *,
    stage_name: str = "",
    schema_fields: Optional[List[Dict[str, Any]]] = None,
    max_sections: int = 20,
) -> str:
    """Render a stage's output artifact as structured Markdown for downstream consumption.

    Args:
        artifact: The stage's output (dict, Pydantic model, list, or raw text)
        stage_name: Label for the report header
        schema_fields: Optional field descriptions for pretty rendering.
            Each: {name, label, render? (bool, default True)}
        max_sections: Max number of artifact entries to render

    Returns:
        Markdown string suitable for injecting into the next stage's prompt
    """
    parts = [f"## {stage_name or 'Stage'} Output\n"]

    # If artifact is a Pydantic model, convert to dict
    if hasattr(artifact, 'model_dump'):
        artifact = artifact.model_dump()
    elif hasattr(artifact, 'dict'):
        artifact = artifact.dict()

    if isinstance(artifact, dict):
        parts.extend(_render_dict(artifact, schema_fields, max_sections))
    elif isinstance(artifact, list):
        parts.extend(_render_list(artifact, schema_fields, max_sections))
    elif isinstance(artifact, str):
        parts.append(artifact[:5000])
    else:
        parts.append(str(artifact)[:5000])

    return "\n".join(parts)


def _render_dict(
    data: Dict[str, Any],
    schema_fields: Optional[List[Dict[str, Any]]] = None,
    max_sections: int = 20,
) -> List[str]:
    """Render a dict artifact as Markdown sections."""
    parts = []
    count = 0

    # If schema_fields provided, use them for ordering and labels
    if schema_fields:
        for sf in schema_fields:
            name = sf.get("name", "")
            if name not in data:
                continue
            label = sf.get("label", name)
            if sf.get("render", True) is False:
                continue
            value = data[name]
            parts.append(f"**{label}**")
            if isinstance(value, (dict, list)):
                parts.append(f"```json\n{json.dumps(value, ensure_ascii=False, indent=2)[:2000]}\n```")
            else:
                parts.append(str(value)[:2000])
            parts.append("")
            count += 1
            if count >= max_sections:
                break
    else:
        # No schema: render top-level keys in order
        for key, value in data.items():
            if key.startswith("_"):
                continue
            parts.append(f"**{key}**")
            if isinstance(value, (dict, list)):
                parts.append(f"```json\n{json.dumps(value, ensure_ascii=False, indent=2)[:2000]}\n```")
            else:
                parts.append(str(value)[:2000])
            parts.append("")
            count += 1
            if count >= max_sections:
                break

    return parts


def _render_list(
    data: List[Any],
    schema_fields: Optional[List[Dict[str, Any]]] = None,
    max_sections: int = 20,
) -> List[str]:
    """Render a list artifact as Markdown bullet points."""
    parts = []
    for i, item in enumerate(data[:max_sections]):
        if isinstance(item, dict):
            title = item.get("name") or item.get("id") or item.get("title") or f"Item {i+1}"
            parts.append(f"- **{title}**")
            # Render 2-3 key fields
            count = 0
            for k, v in item.items():
                if k in ("name", "id", "title"):
                    continue
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False, indent=2)[:500]
                parts.append(f"  {k}: {str(v)[:300]}")
                count += 1
                if count >= 3:
                    break
        else:
            parts.append(f"- {str(item)[:500]}")
    return parts


def inject_rendered_output(
    prompt: str,
    upstream_outputs: Dict[str, Any],
    stage_names: Optional[Dict[str, str]] = None,
) -> str:
    """Inject rendered upstream stage outputs into the current stage's prompt.

    Args:
        prompt: The current stage's prompt template
        upstream_outputs: {output_artifact_key: artifact_dict} from previous stages
        stage_names: Optional {output_artifact_key: display_name} for readable headers

    Returns:
        Prompt with upstream outputs appended as Markdown sections
    """
    parts = [prompt.rstrip()]
    if not upstream_outputs:
        return prompt

    parts.append("\n\n## Upstream Stage Outputs\n")
    for key, artifact in upstream_outputs.items():
        if not artifact:
            continue
        display_name = (stage_names or {}).get(key, key)
        rendered = render_stage_output(artifact, stage_name=display_name)
        parts.append(rendered)
        parts.append("")

    return "\n".join(parts)


__all__ = ["render_stage_output", "inject_rendered_output"]
