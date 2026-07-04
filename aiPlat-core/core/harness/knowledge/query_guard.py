"""Query sanitization — strip control tokens and truncate for safety.

§5.63: All retrieval queries must be sanitized before reaching LLM.
Moved from materials_chat.py Phase 1 refactoring.
"""

import re as _re


def sanitize_query(query: str) -> str:
    """Strip model control tokens and truncate to 1000 chars."""
    q = _re.sub(r'<\|[^|]+\|>', '', query)
    q = _re.sub(r'```[\s\S]*?```', '', q)
    q = q.replace('\\', '')
    return q.strip()[:1000]


def enforce_scope(collection_id: str, domain_id: str) -> bool:
    """§5.62: Verify scope is set — no unscoped full-db scans."""
    return bool(collection_id and collection_id != "default") or bool(domain_id != "default")
