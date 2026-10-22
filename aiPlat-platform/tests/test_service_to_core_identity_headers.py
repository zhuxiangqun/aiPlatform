"""Platform→core must attach server identity secret, never client secret."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CONV = (_ROOT / "api/routers/conversations.py").read_text(encoding="utf-8")
_ROUTES = (_ROOT / "api/rest/routes.py").read_text(encoding="utf-8")
_IDENT_PATH = _ROOT / "auth/request_identity.py"


def _load_identity_mod():
    spec = importlib.util.spec_from_file_location("request_identity_under_test", _IDENT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_service_to_core_headers_include_env_secret(monkeypatch):
    mod = _load_identity_mod()
    monkeypatch.setenv("AIPLAT_PLATFORM_IDENTITY_SECRET", "s3cret-value")
    h = mod.service_to_core_identity_headers(
        tenant_id="t1",
        actor_id="u1",
        request_id="r1",
        actor_role="ops",
        scopes=["kb:read"],
    )
    assert h["X-AIPLAT-TENANT-ID"] == "t1"
    assert h["X-AIPLAT-ACTOR-ID"] == "u1"
    assert h["X-AIPLAT-REQUEST-ID"] == "r1"
    assert h["X-AIPLAT-ACTOR-ROLE"] == "ops"
    assert h["X-AIPLAT-SCOPES"] == "kb:read"
    assert h["X-AIPLAT-IDENTITY-SECRET"] == "s3cret-value"


def test_service_to_core_headers_omit_secret_when_unset(monkeypatch):
    mod = _load_identity_mod()
    monkeypatch.delenv("AIPLAT_PLATFORM_IDENTITY_SECRET", raising=False)
    # Ensure reload sees unset env (module reads env at call time).
    assert not os.getenv("AIPLAT_PLATFORM_IDENTITY_SECRET")
    h = mod.service_to_core_identity_headers(tenant_id="t1", actor_id="u1")
    assert "X-AIPLAT-IDENTITY-SECRET" not in h


def test_conversations_and_core_request_use_helper():
    assert "service_to_core_identity_headers" in _CONV
    assert "service_to_core_identity_headers" in _ROUTES
    # No raw ungated header dict for core gateway execute in conversations.
    assert '"X-AIPLAT-TENANT-ID": str(tenant_id)' not in _CONV
    assert '"X-AIPLAT-ACTOR-ID": str(user_id)' not in _CONV
