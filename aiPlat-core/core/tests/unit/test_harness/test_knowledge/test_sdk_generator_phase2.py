"""W6 Knowledge SDK：ObjectType 表面 + Facade 源码；L1；禁平行 API。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.harness.knowledge_pipeline.sdk_generator import (
    ObjectClient,
    build_sdk_surface,
    create_object_client,
    render_sdk_python,
)


def _seed() -> Path:
    p = (
        Path(__file__).resolve().parents[5]
        / "workspace_seeds"
        / "ontologies"
        / "lock-service-object-types.json"
    )
    if p.is_file():
        return p
    return Path("aiPlat-core/workspace_seeds/ontologies/lock-service-object-types.json")


def test_surface_requires_kb_read():
    out = build_sdk_surface(
        "InstallOrder",
        permissions=["kb:write"],
        bindings_path=_seed(),
    )
    assert out["status"] == "policy_denied"
    assert "kb:read" in (out.get("reason") or "")


def test_surface_for_install_order():
    out = build_sdk_surface(
        "InstallOrder",
        permissions=["kb:read"],
        bindings_path=_seed(),
    )
    assert out["status"] == "ok"
    assert out["client_name"] == "InstallOrderClient"
    assert out["primary_key"] == "order_id"
    vias = {m["via"] for m in out["methods"]}
    assert "query_object_set" in vias
    assert "execute_action" in vias
    assert "invoke_function" in vias


def test_render_source_facade_only_no_sql():
    surface = build_sdk_surface(
        "InstallOrder",
        permissions=["kb:read"],
        bindings_path=_seed(),
    )
    rendered = render_sdk_python(surface)
    assert rendered["status"] == "ok"
    src = rendered["source"]
    assert "from core.api.core_facade import" in src
    assert "query_object_set" in src
    assert "execute_action" in src
    assert "class InstallOrderClient" in src
    low = src.lower()
    assert "write_fact" not in low
    assert "_bypass_approval" not in low
    assert "raw_sql" not in low


@pytest.mark.asyncio
async def test_object_client_delegates_query():
    client = ObjectClient(
        "InstallOrder",
        tenant_id="t1",
        permissions=["kb:read"],
        primary_key="order_id",
    )
    fake = {"status": "ok", "items": [], "total": 0}
    with patch(
        "core.harness.knowledge_pipeline.sdk_generator._facade_query_object_set",
        new_callable=AsyncMock,
        return_value=fake,
    ) as mock_q:
        out = await client.query({"status": "open"})
    assert out["status"] == "ok"
    mock_q.assert_awaited_once()
    args, kwargs = mock_q.await_args
    assert kwargs["tenant_id"] == "t1"
    assert kwargs["permissions"] == ["kb:read"]
    assert args[0]["object_type"] == "InstallOrder"
    assert args[0]["filter"]["status"] == "open"


@pytest.mark.asyncio
async def test_create_client_policy_denied():
    out = create_object_client(
        "InstallOrder",
        tenant_id="t1",
        permissions=[],
        bindings_path=_seed(),
    )
    assert out["status"] == "policy_denied"
    assert out["client"] is None
