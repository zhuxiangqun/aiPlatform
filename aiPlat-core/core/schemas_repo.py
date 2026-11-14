"""
Repo diagnostics / change-control helper schemas.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class RepoChangesetPreviewRequest(BaseModel):
    """RepoChangesetPreviewRequest。"""
    repo_root: str
    include_patch: bool = False  # default: do NOT return full diff
    note: Optional[str] = None
    run_tests: bool = False
    # Governance: when changeset is high-risk or non-local backend, require approval.
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    user_id: Optional[str] = None


class RepoTestsRunRequest(BaseModel):
    """RepoTestsRunRequest。"""
    repo_root: str
    note: Optional[str] = None


class RepoStagedPreviewRequest(BaseModel):
    """RepoStagedPreviewRequest。"""
    repo_root: str
    include_patch: bool = False


class RepoGitBranchRequest(BaseModel):
    """RepoGitBranchRequest。"""
    repo_root: str
    branch: str
    base: Optional[str] = None  # base ref, default: current HEAD
    checkout: bool = True
    # Governance
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    user_id: Optional[str] = None
    change_id: Optional[str] = None  # optional linkage to an existing change
    details: Optional[str] = None


class RepoGitCommitRequest(BaseModel):
    """RepoGitCommitRequest。"""
    repo_root: str
    message: str
    # Governance
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    user_id: Optional[str] = None
    change_id: Optional[str] = None  # optional linkage to an existing change
    details: Optional[str] = None

