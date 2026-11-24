"""N02 deepen + residual：ObjectType 人审发布 / 多租户批量；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    bulk_transition_object_types as facade_bulk,
    evaluate_object_type_publish_gate,
    run_object_type_publish_suite,
)
from core.harness.knowledge_pipeline.object_type_publish import (
    ObjectTypePublishError,
    assert_object_type_publish_role,
    bulk_transition_object_types,
    evaluate_object_type_publish_gate as core_gate,
    run_object_type_publish_suite as core_suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_suite_and_gate_honesty():
    suite = core_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 9
    assert suite["certified"] is False
    assert suite["n02_full_conformance"] is False
    assert suite.get("n02_object_type_freeze") is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "bulk_opt_in" in ids
    assert "bulk_unavailable" in ids
    gate = core_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = core_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]


def test_facade_suite():
    suite = run_object_type_publish_suite()
    assert suite["ok"] is True
    gate = evaluate_object_type_publish_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False


def test_bulk_unavailable_default():
    r = bulk_transition_object_types(
        [
            {
                "tenant_id": "t",
                "object_type_id": "X",
                "version": "1.0.0",
                "to_status": "in_review",
            }
        ],
        actor="a",
        reason="r",
    )
    assert r["status"] == "object_type_bulk_unavailable"
    assert r["certified"] is False
    fr = facade_bulk(
        [
            {
                "tenant_id": "t",
                "object_type_id": "X",
                "version": "1.0.0",
                "to_status": "in_review",
            }
        ],
        actor="a",
        reason="r",
    )
    assert fr["status"] == "object_type_bulk_unavailable"


def test_assert_publish_role_config(monkeypatch):
    monkeypatch.setenv("AIPLAT_OBJECT_TYPE_PUBLISH_RBAC", "1")
    monkeypatch.setenv(
        "AIPLAT_OBJECT_TYPE_PUBLISH_ROLES", "reviewer,knowledge_admin"
    )
    assert_object_type_publish_role(role="reviewer")
    with pytest.raises(ObjectTypePublishError, match="rbac denied"):
        assert_object_type_publish_role(role="viewer")
    monkeypatch.setenv("AIPLAT_OBJECT_TYPE_PUBLISH_RBAC", "0")
    assert_object_type_publish_role(role="")  # opt-out


def test_docs_and_wiring_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "object_type_publish.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "run_object_type_publish_suite" in text
    assert "bulk_transition_object_types" in text
    assert "assert_schema_object_types_published" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    ftext = facade.read_text(encoding="utf-8")
    assert "run_object_type_publish_suite" in ftext
    assert "bulk_transition_object_types" in ftext
    route = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "object_type_publish_routes.py"
    )
    rtext = route.read_text(encoding="utf-8")
    assert "role=body.role" in rtext
    assert "bulk-transition" in rtext
    router = ROOT / "aiPlat-platform" / "apps" / "fde" / "api" / "router.py"
    assert "object_type_publish_routes" in router.read_text(encoding="utf-8")
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "ObjectTypePublishPanel.tsx"
    )
    assert "bulk-transition" in panel.read_text(encoding="utf-8")
