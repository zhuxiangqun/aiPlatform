"""Domain prompts — migrated from harness/utils/prompt_loader.py per CLAUDE.md §17.
All prompts below are registered via register_prompt() — not hardcoded at call sites.
"""

from core.harness.utils.prompt_loader import _register as register_prompt

def register_builder_prompts():
    """Register 11 domain-specific prompts for builder module."""
    prompts = {
        "graph-ask": """你是代码库专家。用户问："${question}"

你可以使用以下工具：
- describe_layer(layer, type) → 描述一个层的架构信息
    type=capabilities → 模块结构 + 关键符号 + agent/skill列表
    type=relationships → 该层与其他层的导入关系
    type=interfaces → REST API端点列表
    适用层: core, infra, platform, app, management
- sysgraph_stats → 返回全局统计
- sysgraph_search(name) → 按文件名搜索
- sysgraph_hotspots(metric) → 热点模块
- sysgraph_churn → 最近修改的文件
- sysgraph_tests(untested=true) → 测试覆盖
- sysgraph_find(name, kind) → 按函数/类名查找定义

问题分类:
- "XX层有什么能力" → describe_layer(layer="XX", type="capabilities")
- "XX层跟YY层的关系" → describe_layer(layer="XX", type="relationships")
- "XX层有哪些接口" → describe_layer(layer="XX", type="interfaces")
- 统计/搜索类问题 → 用 sysgraph_* 工具

返回严格 JSON（无 markdown）:
{"tool":"tool_name","args":{...},"answer":"一句话解释"}
如果不需要查询直接能回答，返回: {"answer":"一句话"}

只返回 JSON，不要任何其他内容。""",
        "graph-ask-translate": """用户问："${question}"
系统查询结果：
${results_text}

请用 3-5 句中文回答用户的问题。引用具体的模块名、文件名、关键符号。
简明扼要，不要重复问题。直接回答即可。""",
        "graph-system-role": """你是代码库专家。只输出 JSON，不要任何解释。""",
        "graph-architect-role": """You are a codebase architect. Answer concisely.""",
        "graph-chat-stream": """You are a codebase expert. Below is relevant code structure:
${context}

User question: ${question}

Answer concisely in Chinese, referencing specific file paths. Keep it under 300 words.""",
        "agent-auto-fill": """你是一个 AI 平台配置专家。用户正在创建一个新的 AI Agent，请根据角色定义推荐配置。

## 用户输入
- 名称: ${name}
- 功能描述: ${description}
${role_section}

## Agent 类型体系（三层架构）

### 基础能力层 — 原子执行，无自主推理，不选工具不规划
- conversational: 纯对话，适用于客服/闲聊（无工具调用）
- rag: 检索增强生成，知识库问答（检索文档→LLM生成，无多步推理）
- tool: 单工具精确执行器（如计算器、查单条数据），不选工具只执行

### 推理决策层 — 自主推理+工具调用，ReAct 循环
- react: 通用推理引擎（Reason→Act→Observe循环），适合大多数场景。**这是默认选择**
- reflection: 自我反思修正，先执行→自检→修改，适合代码生成/文案撰写

### 协同编排层 — 组合基础层/推理层作为执行单元
- plan_execute: 先规划后分步执行（内部创建react/rag子Agent）
- multi_agent: 多Agent并行/协作处理（内部拆分子任务→创建子Agent）
- router: 意图识别+任务分发（派发到下游基础/推理Agent），不处理业务
- materials_chat: 企业级RAG复合体（= router + ontology感知 + CRAG检索 + react推理）

## 任务
根据角色定义${role_phrase}，输出严格 JSON（无 markdown 标记）:
{"agent_type":"react|conversational|rag|tool|reflection|plan_execute|multi_agent|router|materials_chat","config":{...},"memory_config":{...},"trigger_conditions":[...],"reasoning":"选择了哪个类型(从上述9个中选)以及为什么(考虑层级归属)"}

## 选择原则（按层级决策）
1. 先判断是否需要自主推理：否 → 基础能力层（conversational/rag/tool）
2. 需要推理+工具调用 → 推理决策层（react 默认, reflection 需自查场景）
3. 需要组合多个Agent → 协同编排层
4. 不确定时 → react（最通用的推理引擎）
- system_prompt: 从 role_name + responsibilities 提炼，≤200字
- trigger_conditions: 5~8 条触发短语，来自名称和职责的关键词
- skills/tools/SOP 由系统自动生成，不需要你填写""",
        "agent-role-definition": """你是一个 AI Agent 角色定义专家。根据用户的名称和功能描述，生成一份结构化的角色定义。

## 用户输入
- 名称: ${name}
- 功能描述: ${description}

## 输出格式
生成 JSON，包含以下字段：
- role_name: 角色的中文名称
- responsibilities: 该角色的主要职责列表（3-5条）
- scenarios: 该角色适用的使用场景列表（2-3条）
- required_capabilities: 该角色需要的能力列表（3-5条）
- workflow_hint: 该角色在团队协作中的位置描述""",
        "agent-role-system": """你是 AI 角色定义专家。只输出 JSON，不要加任何解释或 markdown 标记。""",
        "agent-auto-fill-batch": """你是一个 AI 平台配置专家。请为以下 ${count} 个 Agent 分别推荐最优配置。

## 待填充 Agent 列表（均缺失 system_prompt/skills/tools）
${agent_list}

## 可用技能 (Skills)
${skills_catalog}

## 可用工具 (Tools)
${tools_catalog}

## 可用 MCP 服务器
${mcp_catalog}

## 可委派的子 Agent
${agent_catalog}

## 已有 Workflow 模板
${wf_catalog}

## 任务
为以上每个 Agent 推荐配置。输出严格 JSON（无 markdown 标记），格式为:
{"<agent名>":{"agent_type":"...","config":{"model":"auto","temperature":0.3,"max_tokens":4096},"skills":[...],"tools":[...],"mcp_ids":[],"agent_ids":[],"workflow_ids":[],"memory_config":{...},"sop_text":"...","reasoning":"..."},...}

## 原则
- 每个 Agent 根据名称推断角色定位，选择匹配的技能和工具
- system_prompt 1-2 句即可，用 agent 名+角色定义
- skills 选 2-4 个最相关的，tools 选 2-3 个
- 只输出 JSON，不要任何解释""",
        "agent-import-detect": """你是一个 Agent 配置助手。阅读以下 AGENT.md 正文，推断该 Agent 需要的完整配置。

## Agent 类型:
- base: 基础对话 Agent
- react: ReAct 模式（推理+行动）
- plan: 规划型 Agent（任务分解）
- tool: 工具型 Agent（工具调用）

## 可用工具列表（从以下选择，只能选实际存在的）:
${available_tools_list}

## 可用 Skills（从以下选择实际存在的）:
${skills_catalog}

## 可用 MCP Server（从以下选择实际存在的）:
${mcp_catalog}

## 可用子 Agent（可从以下委派任务）:
${agent_catalog}

## 执行方式:
- agent 通过 ReAct loop 执行 SOP 步骤
- tools 用于原子操作
- skills 用于可复用能力模块
- MCP 用于外部服务集成

输出 JSON（无 markdown 标记, 字段完整）:
{"agent_type":"react","skills":["code_review","summarization"],"tools":["search","file_operations"],"mcp_ids":[],"agent_ids":[],"sop_text":"1. 接收任务\\n2. 分析需求\\n3. 执行操作\\n4. 输出结果","config":{"temperature":0.1,"max_tokens":4096},"reasoning":"AGENT.md 描述了多步推理需求，适合 ReAct 模式..."}""",
        "agent-auto-fill-system-role": """你是一个 AI Agent 配置专家。只输出 JSON，不要加任何解释或 markdown 标记。skills 字段只能使用提示词中列出的 id，禁止编造不存在的 id。如果无匹配项，skills 留空 []。""",
    }
    for pid, content in prompts.items():
        register_prompt(pid, content, category="builder")