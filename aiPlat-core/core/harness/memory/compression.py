"""
Context Compression

Five-level context compression strategy with per-tool-type summaries and
iterative summary preservation.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class CompressionLevel(Enum):
    """Compression level based on token usage"""
    NORMAL = (0, 0.70)
    WARNING = (0.90, 0.92)
    REPLACE = (0.92, 0.94)
    PRUNE = (0.94, 0.96)
    AGGRESSIVE = (0.96, 0.98)
    EMERGENCY = (0.98, 1.0)


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
    """Five-level context compression with anti-thrashing and iterative summary."""

    def __init__(self, config: Optional[Dict] = None):
        self._config = config or {}
        self._thresholds = self._init_thresholds()
        self._compression_stats: List[Tuple[int, int]] = []  # (before, after) msg counts
        self._prev_summary: Optional[str] = None

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
            result = await self._replace_old_outputs(context)

        elif level == CompressionLevel.PRUNE:
            result = await self._prune_old_messages(context, keep_last=5)

        elif level == CompressionLevel.AGGRESSIVE:
            result = await self._aggressive_compress(context)

        elif level == CompressionLevel.EMERGENCY:
            result = await self._emergency_compress(context)
        else:
            return context

        # Anti-thrashing: track effectiveness, skip if consistently <10% savings
        self._compression_stats.append((len(context), len(result)))
        if len(self._compression_stats) > 3:
            self._compression_stats.pop(0)
        if len(self._compression_stats) >= 2:
            savings = [(b - a) / max(b, 1) for b, a in self._compression_stats[-2:]]
            if all(s < 0.10 for s in savings):
                return context  # skip — compression isn't helping

        return result

    @staticmethod
    def _priority_order(msg: Dict) -> int:
        """Return sort key: 0=high (keep), 1=medium, 2=low (delete first)."""
        p = str(msg.get("priority") or msg.get("metadata", {}).get("priority", "")).lower()
        if p == "high":
            return 0
        if p == "low":
            return 2
        return 1  # medium / unset

    @staticmethod
    def _summarize_tool_msg(msg: Dict, idx: int) -> str:
        """Generate a per-tool-type informed summary preserving actionable info."""
        content = str(msg.get("content", ""))
        name = msg.get("name", "") or msg.get("tool_name", "") or msg.get("tool_call_id", "") or "tool"
        # Extract first meaningful line (skip empty/whitespace prefixes)
        snippet = ""
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith(("#", "//", "<!--")):
                snippet = stripped[:100]
                break
        if not snippet:
            snippet = content[:100].replace("\n", " ").strip()
        if snippet:
            return f"[{name}] {snippet}"
        return f"[{name}] executed"

    async def _replace_old_outputs(self, context: List[Dict]) -> List[Dict]:
        """Replace old tool outputs with informed per-tool-type summaries."""
        result = []
        tool_output_count = 0

        for msg in context:
            if msg.get("role") == "tool":
                tool_output_count += 1
                if tool_output_count <= 3 or tool_output_count % 2 == 0:
                    result.append(msg)
                else:
                    result.append({
                        "role": "system",
                        "content": self._summarize_tool_msg(msg, tool_output_count),
                    })
            else:
                result.append(msg)

        return result

    async def _prune_old_messages(
        self,
        context: List[Dict],
        keep_last: int = 5
    ) -> List[Dict]:
        """Keep only recent N messages fully, respecting priority."""
        system_msgs = [m for m in context if m.get("role") == "system"]
        non_system = [m for m in context if m.get("role") != "system"]
        non_system.sort(key=self._priority_order)
        return system_msgs + non_system[-keep_last:]

    async def _aggressive_compress(self, context: List[Dict]) -> List[Dict]:
        """Aggressive compression — preserve previous summary, append new turns."""
        system_msgs = [m for m in context if m.get("role") == "system"]
        non_system = [m for m in context if m.get("role") != "system"]
        non_system.sort(key=self._priority_order)

        # Detect and preserve previous summary for iterative update
        prev_summary_content = self._prev_summary
        if not prev_summary_content:
            for msg in context:
                c = str(msg.get("content", ""))
                if msg.get("role") in ("system", "assistant") and ("summarized" in c.lower() or "CONTEXT_SUMMARY" in c):
                    prev_summary_content = c
                    break

        recent = non_system[-2:] if len(non_system) > 2 else non_system
        if prev_summary_content:
            summary_msg = {
                "role": "system",
                "content": (
                    f"CONTEXT_SUMMARY (updated):\n{prev_summary_content}\n\n"
                    f"[+{len(non_system) - 2} new turns incorporated]"
                ),
            }
        else:
            summary_msg = {
                "role": "system",
                "content": f"[Previous {max(0, len(non_system) - 2)} messages summarized]",
            }

        self._prev_summary = str(summary_msg["content"])
        return system_msgs + [summary_msg] + recent

    async def _emergency_compress(self, context: List[Dict]) -> List[Dict]:
        """Emergency compression — keep only system + last message."""
        system_msgs = [m for m in context if m.get("role") == "system"]
        non_system = [m for m in context if m.get("role") != "system"]
        non_system.sort(key=self._priority_order)
        return system_msgs + [non_system[-1]] if non_system else system_msgs

    def should_trigger_compression(self, state: ContextState) -> bool:
        """Check if compression should be triggered"""
        level = self.get_level(state.usage_ratio)
        return level != CompressionLevel.NORMAL


__all__ = ["ContextCompression", "CompressionLevel", "ContextState"]
