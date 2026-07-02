"""
Core Layer Exceptions

Unified error handling with error codes, severity levels,
and an error handler for consistent error processing.
"""

from typing import Optional, Any, Dict
from enum import Enum
import uuid
from datetime import datetime, timezone


class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    INFRA = "infra"
    CORE = "core"
    PLATFORM = "platform"


class CoreErrorCode(str, Enum):
    """Structured error codes — single source of truth replacing subclass-per-code pattern.
    
    Usage:
        raise CoreError(CoreErrorCode.AGENT_INIT, "Failed to init agent")
        raise CoreError(CoreErrorCode.MODEL_TIMEOUT, "LLM timed out", details={"retry": 3})
    
    Backward compat: all legacy subclass names remain as aliases (e.g., AgentInitializationError).
    """
    # ── Agent errors ──
    AGENT_BASE = "AG000"
    AGENT_INIT = "AG001"
    AGENT_EXEC = "AG002"
    AGENT_TIMEOUT = "AG003"
    AGENT_STATE = "AG004"

    # ── Agent Memory errors ──
    AGENT_MEMORY_BASE = "MM000"
    AGENT_MEMORY_STORE = "MM001"
    AGENT_MEMORY_RETRIEVE = "MM002"
    AGENT_MEMORY_OVERFLOW = "MM003"

    # ── Model errors ──
    MODEL_BASE = "MD000"
    MODEL_CONNECTION = "MD001"
    MODEL_TIMEOUT = "MD002"
    MODEL_RATE_LIMIT = "MD003"
    MODEL_RESPONSE = "MD004"

    # ── Skill errors ──
    SKILL_BASE = "SK000"
    SKILL_NOT_FOUND = "SK001"
    SKILL_EXEC = "SK002"
    SKILL_TIMEOUT = "SK003"

    # ── Tool errors ──
    TOOL_BASE = "TL000"
    TOOL_NOT_FOUND = "TL001"
    TOOL_EXEC = "TL002"
    TOOL_TIMEOUT = "TL003"
    TOOL_PERMISSION = "TL004"

    # ── Knowledge errors ──
    KNOWLEDGE_BASE = "KN000"
    KNOWLEDGE_INDEX = "KN001"
    KNOWLEDGE_RETRIEVE = "KN002"

    # ── Orchestration errors ──
    ORCHESTRATION_BASE = "OR000"
    ORCHESTRATION_WORKFLOW = "OR001"
    ORCHESTRATION_WORKFLOW_TIMEOUT = "OR002"
    ORCHESTRATION_STEP_EXEC = "OR003"

    # ── Infra errors (via core bridge) ──
    INFRA_BASE = "INF000"
    INFRA_DB = "INF100"
    INFRA_DB_CONNECTION = "INF101"
    INFRA_DB_TIMEOUT = "INF102"
    INFRA_DB_QUERY = "INF103"
    INFRA_LLM = "INF200"
    INFRA_LLM_CONNECTION = "INF201"
    INFRA_LLM_TIMEOUT = "INF202"
    INFRA_LLM_RATE_LIMIT = "INF203"
    INFRA_LLM_AUTH = "INF204"
    INFRA_VECTOR = "INF300"

    # ── Platform errors ──
    PLATFORM_BASE = "PLT000"
    PLATFORM_AUTH = "PLT100"
    PLATFORM_AUTH_TOKEN_EXPIRED = "PLT101"
    PLATFORM_AUTH_PERMISSION = "PLT102"
    PLATFORM_RATE_LIMIT = "PLT200"
    PLATFORM_TENANT = "PLT300"
    PLATFORM_TENANT_NOT_FOUND = "PLT301"
    PLATFORM_TENANT_QUOTA = "PLT302"
    PLATFORM_API = "PLT400"
    PLATFORM_API_NOT_FOUND = "PLT401"
    PLATFORM_API_VALIDATION = "PLT402"


class CoreError(Exception):
    """Base exception for core layer"""

    error_code: str = "COR000"
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    category: ErrorCategory = ErrorCategory.CORE

    def __init__(
        self,
        message: str,
        details: Optional[dict] = None,
        error_code: Optional[str] = None,
        severity: Optional[ErrorSeverity] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.error_code = error_code or self.error_code
        self.severity = severity or self.severity
        self.error_id = str(uuid.uuid4())
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.cause = cause

    def __str__(self) -> str:
        if self.details:
            return f"[{self.error_code}] {self.message} - {self.details}"
        return f"[{self.error_code}] {self.message}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_id": self.error_id,
            "error_code": self.error_code,
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "details": self.details,
            "timestamp": self.timestamp,
            "cause": str(self.cause) if self.cause else None,
        }


class AgentError(CoreError):
    """Base exception for agent errors"""
    error_code = "AG000"


class AgentInitializationError(AgentError):
    """Agent initialization failed"""
    error_code = "AG001"


class AgentExecutionError(AgentError):
    """Agent execution failed"""
    error_code = "AG002"


class AgentTimeoutError(AgentError):
    """Agent execution timeout"""
    error_code = "AG003"


class AgentStateError(AgentError):
    """Agent state error"""
    error_code = "AG004"


class CoreMemoryError(CoreError):
    """Base exception for agent memory errors"""
    error_code = "MM000"


class MemoryStoreError(CoreMemoryError):
    """Memory store failed"""
    error_code = "MM001"


class MemoryRetrieveError(CoreMemoryError):
    """Memory retrieve failed"""
    error_code = "MM002"


class MemoryOverflowError(CoreMemoryError):
    """Memory overflow"""
    error_code = "MM003"


