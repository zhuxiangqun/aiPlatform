"""
Shared smoke-test input generators for Skill / Agent / Tool / MCP execute UIs.

Produces plausible default_input + example chips from input_schema (flat) or
JSON Schema ({properties, required}).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def sample_value_for_field(name: str, spec: Any, *, skill_hint: str = "") -> Any:
    """Generate a plausible smoke-test value for one field."""
    key = str(name or "").strip().lower()
    typ = ""
    desc = ""
    enum_vals: list = []
    if isinstance(spec, dict):
        typ = str(spec.get("type") or "").lower()
        desc = str(spec.get("description") or "")
        if isinstance(spec.get("enum"), list) and spec["enum"]:
            enum_vals = list(spec["enum"])
        if spec.get("default") is not None:
            return spec["default"]
    elif isinstance(spec, str):
        typ = spec.lower()

    if enum_vals:
        return enum_vals[0]

    if key in ("outline",):
        return {
            "title": "aiPlat 产品介绍",
            "sections": [
                {
                    "title": "背景与目标",
                    "pages": [
                        {
                            "title": "我们要解决什么",
                            "bullets": ["交付慢", "知识难沉淀", "质量难度量"],
                        },
                        {
                            "title": "目标",
                            "bullets": ["缩短交付周期", "可治理执行"],
                        },
                    ],
                },
                {
                    "title": "方案概览",
                    "pages": [
                        {
                            "title": "八层架构",
                            "bullets": ["本体语义底座", "知识创造引擎", "上下文注入总线"],
                        },
                    ],
                },
            ],
        }

    # Rich prose for summarization / rewrite / QA style skills
    long_article = (
        "【产品周报｜2026-W38】\n"
        "\n"
        "一、本周进展\n"
        "资产审批增加 Agent 上架硬门禁：绑定 Skill/MCP 须已发布或已上架，Tool 须在注册表可用，"
        "否则拒绝上架并返回依赖明细。应用库 Skill/Agent/Tool/MCP 列表支持按名称与描述搜索。"
        "PPT 生成 Skill 可按大纲与模版写出 .pptx；审批流已打通提交审核→通过→上架。\n"
        "\n"
        "二、问题与风险\n"
        "1. 默认 PPT 模版视觉偏简，客户演示观感不足；\n"
        "2. 部分 Skill 冒烟用例仍是一句话占位，难以验证长文压缩/结构化输出质量；\n"
        "3. 若干 workspace Skill 停在 ready，阻塞依赖它们的 Agent 上架。\n"
        "\n"
        "三、下周计划\n"
        "- 按能力类型丰富执行测试用例（摘要/检索/生成等给出可执行样例）\n"
        "- 迭代 default.pptx 版式与拆页策略\n"
        "- 清理待审核 Skill 队列，优先 unblock 被依赖项\n"
        "\n"
        "请输出：3 条要点 + 1 条风险 + 1 条行动建议（中文，条目化，勿编造原文没有的事实）。"
    )
    _ = skill_hint  # reserved for future skill-specific variants

    string_samples = {
        "query": "企业知识库里，关于资产审批硬门禁与 Skill 上架依赖校验的最新规范是什么？请给出出处要点。",
        "topic": "为客户做一份「aiPlat 资产审批与上架治理」产品介绍，突出硬门禁与迭代路径",
        "markdown": (
            "# 资产审批周报\n\n"
            "## 进展\n"
            "- Agent 上架前校验 Skill/MCP/Tool 依赖\n"
            "- 应用库支持名称/描述搜索\n\n"
            "## 风险\n"
            "- 默认 PPT 模版过简\n"
            "- 冒烟用例偏弱\n\n"
            "## 行动\n"
            "- 丰富测试用例生成器\n"
            "- 迭代 default.pptx\n"
        ),
        "message": long_article,
        "prompt": long_article,
        "text": long_article,
        "content": long_article,
        "input": long_article,
        "template_name": "default",
        "template": "default",
        "url": "https://example.com",
        "path": "/tmp/example.txt",
        "directory": "/tmp",
        "command": "echo hello",
        "cmd": "echo hello",
        "name": "demo",
        "title": "资产审批与上架治理周报",
    }
    if key in string_samples:
        return string_samples[key]

    if key in ("template_path", "source_path", "file_path"):
        return ""

    if "max_chars" in key:
        return 200

    if typ in ("boolean", "bool") or key.startswith("is_") or key.startswith("enable_"):
        return True

    if typ in ("integer", "int") or key.endswith("_count") or key.endswith("_limit"):
        return 3

    if typ in ("number", "float"):
        return 1.0

    if typ in ("array", "list"):
        return ["示例项1", "示例项2"]

    if typ in ("object", "dict"):
        return {"key": "value"}

    if desc:
        return f"示例：{desc[:48]}"
    return f"示例_{key or 'value'}"


def flatten_json_schema(schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalize to flat {name: {type, required, description, ...}}.

    Accepts either:
    - JSON Schema object: {properties, required}
    - Flat skill-style schema: {name: {type, required, description}}
    """
    if not isinstance(schema, dict) or not schema:
        return {}
    props = schema.get("properties")
    if isinstance(props, dict):
        required = {str(x) for x in (schema.get("required") or [])}
        out: Dict[str, Any] = {}
        for k, v in props.items():
            if isinstance(v, dict):
                item = dict(v)
                item["required"] = str(k) in required or bool(v.get("required"))
                out[str(k)] = item
            else:
                out[str(k)] = {"type": "string", "required": str(k) in required}
        return out
    # Already flat (skill input_schema)
    return dict(schema)


