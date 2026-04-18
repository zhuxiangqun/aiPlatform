import importlib
import time

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_autocapture_to_prompt_revision_creates_pr_and_rc(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        store = getattr(server, "_execution_store", None)
        assert store is not None

        now = time.time()
        anyio.run(
            store.upsert_learning_artifact,
            {
                "artifact_id": "auto-1",
                "kind": "feedback_summary",
                "target_type": "agent",
                "target_id": "a1",
                "version": "auto:1",
                "status": "draft",
                "trace_id": "t1",
                "run_id": "r1",
                "payload": {
                    "feedback": {
                        "reason": "ci failure",
                        "top_failed_syscalls": [{"key": "tool:file_operations", "count": 2}],
                    }
                },
                "metadata": {"source": "test"},
                "created_at": now,
            },
        )

        r = client.post(
            "/api/core/learning/autocapture/to_prompt_revision",
            json={"artifact_id": "auto-1", "create_release_candidate": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        pr = data["prompt_revision"]
        assert pr["kind"] == "prompt_revision"
        assert pr["status"] == "draft"
        assert "patch" in pr["payload"]
        assert pr["payload"]["patch"].get("prepend")

        rc = data["release_candidate"]
        assert rc["kind"] == "release_candidate"
        assert rc["status"] == "draft"
        assert pr["artifact_id"] in (rc["payload"]["artifact_ids"] or [])

