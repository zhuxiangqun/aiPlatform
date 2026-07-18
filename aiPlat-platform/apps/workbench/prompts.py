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
    }
    for pid, content in prompts.items():
        register_prompt(pid, content, category="workbench")