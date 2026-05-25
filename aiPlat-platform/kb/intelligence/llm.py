"""Re-export from CoreFacade — maintains backward compatibility."""
from __future__ import annotations

from core.api.core_facade import (  # noqa: F401
    kb_llm_chat_complete as chat_complete,
    extract_json_block,
    kb_llm_enabled as llm_enabled,
)
