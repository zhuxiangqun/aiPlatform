"""
Trace Tracker Module

Tracks and stores agent execution traces.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from .types import AgentTrace
import json
import os


class TraceTracker:
    """Tracks agent execution traces"""
    
    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path
        self.current_trace: Optional[AgentTrace] = None
        self.traces: Dict[str, AgentTrace] = {}
    
    def start_trace(self, session_id: str, task_id: str, prompt: str) -> AgentTrace:
        """Start a new trace"""
        trace = AgentTrace(
            session_id=session_id,
            task_id=task_id,
            prompt=prompt
        )
        self.current_trace = trace
        return trace
    
    def record_tool_call(self, tool_name: str, tool_input: Dict[str, Any]):
        """Record a tool call"""
        if self.current_trace:
            self.current_trace.tool_calls.append({
                "tool": tool_name,
                "input": tool_input,
                "timestamp": datetime.now().isoformat()
            })
    
    def record_tool_result(self, tool_name: str, result: Dict[str, Any]):
        """Record a tool result"""
        if self.current_trace:
            self.current_trace.tool_results.append({
                "tool": tool_name,
                "result": result,
                "timestamp": datetime.now().isoformat()
            })
    
    def end_trace(
        self,
        final_response: str,
        success: bool,
        latency_ms: int,
        tokens_used: int
    ) -> AgentTrace:
        """End current trace"""
        if self.current_trace:
            self.current_trace.final_response = final_response
            self.current_trace.success = success
            self.current_trace.latency_ms = latency_ms
            self.current_trace.tokens_used = tokens_used
            
            self.traces[self.current_trace.session_id] = self.current_trace
            
            completed = self.current_trace
            self.current_trace = None
            return completed
        
        raise RuntimeError("No active trace to end")
    
    def save_to_file(self, path: Optional[str] = None):
        """Save traces to file"""
        save_path = path or self.storage_path
        if not save_path:
            return
        
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        with open(save_path, "w") as f:
            json.dump(
                [t.to_dict() for t in self.traces.values()],
                f,
                indent=2
            )
    
    def load_from_file(self, path: str):
        """Load traces from file"""
        if not os.path.exists(path):
            return
        
        with open(path, "r") as f:
            data = json.load(f)
            for item in data:
                trace = AgentTrace(**item)
                self.traces[trace.session_id] = trace
    
    def get_trace(self, session_id: str) -> Optional[AgentTrace]:
        """Get trace by session ID"""
        return self.traces.get(session_id)
    
    def get_all_traces(self) -> List[AgentTrace]:
        """Get all traces"""
        return list(self.traces.values())


async def track_execution(
    tracker: TraceTracker,
    session_id: str,
    task_id: str,
    prompt: str
) -> AgentTrace:
    """Context manager for tracking execution"""
    return tracker.start_trace(session_id, task_id, prompt)


__all__ = ["TraceTracker", "track_execution"]