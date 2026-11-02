"""A3 — canonical store API on standalone; no core.harness imports."""
from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import EvalServiceConfig
from app.main import create_app


APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _cfg(tmp_path: Path) -> EvalServiceConfig:
    db = tmp_path / "eval_a3.sqlite3"
    return EvalServiceConfig(
        mode="standalone",
        host="127.0.0.1",
        port=8010,
        db_url=f"sqlite:///{db}",
        version="0.1.0",
        protocol="eval.protocol.v0",
    )


def test_canonical_sets_and_reports(tmp_path: Path):
    client = TestClient(create_app(_cfg(tmp_path)))

    hz = client.get("/api/platform/apps/eval/store/healthz").json()
    assert hz["data"]["ok"] is True
    assert hz["data"]["process_split_authorized"] is False

    created = client.post(
        "/api/platform/apps/eval/store/sets",
        json={"name": "a3-set", "meta": {"phase": "A3"}},
    ).json()
    set_id = created["data"]["id"]
    assert created["data"]["name"] == "a3-set"

    listed = client.get("/api/platform/apps/eval/store/sets").json()
    assert listed["data"]["total"] >= 1
    assert any(i["id"] == set_id for i in listed["data"]["items"])

    got = client.get(f"/api/platform/apps/eval/store/sets/{set_id}").json()
    assert got["data"]["id"] == set_id

    rpt = client.post(
        "/api/platform/apps/eval/store/reports",
        json={"metrics": {"phase": "A3"}, "run_ids": []},
    ).json()
    rid = rpt["data"]["id"]
    assert client.get(f"/api/platform/apps/eval/store/reports/{rid}").json()["data"]["id"] == rid

    root = client.get("/").json()
    assert "/api/platform/apps/eval/store/sets" in root["endpoints"]
    assert root["process_split_authorized"] is False


def test_app_sources_forbid_core_private_imports():
    forbidden = (
        "core.harness",
        "core.api.core_facade",
        "core.apps.eval",
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
                        name == p or name.startswith(p + ".") for p in forbidden
                    ), f"{path} imports {name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
                assert not any(
                    mod == p or mod.startswith(p + ".") for p in forbidden
                ), f"{path} imports from {mod}"
