"""
FDE prompt templates — module-level prompt management (v2.5+).

Per the app-module-layout standard, application-specific LLM prompts
are managed by the module itself, not registered in the shared prompt_loader.

Templates are registered via prompt_loader._register() but with category="fde"
for isolation. At query time, the module's prompts are resolved independently.
"""
# FDE prompts are registered in prompt_loader with category="fde"
# This module provides typed accessors for the FDE-specific templates.

from core.harness.utils.prompt_loader import _sync_resolve

def get_infer_industry_system() -> str:
    """System prompt for industry classification."""
    return _sync_resolve("fde-infer-industry-system")

def get_infer_industry_user(company_name: str, description: str) -> str:
    """User prompt for industry classification with company context."""
    return _sync_resolve("fde-infer-industry-user",
        company_name=company_name, description=description)
