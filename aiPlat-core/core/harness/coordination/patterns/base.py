"""
Coordination Patterns Module

Provides coordination patterns for multi-agent collaboration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import asyncio


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
            try:
                result = await agent.execute(context.task)
                
                if hasattr(result, 'output'):
                    outputs.append(result.output)
                    # Pass output to next agent
                    if i < len(context.agents) - 1:
                        context.task = str(result.output)
                else:
                    outputs.append(result)
                    
            except Exception as e:
                errors.append(f"Agent {i} failed: {str(e)}")
        
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
        tasks = [agent.execute(context.task) for agent in context.agents]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Fan-in: aggregate results
        outputs = []
        errors = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors.append(f"Agent {i} failed: {str(result)}")
            else:
                outputs.append(result.output if hasattr(result, 'output') else result)
        
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
        
        # Execute with matched experts
        tasks = [agent.execute(context.task) for agent in matched_experts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        outputs = [r.output if hasattr(r, 'output') else str(r) for r in results if not isinstance(r, Exception)]
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
                producer_result = await producer.execute(current_output)
                current_output = producer_result.output if hasattr(producer_result, 'output') else str(producer_result)
            except Exception as e:
                return CoordinationResult(
                    success=False,
                    outputs=outputs,
                    errors=[f"Producer failed: {str(e)}"]
                )
            
            # Reviewer evaluates
            try:
                review_prompt = f"Review this output:\n{current_output}\n\nIs it correct? Respond YES or NO with feedback."
                review_result = await reviewer.execute(review_prompt)
                review_content = review_result.output if hasattr(review_result, 'output') else str(review_result)
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
            supervisor_result = await self._supervisor.execute(delegation_prompt)
            delegation = supervisor_result.output if hasattr(supervisor_result, 'output') else str(supervisor_result)
        except Exception as e:
            return CoordinationResult(
                success=False,
                errors=[f"Supervisor failed: {str(e)}"]
            )
        
        # Execute delegated tasks in parallel
        tasks = [worker.execute(delegation) for worker in self._workers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        outputs = [r.output if hasattr(r, 'output') else str(r) for r in results if not isinstance(r, Exception)]
        errors = [str(r) for r in results if isinstance(r, Exception)]
        
        # Supervisor aggregates
        aggregation_prompt = f"""Results from workers:
{chr(10).join(outputs)}

Provide final answer.
"""
        
        try:
            final_result = await self._supervisor.execute(aggregation_prompt)
            final_output = final_result.output if hasattr(final_result, 'output') else str(final_result)
        except Exception as e:
            final_output = "\n".join(outputs)
        
        return CoordinationResult(
            success=len(errors) < len(self._workers),
            outputs=[final_output],
            errors=errors
        )


def create_pattern(pattern_type: str) -> ICoordinationPattern:
    """Factory function to create coordination pattern"""
    patterns = {
        "pipeline": PipelinePattern,
        "fan_out_fan_in": FanOutFanInPattern,
        "expert_pool": ExpertPoolPattern,
        "producer_reviewer": ProducerReviewerPattern,
        "supervisor": SupervisorPattern,
    }
    
    if pattern_type not in patterns:
        raise ValueError(f"Unknown pattern: {pattern_type}")
    
    return patterns[pattern_type]()