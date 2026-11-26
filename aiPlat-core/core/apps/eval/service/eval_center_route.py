"""评测中心 UI 路由契约（标准附录 H / Extended E08）。

Canonical 管理端路径为 ``/eval``；旧 ``/diagnostics/eval`` 已硬切（非入口）。
本模块仅声明契约，不替代前端路由实现。
"""
from __future__ import annotations

from typing import Any, Dict

EVAL_CENTER_UI_PATH = "/eval"
EVAL_CENTER_LEGACY_DIAGNOSTICS = "/diagnostics/eval"


def eval_center_route_contract() -> Dict[str, Any]:
    """返回评测中心 canonical UI 路由契约（E08）。

    Returns:
        含 ``canonical_ui_path`` / 旧路径硬切说明；``accuracy_claim=false``。
    """
    return {
        "schema": "aiplat.eval_center_route.v0",
        "canonical_ui_path": EVAL_CENTER_UI_PATH,
        "legacy_paths": {
            EVAL_CENTER_LEGACY_DIAGNOSTICS: "hard_cut_removed",
        },
        "api_canonical_prefix": "/api/platform/apps/eval",
        "accuracy_claim": False,
        "honesty": "UI route contract ≠ certified accuracy / ≠ Gate pass",
        "evidence_refs": [
            "frontend:App.tsx:path=eval→EvalCenter",
            "frontend:pageManifest.ts:key=/eval",
        ],
    }
