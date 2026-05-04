"""
Diagnostics helper schemas.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class DiagnosticsPromptAssembleRequest(BaseModel):
    """
    Diagnostics-only endpoint helper to introspect prompt/context assembly.
    """

    session_id: Optional[str] = None
    user_id: str = "system"
    repo_root: Optional[str] = None
    messages: Optional[list] = None  # list[{"role": "...", "content": "..."}]
    enable_project_context: bool = True
    enable_session_search: Optional[bool] = None  # None=use env

