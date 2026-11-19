"""N07/N22 deepen：H.1 薄表单字段；非矩阵编辑器 / 非 certified。"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[6]


def test_abox_panel_h1_thin_form_fields():
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
    assert "formFieldsFromH1" in text
    assert "buildH1FromForm" in text
    assert "h1Effect" in text
    assert "h1Principals" in text
    assert "h1Actions" in text
    assert "非矩阵编辑器" in text
    assert "H.1 薄表单" in text


def test_apply_still_uses_h1_policy_body():
    """薄表单仍走既有 PUT h1_policy，不另开编辑器后端。"""
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "AboxAclPanel.tsx"
    ).read_text(encoding="utf-8")
    assert "h1_policy" in panel
    assert "buildH1FromForm" in panel
    routes = (
        ROOT / "aiPlat-platform" / "apps" / "fde" / "api" / "action_routes.py"
    ).read_text(encoding="utf-8")
    assert "apply_graph_h1_policy" in routes