def build_sample_payload(
    schema: Optional[Dict[str, Any]],
    *,
    include_optional: bool = True,
    skill_hint: str = "",
) -> Dict[str, Any]:
    flat = flatten_json_schema(schema)
    if not flat:
        return {}
    payload: Dict[str, Any] = {}
    for k, v in flat.items():
        is_req = bool(isinstance(v, dict) and v.get("required"))
        if include_optional or is_req:
            payload[k] = sample_value_for_field(k, v, skill_hint=skill_hint)
    if not include_optional and not payload:
        # nothing marked required → fill all
        for k, v in flat.items():
            payload[k] = sample_value_for_field(k, v, skill_hint=skill_hint)
    return payload


def build_examples_from_input_schema(
    input_schema: Dict[str, Any],
    *,
    skill_id: str = "",
    skill_name: str = "",
) -> List[Dict[str, str]]:
    """Build one-click / auto-fill test cases from skill-style or JSON Schema."""
    flat = flatten_json_schema(input_schema)
    if not flat:
        return []

    skill_hint = f"{skill_id} {skill_name}".strip()
    required_payload = build_sample_payload(flat, include_optional=False, skill_hint=skill_hint)
    full_payload = build_sample_payload(flat, include_optional=True, skill_hint=skill_hint)

    text_field = None
    primary_text_keys = {
        "message",
        "prompt",
        "query",
        "topic",
        "markdown",
        "text",
        "content",
        "input",
    }
    for k, v in flat.items():
        sample = sample_value_for_field(k, v, skill_hint=skill_hint)
        if text_field is None and str(k).lower() in primary_text_keys and isinstance(sample, str):
            text_field = sample

    label = (skill_name or skill_id or "本能力").strip() or "本能力"
    examples: List[Dict[str, str]] = [
        {
            "title": f"{label}（必填字段）",
            "content": json.dumps(required_payload, ensure_ascii=False, indent=2),
        }
    ]
    if full_payload != required_payload:
        examples.append(
            {
                "title": f"{label}（含可选字段）",
                "content": json.dumps(full_payload, ensure_ascii=False, indent=2),
            }
        )

    if text_field:
        examples.append({"title": f"{label}（纯文本）", "content": text_field})
    elif "outline" in flat:
        examples.append(
            {
                "title": f"{label}（大纲文本）",
                "content": (
                    "标题：aiPlat 产品介绍\n"
                    "\n"
                    "一、背景与目标\n"
                    "- 交付慢、知识难沉淀\n"
                    "- 目标：缩短交付周期、可治理执行\n"
                    "\n"
                    "二、方案概览\n"
                    "- 八层架构：本体底座 / 知识引擎 / 上下文总线\n"
                ),
            }
        )

    return examples


def build_agent_task_examples(
    *,
    display_name: str,
    description: str = "",
    skill_ids: Optional[List[str]] = None,
    tool_ids: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """Skill/tool-aware defaults when Agent has no execution_examples / schema."""
    label = (display_name or "Agent").strip() or "Agent"
    skills = {str(s).lower() for s in (skill_ids or [])}
    tools = {str(t).lower() for t in (tool_ids or [])}
    desc = (description or "").strip()
    task_hint = f"任务背景：{desc}\n" if desc else ""

    if any(s in skills for s in ("ppt_generation", "pptx_generation", "slide_generation")):
        outline_text = (
            f"{task_hint}"
            "请根据以下大纲生成 PPT：\n"
            "标题：aiPlat 产品介绍\n"
            "一、背景与目标\n"
            "- 交付慢、知识难沉淀\n"
            "- 目标：缩短交付周期\n"
            "二、方案概览\n"
            "- 八层架构要点\n"
        )
        return [
            {"title": f"{label}（PPT 文本）", "content": outline_text},
            {
                "title": f"{label}（PPT JSON）",
                "content": json.dumps({"message": outline_text.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    if "site_tester" in skills or any("browser" in s for s in skills) or "browser" in tools:
        msg = f"{task_hint}请对 https://example.com 做一次冒烟巡检，输出通过/失败摘要。"
        return [
            {"title": f"{label}（URL 文本）", "content": msg},
            {
                "title": f"{label}（JSON）",
                "content": json.dumps(
                    {"message": msg.strip(), "url": "https://example.com"},
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]

    if "file_operations" in tools:
        msg = f"{task_hint}请列出 /tmp 下最近修改的文件，并给出简要说明。"
        return [
            {"title": f"{label}（目录任务）", "content": msg},
            {
                "title": f"{label}（JSON）",
                "content": json.dumps(
                    {"message": msg.strip(), "directory": "/tmp"},
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]

    msg = f"{task_hint}请完成以下任务：\n按本 Agent 的职责做一次冒烟验证（说明你做了什么、结果如何）。"
    return [
        {"title": f"{label}（文本）", "content": msg},
        {
            "title": f"{label}（JSON）",
            "content": json.dumps({"message": msg.strip()}, ensure_ascii=False, indent=2),
        },
    ]


def examples_are_generic(examples: Optional[List[Dict[str, Any]]]) -> bool:
    """True when examples are empty or still the legacy 通用 / one-liner chips."""
    if not examples:
        return True
    if all(str(e.get("title") or "").strip().startswith("通用") for e in examples if isinstance(e, dict)):
        return True
    legacy = "请按本能力说明完成一次冒烟测试"
    return all(legacy in str(e.get("content") or "") for e in examples if isinstance(e, dict))
