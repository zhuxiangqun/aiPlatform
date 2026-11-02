"""EVAL A3-local A1/A2 — standalone FastAPI entrypoint (:8010).

Honesty:
- Proves independent process + healthz/readyz + local SQLite store.
- Does NOT set process_split_authorized=true.
- No imports from core.harness / Central private modules.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request

from app.config import EvalServiceConfig, load_config
from app.store import open_store, store_health
from app.store.store import local_roundtrip

SCHEMA_HEALTHZ = "evaluation.healthz.v0"
SCHEMA_READYZ = "evaluation.readyz.v0"


def healthz_payload(cfg: EvalServiceConfig) -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": cfg.version,
        "product_id": "evaluation",
        "capability_id": "evaluation",
        "deploy_unit": cfg.deploy_unit,
        "protocol": cfg.protocol,
        "mode": cfg.mode,
        "schema_version": SCHEMA_HEALTHZ,
        "process_split_authorized": False,
        "note": (
            "A2 local standalone healthz — engineering verification only; "
            "not production split authorization."
        ),
    }


def readyz_payload(cfg: EvalServiceConfig, store_info: Dict[str, Any] | None = None) -> Dict[str, Any]:
    info = store_info or {}
    db_ok = bool(info.get("ok"))
    return {
        "status": "ready" if db_ok else "not_ready",
        "product_id": "evaluation",
        "mode": cfg.mode,
        "db_configured": bool(cfg.db_url),
        "db_ok": db_ok,
        "db_path": info.get("db_path"),
        "store_schema_version": info.get("schema_version"),
        "schema_version": SCHEMA_READYZ,
        "process_split_authorized": False,
    }


def _attach_store(application: FastAPI, cfg: EvalServiceConfig) -> None:
    store = open_store(cfg.db_url, migrate=True)
    application.state.store = store
    application.state.store_info = store_health(store)


@asynccontextmanager
async def _lifespan(application: FastAPI):
    cfg: EvalServiceConfig = application.state.config
    _attach_store(application, cfg)
    yield


async def _healthz(request: Request) -> Dict[str, Any]:
    return healthz_payload(request.app.state.config)


async def _readyz(request: Request) -> Dict[str, Any]:
    cfg: EvalServiceConfig = request.app.state.config
    store = getattr(request.app.state, "store", None)
    info: Dict[str, Any]
    if store is None:
        info = {"ok": False}
    else:
        info = store_health(store)
        request.app.state.store_info = info
    return readyz_payload(cfg, info)


async def _canonical_healthz(request: Request) -> Dict[str, Any]:
    """Canonical path preview; A3 hosts full /api/platform/apps/eval/* here."""
    return healthz_payload(request.app.state.config)


async def _store_health(request: Request) -> Dict[str, Any]:
    store = getattr(request.app.state, "store", None)
    if store is None:
        return {"ok": False, "error": "store_not_initialized", "process_split_authorized": False}
    return store_health(store)


async def _store_roundtrip(request: Request) -> Dict[str, Any]:
    """A2 local proof: write/read set+report in eval SQLite (not for production)."""
    store = getattr(request.app.state, "store", None)
    if store is None:
        return {"ok": False, "error": "store_not_initialized", "process_split_authorized": False}
    return local_roundtrip(store)


async def _root(request: Request) -> Dict[str, Any]:
    cfg: EvalServiceConfig = request.app.state.config
    return {
        "product_id": "evaluation",
        "mode": cfg.mode,
        "endpoints": [
            "/healthz",
            "/readyz",
            "/api/platform/apps/eval/healthz",
            "/api/platform/apps/eval/store/health",
            "/api/platform/apps/eval/store/roundtrip",
        ],
        "process_split_authorized": False,
    }


def create_app(cfg: EvalServiceConfig | None = None) -> FastAPI:
    config = cfg or load_config()
    application = FastAPI(
        title="aiplat-evaluation",
        version=config.version,
        description=(
            "Evaluation standalone service (A2 local). "
            "process_split_authorized=false."
        ),
        lifespan=_lifespan,
    )
    application.state.config = config
    # Eager attach so TestClient works without context manager; lifespan re-attaches.
    _attach_store(application, config)
    application.add_api_route("/healthz", _healthz, methods=["GET"])
    application.add_api_route("/readyz", _readyz, methods=["GET"])
    application.add_api_route(
        "/api/platform/apps/eval/healthz", _canonical_healthz, methods=["GET"]
    )
    application.add_api_route(
        "/api/platform/apps/eval/store/health", _store_health, methods=["GET"]
    )
    application.add_api_route(
        "/api/platform/apps/eval/store/roundtrip", _store_roundtrip, methods=["POST"]
    )
    application.add_api_route("/", _root, methods=["GET"])
    return application


app = create_app()


def main() -> None:
    import uvicorn

    cfg = load_config()
    # Warm payload builders (also doubles as same-file call sites for wiring).
    _ = healthz_payload(cfg)
    _ = readyz_payload(cfg, {"ok": True, "db_path": cfg.db_url, "schema_version": "eval.store.v0"})
    uvicorn.run(
        "app.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
