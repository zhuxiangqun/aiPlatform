"""N07/N22 deepen：suggestions OWL / offline_owl_review 身份透传；非 certified。"""
from __future__ import annotations

import inspect
import os
from pathlib import Path
from unittest.mock import patch

from core.harness.knowledge.knowledge_ontology import (
    _redact_suggestion_fields,
    export_suggestions_to_owl,
)
from core.policy.field_level_security import (
    FieldLevelPermission,
    _save_field_permissions,
)


def _seed_perm(tmp_home: Path, collection_id: str, title: str, field: str) -> None:
    os.environ["AIPLAT_HOME"] = str(tmp_home)
    from core.harness.knowledge.knowledge_abox_builder import _safe_uri

    uri = f"http://aiplat.local/knowledge#{_safe_uri(title)}"
    coll = tmp_home / "wiki" / "collections" / collection_id
    coll.mkdir(parents=True, exist_ok=True)
    _save_field_permissions(
        [
            FieldLevelPermission(
                entity_uri=uri,
                field_name=field,
                visibility="role:admin",
                redaction_strategy="replace",
                replace_with="[REDACTED]",
            )
        ],
        collection_id=collection_id,
    )


def test_export_suggestions_signature_has_actor():
    sig = inspect.signature(export_suggestions_to_owl)
    assert "actor_role" in sig.parameters
    assert "actor_scopes" in sig.parameters


def test_redact_suggestion_description(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "lock-service-sug-acl"
    _seed_perm(tmp_path, cid, "InstallOrder", "description")
    out = _redact_suggestion_fields(
        {"type": "new_class", "description": "TOP-SECRET", "status": "pending"},
        title="InstallOrder",
        actor_role="viewer",
        actor_scopes=["kb:read"],
        collection_id=cid,
    )
    assert out["description"] == "[REDACTED]"
    assert out["status"] == "pending"


def test_export_suggestions_redacts_description(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "lock-service-sug-acl2"
    _seed_perm(tmp_path, cid, "InstallOrder", "description")
    suggestions = [
        {
            "status": "pending",
            "type": "new_class",
            "label": "InstallOrder",
            "description": "TOP-SECRET-DESC",
        }
    ]
    with patch(
        "core.harness.knowledge.knowledge_ontology.load_pending_suggestions",
        return_value=suggestions,
    ), patch(
        "core.harness.knowledge.knowledge_ontology._parse_suggestion_label",
        return_value="InstallOrder",
    ), patch(
        "core.harness.knowledge.knowledge_ontology._infer_parent_from_label",
        return_value="aiplat:ConceptPage",
    ):
        ttl = export_suggestions_to_owl(
            collection_id=cid, actor_role="viewer", actor_scopes=["kb:read"]
        )
    assert "[REDACTED]" in ttl
    assert "TOP-SECRET-DESC" not in ttl


def test_offline_owl_review_signature_has_actor():
    from core.apps.fde.service.offline_owl_review import review_domain_owl_offline

    sig = inspect.signature(review_domain_owl_offline)
    assert "actor_role" in sig.parameters
    assert "actor_scopes" in sig.parameters


def test_offline_owl_review_passes_actor_to_export():
    from core.apps.fde.service.offline_owl_review import review_domain_owl_offline

    captured = {}

    def _fake_export(*a, **k):
        captured.update(k)
        return ""

    # 函数内 from core.api.core_facade import export_to_owl_rdf — patch 模块属性即可
    with patch("core.api.core_facade.export_to_owl_rdf", side_effect=_fake_export):
        review_domain_owl_offline(
            "lock-service",
            actor_role="viewer",
            actor_scopes=["kb:read"],
            collection_id="c1",
        )
    assert captured.get("actor_role") == "viewer"
    assert captured.get("actor_scopes") == ["kb:read"]
    assert captured.get("collection_id") == "c1"


def test_router_learned_and_owl_review_wire_actor():
    from core.api.routers import wiki_ontology_export as wiki_exp
    from apps.fde.api import action_routes as ar

    src1 = inspect.getsource(wiki_exp.export_learned_ontology)
    assert "actor_role" in src1
    assert "export_suggestions_to_owl" in src1
    src2 = inspect.getsource(ar.ontology_owl_review)
    assert "actor_role" in src2
    assert "review_domain_owl_offline" in src2
