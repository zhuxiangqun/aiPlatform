"""
LangGraph Planning Graph

Implements the Planning pattern: decompose complex tasks into sub-tasks,
execute them sequentially or in parallel, then aggregate results.

Based on framework/patterns.md §5 Planning 模式.

Decomposition strategies:
- SEQUENTIAL: Sub-tasks execute one after another
- PARALLEL: Sub-tasks execute simultaneously
- HIERARCHICAL: Multi-level task tree decomposition
"""

from typing import Any, Dict, List, Optional, TypedDict
from dataclasses import dataclass, field
from enum import Enum
import asyncio

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None
    END = None

from .react import ReActGraph, ReActGraphConfig
import os
from ....assembly import PromptAssembler


class DecompositionStrategy(Enum):
    """Task decomposition strategies."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"


class SubTaskStatus(Enum):
    """Sub-task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SubTask:
    """
    Sub-task in a plan.
    
    Attributes:
        task_id: Unique task identifier
        description: Task description
        dependencies: List of task IDs this depends on
        status: Current task status
        result: Task execution result
        priority: Execution priority (lower = higher)
        metadata: Additional metadata
    """
    task_id: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    status: SubTaskStatus = SubTaskStatus.PENDING
    result: Optional[str] = None
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_ready(self, completed_ids: set) -> bool:
        """Check if all dependencies are satisfied."""
        return all(dep_id in completed_ids for dep_id in self.dependencies)


@dataclass
class PlanningConfig:
    """Planning pattern configuration.
    
    Attributes:
        strategy: Decomposition strategy
        model: Model for task decomposition and execution
        tools: Tools available for execution
        max_depth: Maximum decomposition depth (for hierarchical)
        max_total_steps: Maximum total sub-tasks
        max_parallel: Maximum parallel sub-tasks (for parallel strategy)
    """
    strategy: DecompositionStrategy = DecompositionStrategy.SEQUENTIAL
    model: Optional[Any] = None
    tools: List[Any] = field(default_factory=list)
    max_depth: int = 3
    max_total_steps: int = 20
    max_parallel: int = 5


class PlanningState(TypedDict, total=False):
    """Planning pattern state.
    
    Attributes:
        task: Original task description
        subtasks: List of decomposed sub-tasks
        completed_ids: Set of completed sub-task IDs
        failed_ids: Set of failed sub-task IDs
        current_phase: Current planning phase
        results: Dictionary of task_id -> result
        final_result: Aggregated final result
        context: Additional context
    """
    task: str
    subtasks: List[SubTask]
    completed_ids: set
    failed_ids: set
    current_phase: str
    results: Dict[str, str]
    final_result: Any
    context: Dict[str, Any]


