"""V1 — five-step replay. Missing steps stay missing. No business writes."""

from __future__ import annotations

import json

from core.apps.fde.service.k_wave_propose import ledger_path
from core.apps.fde.service.k_wave_signal import signals_path
from core.apps.org.service.v_wave_replay import replay_org_trace
from core.harness.knowledge.ontology_case_learning import OntologyCaseStore


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _step(out, name):
    return next(s for s in out["steps"] if s["step"] == name)


def test_full_chain_same_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    tid = "trace-full"
    _write_jsonl(signals_path(), [{
        "signal_id": "sig-1",
        "trace_id": tid,
        "trace_origin": "extraction_confirm",
    }])
    _write_jsonl(tmp_path / "k_wave" / "arbitration.jsonl", [{
        "ticket_id": "arb-1",
        "trace_id": tid,
        "trace_origin": "inherited",
        "status": "pending",
    }])
    runs = tmp_path / "org" / "runs.json"
    runs.parent.mkdir(parents=True, exist_ok=True)
    runs.write_text(json.dumps({"runs": [{
        "run_id": "run-1",
        "trace_id": tid,
        "trace_origin": "inherited",
        "status": "needs_hitl",
    }]}), encoding="utf-8")
    OntologyCaseStore("it-ops").record(
        title="case",
        summary="ok",
        outcome="partial",
        action_id="org_run_goal",
        metadata={"trace_id": tid, "trace_origin": "inherited", "skill_candidate": False},
        write_graph=False,
    )
    _write_jsonl(ledger_path(), [{
        "proposal_id": "prop-1",
        "trace_id": tid,
        "trace_origin": "inherited",
        "auto_apply": False,
        "status": "draft",
    }])
    before_yaml = list((tmp_path / "ontologies").glob("*.yaml")) if (tmp_path / "ontologies").exists() else []
    out = replay_org_trace(tid, domain_id="it-ops")
    assert out["status"] == "ok"
    assert out["read_only"] is True
    for name in ("extraction_confirm", "arbitration", "run", "case", "proposal"):
        step = _step(out, name)
        assert step["status"] == "present", name
        assert step["records"][0]["trace_id"] == tid
    assert _step(out, "proposal")["records"][0]["auto_apply"] is False
    after_yaml = list((tmp_path / "ontologies").glob("*.yaml")) if (tmp_path / "ontologies").exists() else []
    assert before_yaml == after_yaml


def test_direct_run_does_not_invent_upstream(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    tid = "run-only"
    runs = tmp_path / "org" / "runs.json"
    runs.parent.mkdir(parents=True, exist_ok=True)
    runs.write_text(json.dumps({"runs": [{
        "run_id": tid,
        "trace_id": tid,
        "trace_origin": "run",
        "status": "needs_hitl",
    }]}), encoding="utf-8")
    out = replay_org_trace(tid)
    assert out["status"] == "ok"
    assert _step(out, "run")["status"] == "present"
    for name in ("extraction_confirm", "arbitration", "case", "proposal"):
        step = _step(out, name)
        assert step["status"] == "absent"
        assert step["note"] == "该步未发生"
        assert step["records"] == []


def test_run_backfill_is_conflict(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    tid = "run-backfill"
    _write_jsonl(signals_path(), [{
        "signal_id": "sig-x",
        "trace_id": tid,
        "trace_origin": "extraction_confirm",
    }])
    runs = tmp_path / "org" / "runs.json"
    runs.parent.mkdir(parents=True, exist_ok=True)
    runs.write_text(json.dumps({"runs": [{
        "run_id": tid,
        "trace_id": tid,
        "trace_origin": "run",
        "status": "needs_hitl",
    }]}), encoding="utf-8")
    out = replay_org_trace(tid)
    assert out["status"] == "conflict"
    assert "run_backfill_forbidden" in out["conflicts"]
    assert _step(out, "run")["status"] == "conflict"
