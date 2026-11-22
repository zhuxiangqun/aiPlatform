"""N07/N22 deepen：EvolutionRunner suggestions OWL 落盘身份透传；非 certified / 非 UI。"""
from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

from core.harness.knowledge.evolution_runner import EvolutionRunner


def test_evolution_runner_ctor_has_actor():
    sig = inspect.signature(EvolutionRunner.__init__)
    assert "actor_role" in sig.parameters
    assert "actor_scopes" in sig.parameters


def test_evolution_runner_stores_actor(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    with patch.object(EvolutionRunner, "_load_last_generation_id", return_value=0), patch.object(
        EvolutionRunner, "auto_apply_previous_onto_mutations"
    ):
        r = EvolutionRunner(
            collection_id="lock-service-evo",
            max_mutations=1,
            actor_role="viewer",
            actor_scopes=["kb:read"],
        )
    assert r.actor_role == "viewer"
    assert r.actor_scopes == ["kb:read"]


def test_evolution_runner_write_suggestions_call_wires_actor():
    import core.harness.knowledge.evolution_runner as mod

    src = inspect.getsource(mod)
    assert "actor_role=self.actor_role" in src
    assert "actor_scopes=self.actor_scopes" in src
    assert "write_suggestions_owl_file(" in src


def test_wiki_evolve_route_wires_actor():
    from core.api.routers import wiki as wiki_mod

    src = inspect.getsource(wiki_mod.evolve_knowledge)
    assert "actor_role" in src
    assert "actor_scopes" in src
    assert "EvolutionRunner(" in src


def test_wiki_auto_update_signature_has_actor():
    from core.api import core_facade as facade

    sig = inspect.signature(facade.wiki_auto_update)
    assert "actor_role" in sig.parameters
    assert "actor_scopes" in sig.parameters
    src = inspect.getsource(facade.wiki_auto_update)
    assert "actor_role=actor_role" in src
