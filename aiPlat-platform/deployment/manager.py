"""
Deployment Manager - 部署管理（控制面）
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel
from enum import Enum
from threading import Lock


class DeploymentStatus(str, Enum):
    PENDING = "pending"
    DEPLOYING = "deploying"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class DeploymentStrategy(str, Enum):
    ROLLING = "rolling"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"


class Deployment(BaseModel):
    """部署"""
    deployment_id: str
    tenant_id: str
    service_name: str
    version: str
    strategy: DeploymentStrategy = DeploymentStrategy.ROLLING
    status: DeploymentStatus = DeploymentStatus.PENDING
    environment: str = "production"
    canary_percent: int = 0
    created_by: str = ""
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()
    metadata: Dict[str, Any] = {}


class DeploymentManager:
    """部署管理服务（控制面）"""

    def __init__(self):
        self._deployments: Dict[str, Deployment] = {}
        self._lock = Lock()

    def create_deployment(
        self,
        deployment_id: str,
        tenant_id: str,
        service_name: str,
        version: str,
        strategy: DeploymentStrategy = DeploymentStrategy.ROLLING,
        environment: str = "production",
        created_by: str = "",
    ) -> Deployment:
        """创建部署"""
        deployment = Deployment(
            deployment_id=deployment_id,
            tenant_id=tenant_id,
            service_name=service_name,
            version=version,
            strategy=strategy,
            environment=environment,
            created_by=created_by,
        )
        self._deployments[deployment_id] = deployment
        return deployment

    def get_deployment(self, deployment_id: str) -> Optional[Deployment]:
        """获取部署"""
        return self._deployments.get(deployment_id)

    def update_status(
        self,
        deployment_id: str,
        status: DeploymentStatus,
    ) -> Optional[Deployment]:
        """更新部署状态"""
        deployment = self._deployments.get(deployment_id)
        if deployment:
            deployment.status = status
            deployment.updated_at = datetime.now()
        return deployment

    def rollback(self, deployment_id: str) -> bool:
        """回滚部署"""
        deployment = self._deployments.get(deployment_id)
        if deployment and deployment.status == DeploymentStatus.HEALTHY:
            deployment.status = DeploymentStatus.ROLLING_BACK
            deployment.updated_at = datetime.now()
            return True
        return False

    def list_by_tenant(self, tenant_id: str) -> list[Deployment]:
        """列出租户的部署"""
        return [
            d for d in self._deployments.values()
            if d.tenant_id == tenant_id
        ]

    def list_by_service(self, service_name: str) -> list[Deployment]:
        """列出服务的部署"""
        return [
            d for d in self._deployments.values()
            if d.service_name == service_name
        ]

    def get_active_deployments(self, service_name: str) -> list[Deployment]:
        """获取活跃部署"""
        return [
            d for d in self._deployments.values()
            if d.service_name == service_name
            and d.status in [DeploymentStatus.HEALTHY, DeploymentStatus.DEPLOYING]
        ]


deployment_manager = DeploymentManager()