# Backward-compatible alias (was "MemoryError", renamed to avoid collision with infra)
MemoryError = CoreMemoryError


class ModelError(CoreError):
    """Base exception for model errors"""
    error_code = "MD000"


class ModelConnectionError(ModelError):
    """Model connection failed"""
    error_code = "MD001"


class ModelTimeoutError(ModelError):
    """Model timeout"""
    error_code = "MD002"


class ModelRateLimitError(ModelError):
    """Model rate limit exceeded"""
    error_code = "MD003"


class ModelResponseError(ModelError):
    """Model response error"""
    error_code = "MD004"


class SkillError(CoreError):
    """Base exception for skill errors"""
    error_code = "SK000"


class SkillNotFoundError(SkillError):
    """Skill not found"""
    error_code = "SK001"


class SkillExecutionError(SkillError):
    """Skill execution failed"""
    error_code = "SK002"


class SkillTimeoutError(SkillError):
    """Skill timeout"""
    error_code = "SK003"


class ToolError(CoreError):
    """Base exception for tool errors"""
    error_code = "TL000"


class ToolNotFoundError(ToolError):
    """Tool not found"""
    error_code = "TL001"


class ToolExecutionError(ToolError):
    """Tool execution failed"""
    error_code = "TL002"


class ToolTimeoutError(ToolError):
    """Tool timeout"""
    error_code = "TL003"


class ToolPermissionError(ToolError):
    """Tool permission denied"""
    error_code = "TL004"


class KnowledgeError(CoreError):
    """Base exception for knowledge errors"""
    error_code = "KN000"


class KnowledgeIndexError(KnowledgeError):
    """Knowledge index error"""
    error_code = "KN001"


class KnowledgeRetrieveError(KnowledgeError):
    """Knowledge retrieve failed"""
    error_code = "KN002"


class OrchestrationError(CoreError):
    """Base exception for orchestration errors"""
    error_code = "OR000"


class WorkflowError(OrchestrationError):
    """Workflow error"""
    error_code = "OR001"


class WorkflowTimeoutError(OrchestrationError):
    """Workflow timeout"""
    error_code = "OR002"


class StepExecutionError(OrchestrationError):
    """Step execution failed"""
    error_code = "OR003"


class InfraError(CoreError):
    """Base exception for infrastructure errors"""
    error_code = "INF000"
    category = ErrorCategory.INFRA


class DatabaseError(InfraError):
    """Base exception for database errors"""
    error_code = "INF100"


class DatabaseConnectionError(DatabaseError):
    """Database connection failed"""
    error_code = "INF101"


class DatabaseTimeoutError(DatabaseError):
    """Database query timeout"""
    error_code = "INF102"


class DatabaseQueryError(DatabaseError):
    """Database query error"""
    error_code = "INF103"


class LLMError(InfraError):
    """Base exception for LLM errors"""
    error_code = "INF200"


class LLMConnectionError(LLMError):
    """LLM connection failed"""
    error_code = "INF201"


class LLMTimeoutError(LLMError):
    """LLM call timeout"""
    error_code = "INF202"


class LLMRateLimitError(LLMError):
    """LLM rate limit exceeded"""
    error_code = "INF203"


class LLMAuthError(LLMError):
    """LLM authentication failed"""
    error_code = "INF204"


class VectorStoreError(InfraError):
    """Vector store error"""
    error_code = "INF300"


class PlatformError(CoreError):
    """Base exception for platform errors"""
    error_code = "PLT000"
    category = ErrorCategory.PLATFORM


class AuthError(PlatformError):
    """Base exception for auth errors"""
    error_code = "PLT100"


class AuthTokenExpiredError(AuthError):
    """Auth token expired"""
    error_code = "PLT101"


class AuthPermissionDeniedError(AuthError):
    """Permission denied"""
    error_code = "PLT102"


class RateLimitError(PlatformError):
    """Rate limit exceeded"""
    error_code = "PLT200"


class TenantError(PlatformError):
    """Base exception for tenant errors"""
    error_code = "PLT300"


class TenantNotFoundError(TenantError):
    """Tenant not found"""
    error_code = "PLT301"


class TenantQuotaExceededError(TenantError):
    """Tenant quota exceeded"""
    error_code = "PLT302"


class APIError(PlatformError):
    """Base exception for API errors"""
    error_code = "PLT400"


class APINotFoundError(APIError):
    """API not found"""
    error_code = "PLT401"


class APIValidationError(APIError):
    """API validation error"""
    error_code = "PLT402"


class ErrorHandler:
    """
    Unified Error Handler

    Provides centralized error processing with logging,
    context merging, and response conversion.
    """

    def __init__(self):
        self._error_counts: Dict[str, int] = {}

    def handle(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Handle an error and return a standardized response"""
        if isinstance(error, CoreError):
            merged_details = {**error.details, **(context or {})}
            error.details = merged_details
            self._increment_count(error.error_code)
            response = error.to_dict()
        else:
            self._increment_count("UNKNOWN")
            response = {
                "error_id": str(uuid.uuid4()),
                "error_code": "UNKNOWN",
                "message": str(error),
                "severity": "medium",
                "category": "unknown",
                "details": context or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cause": None,
            }
        return response

    def _increment_count(self, error_code: str) -> None:
        self._error_counts[error_code] = self._error_counts.get(error_code, 0) + 1

    def get_stats(self) -> Dict[str, int]:
        return self._error_counts.copy()


# Global error handler
_global_error_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """Get global error handler"""
    global _global_error_handler
    if _global_error_handler is None:
        _global_error_handler = ErrorHandler()
    return _global_error_handler