import importlib
import json

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_run_cost_metrics_from_llm_syscalls(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")
    # Force scripted LLM adapter with non-zero usage
    monkeypatch.setenv("AIPLAT_LLM_PROVIDER", "scripted")
    monkeypatch.setenv(
        "AIPLAT_SCRIPTED_LLM_RESPONSES",
        json.dumps([{"content": "DONE: ok", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}]),
    )

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "u_demo", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        # Execute a minimal agent run (react_agent exists in engine/agents)
        r = client.post(
            "/api/core/gateway/execute",
            headers=hdr,
            json={
                "channel": "test",
                "kind": "agent",
                "target_id": "react_agent",
                "payload": {"input": {"task": "say hi"}, "context": {"tenant_id": "t_demo"}},
            },
        )
        assert r.status_code == 200, r.text
        run_id = r.json().get("run_id")
        assert isinstance(run_id, str) and run_id

        cost = client.get(f"/api/core/runs/{run_id}/cost?tenant_id=t_demo", headers=hdr)
        assert cost.status_code == 200, cost.text
        body = cost.json()
        assert body.get("counts", {}).get("llm_calls") >= 1
        assert body.get("llm_tokens", {}).get("total_tokens") >= 15


@pytest.mark.integration
def test_run_cost_regression_compare(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")
    monkeypatch.setenv("AIPLAT_LLM_PROVIDER", "scripted")
    monkeypatch.setenv("AIPLAT_FORCE_AGENT_MODEL_REBIND", "true")

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "u_demo", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        # baseline: 10 tokens
        monkeypatch.setenv(
            "AIPLAT_SCRIPTED_LLM_RESPONSES",
            json.dumps([{"content": "DONE: ok", "usage": {"prompt_tokens": 6, "completion_tokens": 4, "total_tokens": 10}}]),
        )
        r0 = client.post(
            "/api/core/gateway/execute",
            headers=hdr,
            json={"channel": "test", "kind": "agent", "target_id": "react_agent", "payload": {"input": {"task": "x"}, "context": {"tenant_id": "t_demo"}}},
        )
        base_run = r0.json().get("run_id")
        assert base_run

        # new: 20 tokens
        monkeypatch.setenv(
            "AIPLAT_SCRIPTED_LLM_RESPONSES",
            json.dumps([{"content": "DONE: ok", "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}}]),
        )
        r1 = client.post(
            "/api/core/gateway/execute",
            headers=hdr,
            json={"channel": "test", "kind": "agent", "target_id": "react_agent", "payload": {"input": {"task": "x"}, "context": {"tenant_id": "t_demo"}}},
        )
        new_run = r1.json().get("run_id")
        assert new_run

        cmp = client.get(f"/api/core/runs/{new_run}/cost?tenant_id=t_demo&baseline_run_id={base_run}&max_tokens_increase_pct=0.5", headers=hdr)
        assert cmp.status_code == 200, cmp.text
        reg = cmp.json().get("regression") or {}
        assert reg.get("baseline_run_id") == base_run
        assert reg.get("passed") is False
