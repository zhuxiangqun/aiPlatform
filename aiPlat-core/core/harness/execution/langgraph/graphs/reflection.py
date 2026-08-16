"""
LangGraph Reflection Graph

Implements the Reflection pattern: Executor Agent generates, Critic Agent reviews.
Loop iterates until Critic approves or max iterations reached.

Based on framework/patterns.md §4 Reflection pattern.
"""

from typing import Any, Dict, List, Optional, TypedDict
from dataclasses import dataclass, field
from enum import Enum

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None
    END = None

from .react import ReActGraph, ReActGraphConfig
import os
from ....assembly import MessageFormatter


class EvaluationDimension(Enum):
    """Quality evaluation dimensions for Critic Agent."""
    FACTUALITY = "factuality"
    COMPLETENESS = "completeness"
    CLARITY = "clarity"
    FORMAT = "format"


class ReflectionStatus(Enum):
    """Reflection iteration status."""
    PENDING = "pending"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    FAILED = "failed"


@dataclass
class CriticResult:
    """
    Critic Agent evaluation result.
    
    Attributes:
        passed: Whether the output passed all criteria
        dimensions: Scores per evaluation dimension (0-1)
        feedback: Improvement suggestions
        summary: Overall assessment
    """
    passed: bool = False
    dimensions: Dict[EvaluationDimension, float] = field(default_factory=dict)
    feedback: List[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class ReflectionConfig:
    """Reflection pattern configuration.
    
    Attributes:
        executor_model: Model for Executor Agent
        critic_model: Model for Critic Agent
        max_iterations: Maximum reflection iterations
        tools: Tools available to executor
        pass_keyword: Keyword indicating approval (default: "PASS")
        evaluation_dimensions: Dimensions to evaluate
        dimension_thresholds: Minimum score per dimension (default: 0.8)
    """
    executor_model: Optional[Any] = None
    critic_model: Optional[Any] = None
    max_iterations: int = 3
    tools: List[Any] = field(default_factory=list)
    pass_keyword: str = "PASS"
    evaluation_dimensions: List[EvaluationDimension] = field(default_factory=lambda: [
        EvaluationDimension.FACTUALITY,
        EvaluationDimension.COMPLETENESS,
        EvaluationDimension.CLARITY,
        EvaluationDimension.FORMAT,
    ])
    dimension_thresholds: Dict[EvaluationDimension, float] = field(default_factory=lambda: {
        EvaluationDimension.FACTUALITY: 0.8,
        EvaluationDimension.COMPLETENESS: 0.7,
        EvaluationDimension.CLARITY: 0.7,
        EvaluationDimension.FORMAT: 0.8,
    })


class ReflectionState(TypedDict, total=False):
    """Reflection pattern state.
    
    Attributes:
        task: Original task description
        executor_output: Current output from Executor
        critic_result: Latest evaluation from Critic
        iteration: Current iteration count
        status: Current reflection status
        history: History of all iterations
        final_output: Final approved output
        context: Additional context
    """
    task: str
    executor_output: str
    critic_result: Optional[CriticResult]
    iteration: int
    status: ReflectionStatus
    history: List[Dict[str, Any]]
    final_output: Any
    context: Dict[str, Any]


class ReflectionGraph:
    """
    Reflection Graph Implementation
    
    Two agents collaborate to improve output quality:
    - Executor Agent: Generates or improves the output
    - Critic Agent: Evaluates output quality and provides feedback
    
    The loop continues:
    - Executor generates output
    - Critic evaluates against criteria
    - If approved: return output
    - If not approved: feed feedback back to Executor
    - Repeat until approved or max iterations
    """

    def __init__(self, config: Optional[ReflectionConfig] = None):
        self._config = config or ReflectionConfig()
        self._graph = None
        self._executor = None
        self._critic = None
        
        self._create_agents()
        
        if LANGGRAPH_AVAILABLE:
            self._build_graph()

    def _create_agents(self) -> None:
        """Create Executor and Critic agents."""
        executor_config = ReActGraphConfig(
            max_steps=10,
            model=self._config.executor_model,
            tools=self._config.tools
        )
        self._executor = ReActGraph(executor_config)
        
        critic_config = ReActGraphConfig(
            max_steps=3,
            model=self._config.critic_model,
            tools=[]
        )
        self._critic = ReActGraph(critic_config)

    def _build_graph(self) -> None:
        """Build LangGraph for reflection pattern."""
        if not LANGGRAPH_AVAILABLE:
            return
        
        workflow = StateGraph(ReflectionState)
        
        workflow.add_node("execute", self._executor_wrapper)
        workflow.add_node("review", self._critic_wrapper)
        
        workflow.set_entry_point("execute")
        workflow.add_edge("execute", "review")
        workflow.add_conditional_edges(
            "review",
            self._should_continue,
            {
                "continue": "execute",
                "finish": END
            }
        )
        
        self._graph = workflow.compile()

    def _build_critic_prompt(self, task: str, output: str, feedback: List[str]) -> str:
        """Build the critic prompt based on configuration."""
        import os, json

        default_descriptions = {
            "FACTUALITY": "事实准确性",
            "COMPLETENESS": "逻辑完整性",
            "CLARITY": "表达清晰度",
            "FORMAT": "格式规范性",
        }
        env_descs = os.getenv("AIPLAT_EVAL_DIMENSION_LABELS", "")
        if env_descs:
            try:
                default_descriptions.update(json.loads(env_descs))
            except json.JSONDecodeError:
                pass  # noqa: cleanup-best-effort

        dimension_descriptions = {
            EvaluationDimension.FACTUALITY: default_descriptions.get("FACTUALITY", "factuality"),
            EvaluationDimension.COMPLETENESS: default_descriptions.get("COMPLETENESS", "completeness"),
            EvaluationDimension.CLARITY: default_descriptions.get("CLARITY", "clarity"),
            EvaluationDimension.FORMAT: default_descriptions.get("FORMAT", "format"),
        }

        dimension_lines = "\n".join(
            f"- {dimension_descriptions.get(d, d.value)}"
            for d in self._config.evaluation_dimensions
        )

        previous_feedback = ""
        if feedback:
            previous_feedback = f"\nPrevious improvement suggestions:\n" + "\n".join(f"- {f}" for f in feedback)

        dim_names = [d.value for d in self._config.evaluation_dimensions]
        import os as _os
        prompt_template = _os.getenv("AIPLAT_EVAL_CRITIC_TEMPLATE")
        if not prompt_template:
            from core.harness.utils.prompt_loader import _sync_resolve
            prompt_template = _sync_resolve("reflection-critic",
                output=output, dimensions=dimension_lines,
            )
            return prompt_template  # Already resolved with variables

        prompt = prompt_template.format(
            dimensions=dimension_lines,
            previous=previous_feedback,
            task=task,
            output=output,
        )
        return prompt

    def _build_executor_prompt(self, task: str, previous_output: str, feedback: List[str]) -> str:
        """Build the executor prompt for improvement iteration."""
        if not feedback:
            return f"Task: {task}\n\nPlease provide a complete and accurate answer."
        
        feedback_text = "\n".join(f"- {f}" for f in feedback)
        
        from core.harness.utils.prompt_loader import _sync_resolve
        return _sync_resolve("reflection-improve",
            previous_output=previous_output, feedback=feedback_text, task=task,
        )

    async def _executor_wrapper(self, state: ReflectionState) -> Dict[str, Any]:
        """Executor wrapper - generates or improves output."""
        from core.harness.utils.prompt_loader import _sync_resolve
        if state.iteration == 0:
            prompt = _sync_resolve("reflection-executor", task=state.task)
            state.status = ReflectionStatus.EXECUTING
        else:
            feedback = state.critic_result.feedback if state.critic_result else []
            prompt = self._build_executor_prompt(
                state.task,
                state.executor_output,
                feedback
            )
        
        messages = (
            MessageFormatter().assemble(prompt).messages
            if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "true").lower() in ("1", "true", "yes", "y")
            else [{"role": "user", "content": prompt}]
        )
        result = await self._executor.run({"messages": messages, "context": state.context})
        
        executor_output = result.observation if hasattr(result, 'observation') else ""
        
        history_entry = {
            "iteration": state.iteration,
            "phase": "executor",
            "output": executor_output[:500]
        }
        
        return {
            "executor_output": executor_output,
            "history": state.history + [history_entry],
            "status": ReflectionStatus.REVIEWING
        }

    def _parse_critic_result(self, critic_output: str) -> CriticResult:
        """Parse critic output into structured result."""
        passed = self._config.pass_keyword.upper() in critic_output.upper()
        
        dimensions = {}
        feedback = []
        summary = ""
        
        lines = critic_output.strip().split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if line.startswith("SCORES:"):
                current_section = "scores"
                score_part = line.replace("SCORES:", "").strip()
                for score_item in score_part.split():
                    if "=" in score_item:
                        dim_name, score_val = score_item.split("=", 1)
                        try:
                            score = float(score_val)
                            for dim in EvaluationDimension:
                                if dim.value == dim_name:
                                    dimensions[dim] = score
                                    break
                        except ValueError:
                            pass  # noqa: cleanup-best-effort
            elif line.startswith("FEEDBACK:"):
                current_section = "feedback"
                feedback_content = line.replace("FEEDBACK:", "").strip()
                if feedback_content:
                    feedback.append(feedback_content)
            elif line.startswith("STATUS:"):
                status_val = line.replace("STATUS:", "").strip().upper()
                if status_val == "PASS" or status_val == self._config.pass_keyword.upper():
                    passed = True
            elif current_section == "feedback" and line.startswith("- "):
                feedback.append(line[2:])
            elif line:
                summary += line + " "
        
        if not passed and not feedback:
            feedback.append("Output did not meet quality standards")
        
        return CriticResult(
            passed=passed,
            dimensions=dimensions,
            feedback=feedback,
            summary=summary.strip()
        )

    async def _critic_wrapper(self, state: ReflectionState) -> Dict[str, Any]:
        """Critic wrapper - evaluates output quality."""
        feedback = state.critic_result.feedback if state.critic_result and not state.critic_result.passed else []
        
        prompt = self._build_critic_prompt(state.task, state.executor_output, feedback)
        
        messages = (
            MessageFormatter().assemble(prompt).messages
            if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "true").lower() in ("1", "true", "yes", "y")
            else [{"role": "user", "content": prompt}]
        )
        result = await self._critic.run({"messages": messages, "context": state.context})
        
        critic_output = result.observation if hasattr(result, 'observation') else ""
        critic_result = self._parse_critic_result(critic_output)
        
        if not critic_result.passed and critic_result.dimensions:
            for dim, score in critic_result.dimensions.items():
                threshold = self._config.dimension_thresholds.get(dim, 0.7)
                if score < threshold:
                    critic_result.passed = False
                    critic_result.feedback.append(
                        f"{dim.value} score {score:.2f} below threshold {threshold:.2f}"
                    )
        
        if critic_result.passed:
            status = ReflectionStatus.APPROVED
            final_output = state.executor_output
        else:
            status = ReflectionStatus.REVIEWING
            final_output = None
        
        history_entry = {
            "iteration": state.iteration,
            "phase": "critic",
            "passed": critic_result.passed,
            "scores": {d.value: s for d, s in critic_result.dimensions.items()},
            "feedback_count": len(critic_result.feedback)
        }
        
        return {
            "critic_result": critic_result,
            "iteration": state.iteration + 1,
            "status": status,
            "history": state.history + [history_entry],
            "final_output": final_output
        }

    def _should_continue(self, state: ReflectionState) -> str:
        """Determine if continue reflecting or finish."""
        if state.status == ReflectionStatus.APPROVED:
            return "finish"
        
        if state.iteration >= self._config.max_iterations:
            return "finish"
        
        if state.critic_result and state.critic_result.passed:
            return "finish"
        
        return "continue"

    async def run(self, task: str) -> ReflectionState:
        """
        Run reflection pattern.
        
        Args:
            task: Task to solve
            
        Returns:
            ReflectionState: Final state with approved output
        """
        initial_state = ReflectionState(task=task)
        
        if LANGGRAPH_AVAILABLE and self._graph:
            result = await self._graph.ainvoke(initial_state)
            return result
        
        return await self._run_fallback(task)

    async def _run_fallback(self, task: str) -> ReflectionState:
        """Fallback execution without LangGraph."""
        state = ReflectionState(task=task)
        state.status = ReflectionStatus.EXECUTING
        
        while state.iteration < self._config.max_iterations:
            executor_result = await self._executor_wrapper(state)
            state.executor_output = executor_result["executor_output"]
            state.history = executor_result["history"]
            state.status = executor_result["status"]
            
            critic_result_data = await self._critic_wrapper(state)
            state.critic_result = critic_result_data["critic_result"]
            state.iteration = critic_result_data["iteration"]
            state.history = critic_result_data["history"]
            state.status = critic_result_data["status"]
            
            if critic_result_data["final_output"] is not None:
                state.final_output = critic_result_data["final_output"]
            
            if state.critic_result.passed:
                state.status = ReflectionStatus.APPROVED
                break
        
        if not state.critic_result or not state.critic_result.passed:
            state.status = ReflectionStatus.MAX_ITERATIONS_REACHED
            if not state.final_output:
                state.final_output = state.executor_output
        
        return state


