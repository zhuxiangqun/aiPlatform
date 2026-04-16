"""
ContextGate (Phase 3 - placeholder).

In later phases this gate will:
- enforce token budget & compaction strategies
- integrate with ContextAssembler / PromptAssembler

For Phase 3, it only provides a simple interface and no-op implementations,
so we can wire it into syscalls without changing behavior.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List


class ContextGate:
    def __init__(self) -> None:
        pass

    def prepare_llm_args(self, prompt: Any, *, context: Dict[str, Any] | None = None) -> Any:
        """
        Phase 3 minimal:
        - optional truncation guardrail (disabled by default)
        - does NOT attempt token counting (Phase 4 will introduce PromptContext budgets)
        """
        max_chars = int(os.getenv("AIPLAT_CONTEXT_MAX_CHARS", "0") or "0")
        max_messages = int(os.getenv("AIPLAT_CONTEXT_MAX_MESSAGES", "0") or "0")
        if max_chars <= 0 and max_messages <= 0:
            return prompt

        if isinstance(prompt, str):
            return prompt[:max_chars] if max_chars > 0 else prompt

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

    def prepare_tool_args(self, args: Dict[str, Any], *, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Placeholder: return args as-is."""
        return args
