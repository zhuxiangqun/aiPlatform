"""
Memory Manager

Integrates Working, Episodic, and Semantic memory layers.
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from .working import WorkingMemory
from .episodic import EpisodicMemory
from .semantic import SemanticMemory
from .compression import ContextCompression, ContextState
from .reminders import SystemReminders, get_system_reminders

logger = logging.getLogger(__name__)


@dataclass
class MemoryConfig:
    """Memory system configuration"""
    working_tokens: int = 30000
    episodic_update_interval: int = 5
    max_messages: int = 20
    vector_store_type: str = "simple"
    enable_compression: bool = True
    enable_reminders: bool = True


@dataclass
class BuildContextResult:
    """Result of building context"""
    messages: List[Dict]
    token_count: int
    reminder: Optional[str] = None


class MemoryManager:
    """Unified memory manager with three-layer architecture"""
    
    def __init__(self, config: Optional[MemoryConfig] = None):
        self._config = config or MemoryConfig()
        
        # Initialize layers
        self._working = WorkingMemory(
            max_tokens=self._config.working_tokens,
            max_messages=self._config.max_messages
        )
        self._episodic = EpisodicMemory(
            update_interval=self._config.episodic_update_interval
        )
        self._semantic = SemanticMemory(
            store_type=self._config.vector_store_type
        )
        self._compression = ContextCompression()
        self._reminders = get_system_reminders() if self._config.enable_reminders else None
    
    async def build_context(
        self,
        current_query: str,
        system_prompt: str
    ) -> BuildContextResult:
        """Build complete context from all memory layers"""
        
        # 1. Retrieve relevant semantic memories
        relevant_memories = await self._semantic.retrieve(current_query)
        
        # 2. Get episodic summary
        episodic_summary = self._episodic.get_summary()
        
        # 3. Get working memory context
        working_context = self._working.get_context()
        
        # 4. Build messages list
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add semantic memories as context
        if relevant_memories:
            memory_context = "## Relevant Past Context\n"
            for mem in relevant_memories[:3]:
                memory_context += f"- {mem.content[:200]}...\n"
            messages.append({"role": "system", "content": memory_context})
        
        # Add episodic summary
        if episodic_summary:
            messages.append({
                "role": "system",
                "content": f"## Session Summary\n{episodic_summary}"
            })
        
        # Add working memory
        messages.extend(working_context)
        
        # Add current query
        messages.append({"role": "user", "content": current_query})
        
        # 5. Check compression
        total_tokens = sum(len(m.get("content", "").split()) * 1.3 for m in messages)
        state = ContextState(
            token_usage=int(total_tokens),
            token_limit=self._config.working_tokens,
            message_count=len(messages)
        )
        
        # 6. Check for system reminders
        reminder = None
        if self._reminders:
            exec_state = {
                "token_usage_ratio": total_tokens / self._config.working_tokens,
                "consecutive_reads": self._count_consecutive_reads(working_context),
                "tool_failed": self._check_last_tool_failed(working_context)
            }
            reminder = await self._reminders.check_and_inject(exec_state)
        
        # 7. Apply compression if needed
        if self._config.enable_compression and self._compression.should_trigger_compression(state):
            messages = await self._compression.compress(messages, state)
        
        return BuildContextResult(
            messages=messages,
            token_count=int(total_tokens),
            reminder=reminder
        )
    
    async def save_interaction(
        self,
        user_message: str,
        assistant_message: str,
        tool_calls: Optional[List[Dict]] = None
    ):
        """Save an interaction to memory"""
        # Save to working memory
        self._working.add("user", user_message)
        self._working.add("assistant", assistant_message)
        
        # Save to episodic memory
        await self._episodic.add_interaction(user_message, assistant_message, tool_calls)
        
        # Update episodic summary if needed
        if await self._episodic.should_update():
            summary = await self._episodic.update_summary()
            logger.info(f"Updated episodic summary: {summary.summary[:100]}")
    
    async def capture_to_semantic(
        self,
        key: str,
        content: str,
        metadata: Optional[Dict] = None
    ):
        """Capture important info to semantic memory"""
        await self._semantic.store(key, content, metadata)
    
    def _count_consecutive_reads(self, context: List[Dict]) -> int:
        """Count consecutive read operations"""
        reads = 0
        for msg in reversed(context[-10:]):
            tool = msg.get("metadata", {}).get("tool", "")
            if tool in ["Read", "Grep", "Glob"]:
                reads += 1
            else:
                break
        return reads
    
    def _check_last_tool_failed(self, context: List[Dict]) -> bool:
        """Check if last tool call failed"""
        if context:
            last = context[-1]
            return last.get("metadata", {}).get("tool_failed", False)
        return False
    
    def get_stats(self) -> Dict:
        """Get memory system statistics"""
        return {
            "working": {
                "tokens": self._working.token_count,
                "messages": self._working.message_count
            },
            "semantic": self._semantic.get_stats(),
            "compression": "enabled" if self._config.enable_compression else "disabled",
            "reminders": "enabled" if self._config.enable_reminders else "disabled"
        }


# Global manager instance
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager(config: Optional[MemoryConfig] = None) -> MemoryManager:
    """Get global memory manager"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager(config)
    return _memory_manager


__all__ = [
    "MemoryConfig",
    "BuildContextResult",
    "MemoryManager",
    "get_memory_manager"
]