def create_reflection_graph(
    executor_model: Optional[Any] = None,
    critic_model: Optional[Any] = None,
    max_iterations: int = 3,
    tools: Optional[List[Any]] = None,
    evaluation_dimensions: Optional[List[EvaluationDimension]] = None,
    dimension_thresholds: Optional[Dict[EvaluationDimension, float]] = None
) -> ReflectionGraph:
    """
    Create reflection graph.
    
    Args:
        executor_model: Model for executor agent
        critic_model: Model for critic agent
        max_iterations: Maximum reflection iterations
        tools: Tools for executor agent
        evaluation_dimensions: Dimensions to evaluate
        dimension_thresholds: Thresholds per dimension
        
    Returns:
        ReflectionGraph: Configured reflection graph
    """
    config = ReflectionConfig(
        executor_model=executor_model,
        critic_model=critic_model,
        max_iterations=max_iterations,
        tools=tools or [],
        evaluation_dimensions=evaluation_dimensions or [
            EvaluationDimension.FACTUALITY,
            EvaluationDimension.COMPLETENESS,
            EvaluationDimension.CLARITY,
            EvaluationDimension.FORMAT,
        ],
        dimension_thresholds=dimension_thresholds or {
            EvaluationDimension.FACTUALITY: 0.8,
            EvaluationDimension.COMPLETENESS: 0.7,
            EvaluationDimension.CLARITY: 0.7,
            EvaluationDimension.FORMAT: 0.8,
        }
    )
    return ReflectionGraph(config)

