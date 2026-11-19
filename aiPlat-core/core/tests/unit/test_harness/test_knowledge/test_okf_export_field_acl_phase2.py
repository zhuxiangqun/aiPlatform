"""N07/N22 deepen：OKF 导出写盘路径字段 ACL；非 certified / 非 UI。"""
from __future__ import annotations

import inspect
import os
from pathlib import Path
from types import SimpleNamespace

from core.harness.knowledge.okf_exporter import OKFExporter
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


def test_export_signature_has_actor_role():
    sig = inspect.signature(OKFExporter.export)
    assert "actor_role" in sig.parameters
    assert "actor_scopes" in sig.parameters
    assert "collection_id" in sig.parameters


def test_redact_entity_fields_viewer(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "lock-service-okf-acl"
    _seed_perm(tmp_path, cid, "InstallOrder", "secret_note")
    out = OKFExporter._redact_entity_fields(
        {"title": "InstallOrder", "secret_note": "TOP-SECRET", "public": "ok"},
        actor_role="viewer",
        actor_scopes=["kb:read"],
        collection_id=cid,
    )
    assert out["secret_note"] == "[REDACTED]"
    assert out["public"] == "ok"


def test_redact_entity_fields_admin_bypass(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "lock-service-okf-acl"
    _seed_perm(tmp_path, cid, "InstallOrder", "secret_note")
    out = OKFExporter._redact_entity_fields(
        {"title": "InstallOrder", "secret_note": "TOP-SECRET"},
        actor_role="admin",
        actor_scopes=["kb:read"],
        collection_id=cid,
    )
    assert out["secret_note"] == "TOP-SECRET"


def test_build_body_redacts_metadata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "lock-service-okf-body"
    _seed_perm(tmp_path, cid, "InstallOrder", "secret_note")
    node = SimpleNamespace(
        entity_name="InstallOrder",
        entity_id="InstallOrder",
        class_name="Order",
        metadata={"secret_note": "TOP-SECRET", "status": "open"},
        out_edges=[],
    )
    gi = SimpleNamespace(_nodes={})
    body = OKFExporter()._build_body(
        node,
        gi,
        actor_role="viewer",
        actor_scopes=["kb:read"],
        collection_id=cid,
    )
    assert "[REDACTED]" in body
    assert "TOP-SECRET" not in body
    assert "status" in body


def test_fde_export_okf_wires_actor():
    import apps.fde.api.fde as fde

    src = inspect.getsource(fde.export_okf)
    assert "actor_role" in src
    assert "actor_scopes" in src
