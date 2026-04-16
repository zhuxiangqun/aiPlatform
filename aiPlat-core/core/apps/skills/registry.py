"""
Skill Registry Module

Provides enhanced SkillRegistry with version management, enable/disable,
and binding statistics.
"""

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime

from .base import BaseSkill, SkillMetadata, TextGenerationSkill, CodeGenerationSkill, DataAnalysisSkill, create_skill
from ...harness.interfaces import SkillConfig


@dataclass
class SkillVersion:
    version: str
    config: SkillConfig
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    is_active: bool = True


@dataclass
class SkillBindingStats:
    skill_id: str
    bound_agents: List[str] = field(default_factory=list)
    total_executions: int = 0
    success_count: int = 0
    error_count: int = 0
    avg_latency: float = 0.0


class SkillRegistry:
    """
    Enhanced Skill Registry

    Manages skill registration, versioning, enable/disable,
    and agent binding statistics.
    """

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}
        self._categories: Dict[str, List[str]] = {}
        self._versions: Dict[str, List[SkillVersion]] = {}
        self._enabled: Dict[str, bool] = {}
        self._binding_stats: Dict[str, SkillBindingStats] = {}
        self._stats_override: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def seed_data(self, data: Dict[str, Dict[str, Any]] = None) -> None:
        """Seed the registry with built-in skill instances.
        
        Creates real BaseSkill subclass instances for skills that have them,
        and GenericSkill instances for skills that don't.
        """
        builtin_skills = [
            ("text_generation", "文本生成", "generation", "根据提示生成各类文本内容", True),
            ("code_generation", "代码生成", "generation", "根据需求描述生成代码", False),
            ("data_analysis", "数据分析", "analysis", "分析数据并提供洞察", True),
        ]
        
        generic_skills = [
            ("task_planning", "任务规划", "execution", "根据目标拆解为可执行的子任务步骤", True),
            ("information_search", "信息检索", "retrieval", "从知识库和互联网中检索相关信息", True),
            ("knowledge_retrieval", "知识召回", "retrieval", "从向量数据库中召回相关文档片段", True),
            ("summarization", "内容摘要", "transformation", "将长文本压缩为简洁的摘要", True),
            ("task_decomposition", "任务分解", "analysis", "将复杂任务分解为简单子任务", True),
            ("api_calling", "API调用", "execution", "调用外部API接口获取数据", True),
            ("chitchat", "闲聊", "generation", "处理日常闲聊和简单问答", True),
            ("code_review", "代码审查", "analysis", "审查代码质量并给出改进建议", True),
            ("translation", "多语言翻译", "transformation", "在多语言之间进行翻译", True),
        ]
        
        _skill_type_map = {
            "text_generation": TextGenerationSkill,
            "code_generation": CodeGenerationSkill,
            "data_analysis": DataAnalysisSkill,
        }
        
        with self._lock:
            for name, display_name, category, description, enabled in builtin_skills:
                skill_cls = _skill_type_map.get(name)
                if skill_cls:
                    skill = skill_cls()
                    self.register(skill)
                    if not enabled:
                        self.disable(name)
            
            for name, display_name, category, description, enabled in generic_skills:
                config = SkillConfig(
                    name=name,
                    description=description,
                    metadata={"category": category, "version": "1.0.0"}
                )
                skill = _GenericSkill(config)
                self.register(skill)
                if not enabled:
                    self.disable(name)

    def register(self, skill: BaseSkill) -> None:
        """Register a skill"""
        with self._lock:
            name = skill.get_config().name
            category = self._get_category(skill)
            self._skills[name] = skill
            if category not in self._categories:
                self._categories[category] = []
            if name not in self._categories[category]:
                self._categories[category].append(name)
            version = skill.get_config().metadata.get("version", "1.0.0")
            self._add_version(name, version, skill.get_config())
            self._enabled[name] = True
            self._binding_stats[name] = SkillBindingStats(skill_id=name)

    def get(self, name: str) -> Optional[BaseSkill]:
        """Get skill by name"""
        return self._skills.get(name)

    def get_version(self, name: str, version: str) -> Optional[SkillConfig]:
        """Get a specific version of a skill's config"""
        versions = self._versions.get(name, [])
        for v in versions:
            if v.version == version:
                return v.config
        return None

    def get_versions(self, name: str) -> List[SkillVersion]:
        """Get all versions of a skill"""
        return self._versions.get(name, [])

    def get_active_version(self, name: str) -> Optional[str]:
        """Get currently active version for a skill."""
        versions = self._versions.get(name, [])
        for v in versions:
            if v.is_active:
                return v.version
        return versions[-1].version if versions else None

    def rollback_version(self, name: str, version: str) -> bool:
        """Rollback skill to a specific version"""
        with self._lock:
            versions = self._versions.get(name, [])
            target = None
            for v in versions:
                if v.version == version:
                    target = v
                    break
            if target is None:
                return False
            for v in versions:
                v.is_active = (v.version == version)
            skill = self._skills.get(name)
            if skill:
                # Apply target config to the skill instance so rollback affects subsequent execution.
                try:
                    setattr(skill, "_config", target.config)
                except Exception:
                    pass
                self._skills[name] = skill
            return True

    def _add_version(self, name: str, version: str, config: SkillConfig) -> None:
        """Add a version entry"""
        if name not in self._versions:
            self._versions[name] = []
        sv = SkillVersion(version=version, config=config)
        self._versions[name].append(sv)

    def _get_category(self, skill: BaseSkill) -> str:
        """Extract category from skill config"""
        config = skill.get_config()
        return config.metadata.get("category", "general") if hasattr(config, 'metadata') else "general"

    def list_skills(self, category: Optional[str] = None, enabled_only: bool = False) -> List[str]:
        """List skills, optionally filtered by category and enabled status"""
        with self._lock:
            if category:
                names = self._categories.get(category, [])
            else:
                names = list(self._skills.keys())
            if enabled_only:
                names = [n for n in names if self._enabled.get(n, True)]
            return names

    def unregister(self, name: str) -> None:
        """Unregister a skill"""
        with self._lock:
            if name in self._skills:
                skill = self._skills[name]
                category = self._get_category(skill)
                if category in self._categories and name in self._categories[category]:
                    self._categories[category].remove(name)
                del self._skills[name]
            self._versions.pop(name, None)
            self._enabled.pop(name, None)
            self._binding_stats.pop(name, None)

    def enable(self, name: str) -> bool:
        """Enable a skill"""
        with self._lock:
            if name in self._skills:
                self._enabled[name] = True
                return True
            return False

    def disable(self, name: str) -> bool:
        """Disable a skill"""
        with self._lock:
            if name in self._skills:
                self._enabled[name] = False
                return True
            return False

    def is_enabled(self, name: str) -> bool:
        """Check if a skill is enabled"""
        return self._enabled.get(name, False)

    def bind_agent(self, skill_name: str, agent_id: str) -> None:
        """Bind a skill to an agent"""
        with self._lock:
            if skill_name in self._binding_stats:
                stats = self._binding_stats[skill_name]
                if agent_id not in stats.bound_agents:
                    stats.bound_agents.append(agent_id)

    def unbind_agent(self, skill_name: str, agent_id: str) -> None:
        """Unbind a skill from an agent"""
        with self._lock:
            if skill_name in self._binding_stats:
                stats = self._binding_stats[skill_name]
                if agent_id in stats.bound_agents:
                    stats.bound_agents.remove(agent_id)

    def get_binding_stats(self, name: str) -> Optional[SkillBindingStats]:
        """Get binding statistics for a skill"""
        return self._binding_stats.get(name)

    def get_bound_agents(self, name: str) -> List[str]:
        """Get agents bound to a skill"""
        stats = self._binding_stats.get(name)
        return stats.bound_agents if stats else []

    def record_execution(self, name: str, success: bool, latency: float = 0.0) -> None:
        """Record a skill execution"""
        with self._lock:
            if name in self._binding_stats:
                stats = self._binding_stats[name]
                stats.total_executions += 1
                if success:
                    stats.success_count += 1
                else:
                    stats.error_count += 1
                if latency > 0:
                    prev_avg = stats.avg_latency
                    count = stats.success_count + stats.error_count
                    stats.avg_latency = (prev_avg * (count - 1) + latency) / count

    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all skills"""
        if self._stats_override:
            return self._stats_override
        result = {}
        for name, skill in self._skills.items():
            stats = self._binding_stats.get(name)
            result[name] = {
                "enabled": self._enabled.get(name, True),
                "category": self._get_category(skill),
                "bound_agents": len(stats.bound_agents) if stats else 0,
                "total_executions": stats.total_executions if stats else 0,
                "success_count": stats.success_count if stats else 0,
                "error_count": stats.error_count if stats else 0,
                "avg_latency": stats.avg_latency if stats else 0.0,
                "versions": [v.version for v in self._versions.get(name, [])],
            }
        return result


class _GenericSkill(BaseSkill):
    """Generic skill for skills without a dedicated subclass.
    
    Represents skills that need an LLM adapter to execute but don't 
    have specialized logic. Uses a prompt template derived from the
    skill's description and category.
    """
    
    def __init__(self, config: SkillConfig):
        super().__init__(config)
        self._model = None
    
    def set_model(self, model):
        self._model = model
    
    async def execute(self, context, params):
        if not self._model:
            return SkillResult(
                success=False,
                error=f"No LLM adapter configured for skill '{self._config.name}'"
            )
        
        prompt = params.get("prompt", params.get("input", ""))
        if not prompt:
            prompt = f"Execute skill '{self._config.name}': {self._config.description}"
            if params:
                prompt += f"\nInput: {params}"
        
        try:
            from ...harness.syscalls.llm import sys_llm_generate

            response = await sys_llm_generate(self._model, [
                {"role": "system", "content": f"You are a {self._config.description}."},
                {"role": "user", "content": prompt},
            ])
            return SkillResult(
                success=True,
                output={"text": response.content},
                metadata={"model": response.model, "skill": self._config.name}
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))


# Global registry
_global_registry = SkillRegistry()


def get_skill_registry() -> SkillRegistry:
    """Get global skill registry"""
    return _global_registry
