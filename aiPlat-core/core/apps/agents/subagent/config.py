"""
Subagent Configuration

Defines Subagent configuration structures.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum


class ToolPermissionLevel(Enum):
    """Tool permission levels"""
    READ_ONLY = "read_only"       # Read, Grep, Glob
    READ_WRITE = "read_write"     # Read, Write, Edit
    EXECUTE = "execute"           # Read, Write, Edit, Bash
    FULL = "full"                # All tools


@dataclass
class SubagentConfig:
    """Subagent configuration"""
    name: str
    description: str
    type: str = "subagent"
    
    # Tool permissions
    allowed_tools: List[str] = field(default_factory=list)
    denied_tools: List[str] = field(default_factory=list)
    permission_level: ToolPermissionLevel = ToolPermissionLevel.READ_ONLY
    
    # System prompt
    system_prompt: str = ""
    
    # Pre-loaded skills
    skills: List[str] = field(default_factory=list)
    
    # Execution config
    timeout: int = 300
    max_retries: int = 3
    max_context_tokens: int = 100000
    max_tools_per_task: int = 50
    
    # Hooks
    hooks: List[str] = field(default_factory=list)
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def can_use_tool(self, tool: str) -> bool:
        """Check if tool is allowed"""
        if tool in self.denied_tools:
            return False
        if self.allowed_tools and tool not in self.allowed_tools:
            return False
        return True
    
    @staticmethod
    def from_permission_level(level: ToolPermissionLevel) -> List[str]:
        """Get default tools for permission level"""
        level_tools = {
            ToolPermissionLevel.READ_ONLY: ["Read", "Grep", "Glob"],
            ToolPermissionLevel.READ_WRITE: ["Read", "Grep", "Glob", "Write", "Edit"],
            ToolPermissionLevel.EXECUTE: ["Read", "Write", "Edit", "Bash"],
            ToolPermissionLevel.FULL: ["*"]
        }
        return level_tools.get(level, [])


@dataclass
class SubagentInstance:
    """Runtime instance of a Subagent"""
    config: SubagentConfig
    session_id: str
    state: str = "created"  # created, running, completed, failed, cancelled
    
    # Runtime context
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    
    # Metrics
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    tokens_used: int = 0
    
    def get_context(self) -> List[Dict[str, Any]]:
        """Get current context"""
        return self.messages
    
    def add_message(self, role: str, content: str):
        """Add message to context"""
        self.messages.append({"role": role, "content": content})
    
    def add_tool_call(self, tool: str, params: Dict, result: Any):
        """Add tool call record"""
        self.tool_calls.append({
            "tool": tool,
            "params": params,
            "result": result
        })


# Built-in Subagent definitions
BUILTIN_SUBAGENTS = {
    "secure-reviewer": SubagentConfig(
        name="secure-reviewer",
        description="安全审计专家，只读审查，不能修改任何文件",
        allowed_tools=["Read", "Grep", "Glob"],
        denied_tools=["Write", "Edit", "Bash"],
        system_prompt="""你是一个安全审计专家。你的任务是：
1. 检查认证和授权逻辑
2. 识别 SQL 注入、XSS、CSRF 漏洞
3. 检查硬编码的密钥和 Token
4. 验证输入验证和输出编码

⚠️ 你只有只读权限，发现问题后报告给主代理处理。"""
    ),
    "debugger": SubagentConfig(
        name="debugger",
        description="代码调试专家，可修改但不能创建新文件",
        allowed_tools=["Read", "Edit"],
        system_prompt="""你是一个调试专家。你的任务是：
1. 分析代码问题
2. 定位 Bug 根因
3. 提供修复建议

⚠️ 你可以编辑现有文件，但不能创建新文件。"""
    ),
    "test-engineer": SubagentConfig(
        name="test-engineer",
        description="测试工程师，可创建文件",
        allowed_tools=["Read", "Write", "Bash"],
        system_prompt="""你是一个测试工程师。你的任务是：
1. 分析代码结构
2. 编写单元测试
3. 运行测试验证

⚠️ 你可以创建新文件和运行命令。"""
    ),
    "documentation-writer": SubagentConfig(
        name="documentation-writer",
        description="文档编写专家",
        allowed_tools=["Read", "Write"],
        system_prompt="""你是一个技术文档作家。你的任务是：
1. 理解代码功能
2. 编写清晰的文档
3. 生成示例代码

⚠️ 你只能读取和写入文本文件。"""
    ),
    "performance-analyzer": SubagentConfig(
        name="performance-analyzer",
        description="性能分析专家",
        allowed_tools=["Read", "Grep"],
        system_prompt="""你是一个性能分析专家。你的任务是：
1. 分析代码性能瓶颈
2. 识别 O(n²) 算法
3. 找出 N+1 查询问题
4. 提供优化建议

⚠️ 你只有只读权限。"""
    )
}


__all__ = [
    "ToolPermissionLevel",
    "SubagentConfig",
    "SubagentInstance",
    "BUILTIN_SUBAGENTS"
]