"""N09 K17 — diagnostics drift endpoints bind tenant via actor_from_http."""
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


def _drift_block() -> str:
    text = (_repo_root() / "aiPlat-core/core/api/routers/diagnostics.py").read_text(encoding="utf-8")
    start = text.find("def get_drift_status")
    end = text.find("_drift_cache:", start)
    return text[start:end]


def test_drift_endpoints_source_use_actor_from_http():
    block = _drift_block()
    assert "actor_from_http(request, None)" in block
    assert block.count("actor_from_http(request, None)") >= 2
    # no spoofable query/body tenant_id param on signatures
    assert "tenant_id: str = \"default\"" not in block
    assert "tenant_id: str = \"default\"," not in block
    assert "StalenessMonitor(tenant_id=tid)" in block


def test_get_drift_status_uses_identity_tenant(monkeypatch):
    from core.api.routers import diagnostics as diag

    captured = {}

    class _Mon:
        def __init__(self, *, tenant_id="default"):
            captured["tenant_id"] = tenant_id

        def scan_all_collections(self):
            return []

        def scan_collection(self, _cid):
            return SimpleNamespace(
                stale_count=0,
                scanned_pages=0,
                collection_id="c",
                affected_pages=[],
            )

    monkeypatch.setattr(diag, "actor_from_http", lambda _req, _p: {"tenant_id": "n09-t17"})
    monkeypatch.setattr(
        "core.harness.knowledge.staleness_monitor.StalenessMonitor", _Mon
    )
    # clear cache
    diag._drift_cache["by_tenant"] = {}

    out = diag.get_drift_status(SimpleNamespace(), refresh=True)
    assert captured.get("tenant_id") == "n09-t17"
    assert out.get("tenant_id") == "n09-t17"


@pytest.mark.asyncio
async def test_drift_rebuild_uses_identity_tenant(monkeypatch):
    from core.api.routers import diagnostics as diag

    captured = {}

    class _Mon:
        def __init__(self, *, tenant_id="default"):
            captured["tenant_id"] = tenant_id

        def scan_all_collections(self):
            return []

    monkeypatch.setattr(diag, "actor_from_http", lambda _req, _p: {"tenant_id": "n09-t17b"})
    monkeypatch.setattr(
        "core.harness.knowledge.staleness_monitor.StalenessMonitor", _Mon
    )

    out = await diag.trigger_drift_rebuild(SimpleNamespace(), max_pages=1)
    assert captured.get("tenant_id") == "n09-t17b"
    assert out.get("tenant_id") == "n09-t17b"
