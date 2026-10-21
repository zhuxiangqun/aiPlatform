"""Core actor_from_http must not trust spoofable role/id headers without a gate."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_ACTOR_PATH = Path(__file__).resolve().parents[3] / "api" / "deps" / "actor.py"


def _load_actor():
    """Load actor.py without importing core.api.deps (pulls CoreFacade)."""
    spec = importlib.util.spec_from_file_location("aiplat_test_actor_deps", _ACTOR_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_actor = _load_actor()
actor_from_http = _actor.actor_from_http
header_identity_allowed = _actor.header_identity_allowed


def _req(headers: dict):
    return SimpleNamespace(headers=headers)


def test_headers_alone_do_not_grant_actor(monkeypatch):
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    monkeypatch.delenv("AIPLAT_PLATFORM_IDENTITY_SECRET", raising=False)
    assert header_identity_allowed(None) is False
    out = actor_from_http(
        _req(
            {
                "X-AIPLAT-ACTOR-ID": "admin",
                "X-AIPLAT-ACTOR-ROLE": "admin",
                "X-AIPLAT-TENANT-ID": "victim",
            }
        ),
        {"context": {"actor_role": "admin", "actor_id": "admin"}},
    )
    assert out == {"actor_id": None, "actor_role": None, "tenant_id": None}


def test_dev_mode_trusts_headers(monkeypatch):
    monkeypatch.setenv("AIPLAT_PLATFORM_DEV_MODE", "1")
    out = actor_from_http(
        _req({"X-AIPLAT-ACTOR-ROLE": "operator", "X-AIPLAT-ACTOR-ID": "u1"}),
        None,
    )
    assert out["actor_role"] == "operator"
    assert out["actor_id"] == "u1"


def test_identity_secret_trusts_headers(monkeypatch):
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    monkeypatch.setenv("AIPLAT_PLATFORM_IDENTITY_SECRET", "s3cret-value")
    assert header_identity_allowed("s3cret-value") is True
    assert header_identity_allowed("wrong-value!") is False
    out = actor_from_http(
        _req(
            {
                "X-AIPLAT-IDENTITY-SECRET": "s3cret-value",
                "X-AIPLAT-ACTOR-ROLE": "admin",
                "X-AIPLAT-TENANT-ID": "t1",
            }
        ),
        None,
    )
    assert out["actor_role"] == "admin"
    assert out["tenant_id"] == "t1"


def test_context_role_also_gated(monkeypatch):
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    monkeypatch.delenv("AIPLAT_PLATFORM_IDENTITY_SECRET", raising=False)
    out = actor_from_http(_req({}), {"context": {"actor_role": "admin"}})
    assert out["actor_role"] is None
