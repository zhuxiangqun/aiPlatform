"""
Skill Types Module

Provides type definitions for Skill system enhancements.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SkillCategory(Enum):
    """Skill Category - 9 类分类 (Anthropic)"""
    CODE_REVIEW = "code_review"
    CI_CD = "ci_cd"
    DATA_ANALYSIS = "data_analysis"
    DOCUMENTATION = "documentation"
    RUNBOOK = "runbook"
    TESTING = "testing"
    FRONTEND = "frontend"
    API_DESIGN = "api_design"
    GENERAL = "general"
    
    @classmethod
    def from_string(cls, value: str) -> "SkillCategory":
        """从字符串转换"""
        try:
            return cls(value)
        except ValueError:
            return cls.GENERAL
    
    @classmethod
    def all_categories(cls) -> List[str]:
        """获取所有分类名称"""
        return [c.value for c in cls]


class ExecutionMode(Enum):
    """Skill 执行模式"""
    INLINE = "inline"
    FORK = "fork"
    
    @classmethod
    def from_string(cls, value: str) -> "ExecutionMode":
        try:
            return cls(value)
        except ValueError:
            return cls.INLINE


@dataclass
class SkillManifest:
    """OpenClaw 兼容的 Skill 清单"""
    name: str
    description: str
    trigger_keywords: List[str] = field(default_factory=list)
    category: str = "general"
    version: str = "1.0.0"
    author: str = ""
    execution_mode: str = "inline"
    capabilities: List[str] = field(default_factory=list)
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    requirements: List[Dict[str, str]] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    scripts: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "trigger_keywords": self.trigger_keywords,
            "category": self.category,
            "version": self.version,
            "author": self.author,
            "execution_mode": self.execution_mode,
            "capabilities": self.capabilities,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


@dataclass
class SandboxConfig:
    """沙箱配置"""
    allowed_extensions: List[str] = field(default_factory=lambda: [".sh", ".py", ".js"])
    max_execution_time: float = 30.0
    max_memory_mb: int = 512
    allowed_env_vars: List[str] = field(default_factory=lambda: ["PATH", "HOME", "USER"])
    blocked_commands: List[str] = field(
        default_factory=lambda: [
            "rm -rf /",
            "sudo",
            "kill -9",
            "curl | sh",
            "wget | sh",
            "chmod 777",
        ]
    )
    
    @classmethod
    def get_default(cls) -> "SandboxConfig":
        return cls()


@dataclass
class ScriptResult:
    """脚本执行结果"""
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time: float = 0.0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "execution_time": self.execution_time,
            "error": self.error,
        }


__all__ = [
    "SkillCategory",
    "ExecutionMode",
    "SkillManifest",
    "SandboxConfig",
    "ScriptResult",
]