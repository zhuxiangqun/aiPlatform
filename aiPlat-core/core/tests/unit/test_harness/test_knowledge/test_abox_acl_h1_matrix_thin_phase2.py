"""N07/N22 deepen：H.1 薄矩阵回退路径（共享展开）；per-role 见 matrix_per_role 测试。"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[6]
PANEL = (
    ROOT
    / "aiPlat-management"
    / "frontend"
    / "src"
    / "pages"
    / "KnowledgeFactory"
    / "AboxAclPanel.tsx"
)


def test_panel_documents_h1_matrix_thin():
    text = PANEL.read_text(encoding="utf-8")
    assert "H1_MATRIX_ROLES" in text
    assert "H1_MATRIX_ACTIONS" in text
    assert "matrixCellsFromForm" in text
    assert "formFromMatrixCells" in text
    assert "matrixCellsFromShared" in text
    assert "非 certified" in text
    # 固定轴覆盖 viewer/analyst/admin × read/update/state_change/delete
    for role in ("viewer", "analyst", "admin"):
        assert f"'{role}'" in text or f'"{role}"' in text
    for act in ("read", "update", "state_change", "delete"):
        assert f"'{act}'" in text or f'"{act}"' in text


def test_panel_matrix_folds_to_shared_actions():
    """薄回退：无 role_actions 时仍可从共享 principals/actions 展开。"""
    text = PANEL.read_text(encoding="utf-8")
    assert "matrixCellsFromShared" in text
    assert "共享" in text
    assert "pushFormToRaw" in text