class PlanningGraph:
    """
    Planning Graph Implementation
    
    Decomposes a complex task into sub-tasks, executes them according
    to the selected strategy, then aggregates results.
    
    Phases:
    1. Decompose: Analyze task and create sub-task list
    2. Execute: Execute sub-tasks (sequential, parallel, or hierarchical)
    3. Aggregate: Combine results into final output
    """

    def __init__(self, config: Optional[PlanningConfig] = None):
        self._config = config or PlanningConfig()
        self._graph = None
        self._executor = None
        self._decomposer = None
        
        self._create_agents()
        
        if LANGGRAPH_AVAILABLE:
            self._build_graph()

    def _create_agents(self) -> None:
        """Create decomposer and executor agents."""
        decomposer_config = ReActGraphConfig(
            max_steps=5,
            model=self._config.model,
            tools=[]
        )
        self._decomposer = ReActGraph(decomposer_config)
        
        executor_config = ReActGraphConfig(
            max_steps=10,
            model=self._config.model,
            tools=self._config.tools
        )
        self._executor = ReActGraph(executor_config)

    def _build_graph(self) -> None:
        """Build LangGraph for planning pattern."""
        if not LANGGRAPH_AVAILABLE:
            return
        
        workflow = StateGraph(PlanningState)
        
        workflow.add_node("decompose", self._decompose_wrapper)
        workflow.add_node("execute", self._execute_wrapper)
        workflow.add_node("aggregate", self._aggregate_wrapper)
        
        workflow.set_entry_point("decompose")
        workflow.add_edge("decompose", "execute")
        workflow.add_edge("execute", "aggregate")
        workflow.add_edge("aggregate", END)
        
        self._graph = workflow.compile()

    async def _decompose_wrapper(self, state: PlanningState) -> Dict[str, Any]:
        """Decompose task into sub-tasks."""
        strategy_desc = {
            DecompositionStrategy.SEQUENTIAL: "按顺序依次执行",
            DecompositionStrategy.PARALLEL: "可并行同时执行",
            DecompositionStrategy.HIERARCHICAL: "分层逐级拆解",
        }.get(self._config.strategy, "按顺序依次执行")
        
        prompt = f"""将以下任务分解为子任务。

任务：{state.task}

分解策略：{strategy_desc}

请按以下格式列出子任务：
TASK_1: 子任务描述 [depends_on: 无]
TASK_2: 子任务描述 [depends_on: TASK_1]
TASK_3: 子任务描述 [depends_on: TASK_1]

要求：
- 每个子任务应有明确的输入和输出
- 标注子任务之间的依赖关系
- 子任务数量不超过 {self._config.max_total_steps} 个
"""

        if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y"):
            messages = PromptAssembler().assemble(prompt).messages
        else:
            messages = [{"role": "user", "content": prompt}]

        result = await self._decomposer.run({"messages": messages, "context": state.context})
        
        output = result.observation if hasattr(result, 'observation') else ""
        subtasks = self._parse_subtasks(output)
        
        if not subtasks:
            subtasks = [SubTask(
                task_id="TASK_1",
                description=state.task,
                dependencies=[],
                status=SubTaskStatus.PENDING
            )]
        
        return {
            "subtasks": subtasks,
            "current_phase": "execute"
        }

    def _parse_subtasks(self, output: str) -> List[SubTask]:
        """Parse decomposer output into sub-task list."""
        subtasks = []
        
        for line in output.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            
            task_id = None
            description = line
            dependencies = []
            
            if line.startswith("TASK_") and ":" in line:
                parts = line.split(":", 1)
                task_id = parts[0].strip()
                description = parts[1].strip()
                
                if "[depends_on:" in description:
                    dep_str = description[description.rfind("[depends_on:"):]
                    description = description[:description.rfind("[depends_on:")].strip()
                    dep_str = dep_str.replace("[depends_on:", "").replace("]", "").strip()
                    if dep_str and dep_str != "无":
                        dependencies = [d.strip() for d in dep_str.split(",")]
            
            if task_id:
                subtasks.append(SubTask(
                    task_id=task_id,
                    description=description,
                    dependencies=dependencies,
                    status=SubTaskStatus.PENDING
                ))
        
        for i, subtask in enumerate(subtasks):
            subtask.priority = i
        
        return subtasks

    async def _execute_wrapper(self, state: PlanningState) -> Dict[str, Any]:
        """Execute sub-tasks according to strategy."""
        if self._config.strategy == DecompositionStrategy.SEQUENTIAL:
            return await self._execute_sequential(state)
        elif self._config.strategy == DecompositionStrategy.PARALLEL:
            return await self._execute_parallel(state)
        elif self._config.strategy == DecompositionStrategy.HIERARCHICAL:
            return await self._execute_hierarchical(state)
        else:
            return await self._execute_sequential(state)

    async def _execute_sequential(self, state: PlanningState) -> Dict[str, Any]:
        """Execute sub-tasks sequentially."""
        results = dict(state.results)
        completed_ids = set(state.completed_ids)
        failed_ids = set(state.failed_ids)
        
        sorted_tasks = sorted(
            [t for t in state.subtasks if t.status == SubTaskStatus.PENDING],
            key=lambda t: t.priority
        )
        
        for subtask in sorted_tasks:
            if not subtask.is_ready(completed_ids):
                subtask.status = SubTaskStatus.SKIPPED
                failed_ids.add(subtask.task_id)
                continue
            
            context_str = ""
            for dep_id in subtask.dependencies:
                if dep_id in results:
                    context_str += f"\n前序任务 {dep_id} 的结果：{results[dep_id][:500]}"
            
            prompt = f"任务：{subtask.description}"
            if context_str:
                prompt += f"\n\n参考前序任务结果：{context_str}"
            
            try:
                messages = (
                    PromptAssembler().assemble(prompt).messages
                    if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y")
                    else [{"role": "user", "content": prompt}]
                )
                result = await self._executor.run({"messages": messages, "context": state.context})
                
                subtask.result = result.observation if hasattr(result, 'observation') else ""
                subtask.status = SubTaskStatus.COMPLETED
                results[subtask.task_id] = subtask.result
                completed_ids.add(subtask.task_id)
            except Exception as e:
                subtask.status = SubTaskStatus.FAILED
                subtask.result = str(e)
                results[subtask.task_id] = f"FAILED: {str(e)}"
                failed_ids.add(subtask.task_id)
        
        return {
            "results": results,
            "completed_ids": completed_ids,
            "failed_ids": failed_ids,
            "subtasks": state.subtasks,
            "current_phase": "aggregate"
        }

    async def _execute_parallel(self, state: PlanningState) -> Dict[str, Any]:
        """Execute independent sub-tasks in parallel."""
        results = dict(state.results)
        completed_ids = set(state.completed_ids)
        failed_ids = set(state.failed_ids)
        
        pending = [t for t in state.subtasks if t.status == SubTaskStatus.PENDING]
        
        rounds = []
        while pending:
            ready = [t for t in pending if t.is_ready(completed_ids)]
            if not ready:
                for t in pending:
                    t.status = SubTaskStatus.SKIPPED
                    failed_ids.add(t.task_id)
                break
            
            batch = ready[:self._config.max_parallel]
            
            tasks = []
            for subtask in batch:
                context_str = ""
                for dep_id in subtask.dependencies:
                    if dep_id in results:
                        context_str += f"\n前序任务 {dep_id} 的结果：{results[dep_id][:500]}"
                
                prompt = f"任务：{subtask.description}"
                if context_str:
                    prompt += f"\n\n参考前序任务结果：{context_str}"
                
                messages = (
                    PromptAssembler().assemble(prompt).messages
                    if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y")
                    else [{"role": "user", "content": prompt}]
                )
                tasks.append(self._executor.run({"messages": messages, "context": state.context}))
            
            exec_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for subtask, result in zip(batch, exec_results):
                if isinstance(result, Exception):
                    subtask.status = SubTaskStatus.FAILED
                    subtask.result = str(result)
                    results[subtask.task_id] = f"FAILED: {str(result)}"
                    failed_ids.add(subtask.task_id)
                else:
                    subtask.result = result.observation if hasattr(result, 'observation') else ""
                    subtask.status = SubTaskStatus.COMPLETED
                    results[subtask.task_id] = subtask.result
                    completed_ids.add(subtask.task_id)
            
            pending = [t for t in pending if t.status == SubTaskStatus.PENDING]
        
        return {
            "results": results,
            "completed_ids": completed_ids,
            "failed_ids": failed_ids,
            "subtasks": state.subtasks,
            "current_phase": "aggregate"
        }

    async def _execute_hierarchical(self, state: PlanningState) -> Dict[str, Any]:
        """Execute sub-tasks in hierarchical levels."""
        results = dict(state.results)
        completed_ids = set(state.completed_ids)
        failed_ids = set(state.failed_ids)
        
        remaining = list(state.subtasks)
        
        for depth in range(self._config.max_depth):
            ready = [t for t in remaining if t.status == SubTaskStatus.PENDING and t.is_ready(completed_ids)]
            
            if not ready:
                break
            
            batch = ready[:self._config.max_parallel]
            
            tasks = []
            for subtask in batch:
                context_str = ""
                for dep_id in subtask.dependencies:
                    if dep_id in results:
                        context_str += f"\n前序任务 {dep_id} 的结果：{results[dep_id][:500]}"
                
                prompt = f"任务（层级 {depth + 1}）：{subtask.description}"
                if context_str:
                    prompt += f"\n\n参考前序任务结果：{context_str}"
                
                messages = (
                    PromptAssembler().assemble(prompt).messages
                    if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y")
                    else [{"role": "user", "content": prompt}]
                )
                tasks.append(self._executor.run({"messages": messages, "context": state.context}))
            
            exec_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for subtask, result in zip(batch, exec_results):
                if isinstance(result, Exception):
                    subtask.status = SubTaskStatus.FAILED
                    subtask.result = str(result)
                    results[subtask.task_id] = f"FAILED: {str(result)}"
                    failed_ids.add(subtask.task_id)
                else:
                    subtask.result = result.observation if hasattr(result, 'observation') else ""
                    subtask.status = SubTaskStatus.COMPLETED
                    results[subtask.task_id] = subtask.result
                    completed_ids.add(subtask.task_id)
            
            remaining = [t for t in remaining if t.status == SubTaskStatus.PENDING]
        
        for t in remaining:
            if t.status == SubTaskStatus.PENDING:
                t.status = SubTaskStatus.SKIPPED
                failed_ids.add(t.task_id)
        
        return {
            "results": results,
            "completed_ids": completed_ids,
            "failed_ids": failed_ids,
            "subtasks": state.subtasks,
            "current_phase": "aggregate"
        }

    async def _aggregate_wrapper(self, state: PlanningState) -> Dict[str, Any]:
        """Aggregate sub-task results into final output."""
        completed_results = {
            tid: result
            for tid, result in state.results.items()
            if tid in state.completed_ids and not result.startswith("FAILED:")
        }
        
        if not completed_results:
            final_result = "所有子任务执行失败"
        elif len(completed_results) == 1:
            final_result = list(completed_results.values())[0]
        else:
            sections = []
            for tid, result in completed_results.items():
                task = next((t for t in state.subtasks if t.task_id == tid), None)
                desc = task.description if task else tid
                sections.append(f"### {tid}: {desc}\n{result}")
            
            final_result = "\n\n".join(sections)
        
        failed_count = len(state.failed_ids)
        total_count = len(state.subtasks)
        
        if failed_count > 0:
            final_result += f"\n\n---\n注意：{failed_count}/{total_count} 个子任务执行失败"
        
        return {
            "final_result": final_result,
            "current_phase": "completed"
        }

    async def run(self, task: str) -> PlanningState:
        """
        Run planning pattern.
        
        Args:
            task: Task to solve
            
        Returns:
            PlanningState: Final state with aggregated result
        """
        initial_state = PlanningState(task=task)
        
        if LANGGRAPH_AVAILABLE and self._graph:
            result = await self._graph.ainvoke(initial_state)
            return result
        
        return await self._run_fallback(task)

    async def _run_fallback(self, task: str) -> PlanningState:
        """Fallback execution without LangGraph."""
        state = PlanningState(task=task)
        
        decompose_result = await self._decompose_wrapper(state)
        state.subtasks = decompose_result["subtasks"]
        state.current_phase = decompose_result["current_phase"]
        
        execute_result = await self._execute_wrapper(state)
        state.results = execute_result["results"]
        state.completed_ids = execute_result["completed_ids"]
        state.failed_ids = execute_result["failed_ids"]
        state.current_phase = execute_result["current_phase"]
        
        aggregate_result = await self._aggregate_wrapper(state)
        state.final_result = aggregate_result["final_result"]
        state.current_phase = "completed"
        
        return state


def create_planning_graph(
    strategy: DecompositionStrategy = DecompositionStrategy.SEQUENTIAL,
    model: Optional[Any] = None,
    tools: Optional[List[Any]] = None,
    max_depth: int = 3,
    max_total_steps: int = 20,
    max_parallel: int = 5
) -> PlanningGraph:
    """
    Create planning graph.
    
    Args:
        strategy: Decomposition strategy
        model: Language model
        tools: List of tools
        max_depth: Maximum decomposition depth
        max_total_steps: Maximum total sub-tasks
        max_parallel: Maximum parallel sub-tasks
        
    Returns:
        PlanningGraph: Configured planning graph
    """
    config = PlanningConfig(
        strategy=strategy,
        model=model,
        tools=tools or [],
        max_depth=max_depth,
        max_total_steps=max_total_steps,
        max_parallel=max_parallel
    )
    return PlanningGraph(config)
