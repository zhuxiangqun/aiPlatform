"""F2 — live ontology YAML writes only inside apply/rollback."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from core.harness.knowledge.ontology_loader import save_domain_yaml
from core.harness.knowledge.ontology_yaml_gate import (
    LiveYamlDirectWriteDenied,
    allow_live_yaml_write,
)


def test_save_domain_yaml_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    with pytest.raises(LiveYamlDirectWriteDenied):
        save_domain_yaml("it-ops", "name: it-ops\nclasses: {}\n")
    assert not (tmp_path / "ontologies" / "it-ops.yaml").exists()


def test_save_domain_yaml_allowed_inside_apply_token(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    with allow_live_yaml_write():
        path = save_domain_yaml("it-ops", "name: it-ops\nclasses: {}\n")
    assert path.endswith("it-ops.yaml")
    assert (tmp_path / "ontologies" / "it-ops.yaml").is_file()


def test_import_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_ONTOLOGY_DIR", str(tmp_path / "ont"))
    src = tmp_path / "src.json"
    src.write_text("{}")
    from core.harness.knowledge import ontology_importer as oi

    monkeypatch.setattr(oi, "_parse_external", lambda *a, **k: {"name": "it-ops", "classes": {}})
    with pytest.raises(LiveYamlDirectWriteDenied):
        oi.import_ontology(str(src), target_domain="it-ops", format="jsonld")
    assert not (tmp_path / "ont" / "it-ops.yaml").exists()


def test_deploy_rule_denied(tmp_path, monkeypatch):
    home = tmp_path / "home"
    onto = home / ".aiplat" / "ontologies"
    onto.mkdir(parents=True)
    target = onto / "it-ops.yaml"
    target.write_text("name: it-ops\ninference_rules: []\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    from core.harness.ontology_engine.rule_designer import deploy_rule

    with pytest.raises(LiveYamlDirectWriteDenied):
        deploy_rule("it-ops", {"name": "r1", "premises": [{}, {}], "conclusion": {}})
    assert "inference_rules: []" in target.read_text(encoding="utf-8")


def test_wiki_dump_returns_409(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    from core.api.routers.wiki_ontology_engine import _write_domain_yaml

    with pytest.raises(HTTPException) as ei:
        _write_domain_yaml("it-ops", {"name": "it-ops", "classes": {}})
    assert ei.value.status_code == 409
    assert not (tmp_path / "ontologies" / "it-ops.yaml").exists()
