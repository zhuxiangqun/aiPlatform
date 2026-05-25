"""Audit subsystem — prompt quality, compliance, and safety checks."""
from .prompt_auditor import (
    PromptAuditRecord,
    parse_agent_md,
    audit_agent_md,
)
