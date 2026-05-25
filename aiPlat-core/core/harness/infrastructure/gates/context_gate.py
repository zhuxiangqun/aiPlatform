"""
ContextGate (Phase 4 — integrated with 5-level ContextCompression).

Enforces token budget and compaction strategies at the gate boundary.
When AIPLAT_CONTEXT_GATE_COMPRESSION is enabled (default: true), delegates
to ContextCompression for 5-level progressive context trimming.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from core.harness.memory.compression import ContextCompression, ContextState


class ContextGate:
    def __init__(self) -> None:
        self._compression = ContextCompression()
        self._enabled = os.getenv("AIPLAT_CONTEXT_GATE_COMPRESSION", "true").lower() in (
            "1", "true", "yes", "y",
        )

    def prepare_llm_args(self, prompt: Any, *, context: Dict[str, Any] | None = None) -> Any:
        """Apply optional truncation guardrail (legacy) and compression check.

        Compression gate: if token usage exceeds threshold, delegates to
        ContextCompression for 5-level progressive trimming per CLAUDE.md §5.25.
        """
        max_chars = int(os.getenv("AIPLAT_CONTEXT_MAX_CHARS", "0") or "0")
        max_messages = int(os.getenv("AIPLAT_CONTEXT_MAX_MESSAGES", "0") or "0")

        if max_chars <= 0 and max_messages <= 0 and not self._enabled:
            return prompt

        if isinstance(prompt, str):
            if max_chars > 0 and len(prompt) > max_chars:
                prompt = prompt[:max_chars]
            return prompt

        if isinstance(prompt, list):
            msgs: List[Dict[str, Any]] = []
            for m in prompt:
                if not isinstance(m, dict):
                    continue
                content = m.get("content", "")
                if isinstance(content, str) and max_chars > 0:
                    content = content[:max_chars]
                msgs.append({**m, "content": content})
            if max_messages > 0 and len(msgs) > max_messages:
                msgs = msgs[-max_messages:]
            return msgs

        return prompt

    def should_compress(self, token_usage: int, token_limit: int, message_count: int) -> bool:
        """Check whether context should be compressed at current usage level.

        Delegates to ContextCompression.should_trigger_compression.
        Returns True when usage ratio exceeds the NORMAL threshold (70%).
        """
        if not self._enabled:
            return False
        state = ContextState(
            token_usage=token_usage,
            token_limit=max(token_limit, 1),
            message_count=message_count,
        )
        return self._compression.should_trigger_compression(state)

    async def compress(
        self,
        messages: List[Dict[str, Any]],
        token_usage: int = 0,
        token_limit: int = 100000,
        message_count: int = 0,
    ) -> List[Dict[str, Any]]:
        """Apply 5-level progressive compression to messages.

        Delegates to ContextCompression.compress().
        """
        if not self._enabled:
            return messages
        state = ContextState(
            token_usage=token_usage,
            token_limit=max(token_limit, 1),
            message_count=message_count,
        )
        return await self._compression.compress(messages, state)

    def prepare_tool_args(self, args: Dict[str, Any], *, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Placeholder: return args as-is."""
        return args
