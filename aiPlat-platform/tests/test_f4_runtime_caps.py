"""F4 runtime caps — load app_runtime without builder package __init__."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


def _load_app_runtime():
    path = Path(__file__).resolve().parents[1] / "builder" / "app_runtime.py"
    # Parse-only check for MAX_REPAIR + clamp to avoid heavy imports in CI unit path
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    max_val = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "MAX_REPAIR_ATTEMPTS":
                    if isinstance(node.value, ast.Constant):
                        max_val = node.value.value
    assert max_val == 2, max_val
    assert "repair_exhausted" in src
    assert 'next": "hitl"' in src or "next': 'hitl'" in src or 'next": "hitl"' in src
    assert "max_rounds = max(1, min(max_rounds, MAX_REPAIR_ATTEMPTS))" in src


def test_max_repair_attempts_is_two():
    _load_app_runtime()


def test_deploy_mixin_surfaces_openable_and_rejects():
    # F4 surfaces live on BuilderProjectService after P1-14 God Class split
    # (builder_deploy_mixin keeps deploy/health/insight entrypoints only).
    root = Path(__file__).resolve().parents[1] / "builder"
    service_src = (root / "builder_project_service.py").read_text(encoding="utf-8")
    mixin_src = (root / "builder_deploy_mixin.py").read_text(encoding="utf-8")
    assert "rejected_artifacts" in service_src
    assert "openable" in service_src
    # Persist key is last_deploy (+ rejected_count/rejected_artifacts), not last_deploy_rejects
    assert "last_deploy" in service_src
    assert "rejected_count" in service_src
    assert "smoke_test" in service_src
    assert "async def deploy_to_app" in mixin_src
    assert "async def get_health_report" in mixin_src
