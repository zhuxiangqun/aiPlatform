"""P1.4 expand / bump / coverage."""
from __future__ import annotations

import pytest

from core.apps.eval.service.case_factory import (
    generate_cases_from_template,
    publish_draft_workspace_pack,
)
from core.apps.eval.service.case_freeze import freeze_workspace_pack
from core.apps.eval.service.case_pack_ops import (
    CasePackOpsError,
    bump_workspace_pack_version,
    expand_draft_workspace_pack,
    summarize_workspace_pack_coverage,
)
from core.apps.eval.service.case_review_queue import (
    enqueue_pack_for_review,
    submit_review_decision,
)


def _draft(tmp_path, monkeypatch, pack_id="ws.ops.demo", version="0.1.0"):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cases = generate_cases_from_template(
        {"prompt": "say ok", "rubric": {"type": "lexical"}, "category": "normal"},
        variants=[{"case_id": "o1"}],
    )
    return publish_draft_workspace_pack(
        pack_id=pack_id,
        version=version,
        cases=cases,
        workspace_id="ws-a",
        caller_workspace_id="ws-a",
    )


def test_expand_and_coverage(tmp_path, monkeypatch):
    draft = _draft(tmp_path, monkeypatch)
    out = expand_draft_workspace_pack(
        pack_id="ws.ops.demo",
        version="0.1.0",
        workspace_id="ws-a",
        template={"prompt": "say yes", "rubric": {"type": "lexical"}, "category": "normal"},
        variants=[{"case_id": "o2"}],
    )
    assert out["added"] == 1
    assert out["n_cases"] == 2
    assert out["claim_eligible"] is False
    assert out["pack_hash"] != draft["pack_hash"]
    cov = summarize_workspace_pack_coverage(workspace_id="ws-a")
    assert cov["n_versions"] >= 1
    assert cov["by_status"].get("draft", 0) >= 1
    assert any(i["pack_id"] == "ws.ops.demo" and i["n_cases"] == 2 for i in cov["items"])


def test_expand_frozen_forbidden(tmp_path, monkeypatch):
    _draft(tmp_path, monkeypatch, pack_id="ws.ops.fz", version="1.0.0")
    enqueue_pack_for_review(pack_id="ws.ops.fz", version="1.0.0", workspace_id="ws-a")
    submit_review_decision(
        pack_id="ws.ops.fz", version="1.0.0", workspace_id="ws-a", decision="approve"
    )
    freeze_workspace_pack(pack_id="ws.ops.fz", version="1.0.0", workspace_id="ws-a")
    with pytest.raises(CasePackOpsError, match="immutable"):
        expand_draft_workspace_pack(
            pack_id="ws.ops.fz",
            version="1.0.0",
            workspace_id="ws-a",
            variants=[{"case_id": "x", "prompt": "p", "rubric": {"type": "lexical"}, "category": "normal"}],
        )


def test_bump_from_frozen(tmp_path, monkeypatch):
    _draft(tmp_path, monkeypatch, pack_id="ws.ops.bump", version="1.0.0")
    enqueue_pack_for_review(pack_id="ws.ops.bump", version="1.0.0", workspace_id="ws-a")
    submit_review_decision(
        pack_id="ws.ops.bump", version="1.0.0", workspace_id="ws-a", decision="approve"
    )
    freeze_workspace_pack(pack_id="ws.ops.bump", version="1.0.0", workspace_id="ws-a")
    bumped = bump_workspace_pack_version(
        pack_id="ws.ops.bump",
        from_version="1.0.0",
        workspace_id="ws-a",
        template={"prompt": "extra", "rubric": {"type": "lexical"}, "category": "normal"},
        variants=[{"case_id": "new1"}],
    )
    assert bumped["version"] == "1.0.1"
    assert bumped["status"] == "draft"
    assert bumped["kind"] == "curated"
    assert bumped["n_cases"] == 2
    assert bumped["claim_eligible"] is False
