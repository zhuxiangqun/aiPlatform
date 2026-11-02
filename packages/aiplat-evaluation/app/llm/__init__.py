"""Eval Worker LLM access (EVAL_MODEL_GATEWAY) — no Central HTTP, no core.harness."""
from __future__ import annotations

from app.llm.client import complete_text, llm_enabled, llm_mode

__all__ = ["complete_text", "llm_enabled", "llm_mode"]
