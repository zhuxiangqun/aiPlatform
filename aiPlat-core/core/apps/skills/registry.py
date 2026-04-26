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
from .eval_trigger import SkillEvalTriggerSkill
from .eval_quality import SkillEvalQualitySkill
from .apply_engine_skill_md_patch import ApplyEngineSkillMdPatchSkill
from ...harness.interfaces import SkillConfig, SkillResult


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
            ("skill_eval_trigger", "技能触发评测", "ops", "对指定 Skill 进行触发评测（正负例）并产出指标", True),
            ("skill_eval_quality", "技能质量评测", "ops", "对指定 Skill 执行质量做评测（用例+规则评分）并产出指标", True),
            ("skill_apply_engine_skill_md_patch", "应用 Engine Skill 补丁", "ops", "应用 engine skill 的 SKILL.md 补丁（change-control 治理）", True),
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
            "skill_eval_trigger": SkillEvalTriggerSkill,
            "skill_eval_quality": SkillEvalQualitySkill,
            "skill_apply_engine_skill_md_patch": ApplyEngineSkillMdPatchSkill,
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
            cfg = skill.get_config()
            name = cfg.name
            # P0-1: normalize governance contract fields and attach a stable digest.
            try:
                from core.apps.skills.contract import build_contract_and_digest

                meta = dict(getattr(cfg, "metadata", {}) or {})
                kind = str(meta.get("skill_kind") or meta.get("kind") or "rule")
                version = str(meta.get("version") or "1.0.0")
                contract, digest = build_contract_and_digest(
                    name=name,
                    version=version,
                    kind=kind,
                    input_schema=getattr(cfg, "input_schema", {}) or {},
                    output_schema=getattr(cfg, "output_schema", {}) or {},
                    metadata=meta,
                )
                # Keep contract fields both in metadata (for legacy access) and as a digest.
                meta["permissions"] = contract.get("permissions") or []
                meta["risk_level"] = contract.get("risk_level") or "low"
                meta["auto_trigger_allowed"] = bool(contract.get("auto_trigger_allowed"))
                meta["requires_approval"] = bool(contract.get("requires_approval"))
                meta["contract_digest"] = digest
                setattr(cfg, "metadata", meta)
            except Exception:
                pass
            category = self._get_category(skill)
            self._skills[name] = skill
            if category not in self._categories:
                self._categories[category] = []
            if name not in self._categories[category]:
                self._categories[category].append(name)
            version = cfg.metadata.get("version", "1.0.0")
            self._add_version(name, version, cfg)
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

        def _extract_json(text: str):
            import json
            import re

            if not isinstance(text, str):
                return None
            s = text.strip()
            # strip ```json ... ```
            m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s, re.IGNORECASE)
            if m:
                s = m.group(1).strip()
            # direct parse
            try:
                obj = json.loads(s)
                return obj
            except Exception:
                pass
            # find first {...} block (best-effort)
            i = s.find("{")
            j = s.rfind("}")
            if i >= 0 and j > i:
                try:
                    return json.loads(s[i : j + 1])
                except Exception:
                    return None
            return None

        prompt = params.get("prompt", params.get("input", ""))
        if not prompt:
            # Prefer schema-driven prompt: feed the full params as JSON so SOP can reference fields.
            prompt = f"Execute skill '{self._config.name}': {self._config.description}\nInput(JSON): {params}"

        # Organization-level coding policy profile (Phase-1).
        coding_profile = str((params or {}).get("_coding_policy_profile") or "").strip().lower()
        policy_block = ""
        if coding_profile == "karpathy_v1":
            policy_block = (
                "编码行为规范（karpathy_v1，必须遵循）：\n"
                "1) 编码前思考：不要做未证实假设；遇到歧义/缺参，先在输出中列出需要确认的问题与可选方案。\n"
                "2) 简洁优先：坚持最小可行实现；不要引入未经请求的抽象/架构/额外功能。\n"
                "3) 精准修改：像外科手术一样，只改必须改的地方；避免无关格式化/无关文件改动。\n"
                "4) 目标驱动：把任务转成可验证目标；在输出中给出验收标准（测试/复现步骤/检查清单）。\n"
            )
        
        try:
            sop = ""
            try:
                sop = (self._config.metadata or {}).get("sop_markdown", "") if hasattr(self._config, "metadata") else ""
            except Exception:
                sop = ""

            allowed_tools = []
            try:
                # Prefer runtime context.tools, fallback to config metadata.tools.
                if context and getattr(context, "tools", None):
                    allowed_tools = list(getattr(context, "tools") or [])
                else:
                    allowed_tools = list((self._config.metadata or {}).get("tools", []) if hasattr(self._config, "metadata") else [])
                allowed_tools = [str(t) for t in allowed_tools if str(t).strip()]
            except Exception:
                allowed_tools = []

            system_parts = [
                "你是一个可复用技能（Skill）执行器。",
                f"技能名称：{self._config.name}",
                f"技能描述：{self._config.description}",
            ]
            if policy_block:
                system_parts.append(policy_block)
            if sop:
                system_parts.append("下面是该技能的SOP（必须严格遵循）：")
                system_parts.append(sop)

            # If output_schema exists, require strict JSON output with those top-level keys.
            out_schema = {}
            try:
                out_schema = self._config.output_schema or {}
            except Exception:
                out_schema = {}
            if isinstance(out_schema, dict) and out_schema:
                keys = list(out_schema.keys())
                system_parts.append("输出要求：你必须返回严格 JSON（不要输出任何额外文本/解释/代码块外内容）。")
                system_parts.append(f"JSON 顶层字段必须包含：{keys}")
                system_parts.append("如果某字段无法给出，请给出空值（空数组/空对象/空字符串），但不要遗漏字段。")

            # If tools are available, run as a tool-capable ReAct agent (SkillTool-like orchestration).
            if allowed_tools:
                from ...apps.agents.react import create_react_agent
                from ...harness.interfaces import AgentConfig, AgentContext

                agent = create_react_agent(
                    config=AgentConfig(
                        name=f"skill-inline-{self._config.name}",
                        model=str(getattr(self._model, "model", None) or "gpt-4"),
                        metadata={"role": "skill-agent", "skill": self._config.name},
                    ),
                    model=self._model,
                )

                task = "\n".join(system_parts) + "\n\n用户输入：\n" + prompt
                msgs = [{"role": "system", "content": "\n".join(system_parts)}, {"role": "user", "content": prompt}]
                agent_ctx = AgentContext(
                    session_id=getattr(context, "session_id", "skill"),
                    user_id=getattr(context, "user_id", "system"),
                    messages=[{"role": "user", "content": task}],
                    variables={"messages": msgs, **(getattr(context, "variables", {}) or {})},
                    tools=allowed_tools,
                )
                result = await agent.execute(agent_ctx)
                if isinstance(out_schema, dict) and out_schema:
                    parsed = _extract_json(str(result.output or ""))
                    if isinstance(parsed, dict):
                        return SkillResult(
                            success=bool(result.success),
                            output=parsed,
                            error=result.error,
                            metadata={"skill": self._config.name, "agent": result.metadata, "tools": allowed_tools, "parsed_json": True},
                        )
                    return SkillResult(
                        success=False,
                        output={"raw": result.output},
                        error="json_parse_failed",
                        metadata={"skill": self._config.name, "agent": result.metadata, "tools": allowed_tools},
                    )
                return SkillResult(success=bool(result.success), output={"text": result.output}, error=result.error, metadata={"skill": self._config.name, "agent": result.metadata, "tools": allowed_tools})

            # Fallback: plain LLM generation (no tools)
            from ...harness.syscalls.llm import sys_llm_generate

            response = await sys_llm_generate(
                self._model,
                [
                    {"role": "system", "content": "\n".join(system_parts)},
                    {"role": "user", "content": prompt},
                ],
            )
            if isinstance(out_schema, dict) and out_schema:
                parsed = _extract_json(str(getattr(response, "content", "") or ""))
                if isinstance(parsed, dict):
                    return SkillResult(success=True, output=parsed, metadata={"model": getattr(response, "model", None), "skill": self._config.name, "parsed_json": True})
                return SkillResult(success=False, output={"raw": getattr(response, "content", None)}, error="json_parse_failed", metadata={"model": getattr(response, "model", None), "skill": self._config.name})
            return SkillResult(success=True, output={"text": response.content}, metadata={"model": response.model, "skill": self._config.name})
        except Exception as e:
            return SkillResult(success=False, error=str(e))


# Global registry
_global_registry = SkillRegistry()


def get_skill_registry() -> SkillRegistry:
    """Get global skill registry"""
    return _global_registry
