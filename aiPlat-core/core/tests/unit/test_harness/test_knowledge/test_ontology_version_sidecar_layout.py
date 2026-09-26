"""Version sidecars must live under history/, never as peer domain YAML."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.harness.knowledge.ontology_loader import list_domain_files
from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_list_domain_files_skips_version_sidecars(tmp_path, monkeypatch):
    home = tmp_path / "home"
    onto = home / "ontologies"
    onto.mkdir(parents=True)
    (onto / "lock-service.yaml").write_text("name: lock\nclasses: {}\n", encoding="utf-8")
    (onto / "lock-service_v2.yaml").write_text("name: lock\nclasses: {}\n", encoding="utf-8")
    (onto / "supply-chain.yaml").write_text("name: sc\nclasses: {}\n", encoding="utf-8")
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    stems = list_domain_files()
    assert "lock-service" in stems
    assert "supply-chain" in stems
    assert "lock-service_v2" not in stems


def test_apply_writes_version_only_under_history(tmp_path, monkeypatch):
    home = tmp_path / "home"
    onto = home / "ontologies"
    onto.mkdir(parents=True)
    (onto / "demo-ops.yaml").write_text(
        "name: demo-ops\nnamespace: http://x/\nversion: 1.0.0\nclasses: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    store = VersionedOntologyStore("demo-ops")

    async def scenario():
        await store.store.initialize()
        prop = await store.create_proposal(
            {"add": {"class": {"name": "Widget", "label": "部件", "tier": "edge"}}},
            author="tester",
        )
        ok = await store.approve_proposal(prop, approver_role="analyst")
        assert ok.get("success") is True, ok
        applied = await store.apply_proposal(prop)
        assert applied.get("ok") is True, applied

        live = onto / "demo-ops.yaml"
        assert live.is_file()
        assert "Widget" in live.read_text(encoding="utf-8")

        # No version sidecar next to live pointer
        assert not (onto / "demo-ops_v1.yaml").exists()
        hist_v1 = onto / "history" / "demo-ops_v1.yaml"
        assert hist_v1.is_file()
        assert store.get_current_version() == 1
        assert "demo-ops_v1" not in list_domain_files()

    _run(scenario())


def test_migrate_legacy_live_sidecar_into_history(tmp_path, monkeypatch):
    home = tmp_path / "home"
    onto = home / "ontologies"
    onto.mkdir(parents=True)
    (onto / "lock-service.yaml").write_text("name: lock\nclasses: {}\n", encoding="utf-8")
    (onto / "lock-service_v2.yaml").write_text("name: lock\nclasses: {}\n", encoding="utf-8")
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    store = VersionedOntologyStore("lock-service")
    assert store.get_current_version() == 2
    assert not (onto / "lock-service_v2.yaml").exists()
    assert (onto / "history" / "lock-service_v2.yaml").is_file()
    assert "lock-service_v2" not in list_domain_files()
