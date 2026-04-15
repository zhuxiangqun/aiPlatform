"""
Cost Manager

Manages cost tracking and budgeting.
"""

from typing import Dict, Any, List, Optional
from ..base import ManagementBase, Status, HealthStatus, Metrics
from ..schemas import CostBreakdown, BudgetStatus
from datetime import datetime, timedelta
import time


class CostManager(ManagementBase):
    """
    Manager for cost tracking and budgeting.
    
    Provides budget monitoring, cost analysis, and optimization recommendations.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._costs: Dict[str, List[Dict]] = {}
        self._budgets: Dict[str, float] = {}
        self._spending: Dict[str, float] = {}
        self._cost_history: List[Dict] = []
    
    async def get_status(self) -> Status:
        """Get cost module status."""
        try:
            daily_budget = self._get_config_value("budget.daily", 0)
            monthly_budget = self._get_config_value("budget.monthly", 0)
            
            daily_spent = self._spending.get("daily", 0)
            monthly_spent = self._spending.get("monthly", 0)
            
            if daily_budget > 0 and daily_spent >= daily_budget:
                return Status.UNHEALTHY
            elif monthly_budget > 0 and monthly_spent >= monthly_budget:
                return Status.DEGRADED
            else:
                return Status.HEALTHY
        
        except Exception:
            return Status.UNKNOWN
    
    async def get_metrics(self) -> List[Metrics]:
        """Get cost metrics."""
        metrics = []
        timestamp = time.time()
        
        # Daily metrics
        daily_budget = self._get_config_value("budget.daily", 0)
        daily_spent = self._spending.get("daily", 0)
        
        metrics.append(Metrics(
            name="cost.daily_budget",
            value=daily_budget,
            unit="USD",
            timestamp=timestamp,
            labels={"module": "cost"}
        ))
        
        metrics.append(Metrics(
            name="cost.daily_spent",
            value=daily_spent,
            unit="USD",
            timestamp=timestamp,
            labels={"module": "cost"}
        ))
        
        if daily_budget > 0:
            metrics.append(Metrics(
                name="cost.daily_percentage",
                value=daily_spent / daily_budget,
                unit="ratio",
                timestamp=timestamp,
                labels={"module": "cost"}
            ))
        
        # Monthly metrics
        monthly_budget = self._get_config_value("budget.monthly", 0)
        monthly_spent = self._spending.get("monthly", 0)
        
        metrics.append(Metrics(
            name="cost.monthly_budget",
            value=monthly_budget,
            unit="USD",
            timestamp=timestamp,
            labels={"module": "cost"}
        ))
        
        metrics.append(Metrics(
            name="cost.monthly_spent",
            value=monthly_spent,
            unit="USD",
            timestamp=timestamp,
            labels={"module": "cost"}
        ))
        
        if monthly_budget > 0:
            metrics.append(Metrics(
                name="cost.monthly_percentage",
                value=monthly_spent / monthly_budget,
                unit="ratio",
                timestamp=timestamp,
                labels={"module": "cost"}
            ))
        
        # Cost by service
        for service, costs in self._costs.items():
            total = sum(c.get("amount", 0) for c in costs[-100:])
            metrics.append(Metrics(
                name=f"cost.by_service",
                value=total,
                unit="USD",
                timestamp=timestamp,
                labels={"module": "cost", "service": service}
            ))
        
        return metrics
    
    async def health_check(self) -> HealthStatus:
        """Perform cost health check."""
        try:
            status = await self.get_status()
            
            daily_budget = self._get_config_value("budget.daily", 0)
            monthly_budget = self._get_config_value("budget.monthly", 0)
            daily_spent = self._spending.get("daily", 0)
            monthly_spent = self._spending.get("monthly", 0)
            
            alerts = []
            if daily_budget > 0 and daily_spent >= daily_budget * 0.9:
                alerts.append(f"Daily budget at {daily_spent/daily_budget*100:.1f}%")
            if monthly_budget > 0 and monthly_spent >= monthly_budget * 0.9:
                alerts.append(f"Monthly budget at {monthly_spent/monthly_budget*100:.1f}%")
            
            if status == Status.HEALTHY:
                return HealthStatus(
                    status=status,
                    message="Cost tracking is healthy",
                    details={
                        "daily_spent": daily_spent,
                        "monthly_spent": monthly_spent,
                        "alerts": alerts
                    }
                )
            elif status == Status.DEGRADED:
                return HealthStatus(
                    status=status,
                    message="Cost budget limits approaching",
                    details={
                        "daily_spent": daily_spent,
                        "monthly_spent": monthly_spent,
                        "alerts": alerts
                    }
                )
            else:
                return HealthStatus(
                    status=status,
                    message="Budget limit exceeded",
                    details={
                        "daily_spent": daily_spent,
                        "monthly_spent": monthly_spent,
                        "alerts": alerts
                    }
                )
        
        except Exception as e:
            return HealthStatus(
                status=Status.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                details={"error": str(e)}
            )
    
    async def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self.config
    
    async def update_config(self, config: Dict[str, Any]) -> None:
        """Update configuration."""
        self.config.update(config)
    
    # Cost-specific methods
    
    async def set_budget(self, period: str, amount: float) -> None:
        """
        Set budget limit.
        
        Args:
            period: Period (daily, monthly)
            amount: Budget amount
        """
        self._budgets[period] = amount
    
    async def get_budget(self, period: str) -> Optional[float]:
        """
        Get budget limit.
        
        Args:
            period: Period (daily, monthly)
        
        Returns:
            Budget amount or None
        """
        return self._budgets.get(period)
    
    async def record_cost(self, service: str, amount: float, metadata: Dict = None) -> None:
        """
        Record a cost entry.
        
        Args:
            service: Service name
            amount: Cost amount
            metadata: Additional metadata
        """
        cost_entry = {
            "service": service,
            "amount": amount,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        if service not in self._costs:
            self._costs[service] = []
        
        self._costs[service].append(cost_entry)
        
        # Update spending
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")
        
        self._spending["daily"] = self._spending.get("daily", 0) + amount
        self._spending["monthly"] = self._spending.get("monthly", 0) + amount
        
        # Add to history
        self._cost_history.append(cost_entry)
    
    async def get_cost_breakdown(self, period: str = "daily", date: str = None) -> CostBreakdown:
        """
        Get cost breakdown.
        
        Args:
            period: Period (daily, monthly)
            date: Specific date
        
        Returns:
            Cost breakdown
        """
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        
        total = 0.0
        by_service: Dict[str, float] = {}
        by_user: Dict[str, float] = {}
        
        for service, costs in self._costs.items():
            service_total = sum(c.get("amount", 0) for c in costs)
            by_service[service] = service_total
            total += service_total
            
            # Group by user if metadata is available
            for cost in costs:
                user = cost.get("metadata", {}).get("user", "unknown")
                by_user[user] = by_user.get(user, 0) + cost.get("amount", 0)
        
        return CostBreakdown(
            date=target_date,
            total=total,
            by_model=by_service,
            by_user=by_user
        )
    
    async def get_budget_status(self) -> BudgetStatus:
        """
        Get budget status.
        
        Returns:
            Budget status
        """
        daily_budget = self._budgets.get("daily", self._get_config_value("budget.daily", 0))
        monthly_budget = self._budgets.get("monthly", self._get_config_value("budget.monthly", 0))
        
        daily_spent = self._spending.get("daily", 0)
        monthly_spent = self._spending.get("monthly", 0)
        
        alerts = []
        if daily_budget > 0 and daily_spent >= daily_budget * 0.9:
            alerts.append(f"Daily budget alert: {daily_spent/daily_budget*100:.1f}% used")
        if monthly_budget > 0 and monthly_spent >= monthly_budget * 0.9:
            alerts.append(f"Monthly budget alert: {monthly_spent/monthly_budget*100:.1f}% used")
        
        return BudgetStatus(
            daily_used=daily_spent,
            daily_limit=daily_budget,
            daily_percentage=daily_spent / daily_budget if daily_budget > 0 else 0,
            monthly_used=monthly_spent,
            monthly_limit=monthly_budget,
            monthly_percentage=monthly_spent / monthly_budget if monthly_budget > 0 else 0,
            alerts=alerts
        )
    
    async def get_top_costs(self, limit: int = 10) -> List[Dict]:
        """
        Get top cost services.
        
        Args:
            limit: Maximum number to return
        
        Returns:
            List of top cost services
        """
        service_costs = []
        
        for service, costs in self._costs.items():
            total = sum(c.get("amount", 0) for c in costs)
            service_costs.append({
                "service": service,
                "total_cost": total,
                "entry_count": len(costs)
            })
        
        return sorted(service_costs, key=lambda x: x["total_cost"], reverse=True)[:limit]
    
    async def get_cost_trend(self, days: int = 7) -> List[Dict]:
        """
        Get cost trend over time.
        
        Args:
            days: Number of days
        
        Returns:
            List of daily cost summaries
        """
        trend = []
        
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            
            # In real implementation, would filter by date
            # For now, using placeholder
            trend.append({
                "date": date,
                "total": 0.0,
                "by_service": {}
            })
        
        return trend
    
    async def optimize_costs(self) -> List[Dict]:
        """
        Get cost optimization recommendations.
        
        Returns:
            List of recommendations
        """
        recommendations = []
        
        for service, costs in self._costs.items():
            total = sum(c.get("amount", 0) for c in costs)
            avg = total / len(costs) if costs else 0
            
            if avg > 10:  # Threshold for recommendation
                recommendations.append({
                    "service": service,
                    "type": "high_cost",
                    "message": f"High average cost for {service}: ${avg:.2f}",
                    "potential_savings": avg * 0.2  # Estimate 20% savings
                })
        
        # Budget-based recommendations
        daily_budget = self._budgets.get("daily", 0)
        daily_spent = self._spending.get("daily", 0)
        
        if daily_budget > 0 and daily_spent > daily_budget * 0.8:
            recommendations.append({
                "service": "overall",
                "type": "budget_alert",
                "message": f"Daily budget at {daily_spent/daily_budget*100:.1f}% capacity",
                "potential_savings": 0
            })
        
        return recommendations
    
    async def reset_daily_spending(self) -> None:
        """Reset daily spending counter."""
        self._spending["daily"] = 0
    
    async def reset_monthly_spending(self) -> None:
        """Reset monthly spending counter."""
        self._spending["monthly"] = 0