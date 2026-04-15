"""
Context Compression

Five-level context compression strategy.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class CompressionLevel(Enum):
    """Compression level based on token usage"""
    NORMAL = (0, 0.70)
    WARNING = (0.70, 0.80)
    REPLACE = (0.80, 0.85)
    PRUNE = (0.85, 0.90)
    AGGRESSIVE = (0.90, 0.99)
    EMERGENCY = (0.99, 1.0)


@dataclass
class ContextState:
    """Current state of the context"""
    token_usage: int
    token_limit: int
    message_count: int
    
    @property
    def usage_ratio(self) -> float:
        if self.token_limit == 0:
            return 0
        return self.token_usage / self.token_limit


class ContextCompression:
    """Five-level context compression"""
    
    def __init__(self, config: Optional[Dict] = None):
        self._config = config or {}
        self._thresholds = self._init_thresholds()
    
    def _init_thresholds(self) -> Dict[CompressionLevel, float]:
        return {
            CompressionLevel.NORMAL: 0.70,
            CompressionLevel.WARNING: 0.80,
            CompressionLevel.REPLACE: 0.85,
            CompressionLevel.PRUNE: 0.90,
            CompressionLevel.AGGRESSIVE: 0.99,
            CompressionLevel.EMERGENCY: 1.0
        }
    
    def get_level(self, usage_ratio: float) -> CompressionLevel:
        """Determine compression level based on usage"""
        for level, threshold in self._thresholds.items():
            if usage_ratio < threshold:
                return level
        return CompressionLevel.EMERGENCY
    
    async def compress(
        self,
        context: List[Dict],
        state: ContextState
    ) -> List[Dict]:
        """Compress context based on current level"""
        level = self.get_level(state.usage_ratio)
        
        if level == CompressionLevel.NORMAL:
            return context
        
        elif level == CompressionLevel.WARNING:
            return context  # Just monitor, don't compress yet
        
        elif level == CompressionLevel.REPLACE:
            return await self._replace_old_outputs(context)
        
        elif level == CompressionLevel.PRUNE:
            return await self._prune_old_messages(context, keep_last=5)
        
        elif level == CompressionLevel.AGGRESSIVE:
            return await self._aggressive_compress(context)
        
        elif level == CompressionLevel.EMERGENCY:
            return await self._emergency_compress(context)
        
        return context
    
    async def _replace_old_outputs(self, context: List[Dict]) -> List[Dict]:
        """Replace old tool outputs with summary references"""
        result = []
        tool_output_count = 0
        
        for msg in context:
            if msg.get("role") == "tool":
                tool_output_count += 1
                # Keep only every other tool output after the first 3
                if tool_output_count <= 3 or tool_output_count % 2 == 0:
                    result.append(msg)
                else:
                    result.append({
                        "role": "system",
                        "content": f"[Tool output #{tool_output_count} summarized]"
                    })
            else:
                result.append(msg)
        
        return result
    
    async def _prune_old_messages(
        self,
        context: List[Dict],
        keep_last: int = 5
    ) -> List[Dict]:
        """Keep only recent N messages fully"""
        # Keep system prompt
        system_msgs = [m for m in context if m.get("role") == "system"]
        # Keep last N non-system messages
        non_system = [m for m in context if m.get("role") != "system"]
        
        return system_msgs + non_system[-keep_last:]
    
    async def _aggressive_compress(self, context: List[Dict]) -> List[Dict]:
        """Aggressive compression - keep only essential info"""
        # Keep only system prompt and last 2 messages
        system_msgs = [m for m in context if m.get("role") == "system"]
        recent = context[-2:] if len(context) > 2 else context
        
        # Add summary placeholder
        summary_msg = {
            "role": "system",
            "content": f"[Previous {len(context) - len(system_msgs) - 2} messages summarized]"
        }
        
        return system_msgs + [summary_msg] + recent
    
    async def _emergency_compress(self, context: List[Dict]) -> List[Dict]:
        """Emergency compression - LLM full summary needed"""
        # In real implementation, call LLM to generate full summary
        # For now, just keep system + last message
        system_msgs = [m for m in context if m.get("role") == "system"]
        
        return system_msgs + [context[-1]] if context else system_msgs
    
    def should_trigger_compression(self, state: ContextState) -> bool:
        """Check if compression should be triggered"""
        level = self.get_level(state.usage_ratio)
        return level != CompressionLevel.NORMAL


__all__ = ["ContextCompression", "CompressionLevel", "ContextState"]