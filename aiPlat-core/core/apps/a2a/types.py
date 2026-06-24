"""A2A Protocol data types — follows Google A2A spec v0.3."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskEvent:
    """A2A streaming event during task execution."""
    type: str
    timestamp: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    """A2A task — maps to aiPlat run_id."""
    id: str
    status: TaskStatus = TaskStatus.PENDING
    user_input: str = ""
    result: Any = None
    error: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    artifacts: List[Dict] = field(default_factory=list)
    events: List[TaskEvent] = field(default_factory=list)
