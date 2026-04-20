import time

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_change_control_detail_links_include_trace_and_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_AUTOSMOKE_ENFORCE", "false")

    from core.server import app
    from core.services import get_execution_store

    store = get_execution_store()
    now = time.time()

    anyio.run(
        store.add_syscall_event,
        {
            "id": "se-cc-1",
            "kind": "changeset",
            "name": "change_control.autosmoke.result",
            "status": "success",
            "trace_id": "trace-1",
            "run_id": "run_01HZZZZZZZZZZZZZZZZZZZZZZZ",
            "target_type": "change",
            "target_id": "chg-abc123",
            "args": {"x": 1},
            "result": {"y": 2},
            "created_at": now,
        },
    )

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")  # ensure lifespan init
        r = client.get("/api/core/change-control/changes/chg-abc123")
        assert r.status_code == 200, r.text
        data = r.json()
        links = data.get("links") or {}
        assert "traces_ui" in links
        assert "runs_ui" in links
        assert "links_ui" in links

