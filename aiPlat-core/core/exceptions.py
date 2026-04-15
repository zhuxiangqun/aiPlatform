"""
Core Layer Exceptions

Unified error handling with error codes, severity levels,
and an error handler for consistent error processing.
"""

from typing import Optional, Any, Dict
from enum import Enum
import uuid
from datetime import datetime


class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    INFRA = "infra"
    CORE = "core"
    PLATFORM = "platform"


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
        self.timestamp = datetime.now().isoformat()
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


class MemoryError(CoreError):
    """Base exception for memory errors"""
    error_code = "MM000"


class MemoryStoreError(MemoryError):
    """Memory store failed"""
    error_code = "MM001"


class MemoryRetrieveError(MemoryError):
    """Memory retrieve failed"""
    error_code = "MM002"


class MemoryOverflowError(MemoryError):
    """Memory overflow"""
    error_code = "MM003"


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
                "timestamp": datetime.now().isoformat(),
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