import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_code_intel_scan_and_blast(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}
    with TestClient(server.app) as client:
        r = client.get("/api/core/diagnostics/code-intel/scan", headers=hdr)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status") == "ok"
        assert body.get("stats", {}).get("files", 0) > 10
        nodes = body.get("nodes") or []
        # should include aiPlat-core server
        assert any(str(n.get("path") or "").endswith("aiPlat-core/core/server.py") for n in nodes)

        b = client.get("/api/core/diagnostics/code-intel/blast?file=aiPlat-core/core/server.py", headers=hdr)
        assert b.status_code == 200, b.text
        assert b.json().get("status") == "ok"

