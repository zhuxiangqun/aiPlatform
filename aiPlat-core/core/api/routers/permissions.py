from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from core.apps.tools.permission import Permission, get_permission_manager

router = APIRouter()


@router.get("/permissions/stats")
async def get_permission_stats():
    """Get permission statistics"""
    perm_mgr = get_permission_manager()
    return perm_mgr.get_stats()


@router.get("/permissions/users/{user_id}")
async def get_user_permissions(user_id: str):
    """Get all permissions for a user (resource_id -> permissions)."""
    perm_mgr = get_permission_manager()
    tools = perm_mgr.get_user_tools(user_id)
    return {
        "user_id": user_id,
        "permissions": {k: [p.value for p in v] for k, v in tools.items()},
    }


@router.get("/permissions/resources/{resource_id}")
async def get_resource_permissions(resource_id: str):
    """Get all users who have permissions on a resource."""
    perm_mgr = get_permission_manager()
    users = perm_mgr.get_tool_users(resource_id)
    return {
        "resource_id": resource_id,
        "users": {k: [p.value for p in v] for k, v in users.items()},
    }


@router.post("/permissions/grant")
async def grant_permission(request: Dict[str, Any]):
    """Grant permission to a user for a resource (tool/skill/agent)."""
    user_id = request.get("user_id")
    resource_id = request.get("resource_id") or request.get("tool_name")
    permission = request.get("permission", "execute")
    granted_by = request.get("granted_by")
    if not user_id or not resource_id:
        raise HTTPException(status_code=400, detail="user_id and resource_id are required")
    try:
        perm_enum = Permission(permission)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid permission: {permission}")
    perm_mgr = get_permission_manager()
    perm_mgr.grant_permission(user_id, resource_id, perm_enum, granted_by=granted_by)
    return {"status": "granted", "user_id": user_id, "resource_id": resource_id, "permission": perm_enum.value}


@router.post("/permissions/revoke")
async def revoke_permission(request: Dict[str, Any]):
    """Revoke permission from a user for a resource (tool/skill/agent)."""
    user_id = request.get("user_id")
    resource_id = request.get("resource_id") or request.get("tool_name")
    permission = request.get("permission")
    if not user_id or not resource_id:
        raise HTTPException(status_code=400, detail="user_id and resource_id are required")
    perm_enum: Optional[Permission] = None
    if permission is not None:
        try:
            perm_enum = Permission(permission)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid permission: {permission}")
    perm_mgr = get_permission_manager()
    perm_mgr.revoke_permission(user_id, resource_id, perm_enum)
    return {
        "status": "revoked",
        "user_id": user_id,
        "resource_id": resource_id,
        "permission": perm_enum.value if perm_enum else None,
    }
