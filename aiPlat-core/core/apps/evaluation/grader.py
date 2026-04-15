"""
LLM Grader Module

Uses LLM-as-judge approach to grade agent traces.
"""

from typing import Optional
from .types import AgentTrace, TraceGrade


class LLmGrader:
    """LLM-based trace grader"""
    
    def __init__(self, judge_client=None):
        self.judge_client = judge_client
    
    async def grade(self, trace: AgentTrace) -> TraceGrade:
        """Grade a trace using LLM judge"""
        if not self.judge_client:
            return self._heuristic_grade(trace)
        
        prompt = self._build_judge_prompt(trace)
        
        try:
            response = await self.judge_client.complete(prompt)
            grade_str = response.lower().strip()
            
            if "a" in grade_str and "perfect" in grade_str:
                return TraceGrade.GRADE_A
            elif "b" in grade_str or "slight" in grade_str:
                return TraceGrade.GRADE_B
            elif "c" in grade_str or "人工" in grade_str:
                return TraceGrade.GRADE_C
            else:
                return TraceGrade.GRADE_D
        except Exception:
            return self._heuristic_grade(trace)
    
    def _build_judge_prompt(self, trace: AgentTrace) -> str:
        """Build prompt for LLM judge"""
        return f"""
任务：评估 Agent 执行轨迹质量

轨迹信息：
- 任务：{trace.prompt}
- 工具调用数：{len(trace.tool_calls)}
- 最终响应：{trace.final_response[:200]}...
- 成功：{trace.success}

评估标准：
- A：完美执行，无需任何修正
- B：有轻微问题，自行修正后成功
- C：需要人工介入才能完成
- D：执行失败，无法完成任务

请给出评级（A/B/C/D）及原因：
"""
    
    def _heuristic_grade(self, trace: AgentTrace) -> TraceGrade:
        """Fallback heuristic grading"""
        if trace.success and len(trace.tool_calls) <= 5:
            return TraceGrade.GRADE_A
        elif trace.success:
            return TraceGrade.GRADE_B
        elif len(trace.tool_calls) > 0:
            return TraceGrade.GRADE_C
        else:
            return TraceGrade.GRADE_D


async def grade_trace(trace: AgentTrace, grader: Optional[LLmGrader] = None) -> AgentTrace:
    """Grade a trace and return updated trace"""
    if grader is None:
        grader = LLmGrader()
    
    grade = await grader.grade(trace)
    trace.grade = grade
    return trace


__all__ = ["LLmGrader", "grade_trace"]