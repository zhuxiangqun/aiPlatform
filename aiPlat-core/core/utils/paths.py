"""
Centralized AIPLAT_HOME path resolution.

Single source of truth for all filesystem paths under the aiPlat runtime directory.
All code MUST use these functions instead of:
  - os.getenv("AIPLAT_HOME", "~/.aiplat")          # ❌ scattered, inconsistent
  - os.path.expanduser("~/.aiplat/xxx")              # ❌ ignores AIPLAT_HOME env
  - direct string concatenation of subdir paths       # ❌ typo-prone

Usage:
  from core.utils.paths import get_aiplat_home, get_aiplat_data_dir

  home = get_aiplat_home()                           # ~/.aiplat or $AIPLAT_HOME
  agents_dir = get_aiplat_data_dir("agents")         # ~/.aiplat/agents/
  kb_dir = get_aiplat_data_dir("kb")                 # ~/.aiplat/kb/
"""

from __future__ import annotations

import os
from typing import Optional


def get_aiplat_home() -> str:
    """Return the aiPlat runtime home directory.
    
    Resolution order:
      1. $AIPLAT_HOME (if set and non-empty)
      2. ~/.aiplat (default)
    
    Always returns an expanded absolute path.
    """
    home = os.getenv("AIPLAT_HOME", "").strip()
    if not home:
        home = os.path.expanduser("~/.aiplat")
    return os.path.expanduser(home)


def get_aiplat_data_dir(subdir: Optional[str] = None) -> str:
    """Return an absolute path under the aiPlat runtime directory.
    
    Args:
        subdir: Optional subdirectory name (e.g., "agents", "kb", "skills").
               Multiple levels via "/" (e.g., "kb/collections/default").
    
    Returns:
        Absolute path. Does NOT create the directory.
    """
    home = get_aiplat_home()
    if subdir:
        return os.path.join(home, subdir)
    return home


# ── Common subdirectory shortcuts ──

def get_agents_dir() -> str:
    return get_aiplat_data_dir("agents")

def get_skills_dir() -> str:
    return get_aiplat_data_dir("skills")

def get_tools_dir() -> str:
    return get_aiplat_data_dir("tools")

def get_kb_dir() -> str:
    return get_aiplat_data_dir("kb")

def get_data_dir() -> str:
    return get_aiplat_data_dir("data")

def get_ontologies_dir() -> str:
    return get_aiplat_data_dir("ontologies")

def get_hooks_dir() -> str:
    return get_aiplat_data_dir("hooks")

def get_mcps_dir() -> str:
    return get_aiplat_data_dir("mcps")

def get_workspace_seeds_dir() -> str:
    """Return the workspace seeds directory.
    
    Falls back to the workspace_seeds/ directory alongside the core codebase
    if AIPLAT_WORKSPACE_SEEDS is not set.
    """
    ws_seeds = os.getenv("AIPLAT_WORKSPACE_SEEDS", "").strip()
    if ws_seeds:
        return os.path.expanduser(ws_seeds)
    # Default: workspace_seeds/ in the repo root (alongside core/)
    import inspect
    core_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))))))
    return os.path.join(core_dir, "workspace_seeds")


__all__ = [
    "get_aiplat_home",
    "get_aiplat_data_dir",
    "get_agents_dir",
    "get_skills_dir",
    "get_tools_dir",
    "get_kb_dir",
    "get_data_dir",
    "get_ontologies_dir",
    "get_hooks_dir",
    "get_mcps_dir",
    "get_workspace_seeds_dir",
]
