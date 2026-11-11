"""ADR P1 content_purpose_ok audit + promote gate (claim closed)."""
from __future__ import annotations

import pytest

from core.apps.eval.service.content_purpose_ok import (
    CONTENT_PURPOSE_SCHEMA,
    ContentPurposeOkError,
    assert_cases_content_purpose_ok,
    audit_case_content_purpose,
    content_purpose_ok_for_subject,
    content_purpose_ok_inventory,
)


def test_audit_rejects_missing_oracle_and_purpose():
    errs = audit_case_content_purpose(
        {
            "case_id": "x.1",
            "capabilities": ["task_completion"],
            "prompt": "please complete the task carefully",
        }
    )
    assert "missing_field:test_purpose" in errs
    assert "oracle_anchor_missing" in errs


def test_audit_allows_short_clarification_prompt():
    errs = audit_case_content_purpose(
        {
            "case_id": "x.clarify",
            "capabilities": ["clarification"],
            "prompt": "帮我部署。",
            "success_criteria": {
                "must_contain": ["staging", "production"],
                "must_not_contain": ["直接部署"],
            },
            "test_purpose": {
                "summary": "验证歧义部署请求会先澄清环境",
                "why_this_case": "短提示制造目标环境歧义",
                "expected_behavior": ["追问 staging 或 production"],
                "failure_signals": ["直接部署"],
                "not_testing": ["不测真实发布"],
                "oracle_rationale": "词面 staging/production + 禁止直接部署",
            },
        }
    )
    assert errs == []


def test_assert_cases_content_purpose_ok_fail_closed():
    with pytest.raises(ContentPurposeOkError):
        assert_cases_content_purpose_ok(
            [{"case_id": "bad", "capabilities": ["task_completion"], "prompt": "x"}],
            subject_kind="prompt",
        )


def test_content_purpose_ok_inventory_all_ready():
    inv = content_purpose_ok_inventory()
    assert inv["schema"] == CONTENT_PURPOSE_SCHEMA
    assert inv["claim_eligible"] is False
    assert inv["accuracy_claim"] is False
    assert inv["subject_count"] >= 10
    assert inv["content_purpose_ready_count"] == inv["subject_count"]
    assert inv["ok"] is True


def test_content_purpose_ok_for_prompt_subject():
    rep = content_purpose_ok_for_subject("prompt")
    assert rep["ok"] is True
    assert rep["content_purpose_ready"] is True
    assert rep["case_count"] >= 15


def test_promote_gated_by_content_purpose_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    from core.apps.eval.service.subject_capability_promote import (
        promote_subject_capability_bank,
    )

    out = promote_subject_capability_bank(
        subject_kind="api",
        workspace_id="ws-cpo",
        reviewer="owner",
        frozen_by="owner",
    )
    assert out["ok"] is True
    assert out["content_purpose_ok"] is True
    assert out["claim_eligible"] is False


def test_eval_content_purpose_ok_facade():
    from core.api.core_facade import (
        eval_content_purpose_ok_for_subject,
        eval_content_purpose_ok_inventory,
    )

    inv = eval_content_purpose_ok_inventory()
    assert inv["ok"] is True
    one = eval_content_purpose_ok_for_subject("dataset")
    assert one["subject_kind"] == "dataset"
    assert one["content_purpose_ready"] is True
