"""EVAL_V1 E1 — core /kb-eval legacy shim returns deprecation headers."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api.routers.kb_eval import router as kb_eval_router


def test_core_kb_eval_shim_deprecation():
    app = FastAPI()
    app.include_router(kb_eval_router, prefix="/api/core")
    client = TestClient(app)
    r = client.get("/api/core/kb-eval/samples")
    assert r.status_code == 200
    assert r.headers.get("Deprecation") == "true"
    body = r.json()
    assert body.get("deprecated") is True
    assert body.get("successor_prefix") == "/api/platform/apps/eval/kb-eval"
