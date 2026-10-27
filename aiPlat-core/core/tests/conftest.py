"""
Global test fixtures — shared data isolation and cleanup.

Auto-applied to all tests. Ensures:
  - Session-scoped AIPLAT_HOME under tmp (hermetic; no ~/.aiplat side effects)
  - SharedKnowledgePool cleanup between tests
  - StrategyTracker cleanup between tests
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]  # aiPlat-core/
_SEED_PROFILES = _REPO / "workspace_seeds" / "profiles" / "control_presets.yaml"
_SEED_ONTO = _REPO / "workspace_seeds" / "ontologies" / "ai-knowledge.yaml"


@pytest.fixture(scope="session", autouse=True)
def _hermetic_aiplat_home(tmp_path_factory):
    """Point AIPLAT_HOME at a writable temp tree for the whole test session."""
    home = tmp_path_factory.mktemp("aiplat-home")
    profiles = home / "profiles"
    ontologies = home / "ontologies"
    profiles.mkdir(parents=True, exist_ok=True)
    ontologies.mkdir(parents=True, exist_ok=True)
    if _SEED_PROFILES.is_file():
        shutil.copy2(_SEED_PROFILES, profiles / "control_presets.yaml")
    if _SEED_ONTO.is_file():
        shutil.copy2(_SEED_ONTO, ontologies / "ai-knowledge.yaml")

    prev = os.environ.get("AIPLAT_HOME")
    os.environ["AIPLAT_HOME"] = str(home)
    # Prefer seed profiles dir for control presets consumers
    prev_prof = os.environ.get("AIPLAT_PROFILE_DIR")
    os.environ["AIPLAT_PROFILE_DIR"] = str(profiles)
    yield home
    if prev is None:
        os.environ.pop("AIPLAT_HOME", None)
    else:
        os.environ["AIPLAT_HOME"] = prev
    if prev_prof is None:
        os.environ.pop("AIPLAT_PROFILE_DIR", None)
    else:
        os.environ["AIPLAT_PROFILE_DIR"] = prev_prof
    try:
        from core.harness.ontology_engine import state_history as sh

        sh.close_connection()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _isolate_shared_state():
    """Clean up global singletons between tests to prevent cross-test contamination."""
    yield
    try:
        import core.harness.memory.shared_pool as sp

        if sp._pool is not None and hasattr(sp._pool, "_db_conn") and sp._pool._db_conn:
            try:
                sp._pool._db_conn.close()
            except Exception:
                pass
        sp._pool = None
    except Exception:
        pass
    try:
        import core.harness.optimization.strategy_tracker as st

        st._tracker = None
    except Exception:
        pass
    try:
        import core.harness.optimization.search_engine as se

        se._engine = None
    except Exception:
        pass
