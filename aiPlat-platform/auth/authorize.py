"""
Authorization Service - 授权服务
"""

from typing import Optional
from .rbac import rbac_service, Role, Permission


class AuthorizeService:
    """授权服务"""

    def __init__(self):
        self._rbac = rbac_service

    def check_permission(
        self,
        tenant_id: str,
        actor_id: str,
        permission: Permission,
    ) -> bool:
        """检查权限"""
        return self._rbac.check_permission(tenant_id, actor_id, permission)

    def require_permission(
        self,
        tenant_id: str,
        actor_id: str,
        permission: Permission,
    ) -> None:
        """校验权限，不通过则抛异常"""
        if not self.check_permission(tenant_id, actor_id, permission):
            raise PermissionError(f"Permission denied: {permission}")

    def get_user_role(self, tenant_id: str, actor_id: str) -> Optional[Role]:
        """获取用户角色"""
        return self._rbac.get_role(tenant_id, actor_id)


authorize_service = AuthorizeService()