"""
Centralized constants for commonly referenced agent, skill, and domain names.

All code SHOULD use these constants instead of raw string literals to prevent
typo-driven bugs and enable centralized renaming.

Migration path: import from here instead of writing "code_generation" raw.
"""

from __future__ import annotations


# ── Engine Skills (shipped with core) ──

class Skills:
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    TEXT_GENERATION = "text_generation"
    SUMMARIZATION = "summarization"
    FIELD_ASSESSMENT = "field_assessment"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    DOCUMENT_ANALYSIS = "document_analysis"
    DATA_INSIGHT = "data_insight"
    COMPLIANCE_CHECK = "compliance_check"
    CONTRACT_REVIEW = "contract_review"
    RISK_ANALYSIS = "risk_analysis"
    AUTOREVIEW = "autoreview"
    EVIDENCE_CHAIN = "evidence_chain"
    SCORING_TEMPLATE = "scoring_template"
    KNOWLEDGE_INGEST = "knowledge_ingest"
    POC_DATA_INJECT = "poc_data_inject"


# ── Agent IDs (team pipeline roles) ──

class Agents:
    PM = "pm_agent"
    ARCHITECT = "architect_agent"
    PROGRAMMER = "programmer_agent"
    QA = "qa_agent"
    FRONTEND_ENGINEER = "frontend_engineer"
    BACKEND_DEVELOPER = "backend_developer"
    PLANNING = "planning_agent"
    AUTOREVIEW_REVIEWER = "autoreview_reviewer"
    OPERATOR = "operator_agent"


# ── GraphIndex / Domain IDs ──

class Domains:
    FDE_DELIVERY = "fde-delivery"
    AI_KNOWLEDGE = "ai-knowledge"
    DEFAULT = "default"


__all__ = ["Skills", "Agents", "Domains"]
