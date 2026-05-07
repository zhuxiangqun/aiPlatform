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
    """Unified memory manager with three-layer architecture.

    Supports namespace-based isolation: each agent can use its own namespace
    to keep memories separate (e.g., 'architect', 'programmer', 'qa').
    """

    def __init__(self, config: Optional[MemoryConfig] = None, namespace: str = "default"):
        self._config = config or MemoryConfig()
        self.namespace = namespace
        self._persist_callback = None  # injected by service layer for SQLite persistence

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

    async def get_reminders(self, token_usage_ratio: float = 0.0, consecutive_reads: int = 0,
                            tool_failed: bool = False) -> List[str]:
        """Lightweight reminder check without full context assembly.

        Used by the agent execution loop as a bridge hook.
        Returns a list of reminder strings (empty if no reminders triggered).
        """
        if not self._reminders:
            return []
        exec_state = {
            "token_usage_ratio": token_usage_ratio,
            "consecutive_reads": consecutive_reads,
            "tool_failed": tool_failed,
        }
        reminder = await self._reminders.check_and_inject(exec_state)
        return [reminder] if reminder else []
    
    async def save_interaction(
        self,
        user_message: str,
        assistant_message: str,
        tool_calls: Optional[List[Dict]] = None,
        stability: str = "medium",
    ):
        """Save an interaction to memory.

        Args:
            stability: "high" (stable fact/decision → SQLite), "medium" (normal),
                       "low" (transient tool output → Working only, skip Episodic).
        """
        # Save to working memory (all stability levels)
        self._working.add("user", user_message)
        self._working.add("assistant", assistant_message)

        # Episodic: skip low-stability (transient tool output, debug traces)
        if stability != "low":
            await self._episodic.add_interaction(user_message, assistant_message, tool_calls)

        # Update episodic summary if needed
        if stability != "low" and await self._episodic.should_update():
            summary = await self._episodic.update_summary()
            logger.info(f"Updated episodic summary: {summary.summary[:100]}")

        # Bridge to SQLite: only high-stability (stable facts, decisions)
        if self._persist_callback and stability == "high":
            try:
                await self._persist_callback(
                    namespace=self.namespace,
                    user_message=user_message,
                    assistant_message=assistant_message,
                )
            except Exception:
                pass
    
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


# Per-namespace memory managers
_memory_managers: Dict[str, MemoryManager] = {}
_default_manager: Optional[MemoryManager] = None


def get_memory_manager(config: Optional[MemoryConfig] = None, namespace: str = "default") -> MemoryManager:
    """Get memory manager for a namespace.

    When namespace='default', returns the legacy singleton (backward compat).
    Other namespaces get their own isolated MemoryManager instance.
    """
    global _default_manager, _memory_managers
    if namespace == "default" or not namespace:
        if _default_manager is None:
            _default_manager = MemoryManager(config, namespace="default")
        return _default_manager
    if namespace not in _memory_managers:
        _memory_managers[namespace] = MemoryManager(config, namespace=namespace)
    return _memory_managers[namespace]


__all__ = [
    "MemoryConfig",
    "BuildContextResult",
    "MemoryManager",
    "get_memory_manager"
]