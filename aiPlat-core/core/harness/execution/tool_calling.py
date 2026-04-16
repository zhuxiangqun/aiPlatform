"""
结构化 Tool Calling 解析工具

目标：
- 优先支持结构化 JSON 形式的工具调用（tool/args 或 name/arguments）
- 兼容旧格式：ACTION: tool_name: {json} 或 ACTION: tool_name: text
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
    kind: str  # tool | skill
    name: str
    args: Dict[str, Any]
    raw: str
    format: str  # json | action


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)


def _try_load_json(s: str) -> Optional[Any]:
    s = s.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def _extract_json_candidate(text: str) -> Optional[str]:
    """
    尝试从文本中提取一个 JSON 候选（优先 fenced code block，其次尝试从第一个 { 或 [ 开始）。
    """
    m = _JSON_FENCE_RE.search(text)
    if m:
        return m.group(1).strip()

    def _slice_first_json(s: str) -> Optional[str]:
        """
        从 s 中（假设以 { 或 [ 开头）截取第一个“括号平衡”的 JSON 子串。
        处理常见情况：JSON 后面还跟了解释文本，导致 json.loads 失败。
        """
        s = s.lstrip()
        if not s or s[0] not in "{[":
            return None
        stack = []
        in_str = False
        esc = False
        for i, ch in enumerate(s):
            if in_str:
                if esc:
                    esc = False
                    continue
                if ch == "\\":
                    esc = True
                    continue
                if ch == '"':
                    in_str = False
                continue

            if ch == '"':
                in_str = True
                continue

            if ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if not stack:
                    return None
                left = stack.pop()
                if (left == "{" and ch != "}") or (left == "[" and ch != "]"):
                    return None
                if not stack:
                    return s[: i + 1].strip()
        return None

    # Heuristic: find first { or [ and take the first balanced JSON span
    i_obj = text.find("{")
    i_arr = text.find("[")
    candidates = [i for i in [i_obj, i_arr] if i >= 0]
    if not candidates:
        return None
    start = min(candidates)
    sliced = _slice_first_json(text[start:])
    return sliced or text[start:].strip()


def _normalize_tool_call(obj: Any, raw: str) -> Optional[ParsedToolCall]:
    """
    支持以下结构化形态（择一）：
    1) {"tool": "...", "args": {...}}
    2) {"tool_name": "...", "tool_args": {...}}
    3) {"name": "...", "arguments": {...}} 或 arguments 为 JSON 字符串
    4) [{"tool": "...", "args": {...}}, ...] 取第一项
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
    解析工具调用。

    优先级：
    1) 结构化 JSON（fenced 或内嵌）
    2) 旧式 ACTION: ...
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
    解析“动作调用”（tool 或 skill）。

    支持：
    - Tool（结构化优先）：
      - {"tool":"name","args":{...}}
      - {"name":"name","arguments":"{...}"}（OpenAI style，默认视为 tool）
      - ACTION: name: {json_or_text}
    - Skill（必须显式标注，避免 substring 误触发）：
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
