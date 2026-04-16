"""
LangGraph TriAgent Graph

Implements a three-agent system (Planner, Generator, Evaluator) using LangGraph.
Based on Harness Engineering principles for iterative development with evaluation.
"""

from typing import Any, Dict, List, Optional, TypedDict
from dataclasses import dataclass, field
from enum import Enum
import os

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None
    END = None

from .react import ReActGraph, ReActGraphConfig
from ..nodes import AgentState
from ....assembly import PromptAssembler


class EvaluationDimension(Enum):
    """Evaluator evaluation dimensions."""
    CORRECTNESS = "correctness"      # Test pass rate
    PERFORMANCE = "performance"       # Response time, throughput
    MAINTAINABILITY = "maintainability"  # Code complexity, duplication
    SECURITY = "security"            # Vulnerability scan, permissions


@dataclass
class EvaluationResult:
    """Evaluation result from Evaluator."""
    dimension: EvaluationDimension
    passed: bool
    score: float
    threshold: float
    details: str
    suggestions: List[str] = field(default_factory=list)


@dataclass
class EvaluationMetrics:
    """Metrics for evaluator evaluation."""
    test_pass_rate: float = 0.0
    response_time_ms: float = 0.0
    throughput: float = 0.0
    code_complexity: float = 0.0
    code_duplication: float = 0.0
    vulnerabilities: int = 0
    permission_issues: int = 0


@dataclass
class TriAgentConfig:
    """Tri-agent configuration"""
    planner_model: Optional[Any] = None
    generator_model: Optional[Any] = None
    evaluator_model: Optional[Any] = None
    max_iterations: int = 3
    tools: List[Any] = field(default_factory=list)
    evaluation_thresholds: Dict[EvaluationDimension, float] = field(default_factory=dict)


class TriAgentState(TypedDict, total=False):
    """Tri-agent state"""
    task: str
    plan: str
    spec: str
    generated: str
    evaluation: str
    feedback: List[str]
    iteration: int
    approved: bool
    evaluation_results: List[EvaluationResult]
    final_result: Any
    context: Dict[str, Any]


