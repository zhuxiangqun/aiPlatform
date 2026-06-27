import logging
"""
Context Compression

Five-level context compression strategy with per-tool-type summaries and
iterative summary preservation. Includes async tool output summarization
to prevent context window exhaustion during tool-heavy tasks.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import os


class CompressionLevel(Enum):
    """Compression level based on token usage"""
    NORMAL = (0, 0.85)
    WARNING = (0.85, 0.90)
    REPLACE = (0.90, 0.93)
    PRUNE = (0.93, 0.96)
    AGGRESSIVE = (0.96, 0.99)
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
    """Five-level context compression with anti-thrashing and iterative summary."""

    def __init__(self, config: Optional[Dict] = None):
        self._config = config or {}
        self._thresholds = self._init_thresholds()
        self._compression_stats: List[Tuple[int, int]] = []  # (before, after) msg counts
        self._prev_summary: Optional[str] = None

    def _init_thresholds(self) -> Dict[CompressionLevel, float]:
        return {
            CompressionLevel.NORMAL: 0.85,
            CompressionLevel.WARNING: 0.90,
            CompressionLevel.REPLACE: 0.93,
            CompressionLevel.PRUNE: 0.96,
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

    async def _replace_old_outputs(self, context: List[Dict], protected_roles: Optional[List[str]] = None) -> List[Dict]:
        """Replace old tool outputs with informed per-tool-type summaries.

        Args:
            context: List of message dicts.
            protected_roles: Roles that must never be compressed (e.g. ["system_arch"]).
        """
        protected = set(protected_roles or [])
        result = []
        tool_output_count = 0

        for msg in context:
            role = msg.get("role", "")
            meta_role = msg.get("meta", {}).get("role", "") if isinstance(msg.get("meta"), dict) else ""

            # Never compress protected system-level messages (CLAUDE.md, Domain Prompt, etc.)
            if role == "system" and (meta_role in protected or "system_arch" in protected):
                result.append(msg)
                continue

            if role == "tool":
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


# ── Tool output budget: background summarization ───────────────────

TOOL_OUTPUT_SUMMARY_THRESHOLD = 2000   # chars — trigger async summary above this
TOOL_OUTPUT_SUMMARY_TIMEOUT = 3.0       # seconds — fallback to truncation


async def _background_tool_summarize(
    tool_call_id: str,
    tool_name: str,
    raw_output: str,
    scratchpad: Dict[str, str],
) -> None:
    """Background task: generate LLM summary for large tool outputs.

    Must ALWAYS write a final state to scratchpad — even on timeout or error.
    This prevents "ghost placeholders" in the agent's context.
    """
    import time as _time
    _t0 = _time.time()
    try:
        from core.harness.memory.metrics import inc_tool_truncated
        inc_tool_truncated(tool_name)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    try:
        summary = await asyncio.wait_for(
            _llm_summarize_tool_output(tool_name, raw_output),
            timeout=TOOL_OUTPUT_SUMMARY_TIMEOUT,
        )
        scratchpad[tool_call_id] = summary
    except asyncio.TimeoutError:
        scratchpad[tool_call_id] = (
            f"[TIMEOUT] 工具摘要生成超时({TOOL_OUTPUT_SUMMARY_TIMEOUT}s)。"
            f"原始数据({len(raw_output)}chars)前1000字: {raw_output[:1000]}"
        )
    except Exception as e:
        scratchpad[tool_call_id] = (
            f"[ERROR] 工具摘要生成失败: {e}。"
            f"原始数据({len(raw_output)}chars)前1000字: {raw_output[:1000]}"
        )
    try:
        from core.harness.memory.metrics import observe_tool_summary
        observe_tool_summary(tool_name, _time.time() - _t0)
    except Exception as e:
        logging.debug(str(e), exc_info=True)


async def _llm_summarize_tool_output(tool_name: str, raw_output: str) -> str:
    """Call LLM to generate structured summary of tool output."""
    try:
        from core.harness.infrastructure.infra_llm_adapter import InfraLLMAdapter
        from core.harness.utils.model_injection import best_model_for_purpose
        model_name = best_model_for_purpose("doc_llm") or ""
        adapter = InfraLLMAdapter(model_name=model_name) if model_name else None
        if adapter is None:
            raise RuntimeError("no LLM model configured for tool summarization")

        prompt = (
            f"工具 [{tool_name}] 返回了以下输出。请生成一个简短的结构化摘要，"
            f"保留关键数据（文件路径、错误码、返回值、关键数字），忽略冗余内容。\n\n"
            f"输出({len(raw_output)}字符):\n{raw_output[:3000]}"
        )
        result = await adapter.chat_complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=500,
        )
        content = getattr(result, "content", str(result))
        return f"[摘要] {content.strip()}" if content else raw_output[:1000]
    except Exception:
        raise


__all__ = [
    "CompressionLevel", "ContextState", "ContextCompression",
    "TOOL_OUTPUT_SUMMARY_THRESHOLD", "_background_tool_summarize",
]


__all__ = ["ContextCompression", "CompressionLevel", "ContextState"]
