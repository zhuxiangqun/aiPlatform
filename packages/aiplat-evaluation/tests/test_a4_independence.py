"""A4 — eval store readable without Central / core.harness (in-process)."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import EvalServiceConfig
from app.main import create_app


APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _cfg(tmp_path: Path) -> EvalServiceConfig:
    return EvalServiceConfig(
        mode="standalone",
        host="127.0.0.1",
        port=8010,
        db_url=f"sqlite:///{tmp_path / 'a4.sqlite3'}",
        version="0.1.0",
        protocol="eval.protocol.v0",
    )


def test_report_survives_without_central_imports(tmp_path: Path):
    """Seed via roundtrip, re-read via canonical API — no Central call path."""
    client = TestClient(create_app(_cfg(tmp_path)))

    seed = client.post("/api/platform/apps/eval/store/roundtrip").json()
    assert seed["ok"] is True
    assert seed["process_split_authorized"] is False
    rid = seed["report_id"]
    sid = seed["set_id"]

    # Simulate "Central down": we simply never call it; eval still answers.
    rpt = client.get(f"/api/platform/apps/eval/store/reports/{rid}").json()
    assert rpt["data"]["id"] == rid
    st = client.get(f"/api/platform/apps/eval/store/sets/{sid}").json()
    assert st["data"]["id"] == sid

    hz = client.get("/healthz").json()
    assert hz["product_id"] == "evaluation"
    assert hz["process_split_authorized"] is False

    evid = {
        "schema_version": "aiplat.evaluation.a3.independence.v0",
        "kind": "local-eval-a3-independent",
        "environment": "local",
        "central_required": False,
        "seed": {"set_id": sid, "report_id": rid},
        "process_split_authorized": False,
        "production_signed": False,
    }
    out = tmp_path / "local-eval-a3-independent-unit.json"
    out.write_text(json.dumps(evid, indent=2) + "\n", encoding="utf-8")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["process_split_authorized"] is False
    assert loaded["central_required"] is False


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
