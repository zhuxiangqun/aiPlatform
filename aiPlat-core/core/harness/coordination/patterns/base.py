"""
Coordination Patterns Module

Provides coordination patterns for multi-agent collaboration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import asyncio
import re


_PATTERN_AGENT_CONTRACT_ERROR = (
    "Agent passed to coordination pattern must implement execute(task: str). "
    "For real agents (execute(AgentContext)), wrap them with MultiAgent _PatternAgentAdapter."
)


async def _safe_execute(agent: Any, task: str, agent_index: int) -> Tuple[bool, Any, Optional[str]]:
    """
    Execute a pattern agent with a string task.
    Returns: (ok, output_or_exception, error_message)
    """
    try:
        result = await agent.execute(task)
        output = result.output if hasattr(result, "output") else result
        return True, output, None
    except TypeError as e:
        return False, None, f"Agent {agent_index} failed: {str(e)}; {_PATTERN_AGENT_CONTRACT_ERROR}"
    except Exception as e:
        return False, None, f"Agent {agent_index} failed: {str(e)}"


@dataclass
class CoordinationContext:
    """Coordination context"""
    task: str
    agents: List[Any] = field(default_factory=list)
    state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CoordinationResult:
    """Coordination result"""
    success: bool
    outputs: List[Any] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ICoordinationPattern(ABC):
    """
    Coordination pattern interface

    Contract:
    - context.agents elements MUST implement: `await execute(task: str) -> Any`.
    - If you have a "real" agent that expects `execute(AgentContext)`, you must wrap it with an adapter
      (see MultiAgent._PatternAgentAdapter) before passing to the pattern.
    """

    @abstractmethod
    async def coordinate(
        self,
        context: CoordinationContext
    ) -> CoordinationResult:
        """Execute coordination"""
        pass


class PipelinePattern(ICoordinationPattern):
    """
    Pipeline Pattern
    
    Agents execute in sequence, each passing output to next.
    """

    async def coordinate(
        self,
        context: CoordinationContext
    ) -> CoordinationResult:
        """Execute pipeline coordination"""
        outputs = []
        errors = []
        
        for i, agent in enumerate(context.agents):
            ok, output, err = await _safe_execute(agent, context.task, i)
            if not ok:
                errors.append(err or f"Agent {i} failed")
                continue
            outputs.append(output)
            # Pass output to next agent
            if i < len(context.agents) - 1:
                context.task = str(output)
        
        return CoordinationResult(
            success=len(errors) == 0,
            outputs=outputs,
            errors=errors
        )


class FanOutFanInPattern(ICoordinationPattern):
    """
    Fan-Out Fan-In Pattern
    
    Agents execute in parallel, then results are aggregated.
    """

    async def coordinate(
        self,
        context: CoordinationContext
    ) -> CoordinationResult:
        """Execute fan-out fan-in coordination"""
        # Fan-out: execute all agents in parallel
        async def _run(i: int, agent: Any, task: str):
            ok, output, err = await _safe_execute(agent, task, i)
            if not ok:
                return RuntimeError(err or f"Agent {i} failed")
            return output

        tasks = [_run(i, agent, context.task) for i, agent in enumerate(context.agents)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Fan-in: aggregate results
        outputs = []
        errors = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors.append(f"Agent {i} failed: {str(result)}")
            else:
                outputs.append(result)
        
        # Aggregate (simple concatenation)
        aggregated = "\n---\n".join([
            f"Agent {i}: {out}"
            for i, out in enumerate(outputs)
        ])
        
        return CoordinationResult(
            success=len(errors) == 0,
            outputs=[aggregated],
            errors=errors,
            metadata={"parallel": True, "count": len(context.agents)}
        )


class ExpertPoolPattern(ICoordinationPattern):
    """
    Expert Pool Pattern
    
    Task is routed to most appropriate expert agent.
    """

    def __init__(self):
        self._expertises: Dict[str, List[Any]] = {}

    def register_expert(self, expertise: str, agent: Any) -> None:
        """Register an expert for a specific expertise"""
        if expertise not in self._expertises:
            self._expertises[expertise] = []
        self._expertises[expertise].append(agent)

    async def coordinate(
        self,
        context: CoordinationContext
    ) -> CoordinationResult:
        """Execute expert pool coordination"""
        # Determine required expertise from task
        task = context.task.lower()
        
        matched_experts = []
        for expertise, experts in self._expertises.items():
            if expertise.lower() in task:
                matched_experts.extend(experts)
        
        if not matched_experts:
            matched_experts = context.agents
        
        async def _run(i: int, agent: Any, task: str):
            ok, output, err = await _safe_execute(agent, task, i)
            if not ok:
                return RuntimeError(err or f"Agent {i} failed")
            return output

        tasks = [_run(i, agent, context.task) for i, agent in enumerate(matched_experts)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        outputs = [str(r) for r in results if not isinstance(r, Exception)]
        errors = [str(r) for r in results if isinstance(r, Exception)]
        
        return CoordinationResult(
            success=len(errors) < len(results),
            outputs=outputs,
            errors=errors
        )


class ProducerReviewerPattern(ICoordinationPattern):
    """
    Producer-Reviewer Pattern
    
    One agent produces, another reviews. Can iterate.
    """

    def __init__(self, max_iterations: int = 3):
        self._max_iterations = max_iterations

    async def coordinate(
        self,
        context: CoordinationContext
    ) -> CoordinationResult:
        """Execute producer-reviewer coordination"""
        if len(context.agents) < 2:
            return CoordinationResult(
                success=False,
                errors=["Need at least 2 agents (producer + reviewer)"]
            )
        
        producer = context.agents[0]
        reviewer = context.agents[1]
        
        current_output = context.task
        outputs = []
        
        for iteration in range(self._max_iterations):
            # Producer creates
            try:
                ok, output, err = await _safe_execute(producer, current_output, 0)
                if not ok:
                    raise RuntimeError(err)
                current_output = str(output)
            except Exception as e:
                return CoordinationResult(
                    success=False,
                    outputs=outputs,
                    errors=[f"Producer failed: {str(e)}"]
                )
            
            # Reviewer evaluates
            try:
                review_prompt = f"Review this output:\n{current_output}\n\nIs it correct? Respond YES or NO with feedback."
                ok, output, err = await _safe_execute(reviewer, review_prompt, 1)
                if not ok:
                    raise RuntimeError(err)
                review_content = str(output)
            except Exception as e:
                return CoordinationResult(
                    success=False,
                    outputs=outputs,
                    errors=[f"Reviewer failed: {str(e)}"]
                )
            
            outputs.append({
                "iteration": iteration + 1,
                "produced": current_output,
                "review": review_content
            })
            
            # Check if approved
            if "YES" in review_content.upper():
                break
            
            # Feedback for next iteration
            current_output = f"Previous output: {current_output}\n\nReview feedback: {review_content}"
        
        return CoordinationResult(
            success=True,
            outputs=[outputs[-1] if outputs else current_output],
            metadata={"iterations": len(outputs)}
        )


class SupervisorPattern(ICoordinationPattern):
    """
    Supervisor Pattern
    
    Central supervisor coordinates worker agents.
    """

    def __init__(self):
        self._supervisor = None
        self._workers: List[Any] = []

    def set_supervisor(self, agent: Any) -> None:
        """Set supervisor agent"""
        self._supervisor = agent

    def add_worker(self, agent: Any) -> None:
        """Add worker agent"""
        self._workers.append(agent)

    async def coordinate(
        self,
        context: CoordinationContext
    ) -> CoordinationResult:
        """Execute supervisor coordination"""
        if not self._supervisor or not self._workers:
            return CoordinationResult(
                success=False,
                errors=["Need supervisor and workers"]
            )
        
        # Supervisor delegates
        delegation_prompt = f"""Task: {context.task}

