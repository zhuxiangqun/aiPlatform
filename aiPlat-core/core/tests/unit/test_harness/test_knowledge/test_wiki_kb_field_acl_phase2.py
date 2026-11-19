"""N07/N22 deepen：sys_knowledge_retrieve / KB 召回字段 ACL；非全入口 certified。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from core.harness.syscalls.retrieval import _apply_field_acl_to_results
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


def test_field_acl_redacts_for_viewer(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "lock-service-acl"
    _seed_perm(tmp_path, cid, "InstallOrder", "secret_note")
    items = [
        {
            "title": "InstallOrder",
            "text": "public body",
            "secret_note": "TOP-SECRET",
        }
    ]
    out = _apply_field_acl_to_results(
        items, actor_role="viewer", actor_scopes=["kb:read"], collection_id=cid
    )
    assert out[0]["secret_note"] == "[REDACTED]"
    assert out[0]["text"] == "public body"


def test_field_acl_admin_bypass(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "lock-service-acl"
    _seed_perm(tmp_path, cid, "InstallOrder", "secret_note")
    items = [{"title": "InstallOrder", "secret_note": "TOP-SECRET"}]
    out = _apply_field_acl_to_results(
        items, actor_role="admin", actor_scopes=["kb:read"], collection_id=cid
    )
    assert out[0]["secret_note"] == "TOP-SECRET"


def test_field_acl_no_perm_file_passthrough(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "empty-coll"
    items = [{"title": "X", "secret_note": "keep"}]
    out = _apply_field_acl_to_results(
        items, actor_role="viewer", actor_scopes=["kb:read"], collection_id=cid
    )
    assert out[0]["secret_note"] == "keep"


def test_retrieve_gate_skips_when_no_identity():
    """生产路径：无 actor_role 且 actor_scopes is None 时不调用字段 ACL。"""
    import inspect
    from core.harness.syscalls import retrieval as ret

    src = inspect.getsource(ret.sys_knowledge_retrieve)
    assert "actor_role" in src
    assert "_apply_field_acl_to_results" in src
    assert "if actor_role or actor_scopes is not None" in src


def test_kb_retrieve_signature_has_actor_role():
    import inspect
    from core.harness.syscalls.retrieval import sys_kb_retrieve

    sig = inspect.signature(sys_kb_retrieve)
    assert "actor_role" in sig.parameters
    assert "actor_scopes" in sig.parameters
