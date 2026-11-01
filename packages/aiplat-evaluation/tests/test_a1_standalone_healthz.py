"""A1 — standalone FastAPI healthz/readyz; no core.harness imports."""
from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import EvalServiceConfig
from app.main import create_app


APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _cfg(*, mode: str = "standalone") -> EvalServiceConfig:
    return EvalServiceConfig(
        mode=mode,
        host="127.0.0.1",
        port=8010,
        db_url="sqlite:///./data/eval_local.sqlite3",
        version="0.1.0",
        protocol="eval.protocol.v0",
    )


def test_healthz_and_readyz_standalone():
    client = TestClient(create_app(_cfg(mode="standalone")))
    hz = client.get("/healthz").json()
    assert hz["status"] == "ok"
    assert hz["product_id"] == "evaluation"
    assert hz["capability_id"] == "evaluation"
    assert hz["deploy_unit"] == "evaluation"
    assert hz["mode"] == "standalone"
    assert hz["process_split_authorized"] is False
    assert hz["protocol"] == "eval.protocol.v0"

    rz = client.get("/readyz").json()
    assert rz["status"] == "ready"
    assert rz["process_split_authorized"] is False

    ch = client.get("/api/platform/apps/eval/healthz").json()
    assert ch["product_id"] == "evaluation"
    assert ch["process_split_authorized"] is False


def test_cohost_mode_deploy_unit_central():
    hz = TestClient(create_app(_cfg(mode="cohost"))).get("/healthz").json()
    assert hz["deploy_unit"] == "central"
    assert hz["process_split_authorized"] is False


def test_app_sources_forbid_core_private_imports():
    """Import guard: A1 package must not touch core.harness / Central internals."""
    forbidden_prefixes = (
        "core.harness",
        "core.api.core_facade",
        "aiPlat_core",
        "aiplat_core",
    )
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    assert not any(
                        name == p or name.startswith(p + ".") for p in forbidden_prefixes
                    ), f"{path} imports {name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
                assert not any(
                    mod == p or mod.startswith(p + ".") for p in forbidden_prefixes
                ), f"{path} imports from {mod}"
