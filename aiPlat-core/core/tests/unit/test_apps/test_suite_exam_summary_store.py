"""Suite exam summary ledger — honesty only, claim stays closed."""
from __future__ import annotations

import pytest

from core.apps.eval.service.capability_case_bank import PROFILE_ID_SMOKE
from core.apps.eval.service.suite_exam_summary_store import (
    get_suite_exam_summary,
    record_suite_exam_summary,
)
from core.apps.eval.service.suite_profile_exam import run_suite_profile_exam


def test_record_scoped_by_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    wid = "ws-exam-ledger"
    record_suite_exam_summary(
        {
            "ok": True,
            "profile_id": "prompt.regression.v1",
            "live": False,
            "run_id": "r1",
            "executed_case_count": 2,
            "counts": {"pass": 2},
        },
        workspace_id=wid,
    )
    hit = get_suite_exam_summary("prompt.regression.v1", workspace_id=wid)
    assert hit and hit["ok"] and hit["pass"] == 2 and hit["claim_eligible"] is False
    assert get_suite_exam_summary("prompt.regression.v1", workspace_id="other") is None


@pytest.mark.asyncio
async def test_run_exam_persists_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    wid = "ws-exam-persist"
    out = await run_suite_profile_exam(
        profile_id=PROFILE_ID_SMOKE, live=False, workspace_id=wid
    )
    assert out["ok"] and out["claim_eligible"] is False
    assert out.get("exam_summary_workspace_id") == wid
    summ = get_suite_exam_summary(PROFILE_ID_SMOKE, workspace_id=wid)
    assert summ and summ["ok"] and not summ["live"]
    assert int(summ["executed_case_count"]) == int(out["executed_case_count"])
