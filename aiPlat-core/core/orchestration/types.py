"""Shared orchestration types — extracted to break circular imports."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class ChainStep:
    """A single step in the execution chain."""
    id: str
    role: str
    depends_on: List[str] = field(default_factory=list)
