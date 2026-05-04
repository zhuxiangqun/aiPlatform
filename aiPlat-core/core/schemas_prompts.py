"""
Prompt templates schemas.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel


class PromptTemplateUpsertRequest(BaseModel):
    template_id: str
    name: str
    template: str
    metadata: Optional[Dict[str, Any]] = None
    increment_version: bool = True
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class PromptTemplateRollbackRequest(BaseModel):
    template_id: str
    version: str
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None