Available workers: {[w.get_config().name if hasattr(w, 'get_config') else str(w) for w in self._workers]}

Delegate subtasks to appropriate workers.
"""
        
        try:
            ok, output, err = await _safe_execute(self._supervisor, delegation_prompt, 0)
            if not ok:
                raise RuntimeError(err)
            delegation = str(output)
        except Exception as e:
            return CoordinationResult(
                success=False,
                errors=[f"Supervisor failed: {str(e)}"]
            )
        
        # Execute delegated tasks in parallel
        async def _run(i: int, worker: Any, task: str):
            ok, output, err = await _safe_execute(worker, task, i + 1)
            if not ok:
                return RuntimeError(err or f"Worker {i+1} failed")
            return output

        tasks = [_run(i, worker, delegation) for i, worker in enumerate(self._workers)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        outputs = [str(r) for r in results if not isinstance(r, Exception)]
        errors = [str(r) for r in results if isinstance(r, Exception)]
        
        # Supervisor aggregates
        aggregation_prompt = f"""Results from workers:
{chr(10).join(outputs)}

Provide final answer.
"""
        
        try:
            ok, output, err = await _safe_execute(self._supervisor, aggregation_prompt, 0)
            if not ok:
                raise RuntimeError(err)
            final_output = str(output)
        except Exception as e:
            final_output = "\n".join(outputs)
        
        return CoordinationResult(
            success=len(errors) < len(self._workers),
            outputs=[final_output],
            errors=errors
        )


class HierarchicalDelegationPattern(ICoordinationPattern):
    """
    Hierarchical Delegation Pattern
    
    A simple depth-limited hierarchical decomposition:
    - root agent processes the top-level task and may emit subtasks
    - subtasks are dispatched to remaining agents (round-robin)
    - each subtask output can be further decomposed until depth_limit/max_nodes
    """

    def __init__(self, depth_limit: int = 3, max_nodes: int = 20):
        self._depth_limit = depth_limit
        self._max_nodes = max_nodes

    def _decompose(self, text: str) -> List[str]:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        tasks: List[str] = []
        for ln in lines:
            m = re.match(r"^(\d+[\).\]]|[-*])\s+(.*)$", ln)
            if m:
                tasks.append(m.group(2).strip())
        # fallback: split by "；" or ";"
        if not tasks and (";" in (text or "") or "；" in (text or "")):
            parts = re.split(r"[;；]\s*", text)
            tasks = [p.strip() for p in parts if p.strip()]
        return tasks[: self._max_nodes]

    async def coordinate(self, context: CoordinationContext) -> CoordinationResult:
        if not context.agents:
            return CoordinationResult(success=False, errors=["Need at least 1 agent"])

        depth_limit = int(context.metadata.get("depth_limit", self._depth_limit))
        max_nodes = int(context.metadata.get("max_nodes", self._max_nodes))

        root = context.agents[0]
        workers = context.agents[1:] or [root]

        outputs: List[Any] = []
        errors: List[str] = []

        ok, root_output, err = await _safe_execute(root, context.task, 0)
        if not ok:
            return CoordinationResult(success=False, outputs=[], errors=[err or "Root agent failed"])

        outputs.append(root_output)

        queue: List[Tuple[str, int]] = [(t, 1) for t in self._decompose(str(root_output))]
        node_count = 1
        worker_idx = 0

        while queue and node_count < max_nodes:
            task, depth = queue.pop(0)
            if depth > depth_limit:
                continue

            agent = workers[worker_idx % len(workers)]
            worker_idx += 1

            ok, out, err = await _safe_execute(agent, task, worker_idx)
            if not ok:
                errors.append(err or f"Agent failed at depth {depth}")
                node_count += 1
                continue

            outputs.append(out)
            node_count += 1

            if depth < depth_limit:
                for st in self._decompose(str(out)):
                    if node_count + len(queue) >= max_nodes:
                        break
                    queue.append((st, depth + 1))

        return CoordinationResult(
            success=len(errors) == 0,
            outputs=outputs,
            errors=errors,
            metadata={"depth_limit": depth_limit, "max_nodes": max_nodes, "nodes_executed": node_count},
        )


def create_pattern(pattern_type: str) -> ICoordinationPattern:
    """Factory function to create coordination pattern"""
    patterns = {
        "pipeline": PipelinePattern,
        "fan_out_fan_in": FanOutFanInPattern,
        "expert_pool": ExpertPoolPattern,
        "producer_reviewer": ProducerReviewerPattern,
        "supervisor": SupervisorPattern,
        "hierarchical_delegation": HierarchicalDelegationPattern,
    }
    
    if pattern_type not in patterns:
        raise ValueError(f"Unknown pattern: {pattern_type}")
    
    return patterns[pattern_type]()
