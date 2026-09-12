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
    path = Path(__file__).resolve().parents[1] / "builder" / "builder_deploy_mixin.py"
    src = path.read_text(encoding="utf-8")
    assert "rejected_artifacts" in src
    assert "openable" in src
    assert "last_deploy_rejects" in src
    assert "smoke_test" in src
