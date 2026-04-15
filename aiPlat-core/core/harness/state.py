"""
Agent State Definitions
"""

from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any


class AgentStateEnum(Enum):
    """Agent 状态枚举"""
    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    TERMINATED = "terminated"


@dataclass
class AgentLifecycleState:
    """Agent lifecycle state (CREATED, RUNNING, etc.)
    
    Renamed from AgentState to avoid collision with LangGraph's AgentState 
    (which is a TypedDict for graph execution state).
    """
    agent_id: str
    status: AgentStateEnum
    created_at: float
    updated_at: float
    error: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.created_at is None:
            self.created_at = datetime.now().timestamp()
        if self.updated_at is None:
            self.updated_at = self.created_at
    
    def transition_to(self, new_status: AgentStateEnum) -> "AgentLifecycleState":
        valid_transitions = {
            AgentStateEnum.CREATED: [AgentStateEnum.INITIALIZING, AgentStateEnum.TERMINATED],
            AgentStateEnum.INITIALIZING: [AgentStateEnum.READY, AgentStateEnum.ERROR, AgentStateEnum.TERMINATED],
            AgentStateEnum.READY: [AgentStateEnum.RUNNING, AgentStateEnum.STOPPED, AgentStateEnum.TERMINATED],
            AgentStateEnum.RUNNING: [AgentStateEnum.READY, AgentStateEnum.PAUSED, AgentStateEnum.ERROR, AgentStateEnum.STOPPED],
            AgentStateEnum.PAUSED: [AgentStateEnum.RUNNING, AgentStateEnum.STOPPED, AgentStateEnum.TERMINATED],
            AgentStateEnum.STOPPED: [AgentStateEnum.READY, AgentStateEnum.TERMINATED],
            AgentStateEnum.ERROR: [AgentStateEnum.INITIALIZING, AgentStateEnum.TERMINATED],
            AgentStateEnum.TERMINATED: [],
        }
        
        if new_status not in valid_transitions.get(self.status, []):
            raise ValueError(f"Invalid state transition: {self.status} -> {new_status}")
        
        return AgentLifecycleState(
            agent_id=self.agent_id,
            status=new_status,
            created_at=self.created_at,
            updated_at=datetime.now().timestamp(),
            error=self.error,
            metadata=self.metadata
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "metadata": self.metadata
        }

# Backward compatibility alias
AgentState = AgentLifecycleState