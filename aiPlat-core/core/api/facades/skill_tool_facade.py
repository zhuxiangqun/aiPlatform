"""Skill/Tool facade — registry access (no core_facade dependency)."""
from __future__ import annotations
from typing import Any
import logging


def get_skill_registry() -> Any:
    from core.apps.skills import get_skill_registry as _get
    return _get()


def get_tool_registry() -> Any:
    from core.apps.tools.base import get_tool_registry as _get
    return _get()


def get_model_registry() -> Any:
    from infra.management.model.manager import ModelManager
    return ModelManager()


def seed_all_registries() -> None:
    """Seed SkillRegistry, ToolRegistry, and ModelRegistry with built-in defaults."""
    try:
        get_skill_registry().seed_for_platform()
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    try:
        from core.apps.tools import skill_tools, webfetch, http, repo
        reg = get_tool_registry()
        for mod, cls_name, kwargs in [
            (skill_tools, "SkillFindTool", {}),
            (skill_tools, "SkillLoadTool", {}),
            (webfetch, "WebFetchTool", {}),
            (http, "HTTPClientTool", {}),
            (repo, "RepoTool", {}),
        ]:
            try:
                reg.register(getattr(mod, cls_name)(**kwargs))
            except Exception as e:
                logging.debug(str(e), exc_info=True)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
