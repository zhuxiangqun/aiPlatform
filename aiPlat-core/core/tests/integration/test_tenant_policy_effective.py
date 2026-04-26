import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_tenant_policy_effective_merges_env_and_tenant(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    # env defaults
    monkeypatch.setenv("AIPLAT_RUN_WAIT_AUTO_RESUME_ENABLED", "false")
    monkeypatch.setenv("AIPLAT_RUN_WAIT_AUTO_RESUME_DEFAULT", "true")
    monkeypatch.setenv("AIPLAT_RUN_WAIT_AUTO_RESUME_ALLOWLIST", "tool:*")
    monkeypatch.setenv("AIPLAT_APPROVAL_LAYER_POLICY", "both")
    monkeypatch.setenv("AIPLAT_APPROVAL_TOOL_FORCE_LIST", "tool:file_operations")

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        pol = {
            "run_wait_auto_resume": {"enabled": True, "allowlist": "skill:*"},
            "approval_layering": {"policy": "skill_only"},
        }
        up = client.put("/api/core/policies/tenants/t_demo", headers=hdr, json={"policy": pol})
        assert up.status_code == 200, up.text

        r = client.get("/api/core/policies/tenants/t_demo/effective", headers=hdr)
        assert r.status_code == 200, r.text
        body = r.json()
        eff = body["effective"]

        assert eff["run_wait_auto_resume"]["enabled"] is True  # tenant override
        assert eff["run_wait_auto_resume"]["allowlist"] == "skill:*"  # tenant override
        assert eff["run_wait_auto_resume"]["default"] is True  # env fallback

        assert eff["approval_layering"]["policy"] == "skill_only"  # tenant override
        assert eff["approval_layering"]["tool_force_list"] == "tool:file_operations"  # env fallback

