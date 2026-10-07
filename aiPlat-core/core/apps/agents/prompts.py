"""Domain prompts — agents module."""

from core.harness.utils.prompt_loader import _register as register_prompt


def register_agents_prompts() -> None:
    """Register agents domain prompts."""
    prompts = {
        "agent-sop-design": (
            "你是 AI Agent 流程设计师。先写出可执行的 SOP，再给出配置元数据。只输出 JSON。\n\n"
            "Agent名称: ${name}\n"
            "功能描述: ${description}\n"
            "${role_hint}\n\n"
            "## 可用 Skill 白名单（SOP 步骤里尽量用这些 id，写成 `id` 反引号）\n${skills_text}\n\n"
            "## 可用 Tool 白名单（同上）\n${tools_text}\n\n"
            "## 可用 MCP 白名单（外部系统对接时引用，写成 `server_name`）\n${mcps_text}\n\n"
            "规则：\n"
            "1. 先写 sop_text：4~8 个编号步骤，可执行、可验收。\n"
            "2. 步骤需要调用能力时，优先引用白名单 id（Skill/Tool/MCP）。\n"
            "3. 若白名单没有必需能力，不要假装已有；Skill/Tool 写 [[need:能力名]]，"
            "MCP 写 [[need:mcp:名称]]，并分别列入 needed_skills/needed_tools/needed_mcps。\n"
            "4. 不要为了塞满而引用无关 id（例如做 PPT 不要引用 search/webfetch/无关 MCP，"
            "除非描述明确要求联网或外部对接）。\n"
            "5. PPT/文档生成类：白名单已有 `ppt_generation` 时必须写成 `ppt_generation`；"
            "没有时才写 [[need:ppt_generation]]。可辅以 `summarize`/`requirement_analysis`/`file_operations`。\n"
            "6. system_prompt 写角色与边界（≠ SOP 第一行）。\n\n"
            "输出JSON："
            '{"agent_type":"react",'
            '"sop_text":"1. ...\\n2. ...",'
            '"system_prompt":"你是…",'
            '"memory_config":{"type":"conversation","max_turns":20,"persist":true},'
            '"trigger_conditions":["触发短语"],'
            '"needed_skills":["白名单id或缺口名"],'
            '"needed_tools":["白名单id或缺口名"],'
            '"needed_mcps":["白名单MCP名或缺口名"],'
            '"reasoning":"说明SOP设计与缺口"}'
        ),
        "agent-execution-examples-system-role": (
            "你是测试用例设计师。只输出 JSON 数组，不要 Markdown 解释，不要代码围栏外的闲聊。"
        ),
        "agent-execution-examples": """为下面这个 Agent 设计 2～4 条可直接在「执行」面板点「填入」的冒烟测试用例。

## Agent
- id: ${agent_id}
- name: ${agent_name}
- description: ${description}
- skills: ${skills}
- tools: ${tools}

## input_schema（若有）
${input_schema_json}

## SOP（节选）
${sop_excerpt}

## 额外要求
${refine_hint}

## 输出格式（严格 JSON 数组）
[
  {"title": "短标题（中文，<=24字）", "content": "纯文本任务描述，或合法 JSON 字符串（常见字段 message）"},
  {"title": "…", "content": "…"}
]

## 通用质量门禁
1. 至少 2 条：一条主路径可验收、一条多约束/边界；贴合已绑定 skills/tools
2. 禁止空占位与一句话任务（如「帮我测试一下」「做个需求」）
3. 每条须含：目标、范围（含 1 件不做）、1 条可检查验收点
4. 若有 input_schema 必填字段，至少一条为覆盖必填的合法 JSON 对象（字符串形式）
5. 叙事类任务建议 ≥120 字；有 input_schema 的参数 JSON 可以短，但必须覆盖必填且禁止抄 description
6. 只输出 JSON 数组
7. 不要用「你是某某 Agent」开场（执行时系统已注入角色）
8. 若有 input_schema：禁止把字段 description 原文或「示例：」+ 说明当作值；按类型填可执行样例（路径/URL/字节数/枚举）

## 按技能分叉（必须遵守）
- 若 skills 含 code_generation / file_operations（编码/脚手架）：
  用例必须是可直接交付的任务：写明要交的文件（## FILE 或路径清单）+「调用 code_generation → DONE」。
  禁止：先澄清再生成、未知项待确认不要假设、先列文件清单再 file_operations 落盘、
  「必须落盘」、把「本机能否 npm/uvicorn 起来」当成唯一验收。缺端口时写死 8000/5173。
  脚手架（名称/描述含 脚手架/scaffold）：只交可启动空壳（根目录 main.py + GET /health + Vite 入口 + tsconfig.json；.py 三引号成对），
  禁止待办/CRUD/登录/业务路由（那是下游 FE/BE）。README 的 uvicorn 命令须与 ## FILE 路径一致。
- 若 skills 含 requirement_analysis：允许澄清清单 + PRD 草稿。
- 若 skills 含 architecture_design：输出可评审架构，禁止编造未给的第三方接口。
- 若 skills 含 test_executor（测试执行器）：
  content 必须是「待执行的 test_cases / test_questions」，让执行器产出通过/失败报告。
  至少一条为合法 JSON（含非空 test_cases 数组：id/steps/expected 或 question/min_expectation）。
  另给一条 test_cases 为空、期望 BLOCKED 的输入。
  禁止写成【复杂冒烟】产品口述（钉钉 API、照片不上公网、本次不做）——那是 requirement_analysis / 测试类 Agent 的输入。
- 其它 Agent：未知标待确认；不要套用编码 Agent 的 ## FILE 门禁。"""
    }
    for pid, content in prompts.items():
        register_prompt(pid, content, category="agents")
