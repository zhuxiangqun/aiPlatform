import pytest

from core.services.execution_store import ExecutionStore, ExecutionStoreConfig


@pytest.mark.asyncio
async def test_execution_store_skill_pack_publish_and_install_roundtrip(tmp_path):
    db_path = tmp_path / "executions.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    pack = await store.create_skill_pack({"name": "p1", "description": "d", "manifest": {"skills": [{"id": "s1"}]}})
    assert pack["id"].startswith("sp-")
    assert pack["manifest"]["skills"][0]["id"] == "s1"

    v = await store.publish_skill_pack_version(pack_id=pack["id"], version="0.1.0")
    assert v["pack_id"] == pack["id"]
    assert v["version"] == "0.1.0"

    got_v = await store.get_skill_pack_version(pack_id=pack["id"], version="0.1.0")
    assert got_v is not None
    assert got_v["manifest"]["skills"][0]["id"] == "s1"

    versions = await store.list_skill_pack_versions(pack_id=pack["id"], limit=10, offset=0)
    assert versions["total"] >= 1

    inst = await store.install_skill_pack(pack_id=pack["id"], version="0.1.0", scope="workspace", metadata={"by": "t"})
    assert inst["pack_id"] == pack["id"]
    assert inst["version"] == "0.1.0"
    assert inst["scope"] == "workspace"

    installs = await store.list_skill_pack_installs(scope="workspace", limit=10, offset=0)
    assert installs["total"] >= 1

