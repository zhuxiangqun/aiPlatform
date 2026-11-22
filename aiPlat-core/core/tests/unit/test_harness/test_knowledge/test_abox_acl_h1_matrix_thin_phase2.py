"""N07/N22 deepen：H.1 薄矩阵（角色×动作 UI）；共享 actions 折叠 / 非 per-role / 非 certified。"""
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
    assert "薄矩阵" in text
    assert "非完整 per-role" in text
    assert "非 certified" in text
    # 固定轴覆盖 viewer/analyst/admin × read/update/state_change/delete
    for role in ("viewer", "analyst", "admin"):
        assert f"'{role}'" in text or f'"{role}"' in text
    for act in ("read", "update", "state_change", "delete"):
        assert f"'{act}'" in text or f'"{act}"' in text


def test_panel_matrix_folds_to_shared_actions():
    """诚实锁：写入仍走 principals + 共享 actions，非 per-cell 存储。"""
    text = PANEL.read_text(encoding="utf-8")
    assert "共享 actions" in text
    assert "pushFormToRaw" in text
