"""V1-pre — org run and K5 refuse to start when edge auto-apply is on."""

from __future__ import annotations

from core.apps.fde.service.k_wave_propose import enqueue_repeat_failure_proposals, ledger_path
from core.apps.org.service.org_runtime import run_org_goal


def test_org_run_refuses_when_auto_apply_on(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY", "true")
    out = run_org_goal(domain_id="it-ops")
    assert out["reason"] == "edge_auto_apply_forbidden"
    assert out["auto_apply"] is False
    assert not (tmp_path / "org" / "runs.json").exists()


async def test_k5_refuses_when_auto_apply_on(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY", "true")
    called = {"n": 0}

    def _writer(_d, _c):
        called["n"] += 1
        return "nope"

    out = await enqueue_repeat_failure_proposals("it-ops", writer=_writer)
    assert out["reason"] == "edge_auto_apply_forbidden"
    assert out["created_count"] == 0
    assert called["n"] == 0
    assert not ledger_path().exists()
