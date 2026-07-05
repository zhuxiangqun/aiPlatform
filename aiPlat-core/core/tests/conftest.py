"""
Global test fixtures — shared data isolation and cleanup.

Auto-applied to all tests. Ensures:
  - SharedKnowledgePool cleanup between tests
  - StrategyTracker cleanup between tests
  - Test database isolation
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_shared_state():
    """Clean up global singletons between tests to prevent cross-test contamination."""
    yield
    try:
        import core.harness.memory.shared_pool as sp
        if sp._pool is not None and hasattr(sp._pool, '_db_conn') and sp._pool._db_conn:
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
