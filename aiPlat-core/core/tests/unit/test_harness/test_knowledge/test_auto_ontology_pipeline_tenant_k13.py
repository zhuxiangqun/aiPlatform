"""N09 K13 — auto_ontology_pipeline_for_doc threads tenant into engine."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_auto_ontology_pipeline_passes_tenant(monkeypatch, tmp_path):
    from core.api import core_facade as facade

    monkeypatch.setenv("AIPLAT_AUTO_ONTOLOGY_PIPELINE", "true")

    f = tmp_path / "doc.txt"
    f.write_text("x" * 80, encoding="utf-8")

    class _Router:
        def resolve(self, _cid):
            return "dom-k13"

    monkeypatch.setattr(
        "core.harness.knowledge.domain_router.DomainRouter", lambda: _Router()
    )

    captured = {}

    class _Engine:
        async def process_chunks(self, batch, *, doc_id="", tenant_id="", **kwargs):
            captured["tenant_id"] = tenant_id
            captured["doc_id"] = doc_id
            return SimpleNamespace(instances=[1, 2], relations=[])

    def _load_engine(domain_id, *, tenant_id="default"):
        captured["load_tenant"] = tenant_id
        captured["domain_id"] = domain_id
        return _Engine()

    monkeypatch.setattr(facade, "kb_parse_document", lambda *_a, **_k: [{"text": "x" * 80}])
    monkeypatch.setattr(
        facade,
        "kb_chunk_elements",
        lambda *_a, **_k: [{"text": "y" * 80}],
    )

    import core.harness.ontology_engine.engine as eng

    monkeypatch.setattr(eng, "load_engine", _load_engine)

    r = await facade.auto_ontology_pipeline_for_doc(
        "doc-1", str(f), "col-1", tenant_id="n09-tenant-k13"
    )
    assert r["status"] == "completed"
    assert r["tenant_id"] == "n09-tenant-k13"
    assert captured["load_tenant"] == "n09-tenant-k13"
    assert captured["tenant_id"] == "n09-tenant-k13"


def test_routes_and_watch_source_wire_tenant():
    routes = (_repo_root() / "aiPlat-platform/api/rest/routes.py").read_text(encoding="utf-8")
    assert 'tenant_id=str(identity.tenant_id or "default")' in routes
    assert (
        "auto_ontology_pipeline_for_doc(doc_id, file_path, collection_id, tenant_id=tenant_id)"
        in routes
    )
    kb = (_repo_root() / "aiPlat-platform/kb/service.py").read_text(encoding="utf-8")
    assert "tenant_id=tenant_id," in kb
