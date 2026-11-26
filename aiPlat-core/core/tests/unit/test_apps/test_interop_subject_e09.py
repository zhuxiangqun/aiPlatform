"""评测 Extended E09 — Tool/MCP subject + verified_tier。"""
from __future__ import annotations

import pytest

from core.apps.eval.service.interop_subject import (
    list_e09_subject_kinds,
    normalize_tool_mcp_subject,
)
from core.apps.eval.service.subject_adapter import get_subject_adapter


def test_e09_kinds_include_tool_mcp():
    assert set(list_e09_subject_kinds()) == {"tool", "mcp"}
    assert get_subject_adapter("mcp").subject_kind == "mcp"
    assert get_subject_adapter("tool").subject_kind == "tool"


def test_interop_ref_requires_verified_tier():
    with pytest.raises(ValueError, match="verified_tier_required"):
        normalize_tool_mcp_subject(
            {"subject_kind": "tool", "subject_id": "t1", "interop_ref": "pack:x"}
        )


def test_normalize_ok_with_verified_tier():
    out = normalize_tool_mcp_subject(
        {
            "subject_kind": "mcp",
            "subject_id": "srv1",
            "interop_ref": "mcp:srv1",
            "verified_tier": "L1",
            "claimed_tier": "L2",
        }
    )
    assert out["verified_tier"] == "L1"
    assert out["tier_claim_illegal"] is True
    assert out["claim_eligible"] is False


def test_adapter_binds_verified_tier():
    ad = get_subject_adapter("tool")
    c = ad.build_contract(
        object_id="echo",
        verified_tier="L1",
        interop_ref="tool:echo",
    )
    assert c["verified_tier"] == "L1"
    assert c["interop_ref"] == "tool:echo"
