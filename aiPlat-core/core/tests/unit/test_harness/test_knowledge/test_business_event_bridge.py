"""P0-L2 business event bridge — actions → incremental GraphIndex updates.

The bridge turns the periodic ABox rebuild into event-driven upserts:
an executed business action (e.g. contract signing) immediately creates /
updates the entity in GraphIndex.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))


class TestBusinessEventBridge:
    def test_action_publishes_incremental_update(self, tmp_path, monkeypatch):
        """A completed business action upserts entity + action state in GraphIndex."""
        import core.harness.ontology_engine.graph_index as gi
        # point graph storage at tmp
        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        from core.harness.ontology_engine.business_event_bridge import publish_business_action

        asyncio.run(publish_business_action(
            action_id="sign_contract", entity_id="contract-1001",
            domain_id="default", result={"ok": True},
            status="executed", actor="sales_zhang"))

        g = gi.GraphIndex.load("default")
        node = g._nodes.get("contract-1001")
        assert node is not None, "entity must be upserted incrementally"
        assert (node.metadata or {}).get("last_action") == "sign_contract"
        assert (node.metadata or {}).get("last_status") == "executed"

    def test_bridge_never_raises(self, tmp_path, monkeypatch):
        """Bridge is best-effort: failures never block the caller."""
        from core.harness.ontology_engine import business_event_bridge as beb

        async def bad_update(data):
            raise RuntimeError("boom")

        monkeypatch.setattr(beb, "_apply_incremental_update", bad_update)
        # publish must not raise even though the update raises
        asyncio.run(beb.publish_business_action(
            action_id="a", entity_id="e", domain_id="d", status="executed"))
