"""W5 InterfaceContract：兼容性校验 + L1 permissions。"""
from __future__ import annotations

import pytest

from core.harness.infrastructure.interface_contract import InterfaceContractModel
from core.harness.infrastructure.interface_registry import (
    InterfaceRegistry,
    _reset_interface_registry_for_tests,
)

IID = "platform_interface:lock-service:Trackable"


@pytest.fixture()
def reg():
    _reset_interface_registry_for_tests()
    return InterfaceRegistry()


def _contract(**overrides):
    base = dict(
        interface_id=IID,
        version="1.0.0",
        properties=[{"id": "status", "type": "enum"}],
        links=[],
        actions=[],
        implementers=["InstallOrder"],
        required_permissions=["kb:read"],
    )
    base.update(overrides)
    return InterfaceContractModel.model_validate(base)


def _install_order(**prop_overrides):
    props = [{"id": "status", "type": "enum"}, {"id": "device_model", "type": "string"}]
    if prop_overrides:
        props = prop_overrides.get("properties", props)
    return {
        "object_type_id": "InstallOrder",
        "properties": props,
        "links": prop_overrides.get("links", []),
        "actions": prop_overrides.get("actions", []),
    }


def test_policy_denied_without_permission(reg):
    reg.register(_contract())
    out = reg.check_compatibility(
        IID, "InstallOrder", permissions=["kb:write"], object_type_override=_install_order()
    )
    assert out["status"] == "policy_denied"
    assert "missing_permissions" in (out.get("reason") or "")


def test_compatible_ok(reg):
    reg.register(_contract())
    out = reg.check_compatibility(
        IID,
        "InstallOrder",
        permissions=["kb:read"],
        object_type_override=_install_order(),
    )
    assert out["status"] == "ok", out
    assert out["compatible"] is True


def test_not_an_implementer(reg):
    reg.register(_contract())
    out = reg.check_compatibility(
        IID,
        "DeviceModel",
        permissions=["kb:read"],
        object_type_override={
            "object_type_id": "DeviceModel",
            "properties": [{"id": "brand", "type": "string"}],
            "links": [],
            "actions": [],
        },
    )
    assert out["status"] == "not_an_implementer"
    assert out["compatible"] is False


def test_incompatible_missing_property(reg):
    reg.register(_contract())
    broken = _install_order(
        properties=[{"id": "device_model", "type": "string"}],
    )
    out = reg.check_compatibility(
        IID,
        "InstallOrder",
        permissions=["*"],
        object_type_override=broken,
    )
    assert out["status"] == "incompatible"
    assert "status" in out["details"]["missing_properties"]


def test_not_found(reg):
    out = reg.check_compatibility(
        "platform_interface:missing", "InstallOrder", permissions=["*"]
    )
    assert out["status"] == "not_found"


def test_seed_loads_via_get_interface_registry():
    _reset_interface_registry_for_tests()
    from core.harness.infrastructure.interface_registry import get_interface_registry

    reg = get_interface_registry()
    assert reg.get(IID) is not None
    # 真实 seed ObjectType（InstallOrder 含 status）
    out = reg.check_compatibility(IID, "InstallOrder", permissions=["kb:read"])
    assert out["status"] == "ok", out
    assert out["compatible"] is True
