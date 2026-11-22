"""N07/N22 deepen：H.1 矩阵配置轴（crud_matrix.h1_matrix_* ← role×action SSOT）。"""
from __future__ import annotations

import json
from pathlib import Path

from core.policy.graph_abox_acl import crud_matrix_doc, h1_matrix_axes


ROOT = Path(__file__).resolve().parents[6]


def test_h1_matrix_axes_defaults():
    axes = h1_matrix_axes()
    assert "viewer" in axes["roles"]
    assert "analyst" in axes["roles"]
    assert "admin" in axes["roles"]
    assert "read" in axes["actions"]
    assert "admin" not in axes["actions"]
    assert axes["certified"] is False
    doc = crud_matrix_doc()
    assert doc["h1_matrix_roles"] == axes["roles"]
    assert doc["h1_matrix_actions"] == axes["actions"]


def test_h1_matrix_axes_env_extends(monkeypatch):
    monkeypatch.setenv(
        "AIPLAT_ABOX_ROLE_ACTION_MATRIX",
        json.dumps({"auditor": ["read"], "viewer": ["read"]}),
    )
    axes = h1_matrix_axes()
    assert "auditor" in axes["roles"]
    assert "viewer" in axes["roles"]
    doc = crud_matrix_doc()
    assert "auditor" in doc["h1_matrix_roles"]


def test_panel_documents_h1_matrix_config_axes():
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "AboxAclPanel.tsx"
    )
    text = panel.read_text(encoding="utf-8")
    assert "h1_matrix_" in text
    assert "h1MatrixRoles" in text
    assert "crud_matrix" in text
    assert "配置轴" in text
    assert "非 certified" in text
