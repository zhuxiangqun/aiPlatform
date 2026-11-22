"""N02 deepen：ObjectType 人审发布；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    evaluate_object_type_publish_gate,
    run_object_type_publish_suite,
)
from core.harness.knowledge_pipeline.object_type_publish import (
    ObjectTypePublishError,
    assert_object_type_publish_role,
    evaluate_object_type_publish_gate as core_gate,
    run_object_type_publish_suite as core_suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_suite_and_gate_honesty():
    suite = core_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 7
    assert suite["certified"] is False
    assert suite["n02_full_conformance"] is False
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
    assert "assert_schema_object_types_published" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "run_object_type_publish_suite" in facade.read_text(encoding="utf-8")
    route = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "object_type_publish_routes.py"
    )
    assert "role=body.role" in route.read_text(encoding="utf-8")
    router = ROOT / "aiPlat-platform" / "apps" / "fde" / "api" / "router.py"
    assert "object_type_publish_routes" in router.read_text(encoding="utf-8")
    pkg = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "ontology_package.py"
    )
    assert "assert_schema_object_types_published" in pkg.read_text(encoding="utf-8")
