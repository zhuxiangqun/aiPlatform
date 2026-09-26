"""Phase K5 — repeat failures enqueue edge drafts; never auto-apply."""

from __future__ import annotations

import json

from core.apps.fde.service.k_wave_propose import enqueue_repeat_failure_proposals, ledger_path
from core.harness.knowledge.ontology_case_learning import OntologyCaseStore


def _fail(domain: str, action: str, code: str, n: int = 1):
    store = OntologyCaseStore(domain)
    ids = []
    for i in range(n):
        out = store.record(
            title=f"{action}-{code}-{i}",
            summary="fail",
            outcome="failure",
            action_id=action,
            metadata={"error_code": code, "skill_candidate": False},
            write_graph=False,
        )
        ids.append(out["case_id"])
    return ids


async def test_below_threshold_no_proposal(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _fail("it-ops", "fetch", "timeout", 1)
    called = {"n": 0}

    def _writer(_d, _c):
        called["n"] += 1
        return "nope"

    out = await enqueue_repeat_failure_proposals("it-ops", writer=_writer)
    assert out["created_count"] == 0
    assert out["auto_apply"] is False
    assert called["n"] == 0


async def test_two_low_reward_creates_once(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ONTOLOGY_EVOLVE_MIN_REWARD", "0.7")
    _fail("it-ops", "fetch", "timeout", 2)
    seen = []

    def _writer(_d, changes):
        seen.append(changes)
        return "prop-k5"

    first = await enqueue_repeat_failure_proposals("it-ops", writer=_writer)
    assert first["created_count"] == 1
    assert first["auto_apply"] is False
    change = seen[0]
    assert change["source"]["auto_apply"] is False
    assert change["source"]["policy_gate"] is False
    assert change["add"]["class"]["tier"] == "edge"
    assert first["created"][0]["applied"] is False

    second = await enqueue_repeat_failure_proposals("it-ops", writer=_writer)
    assert second["created_count"] == 0
    assert any(s.get("reason") == "open_draft" for s in second["skipped"])
    assert len(seen) == 1
    rows = [json.loads(line) for line in ledger_path().read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["status"] in ("draft", "local_draft")


async def test_expired_draft_does_not_apply(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _fail("it-ops", "fetch", "denied", 3)
    path = ledger_path()
    path.parent.mkdir(parents=True)
    old = {
        "proposal_id": "old",
        "dedup_key": "it-ops|fetch|denied",
        "status": "draft",
        "applied": False,
        "auto_apply": False,
        "created_at": 1,
    }
    path.write_text(json.dumps(old) + "\n", encoding="utf-8")

    def _writer(_d, _c):
        return "prop-new"

    out = await enqueue_repeat_failure_proposals("it-ops", writer=_writer, now=40 * 86400)
    assert out["created_count"] == 1
    text = ledger_path().read_text(encoding="utf-8")
    assert '"status": "expired"' in text
    assert "prop-new" in text
    assert out["auto_apply"] is False
