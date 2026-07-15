import logging
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
    graph_domain_id: Optional[str] = None  # ReconSubgraph domain for agent writes
    
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


# Built-in Subagent definitions.
# System prompts are loaded from AGENT.md files in ~/.aiplat/agents/builtin/.
# Only structural metadata (tools, permissions) stays in code.
# Override via AIPLAT_SUBAGENT_PROMPTS env var (JSON).

import os as _os
import json as _json


def _load_subagent_prompt(name: str) -> str:
    """Load system prompt from AGENT.md file."""
    import os as __os
    import yaml as __yaml
    paths = [
        __os.path.join(__os.path.expanduser("~/.aiplat"), "agents", "builtin", name, "AGENT.md"),
        __os.path.join(__os.getenv("AIPLAT_HOME", __os.path.expanduser("~/.aiplat")), "agents", "builtin", name, "AGENT.md"),
        __os.path.join(__os.getenv("AIPLAT_WORKSPACE_SEEDS", ""), "agents", "builtin", name, "AGENT.md"),
    ]
    for p in paths:
        if __os.path.exists(p):
            try:
                with open(p, "r") as f:
                    raw = f.read()
                if raw.startswith("---"):
                    parts = raw.split("---", 2)
                    return parts[2].strip() if len(parts) >= 3 else raw.strip()
                return raw.strip()
            except Exception as e:
                logging.debug(str(e), exc_info=True)
    return ""


_DEFAULTS = {
    "secure-reviewer": SubagentConfig(
        name="secure-reviewer",
        description="安全审计专家，只读审查，不能修改任何文件",
        allowed_tools=["Read", "Grep", "Glob"],
        denied_tools=["Write", "Edit", "Bash"],
        system_prompt=_load_subagent_prompt("secure-reviewer"),
    ),
    "debugger": SubagentConfig(
        name="debugger",
        description="代码调试专家，可修改但不能创建新文件",
        allowed_tools=["Read", "Edit"],
        system_prompt=_load_subagent_prompt("debugger"),
    ),
    "test-engineer": SubagentConfig(
        name="test-engineer",
        description="测试工程师，可创建文件",
        allowed_tools=["Read", "Write", "Bash"],
        system_prompt=_load_subagent_prompt("test-engineer"),
    ),
    "documentation-writer": SubagentConfig(
        name="documentation-writer",
        description="文档编写专家",
        allowed_tools=["Read", "Write"],
        system_prompt=_load_subagent_prompt("documentation-writer"),
    ),
    "performance-analyzer": SubagentConfig(
        name="performance-analyzer",
        description="性能分析专家",
        allowed_tools=["Read", "Grep"],
        system_prompt=_load_subagent_prompt("performance-analyzer"),
    )
}

# Apply env-var overrides to system prompts
_overrides_raw = _os.getenv("AIPLAT_SUBAGENT_PROMPTS", "")
if _overrides_raw:
    try:
        _overrides = _json.loads(_overrides_raw)
        for name, prompt in _overrides.items():
            if name in _DEFAULTS:
                _DEFAULTS[name].system_prompt = prompt
    except (_json.JSONDecodeError, KeyError) as e:
        logging.debug(str(e), exc_info=True)

BUILTIN_SUBAGENTS = _DEFAULTS


__all__ = [
    "ToolPermissionLevel",
    "SubagentConfig",
    "SubagentInstance",
    "BUILTIN_SUBAGENTS"
]