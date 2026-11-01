"""EVAL_V1 E1 — canonical /api/platform/apps/eval + legacy deprecation shim."""
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


def _dual_mount_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("AIPLAT_API_KEY", "eval-e1-key")
    monkeypatch.delenv("AIPLAT_ADMIN_KEY", raising=False)
    tenants = tmp_path / "kb" / "tenants"
    (tenants / "default").mkdir(parents=True)
    monkeypatch.setenv("AIPLAT_KB_TENANTS_DIR", str(tenants))
    from apps.eval.api.legacy_shim import EvalLegacyDeprecationMiddleware

    mod = importlib.import_module("apps.eval.api.router")
    app = FastAPI()
    app.include_router(mod.router, prefix=CANONICAL_PREFIX)
    app.include_router(mod.router, prefix="/api/platform/apps")
    app.add_middleware(EvalLegacyDeprecationMiddleware)
    return TestClient(app)


@pytest.fixture
def client(monkeypatch, tmp_path):
    return _dual_mount_client(monkeypatch, tmp_path)


def test_canonical_kb_eval_reachable(client):
    r = client.get(
        f"{CANONICAL_PREFIX}/kb-eval/samples",
        headers={"X-AIPLAT-API-KEY": "eval-e1-key"},
    )
    assert r.status_code not in (401, 403, 404, 500)
    assert "Deprecation" not in r.headers


def test_legacy_kb_eval_has_deprecation(client):
    r = client.get(
        "/api/platform/apps/kb-eval/samples",
        headers={"X-AIPLAT-API-KEY": "eval-e1-key"},
    )
    assert r.status_code not in (401, 403, 404, 500)
    assert r.headers.get("Deprecation") == "true"
    assert r.headers.get("X-Aiplat-Eval-Canonical-Prefix") == CANONICAL_PREFIX
    link = r.headers.get("Link", "")
    assert CANONICAL_PREFIX in link
    assert 'rel="successor-version"' in link


def test_legacy_code_review_gold_has_deprecation(client):
    r = client.get(
        "/api/platform/apps/code-review-gold/profiles",
        headers={"X-AIPLAT-API-KEY": "eval-e1-key"},
    )
    assert r.status_code not in (401, 403)
    assert r.headers.get("Deprecation") == "true"


def test_routes_py_dual_mount_declared():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "api" / "rest" / "routes.py"
    text = src.read_text(encoding="utf-8")
    assert 'prefix="/api/platform/apps/eval"' in text
    assert "EvalLegacyDeprecationMiddleware" in text
