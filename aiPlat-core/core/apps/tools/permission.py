"""
Permission Manager Module

Provides tool-level permission management for controlling
which users/agents can access which tools.
"""

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum


class Permission(Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


@dataclass
class PermissionEntry:
    user_id: str
    tool_name: str
    permissions: Set[Permission] = field(default_factory=set)
    granted_at: Optional[str] = None
    granted_by: Optional[str] = None


class PermissionManager:
    """
    Permission Manager

    Manages tool-level permissions, controlling which users/agents
    can access which tools and with what level of access.
    """

    def __init__(self):
        self._permissions: Dict[str, Dict[str, PermissionEntry]] = {}
        self._lock = threading.RLock()

    def grant_permission(
        self,
        user_id: str,
        tool_name: str,
        permission: Permission,
        granted_by: Optional[str] = None
    ) -> None:
        """Grant a permission to a user for a tool"""
        with self._lock:
            key = f"{user_id}:{tool_name}"
            if key not in self._permissions:
                self._permissions[key] = {}
            if user_id not in self._permissions:
                self._permissions[user_id] = {}
            if tool_name not in self._permissions[user_id]:
                self._permissions[user_id][tool_name] = PermissionEntry(
                    user_id=user_id,
                    tool_name=tool_name,
                    permissions=set()
                )
            self._permissions[user_id][tool_name].permissions.add(permission)

    def revoke_permission(
        self,
        user_id: str,
        tool_name: str,
        permission: Optional[Permission] = None
    ) -> None:
        """Revoke a permission from a user for a tool. If permission is None, revoke all."""
        with self._lock:
            if user_id in self._permissions and tool_name in self._permissions[user_id]:
                if permission is None:
                    self._permissions[user_id][tool_name].permissions.clear()
                else:
                    self._permissions[user_id][tool_name].permissions.discard(permission)

    def check_permission(
        self,
        user_id: str,
        tool_name: str,
        permission: Permission = Permission.EXECUTE
    ) -> bool:
        """Check if a user has a specific permission for a tool"""
        with self._lock:
            if user_id not in self._permissions:
                return False
            if tool_name not in self._permissions[user_id]:
                return False
            return permission in self._permissions[user_id][tool_name].permissions

    def get_permissions(self, user_id: str, tool_name: str) -> Set[Permission]:
        """Get all permissions for a user on a tool"""
        with self._lock:
            if user_id in self._permissions and tool_name in self._permissions[user_id]:
                return self._permissions[user_id][tool_name].permissions.copy()
            return set()

    def get_user_tools(self, user_id: str) -> Dict[str, Set[Permission]]:
        """Get all tools and permissions for a user"""
        with self._lock:
            if user_id not in self._permissions:
                return {}
            return {
                tool: entry.permissions.copy()
                for tool, entry in self._permissions[user_id].items()
            }

    def get_tool_users(self, tool_name: str) -> Dict[str, Set[Permission]]:
        """Get all users and their permissions for a tool"""
        with self._lock:
            result = {}
            for user_id, tools in self._permissions.items():
                if tool_name in tools:
                    result[user_id] = tools[tool_name].permissions.copy()
            return result

    def revoke_all_permissions(self, user_id: str) -> None:
        """Revoke all permissions for a user"""
        with self._lock:
            self._permissions.pop(user_id, None)

    def get_stats(self) -> Dict[str, int]:
        """Get permission statistics"""
        with self._lock:
            total_users = len(self._permissions)
            total_entries = sum(
                len(tools) for tools in self._permissions.values()
            )
            return {
                "total_users": total_users,
                "total_entries": total_entries,
            }


# Global permission manager
_global_permission_manager: Optional[PermissionManager] = None


@dataclass
class ResourcePermission:
    """Resource-level permission"""
    resource_type: str  # "file" | "api" | "database" | "command"
    resource_pattern: str  # Regex pattern
    permission: Permission  # READ | WRITE | EXECUTE


@dataclass
class Role:
    """Role definition with permissions"""
    name: str
    permissions: List[ResourcePermission] = None
    inherits: List[str] = None  # Role names to inherit from
    
    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []
        if self.inherits is None:
            self.inherits = []


class RoleBasedAccess:
    """Role-based access control"""
    
    ROLES: Dict[str, Role] = {
        "developer": Role(
            name="developer",
            permissions=[
                ResourcePermission("file", r"/workspace/.*", Permission.READ),
                ResourcePermission("file", r"/workspace/src/.*", Permission.WRITE),
                ResourcePermission("api", r"https://.*", Permission.READ),
            ]
        ),
        "analyst": Role(
            name="analyst",
            permissions=[
                ResourcePermission("file", r"/workspace/data/.*", Permission.READ),
                ResourcePermission("database", r"analytics_.*", Permission.READ),
            ]
        ),
        "admin": Role(
            name="admin",
            permissions=[
                ResourcePermission("file", r".*", Permission.READ),
                ResourcePermission("file", r".*", Permission.WRITE),
                ResourcePermission("file", r".*", Permission.EXECUTE),
                ResourcePermission("api", r".*", Permission.READ),
                ResourcePermission("api", r".*", Permission.WRITE),
                ResourcePermission("database", r".*", Permission.READ),
                ResourcePermission("database", r".*", Permission.WRITE),
            ]
        ),
    }
    
    def __init__(self):
        self._user_roles: Dict[str, List[str]] = {}  # user_id -> [role_names]
        self._custom_roles: Dict[str, Role] = {}
        
    def assign_role(self, user_id: str, role_name: str) -> bool:
        """Assign role to user"""
        if role_name not in self.ROLES and role_name not in self._custom_roles:
            return False
        if user_id not in self._user_roles:
            self._user_roles[user_id] = []
        if role_name not in self._user_roles[user_id]:
            self._user_roles[user_id].append(role_name)
        return True
        
    def revoke_role(self, user_id: str, role_name: str) -> bool:
        """Revoke role from user"""
        if user_id in self._user_roles and role_name in self._user_roles[user_id]:
            self._user_roles[user_id].remove(role_name)
            return True
        return False
        
    def check_permission(
        self,
        user_id: str,
        resource_type: str,
        resource_pattern: str,
        permission: Permission
    ) -> bool:
        """Check if user has permission for resource"""
        if user_id not in self._user_roles:
            return False
            
        user_roles = self._user_roles[user_id]
        
        for role_name in user_roles:
            # Check direct role
            role = self.ROLES.get(role_name) or self._custom_roles.get(role_name)
            if role:
                for perm in role.permissions:
                    if perm.resource_type == resource_type:
                        import re
                        if re.match(perm.resource_pattern, resource_pattern):
                            if perm.permission == permission:
                                return True
                                
        return False
        
    def get_user_roles(self, user_id: str) -> List[str]:
        """Get all roles for user"""
        return self._user_roles.get(user_id, [])


def get_permission_manager() -> PermissionManager:
    """Get global permission manager"""
    global _global_permission_manager
    if _global_permission_manager is None:
        _global_permission_manager = PermissionManager()
    return _global_permission_manager