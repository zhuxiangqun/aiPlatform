"""
Context Loader Types

Types for progressive context loading.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class LoadStrategy(Enum):
    """Context loading strategy"""
    LAZY = "lazy"       # Load on demand
    EAGER = "eager"     # Pre-load related context
    ADAPTIVE = "adaptive"  # Adaptive based on task


class Priority(Enum):
    """Context priority levels"""
    P0 = 0  # Current file (highest)
    P1 = 1  # Dependencies
    P2 = 2  # Config files
    P3 = 3  # Documentation
    P4 = 4  # Other files (lowest)


@dataclass
class FileContext:
    """Loaded file context"""
    path: str
    content: str
    priority: Priority
    size: int
    token_count: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DirectorySummary:
    """Directory structure summary"""
    root: str
    structure: str
    file_count: int
    total_size: int
    max_depth: int
    excludes: List[str] = field(default_factory=list)

    def to_prompt(self) -> str:
        """Convert to prompt format"""
        return f"""## Project Structure: {self.root}

{self.structure}

Statistics: {self.file_count} files, {self.total_size} bytes
"""


@dataclass
class LoadedContext:
    """Loaded context result"""
    files: List[FileContext]
    directory_summary: Optional[DirectorySummary]
    total_tokens: int
    strategy: LoadStrategy
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def file_count(self) -> int:
        return len(self.files)

    def to_prompt(self) -> str:
        """Convert to prompt format"""
        parts = []
        
        if self.directory_summary:
            parts.append(self.directory_summary.to_prompt())
        
        # Sort by priority
        sorted_files = sorted(self.files, key=lambda f: f.priority.value)
        
        for fc in sorted_files[:10]:  # Limit to top 10 files
            parts.append(f"\n## {fc.path}\n```\n{fc.content[:1000]}...\n```")
        
        return "\n".join(parts)


@dataclass
class TrimmedContext:
    """Trimmed context result"""
    content: str
    original_tokens: int
    trimmed_tokens: int
    removed_files: List[str] = field(default_factory=list)

    @property
    def reduction_ratio(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return (self.original_tokens - self.trimmed_tokens) / self.original_tokens


@dataclass
class TaskSpec:
    """Task specification for context loading"""
    type: str  # "code_edit", "code_review", "debug", "general"
    target_file: Optional[str] = None
    language: Optional[str] = None
    scope: Dict[str, Any] = field(default_factory=dict)


__all__ = [
    "LoadStrategy",
    "Priority",
    "FileContext",
    "DirectorySummary",
    "LoadedContext",
    "TrimmedContext",
    "TaskSpec",
]