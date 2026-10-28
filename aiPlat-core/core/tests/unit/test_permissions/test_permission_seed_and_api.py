import core.apps.tools.permission as perm_mod


def _reset_perm_mgr():
    perm_mod._global_permission_manager = perm_mod.PermissionManager()
    return perm_mod.get_permission_manager()


def test_seed_default_permissions_grants_system_execute():
    pm = _reset_perm_mgr()

    from core import server as server_mod

    server_mod._seed_default_permissions(
        perm_mgr=pm,
        tool_names=["calculator", "search"],
        skill_names=["text_generation"],
        agent_names=["react_agent"],
        users=["system"],
    )

    assert pm.check_permission("system", "calculator", perm_mod.Permission.EXECUTE) is True
    assert pm.check_permission("system", "text_generation", perm_mod.Permission.EXECUTE) is True
    assert pm.check_permission("system", "react_agent", perm_mod.Permission.EXECUTE) is True
    assert pm.check_permission("u1", "calculator", perm_mod.Permission.EXECUTE) is False


def test_permission_grant_and_revoke_via_manager():
    """HTTP grant/revoke live in platform/api/routers/permissions.py; they call this manager."""
    pm = _reset_perm_mgr()
    pm.grant_permission(
        "u1", "calculator", perm_mod.Permission.EXECUTE, granted_by="admin"
    )
    assert pm.check_permission("u1", "calculator", perm_mod.Permission.EXECUTE) is True

    pm.revoke_permission("u1", "calculator")
    assert pm.check_permission("u1", "calculator", perm_mod.Permission.EXECUTE) is False
