"""
Constitution test: Tool configuration validity.

Ensures all registered tools have non-empty descriptions and parameter schemas.
"""

import os
import sys
from pathlib import Path

_CORE_DIR = Path(__file__).resolve().parents[2] / "aiPlat-core"
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

import pytest


class TestToolConfigValidity:
    """All registered tools must have valid configs."""

    def test_tools_have_nonempty_description(self):
        """Every tool class must have a non-empty description."""
        import importlib
        import inspect

        # Tool classes to check
        tool_modules = [
            ("core.apps.tools.base", ["CalculatorTool", "SearchTool", "FileOperationsTool", "ToolSearchTool"]),
            ("core.apps.tools.webfetch", ["WebFetchTool"]),
            ("core.apps.tools.http", ["HTTPClientTool"]),
            ("core.apps.tools.code", ["CodeExecutionTool"]),
            ("core.apps.tools.database", ["DatabaseTool"]),
            ("core.apps.tools.browser", ["BrowserTool"]),
            ("core.apps.tools.repo", ["RepoTool"]),
            ("core.apps.tools.skill_tools", ["SkillFindTool", "SkillLoadTool"]),
            ("core.apps.tools.skill_script_tools", ["SkillRunScriptTool"]),
        ]

        missing = []
        for mod_path, class_names in tool_modules:
            try:
                mod = importlib.import_module(mod_path)
                for cls_name in class_names:
                    cls = getattr(mod, cls_name, None)
                    if cls is None:
                        missing.append(f"{mod_path}::{cls_name}: class not found")
                        continue
                    # Instantiate to get config
                    try:
                        import inspect
                        sig = inspect.signature(cls.__init__)
                        if len(sig.parameters) > 1:
                            # Has constructor args beyond self
                            continue
                        instance = cls()
                    except Exception:
                        missing.append(f"{mod_path}::{cls_name}: cannot instantiate")
                        continue
                    try:
                        desc = instance.get_description()
                    except Exception:
                        desc = ""
                    if not desc or not desc.strip():
                        missing.append(f"{cls_name}: description is empty")
            except ModuleNotFoundError:
                continue
            except Exception as e:
                missing.append(f"{mod_path}: {e}")

        assert not missing, (
            f"Tools with missing/empty descriptions:\n  " + "\n  ".join(missing)
        )

    def test_core_tools_have_parameters_schema(self):
        """Core tools (calculator/search/file_ops) must have parameter schemas."""
        from core.apps.tools.base import CalculatorTool, SearchTool, FileOperationsTool

        bad = []
        for cls in [CalculatorTool, SearchTool, FileOperationsTool]:
            try:
                inst = cls()
                schema = inst.get_schema()
                params = getattr(schema, 'parameters', {}) if schema else {}
                if not params or not isinstance(params, dict) or not params.get("type"):
                    bad.append(f"{cls.__name__}: missing or invalid parameters schema")
            except Exception as e:
                bad.append(f"{cls.__name__}: {e}")

        assert not bad, (
            f"Core tools with invalid parameter schemas:\n  " + "\n  ".join(bad)
        )
