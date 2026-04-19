import pytest

from core.services.execution_store import ExecutionStore, ExecutionStoreConfig


@pytest.mark.asyncio
async def test_execution_store_global_settings_and_tenants(tmp_path):
    db_path = tmp_path / "executions.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    s = await store.upsert_global_setting(key="default_llm", value={"adapter_id": "a1", "model": "m1"})
    assert s["key"] == "default_llm"
    got = await store.get_global_setting(key="default_llm")
    assert got is not None
    assert got["value"]["adapter_id"] == "a1"

    t = await store.upsert_tenant(tenant_id="default", name="default")
    assert t["tenant_id"] == "default"
    ls = await store.list_tenants(limit=10, offset=0)
    assert ls["total"] >= 1

