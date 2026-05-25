"""
Background Skill Review — delegates to harness-level implementation.

Design principle (CLAUDE.md §11):
  This module (apps layer) imports from harness layer (profile_builder),
  which is the correct dependency direction. Shared review logic lives in
  core/harness/memory/profile_builder.py.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

_log = logging.getLogger("pipeline_engine.skill_review")

# Re-export from harness (apps→harness is the correct direction)
from core.harness.memory.profile_builder import build_stage_summary, run_skill_review

__all__ = ["build_stage_summary", "run_skill_review"]
