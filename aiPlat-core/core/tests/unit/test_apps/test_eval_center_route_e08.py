"""评测 Extended E08 — /eval 路由契约。"""
from __future__ import annotations

from pathlib import Path

from core.apps.eval.service.eval_center_route import (
    EVAL_CENTER_UI_PATH,
    eval_center_route_contract,
)


def test_eval_center_route_contract_shape():
    c = eval_center_route_contract()
    assert c["canonical_ui_path"] == EVAL_CENTER_UI_PATH == "/eval"
    assert c["accuracy_claim"] is False
    assert c["api_canonical_prefix"].endswith("/eval")
    assert c["legacy_paths"]["/diagnostics/eval"] == "hard_cut_removed"


def test_frontend_eval_route_exists():
    """交叉验证管理端仍挂载 /eval → EvalCenter（测量证据）。"""
    root = Path(__file__).resolve().parents[5]  # workspace root (aiPlatform)
    # __file__ = .../aiPlat-core/core/tests/unit/test_apps/... → parents[4]=aiPlat-core, [5]=aiPlatform
    app = root / "aiPlat-management" / "frontend" / "src" / "App.tsx"
    manifest = root / "aiPlat-management" / "frontend" / "src" / "pageManifest.ts"
    assert app.is_file(), app
    app_txt = app.read_text(encoding="utf-8")
    assert "path: 'eval'" in app_txt
    assert "EvalCenter" in app_txt
    man_txt = manifest.read_text(encoding="utf-8")
    assert "'/eval'" in man_txt or '"/eval"' in man_txt
