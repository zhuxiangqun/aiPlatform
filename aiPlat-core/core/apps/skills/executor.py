"""
Skill Executor Module

Provides SkillExecutor for executing skills with context management,
timeout control, and execution tracking.
"""

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import BaseSkill
from .registry import get_skill_registry, SkillRegistry
from ...harness.interfaces import SkillContext, SkillResult
from ...apps.tools.base import get_tool_registry
from ...harness.syscalls import sys_skill_call
from core.utils.ids import new_prefixed_id


@dataclass
class ExecutionRecord:
    execution_id: str
    skill_name: str
    status: str  # pending, running, success, failed, timeout
    input_params: Dict[str, Any]
    output: Any = None
    error: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 0.0
    latency: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class SkillExecutor:
    """
    Skill Executor

    Executes skills with timeout control, execution tracking,
    and context management.
    """

    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        default_timeout: float = 60.0,
        discovery=None
    ):
        self._registry = registry or get_skill_registry()
        self._default_timeout = default_timeout
        self._executions: Dict[str, ExecutionRecord] = {}
        self._discovery = discovery

    async def execute(
        self,
        skill_name: str,
        params: Dict[str, Any],
        context: Optional[SkillContext] = None,
        timeout: Optional[float] = None,
        mode: str = "inline"
    ) -> SkillResult:
        """Execute a skill by name
        
        Args:
            skill_name: Name of the skill to execute
            params: Parameters for the skill
            context: Execution context
            timeout: Execution timeout in seconds
            mode: Execution mode - "inline" or "fork"
        """
        if mode == "fork":
            return await self._execute_fork(skill_name, params, context, timeout)
        else:
            return await self._execute_inline(skill_name, params, context, timeout)
    
    async def _execute_inline(
        self,
        skill_name: str,
        params: Dict[str, Any],
        context: Optional[SkillContext],
        timeout: Optional[float]
    ) -> SkillResult:
        """Inline execution - run in current context"""
        skill = self._registry.get(skill_name)
        if skill is None:
            return SkillResult(
                success=False,
                error=f"Skill not found: {skill_name}"
            )

        if not self._registry.is_enabled(skill_name):
            return SkillResult(
                success=False,
                error=f"Skill is disabled: {skill_name}"
            )

        execution_id = new_prefixed_id("run")
        record = ExecutionRecord(
            execution_id=execution_id,
            skill_name=skill_name,
            status="running",
            input_params=params,
            start_time=time.time()
        )
        self._executions[execution_id] = record

        if context is None:
            context = SkillContext(
                session_id=execution_id,
                user_id="system"
            )

        skill_info = self._registry.get(skill_name)
        if skill_info and hasattr(skill_info, '_config') and hasattr(skill_info._config, 'metadata'):
            tool_names = skill_info._config.metadata.get('tools', [])
            if tool_names:
                context.tools = list(tool_names)

        effective_timeout = timeout or self._default_timeout

        try:
            is_valid = await skill.validate(params)
            if not is_valid:
                record.status = "failed"
                record.end_time = time.time()
                record.error = "Parameter validation failed"
                record.latency = record.end_time - record.start_time
                self._registry.record_execution(skill_name, success=False, latency=record.latency)
                return SkillResult(success=False, error="Parameter validation failed")

            result = await asyncio.wait_for(
                sys_skill_call(
                    skill,
                    params,
                    context=context,
                    user_id=context.user_id,
                    session_id=context.session_id,
                ),
                timeout=effective_timeout
            )

            record.status = "success" if result.success else "failed"
            record.end_time = time.time()
            record.latency = record.end_time - record.start_time
            record.output = result.output if result.success else None
            record.error = result.error
            self._registry.record_execution(
                skill_name,
                success=result.success,
                latency=record.latency
            )
            return result

        except asyncio.TimeoutError:
            record.status = "timeout"
            record.end_time = time.time()
            record.latency = record.end_time - record.start_time
            record.error = f"Skill execution timed out after {effective_timeout}s"
            self._registry.record_execution(skill_name, success=False, latency=record.latency)
            return SkillResult(
                success=False,
                error=f"Skill execution timed out after {effective_timeout}s"
            )

        except Exception as e:
            record.status = "failed"
            record.end_time = time.time()
            record.latency = record.end_time - record.start_time
            record.error = str(e)
            self._registry.record_execution(skill_name, success=False, latency=record.latency)
            return SkillResult(success=False, error=str(e))
    
    async def _execute_fork(
        self,
        skill_name: str,
        params: Dict[str, Any],
        context: Optional[SkillContext],
        timeout: Optional[float]
    ) -> SkillResult:
        """Fork execution - spawn sub-agent for parallel execution."""
        skill = self._registry.get(skill_name)
        if not skill:
            return SkillResult(success=False, error=f"Skill not found: {skill_name}")

        effective_timeout = timeout or self._default_timeout

        async def run_in_fork():
            try:
                config = skill.get_config()
                prompt = params.get("prompt", params.get("input", ""))
                if not prompt:
                    prompt = f"Execute skill '{config.name}': {config.description}"
                    if params:
                        prompt += f"\nInput: {params}"

                from core.adapters.llm import create_adapter
                from core.apps.agents.conversational import create_conversational_agent
                from core.harness.interfaces import AgentConfig, AgentContext

                # Prefer skill-injected model if available; otherwise create from environment.
                model = getattr(skill, "_model", None)
                provider = params.get("provider") or os.getenv("LLM_PROVIDER") or "openai"
                model_name = params.get("model") or os.getenv("LLM_MODEL") or "gpt-4"
                api_key = None
                if provider == "openai":
                    api_key = os.getenv("OPENAI_API_KEY")
                elif provider == "anthropic":
                    api_key = os.getenv("ANTHROPIC_API_KEY")

                if model is None:
                    try:
                        model = create_adapter(provider=provider, api_key=api_key, model=model_name)
                    except Exception:
                        model = None

                if model is None:
                    return type(
                        "Result",
                        (),
                        {
                            "success": False,
                            "output": None,
                            "error": "Fork mode requires a configured LLM adapter (set LLM_PROVIDER/LLM_MODEL and provider API key env).",
                        },
                    )()

                sop_text = ""
                try:
                    meta = getattr(config, "metadata", None) or {}
                    if isinstance(meta, dict):
                        sop_text = meta.get("sop_markdown", "") or ""
                except Exception:
                    sop_text = ""

                sop_block = f"技能SOP（必须遵循）：\n{sop_text}\n" if sop_text else ""

                system_prompt = (
                    "你是一个专用技能代理（fork mode）。\n"
                    f"技能名称：{getattr(config, 'name', skill_name)}\n"
                    f"技能描述：{getattr(config, 'description', '')}\n"
                    f"{sop_block}"
                    "你的任务：根据用户给定的参数与输入，严格执行该技能并输出结果。"
                )

                agent_config = AgentConfig(
                    name=f"fork-{skill_name}",
                    model=model_name,
                    metadata={"role": "fork-agent", "skill": skill_name},
                )
                # Use ReAct agent so fork mode can also orchestrate tools when provided.
                from core.apps.agents.react import create_react_agent
                agent = create_react_agent(config=agent_config, model=model)

                task = system_prompt + "\n\n用户输入：\n" + prompt
                agent_context = AgentContext(
                    session_id=context.session_id if context else "fork",
                    user_id=context.user_id if context else "system",
                    messages=[{"role": "user", "content": task}],
                    variables={"messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}], **(params or {})},
                    tools=list(getattr(context, "tools", []) or []) if context else [],
                )

                return await agent.execute(agent_context)

            except Exception as e:
                return type('Result', (), {'success': False, 'output': None, 'error': str(e)})()

        try:
            result = await asyncio.wait_for(run_in_fork(), timeout=effective_timeout)
            return SkillResult(
                success=result.success,
                output=result.output,
                error=result.error,
            )
        except asyncio.TimeoutError:
            return SkillResult(
                success=False,
                error=f"Fork execution timed out after {effective_timeout}s"
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def get_execution(self, execution_id: str) -> Optional[ExecutionRecord]:
        """Get execution record by ID"""
        return self._executions.get(execution_id)

    def list_executions(
        self,
        skill_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ExecutionRecord]:
        """List execution records"""
        records = list(self._executions.values())
        if skill_name:
            records = [r for r in records if r.skill_name == skill_name]
        records.sort(key=lambda r: r.start_time, reverse=True)
        return records[offset:offset + limit]

    def get_stats(self) -> Dict[str, Any]:
        """Get executor statistics"""
        total = len(self._executions)
        success = sum(1 for r in self._executions.values() if r.status == "success")
        failed = sum(1 for r in self._executions.values() if r.status == "failed")
        timeout = sum(1 for r in self._executions.values() if r.status == "timeout")
        return {
            "total_executions": total,
            "success_count": success,
            "failed_count": failed,
            "timeout_count": timeout,
            "success_rate": success / total if total > 0 else 0.0,
        }


# Global executor
_global_executor: Optional[SkillExecutor] = None


def get_skill_executor(discovery=None) -> SkillExecutor:
    """Get global skill executor
    
    Args:
        discovery: Optional SkillDiscovery instance for fork mode
    """
    global _global_executor
    if _global_executor is None:
        _global_executor = SkillExecutor(discovery=discovery)
    return _global_executor
