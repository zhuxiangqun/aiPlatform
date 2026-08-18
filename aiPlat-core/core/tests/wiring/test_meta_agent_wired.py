"""Wiring assertion: MetaAgent / get_meta_agent must have a production caller.

evolution_engine.py's meta_analysis step calls get_meta_agent() — the wire
that previously pointed at a non-existent symbol (P0-C7 golden-sample catch).
"""

import pytest

from .conftest import assert_wired


class TestMetaAgentWired:
    def test_get_meta_agent_has_production_caller(self):
        assert_wired(
            "get_meta_agent",
            "meta_agent.py",
            phase="P0-C7",
            desc="evolution_engine meta_analysis step calls get_meta_agent().analyze(days)",
        )

    def test_meta_agent_module_exported(self):
        """meta/__init__.py must re-export get_meta_agent."""
        from core.harness.meta import get_meta_agent, MetaAgent, MetaSuggestion

        agent = get_meta_agent()
        assert isinstance(agent, MetaAgent)
        assert MetaSuggestion is not None
