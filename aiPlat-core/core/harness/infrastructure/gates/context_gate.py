"""
ContextGate (Phase 4 — integrated with 5-level ContextCompression).

Enforces token budget and compaction strategies at the gate boundary.
When AIPLAT_CONTEXT_GATE_COMPRESSION is enabled (default: true), delegates
to ContextCompression for 5-level progressive context trimming.
"""

from __future__ import annotations

import logging
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
        """Apply pre-context validation, then truncation guardrail and compression check.

        Pre-validation: dedup, staleness check, conflict detection before
        sending to the model. Reduces redundant token spend.
        """
        # Pre-context validation (dedup, staleness, conflicts)
        if isinstance(prompt, list) and self._enabled:
            try:
                from .context_validator import get_context_validator
                validator = get_context_validator()
                memory_ctx = (context or {}).get("memory_context") if context else None
                v = validator.validate(prompt, memory_context=memory_ctx)
                if v.removed_count > 0 or v.stale_warnings or v.conflict_markers:
                    import logging
                    _log = logging.getLogger("context_gate")
                    _log.info(
                        "Context validation: score=%d dedup_removed=%d tokens_saved=%d stale=%d conflicts=%d",
                        v.quality_score, v.removed_count, v.token_saved,
                        len(v.stale_warnings), len(v.conflict_markers),
                    )
                prompt = v.deduplicated
            except Exception as e:
                logging.debug(str(e), exc_info=True)

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
            total_json_saved = 0
            for m in prompt:
                if not isinstance(m, dict):
                    continue
                content = m.get("content", "")
                # JSON-aware compression for tool outputs
                if isinstance(content, str) and self._detect_json_content(content):
                    compressed, saved = self._compress_json_content(content)
                    if saved > 0:
                        total_json_saved += saved
                        content = compressed
                if isinstance(content, str) and max_chars > 0:
                    content = content[:max_chars]
                msgs.append({**m, "content": content})
            if total_json_saved > 0:
                _log = logging.getLogger("context_gate")
                _log.info("JSON compression: ~%d tokens saved", total_json_saved)
            if max_messages > 0 and len(msgs) > max_messages:
                msgs = msgs[-max_messages:]
            return msgs

        return prompt

    def should_compress(self, token_usage: int, token_limit: int, message_count: int) -> bool:
        """Check whether context should be compressed at current usage level.

        Delegates to ContextCompression.should_trigger_compression.
        Returns True when usage ratio reaches the NORMAL threshold (85%).
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
        """Validate and sanitize tool arguments before execution.
        
        Applies: type validation, size limits, injection pattern detection.
        """
        if not isinstance(args, dict):
            return {}
        
        sanitized = {}
        for key, value in args.items():
            if not isinstance(key, str):
                continue
            # Sanitize string values: detect common injection patterns
            if isinstance(value, str):
                if len(value) > 100_000:  # 100KB limit
                    value = value[:100_000] + " [TRUNCATED]"
                # Check for potential prompt injection markers
                if "忽略" in value and "指令" in value:
                    import logging
                    logging.getLogger("context_gate").warning(
                        "Potential prompt injection detected in tool arg '%s'", key)
            sanitized[key] = value
        
        return sanitized

    def apply_profile(self, messages: List[Dict[str, Any]], profile: str = "code") -> List[Dict[str, Any]]:
        """Apply context profile strategy — control what the model sees.

        Profiles:
          "minimal"  — keep system prompt only, strip all other content bodies
          "code"     — keep function signatures + imports, compress bodies
          "debug"    — keep recent changes (last 3) + error messages, compress rest
          "deep"     — full context, no compression beyond dedup
        """
        if not messages or profile == "deep":
            return messages

        result: List[Dict[str, Any]] = []

        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                result.append(msg)
                continue

            role = str(msg.get("role", "")).lower()
            content = str(msg.get("content", ""))

            # Always preserve system messages
            if role == "system":
                result.append(msg)
                continue

            if profile == "minimal":
                # Strip content from non-system messages, keep role structure
                if role != "system":
                    result.append({**msg, "content": "[context trimmed]"})
                else:
                    result.append(msg)

            elif profile == "code":
                # Strip implementation bodies, keep imports/signatures
                if len(content) > 500:
                    stripped = self._strip_bodies(content)
                    result.append({**msg, "content": stripped})
                else:
                    result.append(msg)

            elif profile == "debug":
                # Keep last 3 messages in full, compress older ones
                if i >= len(messages) - 3:
                    result.append(msg)
                elif len(content) > 300:
                    result.append({**msg, "content": content[:300] + " [...]"})
                else:
                    result.append(msg)

            else:
                result.append(msg)

        return result

    def _strip_bodies(self, text: str) -> str:
        """Strip function/method bodies but keep signatures and imports."""
        import re as _re
        lines = text.split('\n')
        result_lines = []
        in_body = False

        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith('import ') or stripped.startswith('from '):
                result_lines.append(line)
                in_body = False; continue
            if _re.match(r'^\s*(def |class |async def )', line):
                result_lines.append(line)
                in_body = True; continue
            if in_body and ('"""' in stripped or "'''" in stripped):
                result_lines.append(line); continue
            if stripped.startswith('@'):
                result_lines.append(line); continue
            if in_body and stripped:
                if not result_lines or result_lines[-1] != '  # [...]':
                    result_lines.append('  # [...]')
                continue
            result_lines.append(line)
        return '\n'.join(result_lines)

    def _compress_json_content(self, content: str, max_rows: int = 10) -> tuple[str, int]:
        """Compress JSON arrays using key-header + row-value layout.

        Headroom SmartCrusher-inspired: extracts repeated keys once as header,
        lists values row-by-row. Falls back to truncation for non-array JSON.

        Returns (compressed_text, tokens_saved).
        """
        import json as _json
        try:
            data = _json.loads(content)
        except Exception:
            return content, 0

        if not isinstance(data, list) or len(data) == 0:
            return content, 0

        # Collect all unique keys from all objects
        all_keys = []
        seen_keys = set()
        for item in data:
            if isinstance(item, dict):
                for k in item:
                    if k not in seen_keys:
                        seen_keys.add(k)
                        all_keys.append(k)

        if not all_keys:
            return content, 0

        # Build compressed output
        lines = [f"[JSON {len(data)} rows → {min(len(data), max_rows)} shown, keys: {', '.join(all_keys[:10])}]"]
        for i, item in enumerate(data[:max_rows]):
            if not isinstance(item, dict):
                lines.append(f"  [{i}] {str(item)[:120]}")
                continue
            row_vals = [str(item.get(k, ""))[:60] for k in all_keys[:8]]
            lines.append(f"  [{i}] {' | '.join(row_vals)}")

        skip_count = max(0, len(data) - max_rows)
        if skip_count > 0:
            # CCR marker — LLM can retrieve original via hash
            import hashlib
            h = hashlib.md5(content.encode()).hexdigest()[:8]
            lines.append(f"  [... {skip_count} more rows — use retrieve:{h} for full data]")

        compressed = '\n'.join(lines)
        saved = max(0, len(content) - len(compressed))
        return compressed, saved // 4  # rough token estimate

    def _detect_json_content(self, content: str) -> bool:
        """Detect if content is JSON (object or array)."""
        if not content or len(content) < 2:
            return False
        stripped = content.strip()
        return (stripped.startswith('{') and stripped.endswith('}')) or \
               (stripped.startswith('[') and stripped.endswith(']'))


def get_context_gate() -> ContextGate:
    """Get the global ContextGate singleton."""
    global _context_gate
    if _context_gate is None:
        _context_gate = ContextGate()
    return _context_gate


_context_gate: Optional[ContextGate] = None


__all__ = ["ContextGate", "get_context_gate"]