class TriAgentGraph:
    """
    Tri-Agent Graph Implementation
    
    Three agents collaborate (Harness Engineering pattern):
    - Planner: Analyzes task, creates specification (spec.md)
    - Generator: Implements code based on plan (sprint-report.md)
    - Evaluator: Validates results and provides feedback (feedback.md)
    
    The loop continues until evaluator approves or max iterations reached.
    """

    def __init__(self, config: Optional[TriAgentConfig] = None):
        self._config = config or self._default_config()
        self._graph = None
        self._planner = None
        self._generator = None
        self._evaluator = None
        
        self._create_agents()
        
        if LANGGRAPH_AVAILABLE:
            self._build_graph()
    
    def _default_config(self) -> TriAgentConfig:
        """Create default config with evaluation thresholds."""
        return TriAgentConfig(
            max_iterations=3,
            evaluation_thresholds={
                EvaluationDimension.CORRECTNESS: 0.95,
                EvaluationDimension.PERFORMANCE: 1.0,
                EvaluationDimension.MAINTAINABILITY: 0.8,
                EvaluationDimension.SECURITY: 1.0
            }
        )
    
    def _get_threshold(self, dimension: EvaluationDimension) -> float:
        """Get threshold for evaluation dimension."""
        return self._config.evaluation_thresholds.get(dimension, 0.8)

    def _create_agents(self) -> None:
        """Create the three agent instances"""
        # Planner: Analyzes task and creates specification (spec.md)
        planner_config = ReActGraphConfig(
            max_steps=self._config.max_iterations,
            model=self._config.planner_model,
            tools=[]
        )
        self._planner = ReActGraph(planner_config)
        
        # Generator: Implements code based on plan (sprint-report.md)
        generator_config = ReActGraphConfig(
            max_steps=self._config.max_iterations,
            model=self._config.generator_model,
            tools=self._config.tools
        )
        self._generator = ReActGraph(generator_config)
        
        # Evaluator: Validates and provides feedback (feedback.md)
        evaluator_config = ReActGraphConfig(
            max_steps=1,
            model=self._config.evaluator_model,
            tools=[]
        )
        self._evaluator = ReActGraph(evaluator_config)

    def _build_graph(self) -> None:
        """Build LangGraph for tri-agent"""
        if not LANGGRAPH_AVAILABLE:
            return
        
        workflow = StateGraph(TriAgentState)
        
        workflow.add_node("plan", self._planner_wrapper)
        workflow.add_node("generate", self._generator_wrapper)
        workflow.add_node("evaluate", self._evaluator_wrapper)
        
        workflow.set_entry_point("plan")
        workflow.add_edge("plan", "generate")
        workflow.add_edge("generate", "evaluate")
        workflow.add_conditional_edges(
            "evaluate",
            self._should_continue,
            {
                "continue": "plan",
                "finish": END
            }
        )
        
        self._graph = workflow.compile()

    async def _planner_wrapper(self, state: TriAgentState) -> Dict[str, Any]:
        """Planner wrapper - creates specification (spec.md)"""
        prompt = f"Task: {state.task}\nAnalyze and create a detailed specification (spec.md)."
        messages = (
            PromptAssembler().assemble(prompt).messages
            if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y")
            else [{"role": "user", "content": prompt}]
        )
        result = await self._planner.run({"messages": messages, "context": state.context})
        
        spec = result.observation if hasattr(result, 'observation') else ""
        
        return {
            "plan": spec,
            "spec": spec,
            "iteration": state.iteration + 1
        }

    async def _generator_wrapper(self, state: TriAgentState) -> Dict[str, Any]:
        """Generator wrapper - implements code (sprint-report.md)"""
        prompt = f"Specification:\n{state.spec}\n\nImplement the code based on this spec."
        messages = (
            PromptAssembler().assemble(prompt).messages
            if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y")
            else [{"role": "user", "content": prompt}]
        )
        result = await self._generator.run({"messages": messages, "context": state.context})
        
        generated = result.observation if hasattr(result, 'observation') else ""
        
        return {
            "generated": generated
        }

    async def _evaluator_wrapper(self, state: TriAgentState) -> Dict[str, Any]:
        """Evaluator wrapper - validates results and creates feedback (feedback.md)"""
        metrics = self._extract_metrics_from_generated(state.generated)
        
        eval_prompt = f"""Task: {state.task}
Specification: {state.spec}
Generated output: {state.generated}

Evaluate the output against these criteria:
1. Correctness: Test pass rate ≥ {self._get_threshold(EvaluationDimension.CORRECTNESS)*100}%
2. Performance: Response time, throughput meeting spec
3. Maintainability: Code complexity and duplication within limits
4. Security: No vulnerabilities or permission issues

Respond with APPROVED if all criteria pass, or REJECTED: <reason> with specific feedback."""

        messages = (
            PromptAssembler().assemble(eval_prompt).messages
            if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y")
            else [{"role": "user", "content": eval_prompt}]
        )
        result = await self._evaluator.run({"messages": messages, "context": state.context})
        
        evaluation = result.observation if hasattr(result, 'observation') else ""
        approved = "APPROVED" in evaluation.upper()
        
        evaluation_results = self._evaluate_dimensions(metrics)
        
        return {
            "evaluation": evaluation,
            "approved": approved,
            "evaluation_results": evaluation_results,
            "feedback": [evaluation] if not approved else []
        }

    def _extract_metrics_from_generated(self, generated: str) -> EvaluationMetrics:
        """Extract metrics from generated output (placeholder implementation)."""
        return EvaluationMetrics(
            test_pass_rate=0.85,
            response_time_ms=100.0,
            throughput=1000.0,
            code_complexity=0.3,
            code_duplication=0.1,
            vulnerabilities=0,
            permission_issues=0
        )

    def _evaluate_dimensions(self, metrics: EvaluationMetrics) -> List[EvaluationResult]:
        """Evaluate all dimensions and return results."""
        results = []
        
        results.append(EvaluationResult(
            dimension=EvaluationDimension.CORRECTNESS,
            passed=metrics.test_pass_rate >= self._get_threshold(EvaluationDimension.CORRECTNESS),
            score=metrics.test_pass_rate,
            threshold=self._get_threshold(EvaluationDimension.CORRECTNESS),
            details=f"Test pass rate: {metrics.test_pass_rate*100}%"
        ))
        
        results.append(EvaluationResult(
            dimension=EvaluationDimension.PERFORMANCE,
            passed=metrics.response_time_ms < 1000,
            score=1.0 - (metrics.response_time_ms / 2000),
            threshold=self._get_threshold(EvaluationDimension.PERFORMANCE),
            details=f"Response time: {metrics.response_time_ms}ms"
        ))
        
        results.append(EvaluationResult(
            dimension=EvaluationDimension.MAINTAINABILITY,
            passed=metrics.code_complexity < 0.5 and metrics.code_duplication < 0.3,
            score=1.0 - metrics.code_complexity - metrics.code_duplication,
            threshold=self._get_threshold(EvaluationDimension.MAINTAINABILITY),
            details=f"Complexity: {metrics.code_complexity}, Duplication: {metrics.code_duplication}"
        ))
        
        results.append(EvaluationResult(
            dimension=EvaluationDimension.SECURITY,
            passed=metrics.vulnerabilities == 0 and metrics.permission_issues == 0,
            score=1.0 if metrics.vulnerabilities == 0 else 0.0,
            threshold=self._get_threshold(EvaluationDimension.SECURITY),
            details=f"Vulnerabilities: {metrics.vulnerabilities}, Permission issues: {metrics.permission_issues}"
        ))
        
        return results
    
    def _should_continue(self, state: TriAgentState) -> str:
        """Determine if continue or finish"""
        if state.approved:
            return "finish"
        
        if state.iteration >= self._config.max_iterations:
            return "finish"
        
        return "continue"

    async def run(self, task: str) -> TriAgentState:
        """
        Run tri-agent coordination
        
        Args:
            task: Task to solve
            
        Returns:
            TriAgentState: Final state
        """
        initial_state = TriAgentState(task=task)
        
        if LANGGRAPH_AVAILABLE and self._graph:
            result = await self._graph.ainvoke(initial_state)
            return result
        
        return await self._run_fallback(task)

    async def _run_fallback(self, task: str) -> TriAgentState:
        """Fallback execution without LangGraph"""
        state = TriAgentState(task=task)
        
        while state.iteration < self._config.max_iterations and not state.approved:
            state.iteration += 1
            
            plan_prompt = f"Task: {task}\nAnalyze and create spec."
            plan_messages = (
                PromptAssembler().assemble(plan_prompt).messages
                if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y")
                else [{"role": "user", "content": plan_prompt}]
            )
            plan_result = await self._planner.run({"messages": plan_messages})
            state.plan = plan_result.observation if hasattr(plan_result, 'observation') else ""
            state.spec = state.plan
            
            gen_prompt = f"Spec: {state.spec}\nImplement."
            gen_messages = (
                PromptAssembler().assemble(gen_prompt).messages
                if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y")
                else [{"role": "user", "content": gen_prompt}]
            )
            generator_result = await self._generator.run({"messages": gen_messages})
            state.generated = generator_result.observation if hasattr(generator_result, 'observation') else ""
            
            generated_result = state.generated
            eval_prompt = f"Task: {task}\nResult: {generated_result}\nEvaluate. Respond APPROVED or REJECTED."
            eval_messages = (
                PromptAssembler().assemble(eval_prompt).messages
                if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y")
                else [{"role": "user", "content": eval_prompt}]
            )
            evaluator_result = await self._evaluator.run({"messages": eval_messages})
            state.evaluation = evaluator_result.observation if hasattr(evaluator_result, 'observation') else ""
            state.approved = "APPROVED" in state.evaluation.upper()
            
            if not state.approved:
                state.feedback.append(state.evaluation)
            
            state.evaluation_results = self._evaluate_dimensions(
                self._extract_metrics_from_generated(state.generated)
            )
        
        if not state.final_result:
            state.final_result = state.generated
        
        return state


