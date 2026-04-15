"""
Sprint Contract Manager

Manages Sprint Contracts throughout their lifecycle.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from .types import (
    SprintContract,
    ContractStatus,
    ContractContext,
    ContractCheckResult,
    ContractCheckResult as CheckResult,
)


class ContractValidationError(Exception):
    """Exception raised for contract validation errors."""
    pass


class SprintContractManager:
    """
    Sprint Contract Manager - Manages sprint contracts lifecycle.
    
    Features:
    - Contract creation and registration
    - Contract validation and verification
    - Scope checking during execution
    - Acceptance criteria evaluation
    - Scope review workflow
    """
    
    def __init__(self):
        self._contracts: Dict[str, SprintContract] = {}
        self._agent_contracts: Dict[str, str] = {}  # agent_id -> contract_id
    
    async def create_contract(
        self,
        scope: str,
        time_constraint: str = "",
        acceptance_criteria: Optional[List[Dict[str, Any]]] = None,
        dependencies: Optional[List[Dict[str, Any]]] = None,
        risk_items: Optional[List[Dict[str, Any]]] = None,
        expires_in_days: Optional[int] = None
    ) -> SprintContract:
        """
        Create a new sprint contract.
        
        Args:
            scope: Feature scope description
            time_constraint: Time constraint (e.g., "2 weeks")
            acceptance_criteria: List of criteria dicts
            dependencies: List of dependency dicts
            risk_items: List of risk dicts
            expires_in_days: Days until expiration
            
        Returns:
            Created SprintContract
        """
        contract_id = str(uuid.uuid4())
        
        contract = SprintContract(
            contract_id=contract_id,
            scope=scope,
            time_constraint=time_constraint
        )
        
        if acceptance_criteria:
            for ac in acceptance_criteria:
                contract.add_criterion(
                    criterion=ac.get("criterion", ""),
                    metric=ac.get("metric", ""),
                    threshold=ac.get("threshold", 0.0),
                    weight=ac.get("weight", 1.0)
                )
        
        if dependencies:
            for dep in dependencies:
                contract.add_dependency(
                    name=dep.get("name", ""),
                    description=dep.get("description", ""),
                    external_service=dep.get("external_service", ""),
                    fallback=dep.get("fallback")
                )
        
        if risk_items:
            for risk in risk_items:
                contract.add_risk(
                    description=risk.get("description", ""),
                    impact=risk.get("impact", "medium"),
                    probability=risk.get("probability", 0.5),
                    mitigation=risk.get("mitigation", "")
                )
        
        if expires_in_days:
            from datetime import timedelta
            contract.expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        
        self._contracts[contract_id] = contract
        return contract
    
    async def get_contract(self, contract_id: str) -> Optional[SprintContract]:
        """Get a contract by ID."""
        return self._contracts.get(contract_id)
    
    async def activate_contract(self, contract_id: str) -> Optional[SprintContract]:
        """Activate a contract."""
        contract = self._contracts.get(contract_id)
        if not contract:
            return None
        
        contract.status = ContractStatus.ACTIVE
        contract.updated_at = datetime.utcnow()
        return contract
    
    async def complete_contract(self, contract_id: str) -> Optional[SprintContract]:
        """Mark a contract as completed."""
        contract = self._contracts.get(contract_id)
        if not contract:
            return None
        
        contract.status = ContractStatus.COMPLETED
        contract.updated_at = datetime.utcnow()
        return contract
    
    async def cancel_contract(self, contract_id: str) -> Optional[SprintContract]:
        """Cancel a contract."""
        contract = self._contracts.get(contract_id)
        if not contract:
            return None
        
        contract.status = ContractStatus.CANCELLED
        contract.updated_at = datetime.utcnow()
        return contract
    
    async def assign_to_agent(self, contract_id: str, agent_id: str) -> bool:
        """Assign a contract to an agent."""
        contract = self._contracts.get(contract_id)
        if not contract:
            return False
        
        self._agent_contracts[agent_id] = contract_id
        return True
    
    async def get_agent_contract(self, agent_id: str) -> Optional[SprintContract]:
        """Get contract assigned to an agent."""
        contract_id = self._agent_contracts.get(agent_id)
        if not contract_id:
            return None
        return self._contracts.get(contract_id)
    
    async def create_contract_context(self, contract_id: str) -> Optional[ContractContext]:
        """Create a contract context for agent execution."""
        contract = await self.get_contract(contract_id)
        if not contract:
            return None
        
        return ContractContext(contract=contract)
    
    async def verify_scope(
        self,
        context: ContractContext,
        action: str
    ) -> bool:
        """
        Verify if an action is within contract scope.
        
        Args:
            context: Contract context
            action: Action to verify
            
        Returns:
            True if within scope
        """
        if not context.contract.is_active():
            return False
        
        action_lower = action.lower()
        scope_lower = context.contract.scope.lower()
        
        if action_lower in scope_lower:
            return True
        
        for violation in context.scope_violations:
            if violation.lower() in action_lower:
                return False
        
        return True
    
    async def check_scope_violation(
        self,
        context: ContractContext,
        action: str
    ) -> Optional[str]:
        """
        Check for scope violation and return violation message.
        
        Args:
            context: Contract context
            action: Action to check
            
        Returns:
            Violation message or None if no violation
        """
        if not context.contract.is_active():
            return "Contract is not active"
        
        if not await self.verify_scope(context, action):
            return f"Action '{action}' is outside contract scope: {context.contract.scope}"
        
        return None
    
    async def record_scope_violation(
        self,
        context: ContractContext,
        action: str,
        reason: str
    ) -> None:
        """Record a scope violation."""
        violation_msg = f"{action}: {reason}"
        context.add_violation(violation_msg)
    
    async def evaluate_acceptance_criteria(
        self,
        context: ContractContext,
        results: Dict[str, float]
    ) -> ContractCheckResult:
        """
        Evaluate acceptance criteria based on results.
        
        Args:
            context: Contract context
            results: Dict of metric_name -> actual_value
            
        Returns:
            ContractCheckResult
        """
        passed = []
        failed = []
        warnings = []
        
        total_weight = 0.0
        weighted_score = 0.0
        
        for criteria in context.contract.acceptance_criteria:
            metric = criteria.metric
            threshold = criteria.threshold
            weight = criteria.weight
            
            total_weight += weight
            
            if metric in results:
                actual = results[metric]
                weighted_score += weight * (1.0 if actual >= threshold else 0.0)
                
                if actual >= threshold:
                    passed.append(criteria.criterion)
                else:
                    failed.append(criteria.criterion)
            else:
                warnings.append(f"Metric '{metric}' not found in results")
                total_weight -= weight
        
        score = weighted_score / total_weight if total_weight > 0 else 0.0
        
        if score >= 0.8:
            result = CheckResult.PASS
        elif score >= 0.5:
            result = CheckResult.WARNING
        else:
            result = CheckResult.FAIL
        
        needs_review = len(failed) > 0 or len(warnings) > 0
        
        return ContractCheckResult(
            result=result,
            passed_criteria=passed,
            failed_criteria=failed,
            warnings=warnings,
            needs_review=needs_review
        )
    
    async def trigger_scope_review(
        self,
        context: ContractContext,
        reason: str
    ) -> Dict[str, Any]:
        """
        Trigger a scope review workflow.
        
        Args:
            context: Contract context
            reason: Reason for review
            
        Returns:
            Review workflow result
        """
        context.review_required = True
        
        return {
            "action": "scope_review",
            "contract_id": context.contract.contract_id,
            "reason": reason,
            "violations": context.scope_violations,
            "timestamp": datetime.utcnow().isoformat(),
            "required": True
        }
    
    async def list_contracts(
        self,
        status: Optional[ContractStatus] = None
    ) -> List[SprintContract]:
        """List contracts, optionally filtered by status."""
        contracts = list(self._contracts.values())
        
        if status:
            contracts = [c for c in contracts if c.status == status]
        
        return contracts
    
    async def get_contract_stats(self) -> Dict[str, Any]:
        """Get contract statistics."""
        total = len(self._contracts)
        by_status = {}
        
        for status in ContractStatus:
            by_status[status.value] = sum(
                1 for c in self._contracts.values() if c.status == status
            )
        
        return {
            "total_contracts": total,
            "by_status": by_status,
            "assigned_agents": len(self._agent_contracts)
        }