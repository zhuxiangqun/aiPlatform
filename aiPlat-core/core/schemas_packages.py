"""
Packages registry schemas (publish/install).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel


class PackagePublishRequest(BaseModel):
    version: str
    # Optional approval gate
    require_approval: bool = False
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class PackageInstallRequest(BaseModel):
    package_name: Optional[str] = None  # allow body override; path param is authoritative
    version: Optional[str] = None  # if omitted, install from filesystem package (latest)
    scope: str = "workspace"  # engine|workspace (target scope for apply)
    allow_overwrite: bool = False
    metadata: Optional[Dict[str, Any]] = None
    # Optional approval gate
    require_approval: bool = False
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class PackageUninstallRequest(BaseModel):
    package_name: Optional[str] = None  # allow body override; path param is authoritative
    keep_modified: bool = True
    metadata: Optional[Dict[str, Any]] = None
    # Optional approval gate
    require_approval: bool = False
    approval_request_id: Optional[str] = None
    details: Optional[str] = None

