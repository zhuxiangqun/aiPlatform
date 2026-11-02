"""B0 — RS256 JWKS accept + bad kid/issuer → 401. process_split stays false."""
from __future__ import annotations

import json
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from app.config import EvalServiceConfig
from app.main import create_app


def _rsa_bundle():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key()
    jwk = json.loads(RSAAlgorithm.to_jwk(pub))
    jwk["kid"] = "b0-test-key"
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    return priv, {"keys": [jwk]}


def _mint_rs256(priv, *, tenant_id: str, issuer: str, kid: str = "b0-test-key") -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": "b0-user",
            "tenant_id": tenant_id,
            "iss": issuer,
            "iat": now,
            "exp": now + 3600,
        },
        priv,
        algorithm="RS256",
        headers={"kid": kid},
    )


def _cfg(tmp_path: Path) -> EvalServiceConfig:
    return EvalServiceConfig(
        mode="standalone",
        host="127.0.0.1",
        port=8010,
        db_url=f"sqlite:///{tmp_path / 'b0.sqlite3'}",
        version="0.1.0",
        protocol="eval.protocol.v0",
        require_auth=True,
    )


def test_jwks_rs256_accepted(tmp_path: Path, monkeypatch):
    priv, doc = _rsa_bundle()
    issuer = "aiplat-eval-b0"
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    monkeypatch.setenv("AIPLAT_EVAL_JWT_ISSUER", issuer)
    monkeypatch.setenv("AIPLAT_EVAL_JWKS_JSON", json.dumps(doc))
    client = TestClient(create_app(_cfg(tmp_path)))
    tok = _mint_rs256(priv, tenant_id="tenant-jwks", issuer=issuer)
    created = client.post(
        "/api/platform/apps/eval/store/sets",
        json={"name": "b0"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert created.status_code == 200
    assert created.json()["data"]["tenant_id"] == "tenant-jwks"
    hz = client.get("/healthz")
    assert hz.json()["process_split_authorized"] is False
    assert hz.json()["jwks_enabled"] is True


def test_jwks_bad_kid_401(tmp_path: Path, monkeypatch):
    priv, doc = _rsa_bundle()
    issuer = "aiplat-eval-b0"
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    monkeypatch.setenv("AIPLAT_EVAL_JWT_ISSUER", issuer)
    monkeypatch.setenv("AIPLAT_EVAL_JWKS_JSON", json.dumps(doc))
    client = TestClient(create_app(_cfg(tmp_path)))
    tok = _mint_rs256(priv, tenant_id="t", issuer=issuer, kid="unknown-kid")
    r = client.get(
        "/api/platform/apps/eval/store/sets",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 401


def test_jwks_wrong_issuer_401(tmp_path: Path, monkeypatch):
    priv, doc = _rsa_bundle()
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    monkeypatch.setenv("AIPLAT_EVAL_JWT_ISSUER", "expected-issuer")
    monkeypatch.setenv("AIPLAT_EVAL_JWKS_JSON", json.dumps(doc))
    client = TestClient(create_app(_cfg(tmp_path)))
    tok = _mint_rs256(priv, tenant_id="t", issuer="other-issuer")
    r = client.get(
        "/api/platform/apps/eval/store/sets",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 401
