"""
Management Base Classes

This module defines the base classes for all management components.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime


class Status(Enum):
    """Module status enumeration"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthStatus:
    """Health check result"""
    status: Status
    message: str
    details: Dict[str, Any]
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class Metrics:
    """Metric data point"""
    name: str
    value: float
    unit: str
    timestamp: float
    labels: Dict[str, str] = None
    
    def __post_init__(self):
        if self.labels is None:
            self.labels = {}


@dataclass
class DiagnosisResult:
    """Diagnosis result"""
    healthy: bool
    issues: List[str]
    recommendations: List[str]
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}


class ManagementBase(ABC):
    """
    Base class for all management components.
    
    All management components should inherit from this class and implement
    the required abstract methods.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize management base.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self._module_name = self.__class__.__name__.replace("Manager", "").lower()
    
    @abstractmethod
    async def get_status(self) -> Status:
        """
        Get module status.
        
        Returns:
            Status: Current module status
        """
        pass
    
    @abstractmethod
    async def get_metrics(self) -> List[Metrics]:
        """
        Get module metrics.
        
        Returns:
            List[Metrics]: List of metric data points
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """
        Perform health check.
        
        Returns:
            HealthStatus: Health check result
        """
        pass
    
    @abstractmethod
    async def get_config(self) -> Dict[str, Any]:
        """
        Get current configuration.
        
        Returns:
            Dict[str, Any]: Current configuration
        """
        pass
    
    @abstractmethod
    async def update_config(self, config: Dict[str, Any]) -> None:
        """
        Update configuration.
        
        Args:
            config: New configuration
        """
        pass
    
    async def diagnose(self) -> DiagnosisResult:
        """
        Run diagnostic checks.
        
        Returns:
            DiagnosisResult: Diagnosis result with issues and recommendations
        """
        issues = []
        recommendations = []
        details = {}
        
        try:
            # Check status
            status = await self.get_status()
            details["status"] = status.value
            
            if status == Status.UNHEALTHY:
                issues.append(f"{self._module_name} is unhealthy")
                recommendations.append(f"Check {self._module_name} logs and configuration")
            
            # Check health
            health = await self.health_check()
            details["health"] = health.message
            
            if health.status == Status.DEGRADED:
                issues.append(f"{self._module_name} is degraded: {health.message}")
                recommendations.append(f"Investigate {self._module_name} performance issues")
            
            # Check metrics
            metrics = await self.get_metrics()
            details["metrics_count"] = len(metrics)
            
            healthy = len(issues) == 0
            
            return DiagnosisResult(
                healthy=healthy,
                issues=issues,
                recommendations=recommendations,
                details=details
            )
        
        except Exception as e:
            return DiagnosisResult(
                healthy=False,
                issues=[f"Diagnosis failed: {str(e)}"],
                recommendations=["Check module configuration and logs"],
                details={"error": str(e)}
            )
    
    def _get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with default.
        
        Args:
            key: Configuration key (supports dot notation)
            default: Default value if key not found
        
        Returns:
            Configuration value
        """
        keys = key.split(".")
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default