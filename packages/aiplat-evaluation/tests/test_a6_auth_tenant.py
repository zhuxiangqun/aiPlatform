"""A6 — standalone Bearer JWT 401 + cross-tenant 404."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.auth import mint_local_token
from app.config import EvalServiceConfig
from app.main import create_app


def _cfg(tmp_path: Path) -> EvalServiceConfig:
    return EvalServiceConfig(
        mode="standalone",
        host="127.0.0.1",
        port=8010,
        db_url=f"sqlite:///{tmp_path / 'a6.sqlite3'}",
        version="0.1.0",
        protocol="eval.protocol.v0",
        require_auth=True,
    )


def _headers(tenant: str) -> dict:
    return {"Authorization": f"Bearer {mint_local_token(tenant_id=tenant)}"}


def test_store_requires_bearer(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    client = TestClient(create_app(_cfg(tmp_path)))
    r = client.get("/api/platform/apps/eval/store/sets")
    assert r.status_code == 401


def test_tenant_isolation_404(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    client = TestClient(create_app(_cfg(tmp_path)))

    created = client.post(
        "/api/platform/apps/eval/store/sets",
        json={"name": "t-a"},
        headers=_headers("tenant-a"),
    )
    assert created.status_code == 200
    set_id = created.json()["data"]["id"]
    assert created.json()["data"]["tenant_id"] == "tenant-a"

    ok = client.get(
        f"/api/platform/apps/eval/store/sets/{set_id}",
        headers=_headers("tenant-a"),
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["id"] == set_id

    denied = client.get(
        f"/api/platform/apps/eval/store/sets/{set_id}",
        headers=_headers("tenant-b"),
    )
    assert denied.status_code == 404

    listed_b = client.get(
        "/api/platform/apps/eval/store/sets",
        headers=_headers("tenant-b"),
    )
    assert listed_b.status_code == 200
    assert listed_b.json()["data"]["total"] == 0


def test_healthz_open_without_token(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    client = TestClient(create_app(_cfg(tmp_path)))
    hz = client.get("/healthz")
    assert hz.status_code == 200
    assert hz.json()["process_split_authorized"] is False
    assert hz.json()["require_auth"] is True
