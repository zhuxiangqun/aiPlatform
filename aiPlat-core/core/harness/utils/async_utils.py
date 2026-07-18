"""Async utility functions relocated from wiki_engine.py.

This module exists to resolve backward-compatible imports from code that
was migrated during the CoreFacade boundary refactoring (commit 6d45d64).
The canonical definition of _run_coro_blocking lives in wiki_engine.py.
"""

from core.harness.knowledge.wiki_engine import _run_coro_blocking  # noqa: F401

__all__ = ["_run_coro_blocking"]
