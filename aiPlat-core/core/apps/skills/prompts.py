"""Domain prompts — skills module."""

from core.harness.utils.prompt_loader import _register as register_prompt


def register_skills_prompts():
    """Register skills domain prompts."""
    prompts = {
        "skill-auto-fill-system-role": """你是 AI Skill 设计专家。只输出 SKILL.md 格式，不要任何额外解释。""",
        "skill-auto-fill": """你是一个 AI Skill 设计专家。请根据以下需求，设计一个完整的 Skill。

## Skill 名称
${skill_name}

## 功能描述
${description}

## 已有技能（避免重复，功能重叠时复用而非新建）
${skills_catalog}

## 输出格式
直接输出完整 SKILL.md 原文（不要用外层 ```yaml 包裹整个文件）。结构必须是：

---
name: english_snake_case_id
display_name: 中文显示名
description: >
  完整功能描述（保留用户关键约束；含冒号的长描述用 > 折行）
category: generation
version: 1.0.0
status: enabled
skill_kind: rule
permissions:
  - llm:generate
trigger_conditions:
  - 中文触发短语1
  - 中文触发短语2
  - 中文触发短语3
capabilities:
  - 核心能力1
  - 核心能力2
input_schema:
  field_a:
    type: string
    required: true
    description: 字段说明
output_schema:
  result:
    type: string
    required: true
    description: 业务结果
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown，与结构化字段一致
---

# 概述

## 目标
一行话

## 何时使用 / 何时不用
- ✅ 适用场景
- ❌ 不适用场景

## 工作流程（SOP）
1. 第一步
2. 第二步
3. 第三步

## 验收清单（Checklist）
- [ ] 输出含 markdown 且与结构化字段一致

## 硬性要求
1. name 必须是小写英文 snake_case（如 ppt_generation），不要用中文
2. category 只能从以下选一个：general, execution, retrieval, analysis, generation, transformation, reasoning, coding, search, tool, communication
3. skill_kind：纯推理/文案用 rule；需要写文件、跑命令、调工具落盘用 executable
4. 若描述涉及写出文件路径（.pptx/.docx/.xlsx/写文件等）：skill_kind=executable，permissions 至少含 llm:generate 与 tool:workspace_fs_write；不要加 tool:websearch/webfetch，除非用户明确要求联网；config 建议含 require_confirmation: true
5. permissions 默认至少 llm:generate；遵循最小权限
6. trigger_conditions 至少 3 条中文常用说法（短词/短句），贴合任务
7. input_schema / output_schema 必须从「功能描述」抽取具体字段名（扁平：字段 → {type,required,description}）。禁止在描述已给出结构化输入/输出时，退化为 prompt/style/format/text 空泛占位。output_schema 必须含 markdown，并与描述中的产出物一致（如路径、页数、摘要等）
8. SOP 步骤必须覆盖描述中的输入校验、核心动作、输出回报与约束（如不联网/不编造）；禁止与描述无关的套话；禁止输出「（待补充）」
9. 参考已有技能，避免重复造功能重叠技能
10. 只输出 SKILL.md 正文（以 --- 开头），不要额外解释""",
        "skill-create-dialog-system-role": """你是 Skill 创建顾问。通过简短对话收集需求，信息足够后输出可生成草稿的结构化 JSON。只输出 JSON，不要 Markdown 代码围栏。""",
        "skill-create-dialog": """根据对话历史与用户最新回复，判断是继续追问还是已可生成 Skill 草稿。

## 对话历史
${history}

## 用户最新回复
${latest_user}

## 输出（严格 JSON 对象）
若还缺关键信息：
{
  "next": "ask",
  "reply": "对用户的一句话回应",
  "questions": ["问题1", "问题2"]
}

若已足够生成草稿（至少有：目标、输入、输出；写文件/联网约束如有则写明）：
{
  "next": "draft",
  "reply": "已收集足够信息，正在生成草稿",
  "display_name": "中文显示名",
  "name": "english_snake_case_id",
  "description": "完整功能描述（含输入/处理/输出/约束，供后续 auto-fill 使用，建议 >=80 字）"
}

## 规则
1. 每轮最多 3 个问题，短句
2. 优先澄清：输入字段、输出形态（文本/文件）、是否写盘、是否联网、禁止事项
3. 用户已说清时尽快 next=draft，不要无限追问
4. description 必须可独立理解，不要只写“同上”
5. 只输出 JSON""",
        "skill-execution-examples-system-role": """你是测试用例设计师。只输出 JSON 数组，不要 Markdown 解释，不要代码围栏外的闲聊。""",
        "skill-execution-examples": """为下面这个 Skill 设计 2～4 条可直接在「执行」面板点「填入」的冒烟测试用例。

## Skill
- id: ${skill_id}
- name: ${skill_name}
- description: ${description}

## input_schema
${input_schema_json}

## SOP（节选，约束真实执行步骤；不要把说明当入参）
${sop_excerpt}

## 额外要求
${refine_hint}

## 输出格式（严格 JSON 数组）
[
  {"title": "短标题（中文，<=20字）", "content": "合法 JSON 字符串或纯文本；JSON 须匹配 input_schema 字段"},
  {"title": "…", "content": "…"}
]

## 通用质量门禁（适用于任意 Skill，禁止偷懒）
1. 至少 2 条：一条「简单但仍可验收」、一条「复杂/多约束」；标题建议带「简单/复杂」
2. 禁止空占位与一句话主输入（如「做个搜索」「帮我总结一下」「测试一下」）
3. 主输入字段（message/query/text/user_requirement/prompt/content 等）必须是多行场景描述，至少包含：
   - 角色与目标
   - 范围（做什么 / 明确 1 件不做）
   - 1 条可检查约束或验收点（未知则写「待确认」）
   - 禁止编造 Skill 描述与 schema 未给出的具体数字/密钥/渠道细节
4. 按能力类型加料（在通用门禁之上，按 description 自行判断）：
   - 摘要/改写：多段业务材料 + 明确输出格式
   - 生成（PPT/文档）：结构化大纲或足够要点
   - 检索/问答：具体 query + 期望边界/出处要求
   - 分析/诊断/PRD：边界与未知项必须可对照输出契约验收
5. 若 schema 有必填字段，至少一条 content 是合法 JSON 对象（字符串形式）覆盖必填字段
6. 叙事类主输入建议 ≥120 字；路径/字节/枚举等参数 JSON 可以短，但必须覆盖全部必填、禁止抄 description /「示例：」
7. 只输出 JSON 数组
8. **禁止把 input_schema 的 description 原文当作字段值**，也禁止 `示例：` + 说明。file/path 填真实风格路径（如 `/tmp/sample.mp4`），字节大小填数字（遵守「不超过」上限），枚举填 enum 中的值。""",
    }
    for pid, content in prompts.items():
        register_prompt(pid, content, category="skills")
