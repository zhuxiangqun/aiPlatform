"""W5 FunctionContract：无副作用硬门 + L1 permissions。"""
from __future__ import annotations

import pytest

from core.harness.infrastructure.function_contract import FunctionContractModel
from core.harness.infrastructure.function_registry import (
    FunctionRegistry,
    _reset_function_registry_for_tests,
)


HANDLER = "core.harness.infrastructure.builtin_functions:priority_hint"
FID = "platform_function:knowledge:priority_hint"


@pytest.fixture()
def reg():
    _reset_function_registry_for_tests()
    return FunctionRegistry()


def _contract(**overrides):
    base = dict(
        function_id=FID,
        version="1.0.0",
        input_schema={},
        output_schema={},
        deterministic=True,
        side_effects=False,
        required_permissions=["kb:read"],
        timeout_ms=2000,
        handler=HANDLER,
    )
    base.update(overrides)
    return FunctionContractModel.model_validate(base)


@pytest.mark.asyncio
async def test_side_effects_forbidden(reg):
    reg.register(_contract(side_effects=True))
    out = await reg.invoke(FID, {"urgency": 3}, permissions=["kb:read"])
    assert out["status"] == "side_effects_forbidden"


@pytest.mark.asyncio
async def test_policy_denied_without_permission(reg):
    reg.register(_contract())
    out = await reg.invoke(FID, {"urgency": 3}, permissions=["kb:write"])
    assert out["status"] == "policy_denied"
    assert "missing_permissions" in (out.get("reason") or "")


@pytest.mark.asyncio
async def test_invoke_ok_pure_compute(reg):
    reg.register(_contract())
    out = await reg.invoke(
        FID,
        {"urgency": 5, "impact": 5},
        permissions=["kb:read"],
        actor="tester",
    )
    assert out["status"] == "ok", out
    assert out["result"]["score"] == 100.0
    assert "urgency=5" in out["result"]["reason"]


@pytest.mark.asyncio
async def test_not_found(reg):
    out = await reg.invoke("platform_function:missing", {}, permissions=["*"])
    assert out["status"] == "not_found"


@pytest.mark.asyncio
async def test_seed_loads_via_get_function_registry():
    _reset_function_registry_for_tests()
    from core.harness.infrastructure.function_registry import get_function_registry

    reg = get_function_registry()
    assert reg.get(FID) is not None
    out = await reg.invoke(
        FID, {"urgency": 2, "impact": 4}, permissions=["kb:read"]
    )
    assert out["status"] == "ok"
    assert out["result"]["score"] > 0
