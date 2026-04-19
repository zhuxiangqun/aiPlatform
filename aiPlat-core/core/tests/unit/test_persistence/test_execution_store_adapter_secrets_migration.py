import pytest

from core.services.execution_store import ExecutionStore, ExecutionStoreConfig


@pytest.mark.asyncio
async def test_execution_store_migrate_adapter_secrets_requires_key(tmp_path, monkeypatch):
    db_path = tmp_path / "executions.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    # Insert adapter with plaintext key (no encryption configured)
    await store.upsert_adapter(
        {
            "adapter_id": "a1",
            "name": "A",
            "provider": "OpenAI",
            "api_key": "plain",
            "api_base_url": "https://example.com",
        }
    )
    st = await store.get_adapter_secrets_status()
    assert st["plaintext"] >= 1

    monkeypatch.delenv("AIPLAT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        await store.migrate_adapter_secrets_to_encrypted()


@pytest.mark.asyncio
async def test_execution_store_migrate_adapter_secrets_encrypts_and_clears_plain(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("AIPLAT_SECRET_KEY", Fernet.generate_key().decode())

    db_path = tmp_path / "executions.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    # Force plaintext legacy row (simulate historical data)
    await store.upsert_adapter(
        {
            "adapter_id": "a1",
            "name": "A",
            "provider": "OpenAI",
            "api_key": "plain",
            "api_base_url": "https://example.com",
        }
    )

    # Ensure plaintext exists for migration (upsert may already encrypt if key configured)
    # So we insert directly for deterministic behavior
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("UPDATE adapters SET api_key='plain', api_key_enc=NULL WHERE adapter_id='a1';")
        conn.commit()
    finally:
        conn.close()

    res = await store.migrate_adapter_secrets_to_encrypted()
    assert res["updated"] >= 1

    st = await store.get_adapter_secrets_status()
    assert st["encrypted"] >= 1
    assert st["plaintext"] == 0

