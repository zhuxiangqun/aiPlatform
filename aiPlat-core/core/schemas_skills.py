"""
Skills / skill packs / installer schemas.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SkillCreateRequest(BaseModel):
    # v2: name = display_name；skill_id 可选（不填则由 name 派生）
    name: str
    skill_id: Optional[str] = None
    display_name: Optional[str] = None
    description: str = ""
    category: str = "general"
    version: Optional[str] = None
    status: Optional[str] = None
    skill_kind: Optional[str] = None  # rule|executable
    permissions: Optional[List[str]] = None
    trigger_conditions: Optional[List[str]] = None
    decision_tree: Optional[List[Dict[str, Any]]] = None
    resources: Optional[Dict[str, Any]] = None

    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)
    template: Optional[str] = None
    sop: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


class SkillUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class SkillExecuteRequest(BaseModel):
    input: Dict[str, Any] = Field(default_factory=dict)
    context: Optional[Dict[str, Any]] = None
    mode: str = "inline"
    # Roadmap-2: runtime governance hints (e.g. toolset).
    # This is optional and forward-compatible.
    options: Optional[Dict[str, Any]] = None


class SkillInstallerSourceType(str, Enum):
    git = "git"  # git clone url + ref
    path = "path"  # local directory path on server
    zip = "zip"  # local zip file path on server


class SkillInstallerInstallRequest(BaseModel):
    scope: str = "workspace"  # workspace only (production safe); engine is not recommended
    source_type: SkillInstallerSourceType = SkillInstallerSourceType.git
    # For git:
    url: Optional[str] = None
    ref: Optional[str] = None  # required for git (tag/commit SHA)
    # For path/zip:
    path: Optional[str] = None
    # Optional: install a single skill (by directory name or frontmatter name)
    skill_id: Optional[str] = None
    # Optional: subdir inside repo/path that contains skills
    subdir: Optional[str] = None
    auto_detect_subdir: bool = True
    allow_overwrite: bool = False
    # Optional guard: require explicit confirmation before mutating filesystem
    confirm: bool = False
    # plan_id returned by /workspace/skills/installer/plan
    plan_id: Optional[str] = None
    # Optional approval gate (similar to packages)
    require_approval: bool = False
    approval_request_id: Optional[str] = None
    details: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SkillInstallerUpdateRequest(BaseModel):
    scope: str = "workspace"
    ref: Optional[str] = None  # if omitted, keep existing manifest ref (git only)
    metadata: Optional[Dict[str, Any]] = None


class SkillPackCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    manifest: Dict[str, Any] = Field(default_factory=dict)


class SkillPackUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    manifest: Optional[Dict[str, Any]] = None


class SkillPackPublishRequest(BaseModel):
    version: str


class SkillPackInstallRequest(BaseModel):
    version: Optional[str] = None
    scope: str = "workspace"  # engine|workspace
    metadata: Optional[Dict[str, Any]] = None


class SkillBindRequest(BaseModel):
    skill_ids: List[str]

