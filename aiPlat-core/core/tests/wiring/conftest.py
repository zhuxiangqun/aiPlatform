"""
Wiring test conftest: pre-build symbol→caller_files index once per session.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CORE_ROOT = Path(__file__).resolve().parent.parent.parent  # aiPlat-core/core

# ── Build index once per session ──────────────────────────────

_index: dict = {}
_index_built = False


def _build_index():
    """Build a dict: symbol → set of full file paths that mention it."""
    global _index, _index_built
    if _index_built:
        return _index

    cache_file = os.path.join(
        os.path.dirname(__file__), ".wiring_index_cache.json"
    )

    # Rebuild every session (cheap, ~2s)
    files = []
    for root, dirs, filenames in os.walk(str(CORE_ROOT)):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "node_modules")]
        for fn in filenames:
            if fn.endswith(".py"):
                files.append(os.path.join(root, fn))

    sym_to_files = {}
    for fp in files:
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                content = f.read()
            # Extract all identifiers (crude but fast)
            import re
            tokens = set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', content))
            for t in tokens:
                if len(t) >= 4:  # skip short tokens to reduce noise
                    sym_to_files.setdefault(t, set()).add(fp)
        except Exception:
            pass

    _index = sym_to_files
    _index_built = True
    # Save cache
    try:
        with open(cache_file, "w") as f:
            json.dump({k: list(v) for k, v in sym_to_files.items()}, f)
    except Exception:
        pass
    return _index


@pytest.fixture(scope="session", autouse=True)
def _warm_index():
    _build_index()


# ── Public helper ─────────────────────────────────────────────

def has_production_caller(symbol: str, module_filename: str) -> bool:
    """Check if a symbol has at least 1 caller outside its own file and test dirs."""
    idx = _build_index()
    files = idx.get(symbol, set())
    callers = [
        f for f in files
        if module_filename not in os.path.basename(f)
        and "/tests/" not in f
        and "__pycache__" not in f
    ]
    return len(callers) > 0


def assert_wired(symbol: str, module_filename: str, phase: str, desc: str):
    """Assert that a symbol has at least 1 production caller."""
    assert has_production_caller(symbol, module_filename), (
        f"{symbol} in {module_filename} has 0 production callers.\n"
        f"  Phase: {phase}\n"
        f"  Purpose: {desc}\n"
        f"  Action: wire this module to its intended production path, "
        f"then remove @pytest.mark.xfail from this test."
    )
