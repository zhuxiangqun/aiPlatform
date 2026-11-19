"""N07/N22 deepen：裸 sys_wiki_retrieve / GraphRAG chunks 字段 ACL；非全入口 certified。"""
from __future__ import annotations

import inspect
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.harness.syscalls.retrieval import sys_wiki_retrieve
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


def test_wiki_retrieve_signature_has_actor_role():
    sig = inspect.signature(sys_wiki_retrieve)
    assert "actor_role" in sig.parameters
    assert "actor_scopes" in sig.parameters


def test_sync_wiki_retrieve_wires_acl_gate():
    from core.harness.syscalls.retrieval import _sync_wiki_retrieve

    src = inspect.getsource(_sync_wiki_retrieve)
    assert "_apply_field_acl_to_results" in src
    assert "if actor_role or actor_scopes is not None" in src


def test_sync_wiki_retrieve_calls_field_acl(tmp_path: Path, monkeypatch):
    """mock 异步检索结果，断言带身份时调用 _apply_field_acl_to_results。"""
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "lock-service-wiki-acl"

    class _Meta:
        tags: list = []

    class _Entry:
        content = "public"
        title = "InstallOrder"
        summary = ""
        references = ""
        metadata = _Meta()

    class _Hit:
        entry = _Entry()
        score = 0.9
        highlight = ""

    from core.harness.syscalls import retrieval as ret

    called = {}

    def _spy(results, *, actor_role="", actor_scopes=None, collection_id=""):
        called["actor_role"] = actor_role
        called["collection_id"] = collection_id
        return results

    with patch("core.harness.knowledge.wiki_retriever.WikiPageRetriever"), patch.object(
        ret, "_run_async_in_sync", return_value=[_Hit()]
    ), patch.object(ret, "_apply_field_acl_to_results", side_effect=_spy):
        out = ret._sync_wiki_retrieve(
            "q",
            collection_ids=[cid],
            actor_role="viewer",
            actor_scopes=["kb:read"],
        )
    assert out[0]["title"] == "InstallOrder"
    assert called.get("actor_role") == "viewer"
    assert called.get("collection_id") == cid


def test_graphrag_chunk_acl_redacts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "lock-service-gr-acl"
    _seed_perm(tmp_path, cid, "InstallOrder", "content")
    from core.harness.knowledge_pipeline.retriever import GraphRAGRetriever

    chunks = [{"title": "InstallOrder", "content": "TOP-SECRET-BODY", "source": "vector:t"}]
    out = GraphRAGRetriever._apply_chunk_field_acl(
        chunks, actor_role="viewer", actor_scopes=["kb:read"], collection_id=cid
    )
    assert out[0]["content"] == "[REDACTED]"


def test_graphrag_retrieve_signature_has_actor_role():
    from core.harness.knowledge_pipeline.retriever import GraphRAGRetriever

    sig = inspect.signature(GraphRAGRetriever.retrieve)
    assert "actor_role" in sig.parameters
    assert "actor_scopes" in sig.parameters


@pytest.mark.asyncio
async def test_graphrag_retrieve_applies_acl_on_chunks(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cid = "lock-service-gr-acl2"
    _seed_perm(tmp_path, cid, "InstallOrder", "content")
    from core.harness.knowledge_pipeline.retriever import GraphRAGRetriever

    gr = GraphRAGRetriever()
    with patch.object(
        gr,
        "_extract_query_entities",
        new=AsyncMock(return_value=[{"name": "InstallOrder", "class_type": "概念"}]),
    ), patch.object(
        gr, "_find_node", return_value={"id": "n1", "name": "InstallOrder", "class": "概念"}
    ), patch.object(
        gr, "_extract_subgraph", return_value={"nodes": [{"id": "n1"}], "edges": []}
    ), patch.object(
        gr, "_get_doc_ids_from_subgraph", return_value=["InstallOrder"]
    ), patch.object(
        gr,
        "_vector_search",
        new=AsyncMock(
            return_value=[{"title": "InstallOrder", "content": "TOP-SECRET-BODY", "source": "v"}]
        ),
    ), patch.object(gr, "_extract_reasoning_paths", return_value=[]):
        result = await gr.retrieve(
            "q",
            domain_id=cid,
            actor_role="viewer",
            actor_scopes=["kb:read"],
            collection_id=cid,
        )
    assert result["chunks"][0]["content"] == "[REDACTED]"


def test_crag_l0_wires_chunk_acl():
    from core.harness.syscalls import retrieval_crag as crag

    src = inspect.getsource(crag.sys_crag_retrieve)
    assert "_apply_field_acl_to_results" in src
    assert "actor_role=actor_role" in src
