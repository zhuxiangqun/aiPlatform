import pytest

from core.services.execution_store import ExecutionStore, ExecutionStoreConfig


@pytest.mark.asyncio
async def test_execution_store_package_publish_and_install_roundtrip(tmp_path):
    db_path = tmp_path / "executions.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    v = await store.publish_package_version(
        package_name="starter",
        version="0.1.0",
        manifest={"name": "starter", "version": "0.1.0", "resources": [{"kind": "agent", "id": "react_agent"}]},
        artifact_path="/tmp/starter-0.1.0.tar.gz",
        artifact_sha256="deadbeef",
        approval_request_id="apr-1",
    )
    assert v["package_name"] == "starter"
    assert v["version"] == "0.1.0"
    assert v["approval_request_id"] == "apr-1"

    got = await store.get_package_version(package_name="starter", version="0.1.0")
    assert got is not None
    assert got["manifest"]["resources"][0]["id"] == "react_agent"

    versions = await store.list_package_versions(package_name="starter", limit=10, offset=0)
    assert versions["total"] >= 1

    inst = await store.record_package_install(
        package_name="starter",
        version="0.1.0",
        scope="workspace",
        metadata={"by": "t"},
        approval_request_id="apr-2",
    )
    assert inst["package_name"] == "starter"
    assert inst["version"] == "0.1.0"
    assert inst["scope"] == "workspace"
    assert inst["approval_request_id"] == "apr-2"

    installs = await store.list_package_installs(scope="workspace", limit=10, offset=0)
    assert installs["total"] >= 1

