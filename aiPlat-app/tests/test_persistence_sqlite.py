import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_app_channels_sessions_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_APP_DB_PATH", str(tmp_path / "app.sqlite3"))

    import api.rest.routes as routes

    importlib.reload(routes)

    with TestClient(routes.app) as client:
        c = client.post("/app/channels", json={"name": "c1", "type": "webhook"})
        assert c.status_code == 200
        cid = c.json()["id"]

        l = client.get("/app/channels")
        assert l.status_code == 200
        assert any(x["id"] == cid for x in l.json()["channels"])

        t = client.post(f"/app/channels/{cid}/test")
        assert t.status_code == 200
        assert t.json()["status"] == "ok"

        s = client.post("/app/sessions", json={"channel_id": cid, "user_id": "u1"})
        assert s.status_code == 200
        sid = s.json()["id"]

        s2 = client.get(f"/app/sessions/{sid}")
        assert s2.status_code == 200
        assert s2.json()["id"] == sid

        end = client.post(f"/app/sessions/{sid}/end")
        assert end.status_code == 200

        ended = client.get("/app/sessions", params={"status": "ended"})
        assert ended.status_code == 200
        assert any(x["id"] == sid for x in ended.json()["sessions"])

