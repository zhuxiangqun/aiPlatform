"""
Structured Tool Calling parsing utilities

Goals:
- Prioritize structured JSON-form tool calls (tool/args or name/arguments)
- Backward-compatible with legacy formats: ACTION: tool_name: {json} or ACTION: tool_name: text
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union, List
import json
import re


@dataclass(frozen=True)
class ParsedToolCall:
    tool_name: str
    tool_args: Dict[str, Any]
    raw: str
    format: str  # json | action


@dataclass(frozen=True)
class ParsedActionCall:
    kind: str  # tool | skill | agent | workflow
    name: str
    args: Dict[str, Any]
    raw: str
    format: str  # json | action


def _try_load_json(s: str) -> Optional[Any]:
    s = s.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def _extract_json_candidate(text: str) -> Optional[str]:
    """Delegates to canonical JSON extraction via CoreFacade."""
    from core.utils.json_utils import extract_json_safe
    return extract_json_safe(text)

def _normalize_tool_call(obj: Any, raw: str) -> Optional[ParsedToolCall]:
    """
    Supports the following structured forms (pick one):
    1) {"tool": "...", "args": {...}}
    2) {"tool_name": "...", "tool_args": {...}}
    3) {"name": "...", "arguments": {...}} or arguments as a JSON string
    4) [{"tool": "...", "args": {...}}, ...] take the first item
    """
    if isinstance(obj, list) and obj:
        return _normalize_tool_call(obj[0], raw)

    if not isinstance(obj, dict):
        return None

    tool_name = obj.get("tool") or obj.get("tool_name") or obj.get("name")
    if not tool_name or not isinstance(tool_name, str):
        return None

    args = obj.get("args")
    if args is None:
        args = obj.get("tool_args")
    if args is None:
        args = obj.get("arguments")
    if args is None:
        args = obj.get("input")

    tool_args: Dict[str, Any] = {}
    if isinstance(args, dict):
        tool_args = args
    elif isinstance(args, str):
        loaded = _try_load_json(args)
        tool_args = loaded if isinstance(loaded, dict) else {"input": args}
    elif args is None:
        tool_args = {}
    else:
        # numbers/bool/list etc.
        tool_args = {"input": args}

    return ParsedToolCall(tool_name=tool_name.strip(), tool_args=tool_args, raw=raw, format="json")


def parse_tool_call(text: str) -> Optional[ParsedToolCall]:
    """
    Parse a tool call.

    Priority:
    1) Structured JSON (fenced or inline)
    2) Legacy ACTION: ...
    """
    if not text:
        return None

    # 1) JSON
    candidate = _extract_json_candidate(text)
    if candidate:
        obj = _try_load_json(candidate)
        parsed = _normalize_tool_call(obj, raw=candidate) if obj is not None else None
        if parsed:
            return parsed

    # 2) ACTION: tool: args
    up = text.upper()
    if "ACTION:" not in up:
        return None

    idx = up.find("ACTION:")
    parts = text[idx + len("ACTION:") :].strip()
    if not parts:
        return None

    if ":" in parts:
        tool_name, arg_str = parts.split(":", 1)
        tool_name = tool_name.strip()
        arg_str = arg_str.strip()
        args_obj = _try_load_json(arg_str)
        if isinstance(args_obj, dict):
            tool_args = args_obj
        elif arg_str:
            tool_args = {"input": arg_str}
        else:
            tool_args = {}
        return ParsedToolCall(tool_name=tool_name, tool_args=tool_args, raw=parts, format="action")

    return ParsedToolCall(tool_name=parts.strip(), tool_args={}, raw=parts, format="action")


def parse_action_call(text: str) -> Optional[ParsedActionCall]:
    """
    Parse an "action call" (tool or skill).

    Supports:
    - Tool (structured first):
      - {"tool":"name","args":{...}}
      - {"name":"name","arguments":"{...}"} (OpenAI style, treated as tool by default)
      - ACTION: name: {json_or_text}
    - Skill (must be explicitly tagged to avoid substring false triggers):
      - {"skill":"name","args":{...}} / {"skill_name":"name","skill_args":{...}}
      - SKILL: name: {json_or_text}
    """
    if not text:
        return None

    # 1) JSON
    candidate = _extract_json_candidate(text)
    if candidate:
        obj = _try_load_json(candidate)
        if isinstance(obj, list) and obj:
            obj = obj[0]
        if isinstance(obj, dict):
            # Skill (explicit)
            skill_name = obj.get("skill") or obj.get("skill_name")
            if isinstance(skill_name, str) and skill_name.strip():
                args = obj.get("args") if obj.get("args") is not None else obj.get("skill_args")
                if args is None:
                    args = obj.get("arguments")
                if args is None:
                    args = obj.get("input")
                if isinstance(args, dict):
                    parsed_args = args
                elif isinstance(args, str):
                    loaded = _try_load_json(args)
                    parsed_args = loaded if isinstance(loaded, dict) else {"input": args}
                elif args is None:
                    parsed_args = {}
                else:
                    parsed_args = {"input": args}
                return ParsedActionCall(
                    kind="skill",
                    name=skill_name.strip(),
                    args=parsed_args,
                    raw=candidate,
                    format="json",
                )

            # Agent delegation ({"agent": "name", "args": {...}})
            agent_name = obj.get("agent") or obj.get("agent_name")
            if isinstance(agent_name, str) and agent_name.strip():
                agent_args = obj.get("args") if obj.get("args") is not None else obj.get("agent_args")
                if agent_args is None:
                    agent_args = obj.get("task")
                if agent_args is None:
                    agent_args = obj.get("input")
                if isinstance(agent_args, str):
                    agent_args = {"task": agent_args}
                elif not isinstance(agent_args, dict):
                    agent_args = {"task": str(agent_args)}
                return ParsedActionCall(
                    kind="agent",
                    name=agent_name.strip(),
                    args=agent_args,
                    raw=candidate,
                    format="json",
                )

            # Workflow trigger
            workflow_name = obj.get("workflow") or obj.get("workflow_id")
            if isinstance(workflow_name, str) and workflow_name.strip():
                wf_args = obj.get("args") or obj.get("workflow_args") or {}
                if not isinstance(wf_args, dict):
                    wf_args = {"input": str(wf_args)}
                return ParsedActionCall(
                    kind="workflow",
                    name=workflow_name.strip(),
                    args=wf_args,
                    raw=candidate,
                    format="json",
                )

            # Tool (fallback to existing normalization)
            tool_parsed = _normalize_tool_call(obj, raw=candidate)
            if tool_parsed:
                return ParsedActionCall(
                    kind="tool",
                    name=tool_parsed.tool_name,
                    args=tool_parsed.tool_args,
                    raw=tool_parsed.raw,
                    format=tool_parsed.format,
                )

    # 2) SKILL: ...
    up = text.upper()
    if "SKILL:" in up:
        idx = up.find("SKILL:")
        parts = text[idx + len("SKILL:") :].strip()
        if not parts:
            return None
        if ":" in parts:
            name, arg_str = parts.split(":", 1)
            name = name.strip()
            arg_str = arg_str.strip()
            args_obj = _try_load_json(arg_str)
            if isinstance(args_obj, dict):
                args = args_obj
            elif arg_str:
                args = {"input": arg_str}
            else:
                args = {}
            return ParsedActionCall(kind="skill", name=name, args=args, raw=parts, format="action")
        return ParsedActionCall(kind="skill", name=parts.strip(), args={}, raw=parts, format="action")

    # 3) ACTION: ... => tool
    tool_parsed = parse_tool_call(text)
    if tool_parsed:
        return ParsedActionCall(kind="tool", name=tool_parsed.tool_name, args=tool_parsed.tool_args, raw=tool_parsed.raw, format=tool_parsed.format)

    return None
