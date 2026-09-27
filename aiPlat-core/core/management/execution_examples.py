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
    label_blob = f"{label} {desc}".lower()

    if any(s in skills for s in ("ppt_generation", "pptx_generation", "slide_generation")):
        outline_text = (
            f"{task_hint}"
            "请根据以下大纲生成 PPT（有默认模版也须先确认再生成）：\n"
            "标题：aiPlat 产品介绍\n"
            "一、背景与目标\n"
            "- 交付慢、知识难沉淀\n"
            "- 目标：缩短交付周期\n"
            "二、方案概览\n"
            "- 八层架构要点\n"
            "三、下一步\n"
            "- 试点范围与成功指标\n"
            "\n"
            "约束：不编造数据；输出 pptx 绝对路径；生成前列出将使用的模版路径请用户确认。"
        )
        return [
            {"title": f"{label}（PPT 大纲）", "content": outline_text},
            {
                "title": f"{label}（PPT JSON）",
                "content": json.dumps({"message": outline_text.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    # Research / multi-source survey — before browser, so webfetch+browser agents aren't misclassified.
    if (
        "last30days" in skills
        or "knowledge_multi_query" in skills
        or any(k in label_blob for k in ("调研", "research", "竞品", "paper_monitor", "competitor"))
    ):
        research_msg = (
            f"{task_hint}"
            "【调研任务】话题：企业级 Agent 平台的「技能上架审批」实践（最近 30 天）。\n"
            "\n"
            "请完成一次可验收的调研冒烟（不要只堆链接）：\n"
            "1. 从至少 3 类来源检索（如 HN / Reddit / 技术博客 / 文档站；没有某源就跳过并说明）；\n"
            "2. 输出结构化报告：共识观点 / 争议焦点 / 新兴趋势 / 可能偏见；\n"
            "3. 每个观点至少标注 1 个可点击来源（标题+URL）；\n"
            "4. 末尾给「对我们产品的 3 条可执行建议」。\n"
            "禁止编造未检索到的来源。"
        )
        narrow_msg = (
            f"{task_hint}"
            "只做开场规划：话题「本地 LLM 推理网关选型」。\n"
            "- 列出检索关键词（中英各 4 个）与计划访问的来源清单；\n"
            "- 说明成功标准（报告章节骨架）；\n"
            "- 暂不抓全文，等用户确认后再深挖。"
        )
        return [
            {"title": f"{label}（技能上架·调研报告）", "content": research_msg},
            {"title": f"{label}（选题·检索规划）", "content": narrow_msg},
            {
                "title": f"{label}（调研 JSON）",
                "content": json.dumps({"message": research_msg.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    # Product / requirements / PRD agents.
    # Match on skill or *display name* only — descriptions often mention "PRD" (architect/coder)
    # and must not steal those roles' templates.
    name_l = label.lower()
    if "requirement_analysis" in skills or any(
        k in name_l for k in ("产品经理", "pm_agent", "product manager", "产品负责人")
    ):
        prd_msg = (
            f"{task_hint}"
            "【客户口述｜请按产品经理职责做草稿轮/冒烟，不要 PRD_READY】\n"
            "客户：江苏某制造企业，想做一个「现场巡检报障」小应用。\n"
            "- 一线工人用手机拍照上报设备异常；班组长审批后派维修。\n"
            "- 希望和现有钉钉账号打通，但暂时没有开放 API 文档。\n"
            "- 管理层要看「本周报障量 / 平均闭环时长」两个数。\n"
            "- 上线时间：希望 6 周内能试点 1 个车间；预算与编制未定。\n"
            "- 合规：照片可能含产线布局，不能传到公网。\n"
            "\n"
            "请完成一次可验收的需求分析草稿（不要只回「已验证」）：\n"
            "1. 列出至少 5 个必须向客户追问的澄清问题（按优先级，每题说明为什么问）；\n"
            "2. 基于已知信息起草结构化 PRD 草稿，至少包含：\n"
            "   - 背景与目标 / 用户与场景 / 功能需求(FR-001…) / 非功能需求 / 验收标准(AC) /\n"
            "     待确认问题 / 里程碑假设（分期切片，勿把开放问题当里程碑）；\n"
            "3. 每条 FR 给出可验证 AC（禁止「清晰可见/功能正常/实际操作测试」）；\n"
            "4. 信息不足一律标「待确认」；禁止编造多语言、具体 SLA、加密方案、\n"
            "   「已在钉钉应用内完成全流程」等未口述边界。\n"
            "\n"
            "【硬性自检——缺任一条视为失败】\n"
            "- 正文必须显式保留「照片不能传到公网 / 不上公网」（不得弱化成笼统合规）；\n"
            "- 正文必须显式保留「钉钉 API 文档未开放 / 集成方式待确认」；\n"
            "- 不要输出 <!-- PRD_READY -->；不要在文末再套一层 markdown 代码块复读全文。\n"
            "优先调用技能 requirement_analysis；输出一份中文 Markdown 即可。"
        )
        clarifying_msg = (
            f"{task_hint}"
            "用户只说了一句：「我们想做个智能客服，能回答知识库里的制度问题。」\n"
            "\n"
            "请以产品经理身份开场澄清（不要直接写完整 PRD）：\n"
            "- 用 6～8 个选择题/填空题把范围钉住（渠道、知识源、权限、幻觉处理、转人工、成功指标）；\n"
            "- 每题说明「为什么要问」；\n"
            "- 最后给一版「若用户全选默认值」的范围摘要（≤8 行），方便下一轮生成 PRD。\n"
        )
        return [
            {"title": f"{label}（巡检报障·PRD 草稿）", "content": prd_msg},
            {"title": f"{label}（智能客服·澄清开场）", "content": clarifying_msg},
            {
                "title": f"{label}（PRD JSON）",
                "content": json.dumps({"message": prd_msg.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    # Architect — before generic keyword roles that might overlap descriptions
    if (
        "architecture_design" in skills
        or any(k in name_l for k in ("架构师", "architect"))
        or ("系统设计" in label_blob and "architecture_design" in skills)
    ):
        arch_msg = (
            f"{task_hint}"
            "【输入｜精简 PRD 摘要】\n"
            "目标：现场巡检报障小应用（拍照上报 → 班组长审批 → 派修 → 看板）。\n"
            "约束：照片不可上公网；希望对接钉钉但暂无 API 文档；6 周试点一个车间。\n"
            "\n"
            "请按架构师职责输出一版可评审的架构草稿：\n"
            "1. 上下文与假设（标明待确认）；\n"
            "2. 逻辑架构 + 关键组件职责；\n"
            "3. 数据流（上报/审批/派修/看板）与存储选型理由；\n"
            "4. 对外 API 契约草案（3～5 个端点：方法/路径/请求响应要点）；\n"
            "5. 安全与合规（照片落地、脱敏、内网边界）；\n"
            "6. 6 周试点的分期切片与风险。\n"
            "禁止编造未给定的第三方接口细节。"
        )
        review_msg = (
            f"{task_hint}"
            "已有一版架构说「全部用公有云对象存储存巡检照片」。\n"
            "请做架构评审：指出与「照片不可上公网」的冲突，给出 2 套可落地替代方案及取舍。"
        )
        return [
            {"title": f"{label}（巡检报障·架构草稿）", "content": arch_msg},
            {"title": f"{label}（合规冲突·架构评审）", "content": review_msg},
            {
                "title": f"{label}（架构 JSON）",
                "content": json.dumps({"message": arch_msg.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    # QA / test design
    if "test_case_generation" in skills or any(
        k in name_l for k in ("测试经理", "qa_agent", "测试工程师")
    ):
        qa_msg = (
            f"{task_hint}"
            "【被测对象｜巡检报障】能力：工人拍照上报、班组长审批、派修、周看板。\n"
            "\n"
            "请设计可执行的冒烟用例集（不要空话）：\n"
            "1. 至少 8 条用例：编号 / 前置 / 步骤 / 期望 / 优先级；\n"
            "2. 覆盖主路径 + 至少 3 条异常（无权限、照片超限、审批驳回）；\n"
            "3. 另附 3 条接口级用例（若契约未知则标「待契约确认」并写假设）；\n"
            "4. 给出首轮冒烟的执行顺序（≤15 分钟能跑完）。"
        )
        agent_qa = (
            f"{task_hint}"
            "被测 Agent：产品经理（输入自然语言需求 → 输出 PRD Markdown）。\n"
            "请设计 5 条「Agent 对话」用例，每条含：用户输入样例、期望结构检查点、失败判据。"
        )
        return [
            {"title": f"{label}（巡检报障·用例集）", "content": qa_msg},
            {"title": f"{label}（Agent 对话用例）", "content": agent_qa},
            {
                "title": f"{label}（用例 JSON）",
                "content": json.dumps({"message": qa_msg.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    # Frontend page / app_page
    if "app_page_generation" in skills or any(
        k in name_l for k in ("前端程序员", "frontend_developer")
    ):
        page_msg = (
            f"{task_hint}"
            "【输入】为「巡检报障」Agent 应用生成使用页布局描述（app_page.json 风格）。\n"
            "角色：一线工人（上报）+ 班组长（审批列表）。\n"
            "\n"
            "请输出：\n"
            "1. 页面信息架构（路由/区块）；\n"
            "2. 关键组件与绑定的 Agent/Skill 动作；\n"
            "3. 一份可粘贴的 JSON 草稿（字段名清晰）；\n"
            "4. 列出 3 个需产品确认的交互问题。\n"
            "不要生成完整前端工程代码。"
        )
        return [
            {"title": f"{label}（巡检报障·页面草稿）", "content": page_msg},
            {
                "title": f"{label}（页面 JSON）",
                "content": json.dumps({"message": page_msg.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    # Programmer / code generation
    if "code_generation" in skills or any(
        k in name_l for k in ("程序员", "programmer", "后端开发", "backend_developer")
    ):
        code_msg = (
            f"{task_hint}"
            "【输入摘要】\n"
            "- PRD：巡检报障（上报/审批/派修）\n"
            "- 架构约束：照片仅内网对象存储；API 前缀 /api/v1/inspection\n"
            "\n"
            "请完成一次编码冒烟（小切片，可运行）：\n"
            "1. 实现 POST /api/v1/inspection/reports（创建报障）的路由 + Pydantic model；\n"
            "2. 字段：reporter_id, equipment_id, description, photo_uris[]；\n"
            "3. 附 1 个成功 + 1 个校验失败的示例请求；\n"
            "4. 说明如何本地用 curl 验证；\n"
            "5. 未给出的鉴权细节标 TODO，禁止假实现「已对接钉钉」。"
        )
        review_msg = (
            f"{task_hint}"
            "下面伪代码把照片 URL 直接拼到公网 CDN。请指出问题并用最小 diff 思路给出内网存储修正方案（文字即可）。"
        )
        return [
            {"title": f"{label}（报障 API·小切片）", "content": code_msg},
            {"title": f"{label}（安全·代码评审）", "content": review_msg},
            {
                "title": f"{label}（编码 JSON）",
                "content": json.dumps({"message": code_msg.strip()}, ensure_ascii=False, indent=2),
            },
        ]

    if "site_tester" in skills or (
        ("browser" in tools or any(s == "browser" or s.endswith("_browser") for s in skills))
        and "last30days" not in skills
    ):
        msg = (
            f"{task_hint}"
            "请对 https://example.com 做一次可验收冒烟巡检：\n"
            "1. 打开首页，记录标题与主 CTA 是否可见；\n"
            "2. 检查控制台是否有明显 JS error（有则摘录）；\n"
            "3. 输出：通过/失败 + 证据截图或 DOM 要点 + 阻塞项。\n"
            "不要声称访问了未打开的页面。"
        )
        return [
            {"title": f"{label}（站点冒烟）", "content": msg},
            {
                "title": f"{label}（JSON）",
                "content": json.dumps(
                    {"message": msg.strip(), "url": "https://example.com"},
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]

    if "summarize" in skills or "summarization" in skills:
        msg = (
            f"{task_hint}"
            "请阅读以下材料并输出结构化摘要（3 条要点 + 1 条风险 + 1 条行动，勿编造原文没有的事实）：\n"
            "\n"
            + sample_value_for_field("message", {"type": "string"})
        )
        return [
            {"title": f"{label}（长文摘要）", "content": str(msg)},
            {
                "title": f"{label}（JSON）",
                "content": json.dumps({"message": str(msg).strip()}, ensure_ascii=False, indent=2),
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
    legacy_markers = (
        "请按本能力说明完成一次冒烟测试",
        "按本 Agent 的职责做一次冒烟验证",
    )
    return all(
        any(m in str(e.get("content") or "") for m in legacy_markers)
        for e in examples
        if isinstance(e, dict)
    )
