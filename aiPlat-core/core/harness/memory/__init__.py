"""
Memory Module

Provides multi-layer memory architecture: Working, Episodic, Semantic.
"""

from .working import WorkingMemory, Message
from .episodic import EpisodicMemory, SessionSummary
from .semantic import SemanticMemory, MemoryItem
from .compression import ContextCompression, CompressionLevel, ContextState
from .reminders import SystemReminders, ReminderRule, ReminderType, get_system_reminders
from .manager import MemoryManager, MemoryConfig, BuildContextResult, get_memory_manager
from .base import MemoryBase, MemoryScope, MemoryEntry, MemoryType
from .short_term import ShortTermMemory
from .long_term import LongTermMemory
from .session import SessionManager

__all__ = [
    "WorkingMemory",
    "Message",
    "EpisodicMemory",
    "SessionSummary",
    "SemanticMemory",
    "MemoryItem",
    "ContextCompression",
    "CompressionLevel",
    "ContextState",
    "SystemReminders",
    "ReminderRule",
    "ReminderType",
    "get_system_reminders",
    "MemoryManager",
    "MemoryConfig",
    "BuildContextResult",
    "get_memory_manager",
    "MemoryBase",
    "MemoryScope",
    "MemoryEntry",
    "MemoryType",
    "ShortTermMemory",
    "LongTermMemory",
    "SessionManager",
]
