"""Fault injection #1 (auth) and #4 (offline TTL / denied_ops) for five-products slice."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from core.apps.fde.service.slice_offline_policy import evaluate_slice_offline_policy

# Load auth.deps without importing auth/__init__ (pulls CoreFacade → py3.9 typing issue).
_DEPS_PATH = Path(__file__).resolve().parents[5] / "aiPlat-platform" / "auth" / "deps.py"
_spec = importlib.util.spec_from_file_location("aiplat_auth_deps_slice_fi", _DEPS_PATH)
assert _spec and _spec.loader
_deps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_deps)
require_auth = _deps.require_auth


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def test_offline_ttl_exceeded_denies():
    last = datetime.now(timezone.utc) - timedelta(hours=13)
    r = evaluate_slice_offline_policy(
        last_bundle_validated_at=_iso(last),
        has_revocation_channel=False,
        requested_ops=["read_status"],
    )
    assert r["ok"] is False
    assert r["decision"] == "deny"
    assert r["reason"] == "offline_ttl_exceeded"


def test_offline_within_ttl_allows_readonly():
    last = datetime.now(timezone.utc) - timedelta(hours=1)
    r = evaluate_slice_offline_policy(
        last_bundle_validated_at=_iso(last),
        has_revocation_channel=False,
        requested_ops=["read_status"],
    )
    assert r["ok"] is True
    assert r["decision"] == "allow"


def test_offline_denied_ops_blocks_heal():
    last = datetime.now(timezone.utc) - timedelta(minutes=5)
    r = evaluate_slice_offline_policy(
        last_bundle_validated_at=_iso(last),
        requested_ops=["heal", "read_status"],
    )
    assert r["ok"] is False
    assert r["reason"] == "denied_ops"
    assert "heal" in r.get("denied_ops_hit", [])


def test_require_auth_rejects_missing_and_invalid_key(monkeypatch):
    monkeypatch.setenv("AIPLAT_API_KEY", "slice-test-secret")
    monkeypatch.delenv("AIPLAT_ADMIN_KEY", raising=False)

    app = FastAPI()

    @app.get("/probe")
    async def probe(_auth: str = Depends(require_auth)):
        return {"auth": _auth}

    client = TestClient(app)

    missing = client.get("/probe")
    assert missing.status_code == 401

    bad = client.get("/probe", headers={"X-AIPLAT-API-KEY": "wrong"})
    assert bad.status_code == 403

    ok = client.get("/probe", headers={"X-AIPLAT-API-KEY": "slice-test-secret"})
    assert ok.status_code == 200
    assert ok.json()["auth"] == "authenticated"


def test_auth_gate_on_offline_evaluate_endpoint(monkeypatch):
    """#1: missing/invalid key rejected; valid key reaches offline evaluator (#4)."""
    monkeypatch.setenv("AIPLAT_API_KEY", "slice-test-secret")
    monkeypatch.delenv("AIPLAT_ADMIN_KEY", raising=False)

    app = FastAPI()

    @app.post("/fde/slice/offline/evaluate")
    async def offline_evaluate(body: dict, _auth: str = Depends(require_auth)):
        return evaluate_slice_offline_policy(
            last_bundle_validated_at=str(body.get("last_bundle_validated_at") or ""),
            requested_ops=list(body.get("requested_ops") or []),
            has_revocation_channel=bool(body.get("has_revocation_channel")),
        )

    client = TestClient(app)
    payload = {
        "last_bundle_validated_at": _iso(datetime.now(timezone.utc)),
        "requested_ops": ["heal"],
    }

    assert client.post("/fde/slice/offline/evaluate", json=payload).status_code == 401
    assert (
        client.post(
            "/fde/slice/offline/evaluate",
            headers={"X-AIPLAT-API-KEY": "wrong"},
            json=payload,
        ).status_code
        == 403
    )

    r2 = client.post(
        "/fde/slice/offline/evaluate",
        headers={"X-AIPLAT-API-KEY": "slice-test-secret"},
        json=payload,
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data.get("decision") == "deny"
    assert data.get("reason") == "denied_ops"
