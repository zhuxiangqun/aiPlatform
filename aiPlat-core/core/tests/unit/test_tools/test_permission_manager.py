import importlib.util
from pathlib import Path


def _load_permission_module():
    core_dir = Path(__file__).resolve().parents[3]  # .../aiPlat-core/core
    module_path = core_dir / "apps" / "tools" / "permission.py"
    spec = importlib.util.spec_from_file_location("permission_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


permission_module = _load_permission_module()
PermissionManager = permission_module.PermissionManager
Permission = permission_module.Permission


def test_grant_and_check_permission():
    pm = PermissionManager()
    assert pm.check_permission("u1", "calculator", Permission.EXECUTE) is False

    pm.grant_permission("u1", "calculator", Permission.EXECUTE)
    assert pm.check_permission("u1", "calculator", Permission.EXECUTE) is True
    assert pm.check_permission("u1", "calculator", Permission.READ) is False


def test_revoke_permission():
    pm = PermissionManager()
    pm.grant_permission("u1", "calculator", Permission.EXECUTE)
    pm.grant_permission("u1", "calculator", Permission.READ)

    pm.revoke_permission("u1", "calculator", Permission.READ)
    assert pm.check_permission("u1", "calculator", Permission.READ) is False
    assert pm.check_permission("u1", "calculator", Permission.EXECUTE) is True

    pm.revoke_permission("u1", "calculator")
    assert pm.check_permission("u1", "calculator", Permission.EXECUTE) is False


def test_get_user_tools_and_tool_users():
    pm = PermissionManager()
    pm.grant_permission("u1", "calculator", Permission.EXECUTE)
    pm.grant_permission("u2", "calculator", Permission.EXECUTE)
    pm.grant_permission("u2", "search", Permission.READ)

    u2_tools = pm.get_user_tools("u2")
    assert set(u2_tools.keys()) == {"calculator", "search"}
    assert u2_tools["search"] == {Permission.READ}

    users_for_calc = pm.get_tool_users("calculator")
    assert users_for_calc["u1"] == {Permission.EXECUTE}
    assert users_for_calc["u2"] == {Permission.EXECUTE}


def test_stats_are_consistent():
    pm = PermissionManager()
    pm.grant_permission("u1", "calculator", Permission.EXECUTE)
    pm.grant_permission("u1", "search", Permission.READ)
    pm.grant_permission("u2", "calculator", Permission.EXECUTE)

    stats = pm.get_stats()
    assert stats["total_users"] == 2
    assert stats["total_entries"] == 3
