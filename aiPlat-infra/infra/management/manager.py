"""
Infrastructure Manager

This module provides a unified manager for all infrastructure components.
"""

from typing import Dict, Type, Optional, List
from .base import ManagementBase, Status, HealthStatus, Metrics


class InfraManager:
    """
    Unified infrastructure manager.
    
    This class provides a centralized management interface for all
    infrastructure components.
    """
    
    def __init__(self):
        """Initialize infrastructure manager."""
        self._managers: Dict[str, ManagementBase] = {}
    
    def register(self, name: str, manager: ManagementBase) -> None:
        """
        Register a management component.
        
        Args:
            name: Manager name
            manager: Management component instance
        """
        self._managers[name] = manager
    
    def get(self, name: str) -> Optional[ManagementBase]:
        """
        Get a management component by name.
        
        Args:
            name: Manager name
        
        Returns:
            Management component or None if not found
        """
        return self._managers.get(name)
    
    def list_managers(self) -> list[str]:
        """
        List all registered manager names.
        
        Returns:
            List of manager names
        """
        return list(self._managers.keys())
    
    async def get_all_status(self) -> Dict[str, Status]:
        """
        Get status of all modules.
        
        Returns:
            Dict of module name to status
        """
        status_dict = {}
        for name, manager in self._managers.items():
            try:
                status = await manager.get_status()
                status_dict[name] = status
            except Exception as e:
                status_dict[name] = Status.UNKNOWN
        return status_dict
    
    async def health_check_all(self) -> Dict[str, HealthStatus]:
        """
        Perform health check on all modules.
        
        Returns:
            Dict of module name to health status
        """
        health_dict = {}
        for name, manager in self._managers.items():
            try:
                health = await manager.health_check()
                health_dict[name] = health
            except Exception as e:
                health_dict[name] = HealthStatus(
                    status=Status.UNHEALTHY,
                    message=f"Health check failed: {str(e)}",
                    details={"error": str(e)}
                )
        return health_dict
    
    async def get_all_metrics(self) -> Dict[str, List[Metrics]]:
        """
        Get metrics from all modules.
        
        Returns:
            Dict of module name to list of metrics
        """
        metrics_dict = {}
        for name, manager in self._managers.items():
            try:
                metrics = await manager.get_metrics()
                metrics_dict[name] = metrics
            except Exception as e:
                metrics_dict[name] = []
        return metrics_dict
    
    async def diagnose_all(self) -> Dict[str, Dict]:
        """
        Run diagnostics on all modules.
        
        Returns:
            Dict of module name to diagnosis result
        """
        diagnosis_dict = {}
        for name, manager in self._managers.items():
            try:
                diagnosis = await manager.diagnose()
                diagnosis_dict[name] = {
                    "healthy": diagnosis.healthy,
                    "issues": diagnosis.issues,
                    "recommendations": diagnosis.recommendations,
                    "details": diagnosis.details
                }
            except Exception as e:
                diagnosis_dict[name] = {
                    "healthy": False,
                    "issues": [f"Diagnosis failed: {str(e)}"],
                    "recommendations": ["Check module configuration"],
                    "details": {"error": str(e)}
                }
        return diagnosis_dict
    
    def create_manager(self, manager_class: Type[ManagementBase], config: Dict) -> ManagementBase:
        """
        Create a manager instance.
        
        Args:
            manager_class: Manager class to instantiate
            config: Configuration dictionary
        
        Returns:
            Manager instance
        """
        manager = manager_class(config)
        return manager
    
    def register_manager(self, name: str, manager_class: Type[ManagementBase], config: Dict) -> None:
        """
        Create and register a manager.
        
        Args:
            name: Manager name
            manager_class: Manager class to instantiate
            config: Configuration dictionary
        """
        manager = self.create_manager(manager_class, config)
        self.register(name, manager)