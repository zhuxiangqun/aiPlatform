"""Regression: materials_chat must not locally `import logging` inside _execute_impl.

A local import makes `logging` a function-local name; if that branch is skipped,
later `logging.getLogger(...)` raises UnboundLocalError — surfaced to 小朱 as the answer.
"""
from __future__ import annotations

import ast
from pathlib import Path


def test_materials_chat_no_local_logging_import():
    path = Path(__file__).resolve().parents[3] / "apps" / "agents" / "materials_chat.py"
    # parents: test_apps -> unit -> tests -> core
    # actually: .../core/tests/unit/test_apps/thisfile -> parents[3]=core
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for stmt in ast.walk(sub):
                    if isinstance(stmt, ast.Import):
                        for alias in stmt.names:
                            if alias.name == "logging":
                                offenders.append(f"{sub.name}:{getattr(stmt, 'lineno', '?')}")
                    if isinstance(stmt, ast.ImportFrom) and stmt.module == "logging":
                        offenders.append(f"{sub.name}:{getattr(stmt, 'lineno', '?')}")

    assert not offenders, (
        "materials_chat has local `import logging` which causes UnboundLocalError "
        f"when that branch is skipped: {offenders}"
    )
