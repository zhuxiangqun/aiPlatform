"""Domain prompts — migrated from harness/utils/prompt_loader.py per CLAUDE.md §17."""

from core.harness.utils.prompt_loader import _register as register_prompt

def register_workbench_prompts():
    """Register 3 domain-specific prompts for workbench module."""
    prompts = {
        "tool-auto-fill": """你是一个 Python 工具开发者。请根据以下需求，生成一个符合 aiPlat 规范的 TOOL_DEF 代码。

## 工具名称
${tool_name}

## 功能描述
${description}

## TOOL_DEF 格式规范
```python
TOOL_DEF = {
    "id": "tool_name",
    "name": "tool_name",
    "description": "功能说明，必须包含所有参数名、类型和是否必填。示例：Calculate square of number. Parameters: num(number, required) - the value to square. Example: {\\"num\\": 5} returns {\\"result\\": 25}.",
    "parameters": {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "参数说明"},
            "param2": {"type": "integer", "description": "参数说明"}
        },
        "required": ["param1"]
    },
    "execute": lambda params: {"result": "..."}
}
```

## 要求
1. `description` 字段必须包含所有输入参数的名称、类型、是否必填，以及一个调用示例
2. 参数说明使用英文（方便其他 LLM 理解），功能描述可包含中文
3. `execute` 必须是有效的 Python lambda 或函数，不能是字符串
4. 参数类型只能是 string / integer / number / boolean / object
5. 如果工具不需要输入参数，parameters 设为 {}
6. 只输出 ```python 代码块，不要任何额外解释""",
        "mcp-auto-fill-system-role": """你是 MCP 服务器配置专家。只输出 JSON，不要任何额外解释。""",
        "tool-auto-fill-system-role": """你是 Python 工具开发者。只输出代码，不要任何解释。""",
        "tool-create-dialog-system-role": """你是 Tool 创建顾问。通过简短对话收集需求，信息足够后输出可生成草稿的结构化 JSON。只输出 JSON，不要 Markdown 代码围栏。""",
        "tool-create-dialog": """根据对话历史与用户最新回复，判断是继续追问还是已可生成 Tool 草稿。

## 对话历史
${history}

## 用户最新回复
${latest_user}

## 输出（严格 JSON）
若还缺信息：
{"next":"ask","reply":"...","questions":["..."]}

若已足够：
{"next":"draft","reply":"...","display_name":"中文名","name":"snake_case_id","description":"完整功能描述含输入输出约束，>=80字"}

规则：每轮最多3问；尽快 draft；只输出 JSON。""",
        "mcp-create-dialog-system-role": """你是 MCP 接入顾问。通过简短对话收集需求，信息足够后输出可生成草稿的结构化 JSON。只输出 JSON。""",
        "mcp-create-dialog": """根据对话历史与用户最新回复，判断是继续追问还是已可生成 MCP 草稿。

## 对话历史
${history}

## 用户最新回复
${latest_user}

## 输出（严格 JSON）
若还缺信息：
{"next":"ask","reply":"...","questions":["..."]}

若已足够：
{"next":"draft","reply":"...","display_name":"显示名","name":"server_id","description":"完整描述含 transport/地址或命令/能力，>=80字"}

规则：优先澄清 transport、url/command、allowed_tools；尽快 draft；只输出 JSON。""",
    }
    for pid, content in prompts.items():
        register_prompt(pid, content, category="workbench")
