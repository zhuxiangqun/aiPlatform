"""
Backwards-compatible exports for Pydantic schemas.

Important: this module intentionally avoids importing all schema classes eagerly,
to keep import-time coupling low. It provides lazy attribute resolution via
PEP-562 module __getattr__.
"""

from __future__ import annotations

from importlib import import_module
from typing import Dict, Tuple

__all__ = [
    # agents
    "AgentCreateRequest",
    "AgentUpdateRequest",
    # skills
    "SkillCreateRequest",
    "SkillUpdateRequest",
    "SkillExecuteRequest",
    "SkillBindRequest",
    "ToolBindRequest",
    "TriggerConditionsUpdateRequest",
    "TriggerTestRequest",
    "SkillInstallerSourceType",
    "SkillInstallerInstallRequest",
    "SkillInstallerUpdateRequest",
    "SkillPackCreateRequest",
    "SkillPackUpdateRequest",
    "SkillPackPublishRequest",
    "SkillPackInstallRequest",
    # eval
    "AutoEvalStep",
    "AutoEvalRequest",
    "UpsertEvaluationPolicyRequest",
    "UpsertProjectEvaluationPolicyRequest",
    "EvidenceDiffRequest",
    # run
    "RunStatus",
    "RunError",
    "RunSummary",
    # jobs
    "JobCreateRequest",
    "JobUpdateRequest",
    # gateway
    "GatewayExecuteRequest",
    # packages
    "PackagePublishRequest",
    "PackageInstallRequest",
    "PackageUninstallRequest",
    # onboarding
    "OnboardingDefaultLLMRequest",
    "OnboardingInitTenantRequest",
    "OnboardingAutosmokeConfigRequest",
    "OnboardingSecretsMigrateRequest",
    "OnboardingStrongGateRequest",
    "OnboardingExecBackendRequest",
    "OnboardingTrustedSkillKeysRequest",
    "OnboardingContextConfigRequest",
    # prompts
    "PromptTemplateUpsertRequest",
    "PromptTemplateRollbackRequest",
    # repo
    "RepoChangesetPreviewRequest",
    "RepoTestsRunRequest",
    "RepoStagedPreviewRequest",
    "RepoGitBranchRequest",
    "RepoGitCommitRequest",
    # memory / knowledge
    "LongTermMemoryAddRequest",
    "LongTermMemorySearchRequest",
    "MessageCreateRequest",
    "SessionCreateRequest",
    "SearchRequest",
    "CollectionCreateRequest",
    "DocumentCreateRequest",
    # adapters/harness
    "AdapterCreateRequest",
    "AdapterUpdateRequest",
    "ModelUpdateRequest",
    "HookCreateRequest",
    "HookUpdateRequest",
    "CoordinatorCreateRequest",
    "FeedbackConfigUpdateRequest",
    # diagnostics
    "DiagnosticsPromptAssembleRequest",
    # builder
    "BuilderSessionCreateRequest",
    "BuilderChatRequest",
    "BuilderConfirmRequest",
    "BuilderRejectRequest",
    "BuilderSessionStateResponse",
    "BuilderChatResponse",
    # common (response models)
    "CoreResponse",
    "PaginatedResponse",
    "StatusResponse",
    "IdResponse",
    "CountResponse",
    "DeleteResponse",
    "ListResponse",
    "MessageResponse",
    "DictResponse",
    "IdNameResponse",
    "WikiPageResponse",
    "WikiDeleteAllResponse",
    "ErrorDetail",
    "EnvInfoResponse",
]


