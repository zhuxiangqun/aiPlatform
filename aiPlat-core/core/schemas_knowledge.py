"""
Knowledge / search schemas.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class CollectionCreateRequest(BaseModel):
    name: str
    description: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentCreateRequest(BaseModel):
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

