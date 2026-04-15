"""
Approval Types

Data structures for the Human-in-the-Loop approval system.
Based on framework/patterns.md §7.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RuleType(Enum):
    """Approval rule types, matching the trigger conditions in patterns.md §7.2."""
    AMOUNT_THRESHOLD = "amount_threshold"
    SENSITIVE_OPERATION = "sensitive_operation"
    BATCH_OPERATION = "batch_operation"
    FIRST_TIME = "first_time"


class RequestStatus(Enum):
    """Approval request status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"


@dataclass
class ApprovalRule:
    """
    Approval rule definition.
    
    Attributes:
        rule_id: Unique rule identifier
        rule_type: Type of approval trigger
        name: Human-readable rule name
        description: Rule description
        condition: Condition function or string expression
        threshold: Numeric threshold (for AMOUNT_THRESHOLD type)
        enabled: Whether the rule is active
        priority: Rule priority (lower = higher priority)
        auto_approve: Whether to auto-approve when condition is NOT met
        expires_in_seconds: Request expiration time (None = no expiration)
        metadata: Additional rule metadata
    """
    rule_id: str
    rule_type: RuleType
    name: str
    description: str = ""
    condition: Optional[str] = None
    threshold: Optional[float] = None
    enabled: bool = True
    priority: int = 0
    auto_approve: bool = False
    expires_in_seconds: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def matches(self, context: "ApprovalContext") -> bool:
        """Check if this rule matches the given context."""
        if not self.enabled:
            return False
        
        if self.rule_type == RuleType.AMOUNT_THRESHOLD:
            if context.amount is not None and self.threshold is not None:
                return context.amount >= self.threshold
            return False
        
        elif self.rule_type == RuleType.SENSITIVE_OPERATION:
            if context.operation:
                sensitive_ops = self.metadata.get("sensitive_operations", [])
                return context.operation in sensitive_ops
            return False
        
        elif self.rule_type == RuleType.BATCH_OPERATION:
            if context.batch_size is not None and self.threshold is not None:
                return context.batch_size >= self.threshold
            return False
        
        elif self.rule_type == RuleType.FIRST_TIME:
            return context.is_first_time
        
        return False


@dataclass
class ApprovalRequest:
    """
    Approval request for an operation.
    
    Attributes:
        request_id: Unique request identifier
        user_id: User identifier
        operation: Operation name
        details: Operation details
        rule_id: ID of the rule that triggered this request
        rule_type: Type of the rule that triggered
        status: Current request status
        amount: Operation amount (for AMOUNT_THRESHOLD rules)
        batch_size: Batch size (for BATCH_OPERATION rules)
        is_first_time: Whether this is first time (for FIRST_TIME rules)
        created_at: Request creation timestamp
        updated_at: Last update timestamp
        expires_at: Expiration timestamp
        metadata: Additional request metadata
        result: Approval result (set when resolved)
    """
    request_id: str
    user_id: str
    operation: str
    details: str = ""
    rule_id: Optional[str] = None
    rule_type: Optional[RuleType] = None
    status: RequestStatus = RequestStatus.PENDING
    amount: Optional[float] = None
    batch_size: Optional[int] = None
    is_first_time: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    result: Optional["ApprovalResult"] = None

    def is_expired(self) -> bool:
        """Check if request has expired."""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False

    def is_resolved(self) -> bool:
        """Check if request has been resolved."""
        return self.status in (
            RequestStatus.APPROVED,
            RequestStatus.REJECTED,
            RequestStatus.CANCELLED,
            RequestStatus.EXPIRED,
            RequestStatus.AUTO_APPROVED,
        )


@dataclass
class ApprovalResult:
    """
    Result of an approval decision.
    
    Attributes:
        request_id: Associated request ID
        decision: Approval decision
        comments: Reviewer comments
        approved_by: Who approved/rejected
        timestamp: Decision timestamp
        metadata: Additional result metadata
    """
    request_id: str
    decision: RequestStatus
    comments: str = ""
    approved_by: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalContext:
    """
    Context for approval evaluation.
    
    Attributes:
        session_id: Session identifier
        user_id: User identifier
        operation: Operation being performed
        amount: Operation amount (for amount threshold checks)
        batch_size: Batch size (for batch operation checks)
        is_first_time: Whether this is the first time for this operation
        operation_context: Additional context about the operation
        metadata: Additional context metadata
    """
    session_id: str = ""
    user_id: str = ""
    operation: str = ""
    amount: Optional[float] = None
    batch_size: Optional[int] = None
    is_first_time: bool = False
    operation_context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)