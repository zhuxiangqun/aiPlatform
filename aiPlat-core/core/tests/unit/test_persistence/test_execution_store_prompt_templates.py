import pytest

from core.services.execution_store import ExecutionStore, ExecutionStoreConfig


@pytest.mark.asyncio
async def test_prompt_template_upsert_list_versions_and_rollback(tmp_path):
    db_path = tmp_path / "executions.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    r1 = await store.upsert_prompt_template(
        template_id="t1",
        name="T1",
        template="hello {name}",
        metadata={"scope": "engine"},
        increment_version=True,
    )
    assert r1["template_id"] == "t1"
    assert r1["version"] == "1.0.0"

    r2 = await store.upsert_prompt_template(
        template_id="t1",
        name="T1",
        template="hello2 {name}",
        metadata={"scope": "engine"},
        increment_version=True,
    )
    assert r2["version"] == "1.0.1"

    lst = await store.list_prompt_templates(limit=10, offset=0)
    assert lst["total"] == 1

    vs = await store.list_prompt_template_versions(template_id="t1", limit=10, offset=0)
    # versions are inserted on every upsert; should include 1.0.0 and 1.0.1
    got = {v["version"] for v in vs["items"]}
    assert "1.0.0" in got
    assert "1.0.1" in got

    rb = await store.rollback_prompt_template_version(template_id="t1", version="1.0.0")
    assert rb["version"] == "1.0.0"

