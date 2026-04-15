"""
Sprint Contract Types

Defines data structures for Sprint Contract functionality.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ContractStatus(Enum):
    """Contract status enumeration."""
    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ContractCheckResult(Enum):
    """Contract check result."""
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    NEEDS_REVIEW = "needs_review"


@dataclass
class AcceptanceCriteria:
    """
    Acceptance Criteria - Measurable delivery conditions.
    
    Attributes:
        criterion: Criterion description
        metric: Measurable metric
        threshold: Target threshold value
        weight: Priority weight (0-1)
    """
    criterion: str
    metric: str
    threshold: float
    weight: float = 1.0


@dataclass
class Dependency:
    """
    Dependency - External dependency declaration.
    
    Attributes:
        name: Dependency name
        description: Dependency description
        external_service: External service name
        fallback: Fallback strategy
    """
    name: str
    description: str
    external_service: str
    fallback: Optional[str] = None


@dataclass
class RiskItem:
    """
    Risk Item - Known risk and mitigation strategy.
    
    Attributes:
        description: Risk description
        impact: Impact level (high/medium/low)
        probability: Probability (0-1)
        mitigation: Mitigation strategy
    """
    description: str
    impact: str
    probability: float
    mitigation: str


@dataclass
class SprintContract:
    """
    Sprint Contract - Agreement on scope and acceptance criteria.
    
    Attributes:
        contract_id: Unique contract ID
        scope: Feature scope description
        acceptance_criteria: List of acceptance criteria
        time_constraint: Time constraint (e.g., "2 weeks")
        dependencies: List of dependencies
        risk_items: List of known risks
        status: Contract status
        created_at: Creation timestamp
        updated_at: Last update timestamp
        expires_at: Expiration timestamp
        metadata: Additional metadata
    """
    contract_id: str
    scope: str
    acceptance_criteria: List[AcceptanceCriteria] = field(default_factory=list)
    time_constraint: str = ""
    dependencies: List[Dependency] = field(default_factory=list)
    risk_items: List[RiskItem] = field(default_factory=list)
    status: ContractStatus = ContractStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_criterion(self, criterion: str, metric: str, threshold: float, weight: float = 1.0) -> None:
        """Add an acceptance criterion."""
        self.acceptance_criteria.append(AcceptanceCriteria(
            criterion=criterion,
            metric=metric,
            threshold=threshold,
            weight=weight
        ))
        self.updated_at = datetime.utcnow()
    
    def add_dependency(self, name: str, description: str, external_service: str, fallback: Optional[str] = None) -> None:
        """Add a dependency."""
        self.dependencies.append(Dependency(
            name=name,
            description=description,
            external_service=external_service,
            fallback=fallback
        ))
        self.updated_at = datetime.utcnow()
    
    def add_risk(self, description: str, impact: str, probability: float, mitigation: str) -> None:
        """Add a risk item."""
        self.risk_items.append(RiskItem(
            description=description,
            impact=impact,
            probability=probability,
            mitigation=mitigation
        ))
        self.updated_at = datetime.utcnow()
    
    def is_expired(self) -> bool:
        """Check if contract is expired."""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    def is_active(self) -> bool:
        """Check if contract is active."""
        return (
            self.status == ContractStatus.ACTIVE
            and not self.is_expired()
        )


@dataclass
class ContractCheckResult:
    """
    Contract Check Result - Result of contract validation.
    
    Attributes:
        result: Check result status
        passed_criteria: List of passed criteria
        failed_criteria: List of failed criteria
        warnings: List of warnings
        needs_review: Whether manual review is needed
        timestamp: Check timestamp
    """
    result: ContractCheckResult
    passed_criteria: List[str] = field(default_factory=list)
    failed_criteria: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    needs_review: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ContractContext:
    """
    Contract Context - Holds contract state during agent execution.
    
    Attributes:
        contract: Associated sprint contract
        current_scope_verified: Whether current scope is within contract
        scope_violations: List of scope violations
        criteria_check_results: Results of acceptance criteria checks
        review_required: Whether scope review is required
    """
    contract: SprintContract
    current_scope_verified: bool = True
    scope_violations: List[str] = field(default_factory=list)
    criteria_check_results: List[ContractCheckResult] = field(default_factory=list)
    review_required: bool = False
    
    def add_violation(self, violation: str) -> None:
        """Add a scope violation."""
        self.scope_violations.append(violation)
        self.current_scope_verified = False
        self.review_required = True
    
    def is_within_scope(self, action: str) -> bool:
        """Check if an action is within contract scope."""
        if not self.current_scope_verified:
            return False
        return action not in self.scope_violations