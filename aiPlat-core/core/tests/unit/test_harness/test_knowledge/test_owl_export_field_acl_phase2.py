"""N07/N22 deepen：OWL/RDF 导出 A-Box 字段 ACL；非 certified / 非 UI。"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

from core.harness.knowledge.knowledge_ontology import (
    OntologyTriple,
    _redact_owl_abox_triples,
    export_to_owl_rdf,
)
from core.policy.field_level_security import (
    FieldLevelPermission,
    _save_field_permissions,
)


def _seed_perm(tmp_home: Path, collection_id: str, entity_uri: str, field: str) -> None:
    os.environ["AIPLAT_HOME"] = str(tmp_home)
    coll = tmp_home / "wiki" / "collections" / collection_id
    coll.mkdir(parents=True, exist_ok=True)
    _save_field_permissions(
        [
            FieldLevelPermission(
                entity_uri=entity_uri,
                field_name=field,
                visibility="role:admin",
                redaction_strategy="replace",
                replace_with="[REDACTED]",
            )
        ],
        collection_id=collection_id,
    )


def test_export_to_owl_rdf_signature_has_actor():
    sig = inspect.signature(export_to_owl_rdf)
    assert "actor_role" in sig.parameters
    assert "actor_scopes" in sig.parameters
    assert "collection_id" in sig.parameters


def test_redact_owl_abox_literal(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "lock-service-owl-acl"
    uri = "http://aiplat.local/knowledge#InstallOrder"
    _seed_perm(tmp_path, cid, uri, "secret_note")
    triples = [
        OntologyTriple(uri, "http://aiplat.local/knowledge#secret_note", '"TOP-SECRET"'),
        OntologyTriple(uri, "http://aiplat.local/knowledge#status", '"open"'),
    ]
    out = _redact_owl_abox_triples(
        triples, actor_role="viewer", actor_scopes=["kb:read"], collection_id=cid
    )
    by_pred = {t.predicate.rsplit("#", 1)[-1]: t.object for t in out}
    assert by_pred["secret_note"] == '"[REDACTED]"'
    assert by_pred["status"] == '"open"'


def test_redact_owl_abox_admin_bypass(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "lock-service-owl-acl"
    uri = "http://aiplat.local/knowledge#InstallOrder"
    _seed_perm(tmp_path, cid, uri, "secret_note")
    triples = [
        OntologyTriple(uri, "http://aiplat.local/knowledge#secret_note", '"TOP-SECRET"'),
    ]
    out = _redact_owl_abox_triples(
        triples, actor_role="admin", actor_scopes=["kb:read"], collection_id=cid
    )
    assert out[0].object == '"TOP-SECRET"'


def test_redact_owl_abox_no_identity_passthrough(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "lock-service-owl-acl"
    uri = "http://aiplat.local/knowledge#InstallOrder"
    _seed_perm(tmp_path, cid, uri, "secret_note")
    triples = [
        OntologyTriple(uri, "http://aiplat.local/knowledge#secret_note", '"TOP-SECRET"'),
    ]
    out = _redact_owl_abox_triples(triples, actor_role="", actor_scopes=None, collection_id=cid)
    assert out[0].object == '"TOP-SECRET"'


def test_router_export_wires_actor():
    from core.api.routers import wiki_ontology_export as mod

    src = inspect.getsource(mod.export_ontology_rdf)
    assert "actor_role" in src
    assert "export_to_owl_rdf" in src
    assert "collection_id=collection" in src
