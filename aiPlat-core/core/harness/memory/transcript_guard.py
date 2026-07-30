"""
Transcript Guard — role normalization for multi-turn conversations (Phase 42).

Ensures valid role alternation (user→assistant→user...) before context
is sent to LLM. Prevents model behavior degradation caused by consecutive
same-role messages in certain model providers (OpenAI, Anthropic).

Design:
  - System messages pass through unchanged
  - Consecutive same roles: merge short content, insert placeholder for long
  - Marker '[short responses]' already-compressed messages are skipped
"""

from typing import List


def normalize_roles(messages: List[dict]) -> List[dict]:
    """Ensure valid role alternation for LLM conversation format.

    Handles:
      - Consecutive user messages → merge (short) or placeholder (long)
      - Consecutive assistant messages → merge (short) or placeholder (long)
      - Consecutive tool messages → insert user placeholder to restore alternation
      - System messages → always pass through unchanged
      - Already-compressed markers → skip (don't re-compress)
    """
    if not messages or len(messages) < 2:
        return messages

    result = []
    for m in messages:
        role = str(m.get("role", ""))
        content = str(m.get("content", ""))

        if role == "system":
            result.append(dict(m))
            continue

        if "[short responses]" in content:
            result.append(dict(m))
            continue

        if result and result[-1].get("role") == role and role != "system":
            prev = result[-1]
            prev_content = str(prev.get("content", ""))

            if len(content) < 200 and len(prev_content) < 500:
                prev["content"] = f"{prev_content}\n{content}"
            else:
                placeholder_role = "assistant" if role == "user" else "user"
                result.append({
                    "role": placeholder_role,
                    "content": "(continued)",
                    "meta": {"source": "transcript_guard", "reason": "role_alternation"},
                })
                result.append(dict(m))
        else:
            result.append(dict(m))

    return result