def create_tri_agent_graph(
    planner_model: Optional[Any] = None,
    generator_model: Optional[Any] = None,
    evaluator_model: Optional[Any] = None,
    tools: Optional[List[Any]] = None,
    max_iterations: int = 3,
    evaluation_thresholds: Optional[Dict[EvaluationDimension, float]] = None
) -> TriAgentGraph:
    """
    Create tri-agent graph
    
    Args:
        planner_model: Model for planner
        generator_model: Model for generator
        evaluator_model: Model for evaluator
        tools: Tools for generator
        max_iterations: Maximum iterations
        evaluation_thresholds: Custom evaluation thresholds
        
    Returns:
        TriAgentGraph: Configured tri-agent graph
    """
    thresholds = evaluation_thresholds or {
        EvaluationDimension.CORRECTNESS: 0.95,
        EvaluationDimension.PERFORMANCE: 1.0,
        EvaluationDimension.MAINTAINABILITY: 0.8,
        EvaluationDimension.SECURITY: 1.0
    }
    
    config = TriAgentConfig(
        planner_model=planner_model,
        generator_model=generator_model,
        evaluator_model=evaluator_model,
        max_iterations=max_iterations,
        tools=tools or [],
        evaluation_thresholds=thresholds
    )
    return TriAgentGraph(config)
