"""EVAL_V1 — canonical /api/platform/apps/eval + 308 legacy redirect (ARCH v1.2)."""
from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.eval.api.legacy_shim import (
    CANONICAL_PREFIX,
    canonical_successor,
    is_legacy_eval_path,
)


def test_legacy_path_detection():
    assert is_legacy_eval_path("/api/platform/apps/kb-eval/samples")
    assert is_legacy_eval_path("/api/platform/apps/code-review-gold/profiles")
    assert is_legacy_eval_path("/api/platform/apps/runs/r1/evaluate")
    assert not is_legacy_eval_path("/api/platform/apps/eval/kb-eval/samples")
    assert not is_legacy_eval_path("/api/platform/apps/learning/artifacts")


def test_canonical_successor():
    assert (
        canonical_successor("/api/platform/apps/kb-eval/samples")
        == "/api/platform/apps/eval/kb-eval/samples"
    )
    assert (
        canonical_successor("/api/core/kb-eval/samples")
        == "/api/platform/apps/eval/kb-eval/samples"
    )


def _canonical_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("AIPLAT_API_KEY", "eval-e1-key")
    monkeypatch.delenv("AIPLAT_ADMIN_KEY", raising=False)
    tenants = tmp_path / "kb" / "tenants"
    (tenants / "default").mkdir(parents=True)
    monkeypatch.setenv("AIPLAT_KB_TENANTS_DIR", str(tenants))
    from apps.eval.api.legacy_shim import EvalLegacyDeprecationMiddleware

    mod = importlib.import_module("apps.eval.api.router")
    app = FastAPI()
    app.include_router(mod.router, prefix=CANONICAL_PREFIX)
    app.add_middleware(EvalLegacyDeprecationMiddleware)
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def client(monkeypatch, tmp_path):
    return _canonical_client(monkeypatch, tmp_path)


def test_canonical_kb_eval_reachable(client):
    r = client.get(
        f"{CANONICAL_PREFIX}/kb-eval/samples",
        headers={"X-AIPLAT-API-KEY": "eval-e1-key"},
    )
    assert r.status_code not in (401, 403, 404, 500)
    assert "Deprecation" not in r.headers


def test_legacy_kb_eval_redirects(client):
    r = client.get(
        "/api/platform/apps/kb-eval/samples",
        headers={"X-AIPLAT-API-KEY": "eval-e1-key"},
    )
    assert r.status_code == 308
    assert r.headers.get("Deprecation") == "true"
    assert r.headers.get("X-Aiplat-Eval-Canonical-Prefix") == CANONICAL_PREFIX
    loc = r.headers.get("location") or r.headers.get("Location") or ""
    assert loc == "/api/platform/apps/eval/kb-eval/samples"
    link = r.headers.get("Link", "")
    assert CANONICAL_PREFIX in link
    assert 'rel="successor-version"' in link


def test_legacy_code_review_gold_redirects(client):
    r = client.get(
        "/api/platform/apps/code-review-gold/profiles",
        headers={"X-AIPLAT-API-KEY": "eval-e1-key"},
    )
    assert r.status_code == 308
    assert r.headers.get("Deprecation") == "true"
    loc = r.headers.get("location") or r.headers.get("Location") or ""
    assert loc.startswith("/api/platform/apps/eval/code-review-gold/profiles")


def test_routes_py_single_canonical_mount():
    from pathlib import Path
    import re

    src = Path(__file__).resolve().parents[1] / "api" / "rest" / "routes.py"
    text = src.read_text(encoding="utf-8")
    mounts = len(re.findall(r"include_router\(\s*eval_platform_router", text))
    assert mounts == 1
    assert 'prefix="/api/platform/apps/eval"' in text
    assert "EvalLegacyDeprecationMiddleware" in text