_EXPORTS: Dict[str, Tuple[str, str]] = {
    # agents
    "AgentCreateRequest": ("core.schemas_agents", "AgentCreateRequest"),
    "AgentUpdateRequest": ("core.schemas_agents", "AgentUpdateRequest"),
    # skills
    "SkillCreateRequest": ("core.schemas_skills", "SkillCreateRequest"),
    "SkillUpdateRequest": ("core.schemas_skills", "SkillUpdateRequest"),
    "SkillExecuteRequest": ("core.schemas_skills", "SkillExecuteRequest"),
    "SkillBindRequest": ("core.schemas_skills", "SkillBindRequest"),
    "ToolBindRequest": ("core.schemas_tools", "ToolBindRequest"),
    "TriggerConditionsUpdateRequest": ("core.schemas_tools", "TriggerConditionsUpdateRequest"),
    "TriggerTestRequest": ("core.schemas_tools", "TriggerTestRequest"),
    "SkillInstallerSourceType": ("core.schemas_skills", "SkillInstallerSourceType"),
    "SkillInstallerInstallRequest": ("core.schemas_skills", "SkillInstallerInstallRequest"),
    "SkillInstallerUpdateRequest": ("core.schemas_skills", "SkillInstallerUpdateRequest"),
    "SkillPackCreateRequest": ("core.schemas_skills", "SkillPackCreateRequest"),
    "SkillPackUpdateRequest": ("core.schemas_skills", "SkillPackUpdateRequest"),
    "SkillPackPublishRequest": ("core.schemas_skills", "SkillPackPublishRequest"),
    "SkillPackInstallRequest": ("core.schemas_skills", "SkillPackInstallRequest"),
    # eval
    "AutoEvalStep": ("core.schemas_eval", "AutoEvalStep"),
    "AutoEvalRequest": ("core.schemas_eval", "AutoEvalRequest"),
    "UpsertEvaluationPolicyRequest": ("core.schemas_eval", "UpsertEvaluationPolicyRequest"),
    "UpsertProjectEvaluationPolicyRequest": ("core.schemas_eval", "UpsertProjectEvaluationPolicyRequest"),
    "EvidenceDiffRequest": ("core.schemas_eval", "EvidenceDiffRequest"),
    # run
    "RunStatus": ("core.schemas_run", "RunStatus"),
    "RunError": ("core.schemas_run", "RunError"),
    "RunSummary": ("core.schemas_run", "RunSummary"),
    # jobs
    "JobCreateRequest": ("core.schemas_jobs", "JobCreateRequest"),
    "JobUpdateRequest": ("core.schemas_jobs", "JobUpdateRequest"),
    # gateway
    "GatewayExecuteRequest": ("core.schemas_gateway", "GatewayExecuteRequest"),
    # packages
    "PackagePublishRequest": ("core.schemas_packages", "PackagePublishRequest"),
    "PackageInstallRequest": ("core.schemas_packages", "PackageInstallRequest"),
    "PackageUninstallRequest": ("core.schemas_packages", "PackageUninstallRequest"),
    # onboarding
    "OnboardingDefaultLLMRequest": ("core.schemas_onboarding", "OnboardingDefaultLLMRequest"),
    "OnboardingInitTenantRequest": ("core.schemas_onboarding", "OnboardingInitTenantRequest"),
    "OnboardingAutosmokeConfigRequest": ("core.schemas_onboarding", "OnboardingAutosmokeConfigRequest"),
    "OnboardingSecretsMigrateRequest": ("core.schemas_onboarding", "OnboardingSecretsMigrateRequest"),
    "OnboardingStrongGateRequest": ("core.schemas_onboarding", "OnboardingStrongGateRequest"),
    "OnboardingExecBackendRequest": ("core.schemas_onboarding", "OnboardingExecBackendRequest"),
    "OnboardingTrustedSkillKeysRequest": ("core.schemas_onboarding", "OnboardingTrustedSkillKeysRequest"),
    "OnboardingContextConfigRequest": ("core.schemas_onboarding", "OnboardingContextConfigRequest"),
    # prompts
    "PromptTemplateUpsertRequest": ("core.schemas_prompts", "PromptTemplateUpsertRequest"),
    "PromptTemplateRollbackRequest": ("core.schemas_prompts", "PromptTemplateRollbackRequest"),
    # repo
    "RepoChangesetPreviewRequest": ("core.schemas_repo", "RepoChangesetPreviewRequest"),
    "RepoTestsRunRequest": ("core.schemas_repo", "RepoTestsRunRequest"),
    "RepoStagedPreviewRequest": ("core.schemas_repo", "RepoStagedPreviewRequest"),
    "RepoGitBranchRequest": ("core.schemas_repo", "RepoGitBranchRequest"),
    "RepoGitCommitRequest": ("core.schemas_repo", "RepoGitCommitRequest"),
    # memory / knowledge
    "LongTermMemoryAddRequest": ("core.schemas_memory", "LongTermMemoryAddRequest"),
    "LongTermMemorySearchRequest": ("core.schemas_memory", "LongTermMemorySearchRequest"),
    "MessageCreateRequest": ("core.schemas_memory", "MessageCreateRequest"),
    "SessionCreateRequest": ("core.schemas_memory", "SessionCreateRequest"),
    "SearchRequest": ("core.schemas_knowledge", "SearchRequest"),
    "CollectionCreateRequest": ("core.schemas_knowledge", "CollectionCreateRequest"),
    "DocumentCreateRequest": ("core.schemas_knowledge", "DocumentCreateRequest"),
    # adapters/harness
    "AdapterCreateRequest": ("core.schemas_adapters", "AdapterCreateRequest"),
    "AdapterUpdateRequest": ("core.schemas_adapters", "AdapterUpdateRequest"),
    "ModelUpdateRequest": ("core.schemas_adapters", "ModelUpdateRequest"),
    "HookCreateRequest": ("core.schemas_harness", "HookCreateRequest"),
    "HookUpdateRequest": ("core.schemas_harness", "HookUpdateRequest"),
    "CoordinatorCreateRequest": ("core.schemas_harness", "CoordinatorCreateRequest"),
    "FeedbackConfigUpdateRequest": ("core.schemas_harness", "FeedbackConfigUpdateRequest"),
    # diagnostics
    "DiagnosticsPromptAssembleRequest": ("core.schemas_diagnostics", "DiagnosticsPromptAssembleRequest"),
    # builder
    "BuilderSessionCreateRequest": ("core.schemas_builder", "BuilderSessionCreateRequest"),
    "BuilderChatRequest": ("core.schemas_builder", "BuilderChatRequest"),
    "BuilderConfirmRequest": ("core.schemas_builder", "BuilderConfirmRequest"),
    "BuilderSessionStateResponse": ("core.schemas_builder", "BuilderSessionStateResponse"),
    "BuilderChatResponse": ("core.schemas_builder", "BuilderChatResponse"),
    # common (response models)
    "CoreResponse": ("core.schemas_common", "CoreResponse"),
    "PaginatedResponse": ("core.schemas_common", "PaginatedResponse"),
    "StatusResponse": ("core.schemas_common", "StatusResponse"),
    "IdResponse": ("core.schemas_common", "IdResponse"),
    "CountResponse": ("core.schemas_common", "CountResponse"),
    "DeleteResponse": ("core.schemas_common", "DeleteResponse"),
    "ListResponse": ("core.schemas_common", "ListResponse"),
    "MessageResponse": ("core.schemas_common", "MessageResponse"),
    "DictResponse": ("core.schemas_common", "DictResponse"),
    "IdNameResponse": ("core.schemas_common", "IdNameResponse"),
    "WikiPageResponse": ("core.schemas_common", "WikiPageResponse"),
    "WikiDeleteAllResponse": ("core.schemas_common", "WikiDeleteAllResponse"),
    "ErrorDetail": ("core.schemas_common", "ErrorDetail"),
    "EnvInfoResponse": ("core.schemas_common", "EnvInfoResponse"),
}


def __getattr__(name: str):
    ref = _EXPORTS.get(name)
    if not ref:
        raise AttributeError(name)
    mod_name, attr = ref
    mod = import_module(mod_name)
    v = getattr(mod, attr)
    globals()[name] = v
    return v
