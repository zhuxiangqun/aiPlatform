import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_gate_policy_crud(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}
    with TestClient(server.app) as client:
        r0 = client.get("/api/core/governance/gate-policies", headers=hdr)
        assert r0.status_code == 200

        boot = client.post("/api/core/governance/gate-policies/bootstrap?force=true", headers=hdr, json={})
        assert boot.status_code == 200, boot.text
        assert boot.json().get("seeded") is True

        r1 = client.get("/api/core/governance/gate-policies", headers=hdr)
        assert r1.status_code == 200
        items = r1.json().get("items") or []
        ids = [x.get("policy_id") for x in items if isinstance(x, dict)]
        assert "dev" in ids and "staging" in ids and "prod" in ids

        up = client.put(
            "/api/core/governance/gate-policies/prod",
            headers=hdr,
            json={"name": "生产门禁", "description": "all gates", "config": {"apply_gate": {"gate_policy": "all"}}},
        )
        assert up.status_code == 200, up.text
        assert up.json().get("item", {}).get("policy_id") == "prod"
        assert up.json().get("change_id")

        g1 = client.get("/api/core/governance/gate-policies/prod", headers=hdr)
        assert g1.status_code == 200

        # update to create a revision
        up2 = client.put(
            "/api/core/governance/gate-policies/prod",
            headers=hdr,
            json={"name": "生产门禁", "description": "v2", "config": {"apply_gate": {"gate_policy": "autosmoke"}}},
        )
        assert up2.status_code == 200, up2.text
        assert int(up2.json().get("item", {}).get("version") or 0) >= 2

        vers = client.get("/api/core/governance/gate-policies/prod/versions", headers=hdr)
        assert vers.status_code == 200, vers.text
        revs = vers.json().get("revisions") or []
        assert len(revs) >= 1
        # rollback to version 1 (should exist as first revision)
        v0 = int(revs[-1].get("version") or 1)
        rb = client.post("/api/core/governance/gate-policies/prod/rollback", headers=hdr, json={"version": v0})
        assert rb.status_code == 200, rb.text
        assert rb.json().get("change_id")

        sd = client.post("/api/core/governance/gate-policies/prod/set-default", headers=hdr)
        assert sd.status_code == 200
        assert sd.json().get("default_id") == "prod"
        assert sd.json().get("change_id")

        d0 = client.delete("/api/core/governance/gate-policies/prod", headers=hdr)
        assert d0.status_code == 200
        assert d0.json().get("change_id")


@pytest.mark.integration
def test_gate_policy_change_control_workflow(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}
    with TestClient(server.app) as client:
        client.post("/api/core/governance/gate-policies/bootstrap?force=true", headers=hdr, json={})

        prop = client.post(
            "/api/core/governance/gate-policies/prod/propose",
            headers=hdr,
            json={"config": {"apply_gate": {"gate_policy": "autosmoke"}}, "set_default": True, "require_approval": True},
        )
        assert prop.status_code == 200, prop.text
        change_id = prop.json().get("change_id")
        req_id = prop.json().get("approval_request_id")
        assert change_id and req_id

        # Apply before approval should be blocked
        ap0 = client.post(f"/api/core/governance/gate-policies/changes/{change_id}/apply", headers=hdr, json={})
        assert ap0.status_code == 409, ap0.text
        assert ap0.json().get("detail", {}).get("code") == "approval_required"

        ok = client.post(f"/api/core/approvals/{req_id}/approve", headers=hdr, json={"approved_by": "admin"})
        assert ok.status_code == 200, ok.text

        ap1 = client.post(f"/api/core/governance/gate-policies/changes/{change_id}/apply", headers=hdr, json={})
        assert ap1.status_code == 200, ap1.text
        assert ap1.json().get("item", {}).get("policy_id") == "prod"
        assert ap1.json().get("default_id") == "prod"
