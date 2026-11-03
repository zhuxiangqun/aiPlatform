"""EVAL_V1 ARCH v1.2 — core /kb-eval redirects 308 to platform canonical."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api.routers.eval_legacy_shim import EvalCoreLegacyDeprecationMiddleware


def test_core_kb_eval_redirects_to_canonical():
    app = FastAPI()
    app.add_middleware(EvalCoreLegacyDeprecationMiddleware)
    client = TestClient(app, follow_redirects=False)
    r = client.get("/api/core/kb-eval/samples")
    assert r.status_code == 308
    assert r.headers.get("Deprecation") == "true"
    loc = r.headers.get("location") or r.headers.get("Location") or ""
    assert loc.startswith("/api/platform/apps/eval/kb-eval/samples")
