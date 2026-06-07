"""
Onboarding schemas (global-impact operations).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OnboardingDefaultLLMRequest(BaseModel):
    adapter_id: str
    model: str
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class OnboardingInitTenantRequest(BaseModel):
    tenant_id: str = "default"
    tenant_name: Optional[str] = None
    init_policies: bool = True
    strict_tool_approval: bool = True  # if true, approval_required_tools=['*']
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class OnboardingAutosmokeConfigRequest(BaseModel):
    enabled: bool = True
    enforce: bool = True
    webhook_url: Optional[str] = None
    dedup_seconds: Optional[int] = None
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class OnboardingSecretsMigrateRequest(BaseModel):
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class OnboardingStrongGateRequest(BaseModel):
    tenant_id: str = "default"
    enabled: bool = True
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class OnboardingExecBackendRequest(BaseModel):
    backend: str = "local"  # local|docker
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class OnboardingTrustedSkillKeysRequest(BaseModel):
    # List of {key_id, public_key}; if key_id omitted, server will derive a deterministic id.
    keys: List[Dict[str, Any]] = Field(default_factory=list)
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None


class OnboardingGenerateSkillKeyRequest(BaseModel):
    label: Optional[str] = None  # human-readable label for this key pair


class OnboardingGenerateSkillKeyResponse(BaseModel):
    key_id: str
    public_key: str
    private_key: str
    label: Optional[str] = None


class OnboardingContextConfigRequest(BaseModel):
    """
    Runtime context behavior toggles (persisted as global_setting: key='context').
    NOTE: This is diagnostics/onboarding oriented; service restart may still require
    environment configuration depending on deployment.
    """

    enable_session_search: Optional[bool] = None
    context_token_limit: Optional[int] = None
    context_char_limit: Optional[int] = None
    context_max_messages: Optional[int] = None
    require_approval: bool = True
    approval_request_id: Optional[str] = None
    details: Optional[str] = None

