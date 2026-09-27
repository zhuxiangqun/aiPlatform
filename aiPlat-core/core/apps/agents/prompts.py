"""Domain prompts — agents module."""

from core.harness.utils.prompt_loader import _register as register_prompt


def register_agents_prompts() -> None:
    """Register agents domain prompts."""
    prompts = {
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

## 额外要求
${refine_hint}

## 输出格式（严格 JSON 数组）
[
  {"title": "短标题（中文，<=24字）", "content": "纯文本任务描述，或合法 JSON 字符串（常见字段 message）"},
  {"title": "…", "content": "…"}
]

## 硬性要求
1. 内容必须贴合该 Agent 职责与已绑定技能，足够真实、可执行
2. 禁止「按本 Agent 的职责做一次冒烟验证」「请按本能力说明完成一次冒烟测试」这类空占位
3. 产品/需求类：至少一条含具体客户口述场景 + 澄清/PRD 产出要求；另一条可侧重开场澄清
4. 对话类 Agent：content 以用户会说的话/任务为主，不要写系统内部配置
5. 若有 input_schema 必填字段，至少一条 content 是覆盖必填字段的合法 JSON 对象（字符串形式）
6. 只输出 JSON 数组""",
    }
    for pid, content in prompts.items():
        register_prompt(pid, content, category="agents")
