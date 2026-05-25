"""
SkillWorkflowRunner — execute multi-step skill pipelines declared in SKILL.md frontmatter.

A Skill with `steps:` in its frontmatter is a composite skill that chains other skills
in sequence, piping outputs between them.

DSL Format (YAML frontmatter):
  steps:
    - "skill_name":                         # step 0
        params:                               # optional input overrides
          key: "value"
    - "another_skill":                       # step 1
        params: {}
        timeout: 90

Execution:
  WorkflowRunner.execute_workflow(config, initial_params)
    → For each step: SkillExecutor.execute(skill_name, merged_params)
    → Step output merges into shared context
    → Final result = last step's output

Usage from SKILL.md:
  steps: [skill_a, skill_b]   → executes skill_a then skill_b
"""

from __future__ import annotations

import asyncio
import copy
from typing import Any, Dict, List, Optional

from core.harness.interfaces.skill import SkillContext, SkillResult


class SkillWorkflowRunner:
    def __init__(self):
        self._context_cache: Dict[str, SkillResult] = {}

    async def execute_workflow(
        self,
        steps: List[Dict[str, Any]],
        initial_params: Dict[str, Any],
        context: Optional[SkillContext] = None,
        timeout: Optional[float] = None,
    ) -> SkillResult:
        """Execute a sequence of skills, piping outputs."""
        workflow_input = copy.deepcopy(initial_params or {})
        last_result: Optional[SkillResult] = None
        session_id = context.session_id if context else "workflow"

        for i, step in enumerate(steps):
            step_name, step_config = self._parse_step(step)
            step_params = copy.deepcopy(workflow_input)
            if isinstance(step_config, dict):
                step_params.update(step_config.get("params", {}))
                step_timeout = step_config.get("timeout", timeout)
            else:
                step_timeout = timeout

            try:
                from .executor import SkillExecutor
                executor = SkillExecutor()
                result = await executor.execute(
                    skill_name=step_name,
                    params=step_params,
                    context=context or SkillContext(session_id=session_id, user_id="system"),
                    timeout=step_timeout,
                )
            except Exception as e:
                return SkillResult(
                    success=False,
                    error=f"Step {i} '{step_name}': SkillExecutor error: {e}",
                )
                self._context_cache[f"step_{i}"] = result
                if result.success and isinstance(result.output, dict):
                    workflow_input.update(result.output)
                last_result = result

                if not result.success:
                    return SkillResult(
                        success=False,
                        error=f"Step {i} '{step_name}' failed: {result.error}",
                        metadata={"failed_step": i, "failed_skill": step_name, "inner_error": result.error},
                    )
            except asyncio.TimeoutError:
                return SkillResult(
                    success=False,
                    error=f"Step {i} '{step_name}' timed out",
                    metadata={"failed_step": i, "failed_skill": step_name},
                )

        return last_result or SkillResult(success=True, output=workflow_input)

    @staticmethod
    def _parse_step(step: Any) -> tuple:
        if isinstance(step, str):
            return step, {}
        if isinstance(step, dict):
            for name, config in step.items():
                return name, config
        raise ValueError(f"Invalid step format: {step}")

    @staticmethod
    def has_workflow(frontmatter: Dict[str, Any]) -> bool:
        """Check if a SKILL.md frontmatter declares a workflow."""
        steps = frontmatter.get("steps")
        return isinstance(steps, list) and len(steps) > 0


def get_workflow_runner() -> SkillWorkflowRunner:
    return SkillWorkflowRunner()
