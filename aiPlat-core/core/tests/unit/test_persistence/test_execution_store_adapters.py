import pytest

from core.services.execution_store import ExecutionStore, ExecutionStoreConfig


@pytest.mark.asyncio
async def test_execution_store_adapters_roundtrip(tmp_path):
    db_path = tmp_path / "executions.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    a = await store.upsert_adapter(
        {
            "adapter_id": "adapter-1",
            "name": "DeepSeek",
            "provider": "OpenAI",
            "description": "deepseek via openai-compatible",
            "status": "active",
            "api_key": "k",
            "api_base_url": "https://api.deepseek.com",
            "models": [{"name": "deepseek-reasoner", "enabled": True, "max_tokens": 8192, "temperature": 0.7}],
        }
    )
    assert a["adapter_id"] == "adapter-1"
    assert a["models"][0]["name"] == "deepseek-reasoner"

    got = await store.get_adapter("adapter-1")
    assert got is not None
    assert got["api_base_url"].startswith("https://")

    ls = await store.list_adapters(limit=10, offset=0)
    assert ls["total"] >= 1

    ok = await store.delete_adapter("adapter-1")
    assert ok is True

