"""
RBAC - Role-Based Access Control
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class Role(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class Permission(str, Enum):
    AGENT_EXECUTE = "agent:execute"
    AGENT_CREATE = "agent:create"
    AGENT_READ = "agent:read"
    AGENT_UPDATE = "agent:update"
    AGENT_DELETE = "agent:delete"
    SKILL_EXECUTE = "skill:execute"
    SKILL_CREATE = "skill:create"
    SKILL_READ = "skill:read"
    SKILL_UPDATE = "skill:update"
    SKILL_DELETE = "skill:delete"
    TOOL_USE = "tool:use"
    TOOL_CREATE = "tool:create"
    TOOL_READ = "tool:read"
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    TENANT_ADMIN = "tenant:admin"
    BILLING_VIEW = "billing:view"
    BILLING_MANAGE = "billing:manage"


ROLE_PERMISSIONS = {
    Role.ADMIN: [
        Permission.AGENT_EXECUTE,
        Permission.AGENT_CREATE,
        Permission.AGENT_READ,
        Permission.AGENT_UPDATE,
        Permission.AGENT_DELETE,
        Permission.SKILL_EXECUTE,
        Permission.SKILL_CREATE,
        Permission.SKILL_READ,
        Permission.SKILL_UPDATE,
        Permission.SKILL_DELETE,
        Permission.TOOL_USE,
        Permission.TOOL_CREATE,
        Permission.TOOL_READ,
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
        Permission.TENANT_ADMIN,
        Permission.BILLING_VIEW,
        Permission.BILLING_MANAGE,
    ],
    Role.OPERATOR: [
        Permission.AGENT_EXECUTE,
        Permission.AGENT_READ,
        Permission.SKILL_EXECUTE,
        Permission.SKILL_READ,
        Permission.TOOL_USE,
        Permission.TOOL_READ,
        Permission.MEMORY_READ,
    ],
    Role.DEVELOPER: [
        Permission.AGENT_EXECUTE,
        Permission.AGENT_CREATE,
        Permission.AGENT_READ,
        Permission.AGENT_UPDATE,
        Permission.SKILL_EXECUTE,
        Permission.SKILL_CREATE,
        Permission.SKILL_READ,
        Permission.SKILL_UPDATE,
        Permission.TOOL_USE,
        Permission.TOOL_READ,
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
    ],
    Role.VIEWER: [
        Permission.AGENT_READ,
        Permission.SKILL_READ,
        Permission.TOOL_READ,
        Permission.MEMORY_READ,
    ],
}


class Actor(BaseModel):
    actor_id: str
    role: Role
    tenant_id: str


class RbacService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._tenant_roles: dict[str, dict[str, Role]] = {}

    def grant_role(self, tenant_id: str, actor_id: str, role: Role) -> None:
        """授予角色"""
        if tenant_id not in self._tenant_roles:
            self._tenant_roles[tenant_id] = {}
        self._tenant_roles[tenant_id][actor_id] = role

    def revoke_role(self, tenant_id: str, actor_id: str) -> bool:
        """撤销角色"""
        if tenant_id in self._tenant_roles and actor_id in self._tenant_roles[tenant_id]:
            del self._tenant_roles[tenant_id][actor_id]
            return True
        return False

    def get_role(self, tenant_id: str, actor_id: str) -> Optional[Role]:
        """获取角色"""
        return self._tenant_roles.get(tenant_id, {}).get(actor_id)

    def check_permission(self, tenant_id: str, actor_id: str, permission: Permission) -> bool:
        """检查权限"""
        role = self.get_role(tenant_id, actor_id)
        if not role:
            return False
        return permission in ROLE_PERMISSIONS.get(role, [])

    def get_permissions(self, tenant_id: str, actor_id: str) -> list[Permission]:
        """获取权限列表"""
        role = self.get_role(tenant_id, actor_id)
        if not role:
            return []
        return ROLE_PERMISSIONS.get(role, [])


rbac_service = RbacService()