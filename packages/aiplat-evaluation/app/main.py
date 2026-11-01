"""EVAL A3-local A1 — standalone FastAPI entrypoint (:8010).

Honesty:
- Proves independent process + healthz/readyz only.
- Does NOT set process_split_authorized=true.
- No imports from core.harness / Central private modules.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, Request

from app.config import EvalServiceConfig, load_config

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
            "A1 local standalone healthz — engineering verification only; "
            "not production split authorization."
        ),
    }


def readyz_payload(cfg: EvalServiceConfig) -> Dict[str, Any]:
    # A1: process is ready when the app is up. A2+ will check DB connectivity.
    return {
        "status": "ready",
        "product_id": "evaluation",
        "mode": cfg.mode,
        "db_configured": bool(cfg.db_url),
        "schema_version": SCHEMA_READYZ,
        "process_split_authorized": False,
    }


async def _healthz(request: Request) -> Dict[str, Any]:
    return healthz_payload(request.app.state.config)


async def _readyz(request: Request) -> Dict[str, Any]:
    return readyz_payload(request.app.state.config)


async def _canonical_healthz(request: Request) -> Dict[str, Any]:
    """Canonical path preview; A3 hosts full /api/platform/apps/eval/* here."""
    return healthz_payload(request.app.state.config)


async def _root(request: Request) -> Dict[str, Any]:
    cfg: EvalServiceConfig = request.app.state.config
    return {
        "product_id": "evaluation",
        "mode": cfg.mode,
        "endpoints": ["/healthz", "/readyz", "/api/platform/apps/eval/healthz"],
        "process_split_authorized": False,
    }


def create_app(cfg: EvalServiceConfig | None = None) -> FastAPI:
    config = cfg or load_config()
    application = FastAPI(
        title="aiplat-evaluation",
        version=config.version,
        description=(
            "Evaluation standalone service (A1 local). "
            "process_split_authorized=false."
        ),
    )
    application.state.config = config
    application.add_api_route("/healthz", _healthz, methods=["GET"])
    application.add_api_route("/readyz", _readyz, methods=["GET"])
    application.add_api_route(
        "/api/platform/apps/eval/healthz", _canonical_healthz, methods=["GET"]
    )
    application.add_api_route("/", _root, methods=["GET"])
    return application


app = create_app()


def main() -> None:
    import uvicorn

    cfg = load_config()
    # Warm payload builders (also doubles as same-file call sites for wiring).
    _ = healthz_payload(cfg)
    _ = readyz_payload(cfg)
    uvicorn.run(
        "app.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
