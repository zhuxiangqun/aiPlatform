"""aiPlat control-plane v0 + healthz shape."""
from __future__ import annotations

import json
from pathlib import Path

from core.harness.meta.control_plane import (
    SCHEMA_VERSION,
    normalize_health_status,
    to_aiplat_healthz,
    to_control_plane_v0,
)


def test_normalize_and_healthz():
    assert normalize_health_status("healthy") == "ok"
    assert normalize_health_status("degraded") == "degraded"
    hz = to_aiplat_healthz(status="healthy", checks={"db": {"ok": True}})
    assert hz["status"] == "ok"
    assert hz["product_id"] == "aiplat"
    assert hz["checks"]["db"]["ok"] is True


def test_control_plane_envelope():
    env = to_control_plane_v0(kind="status", payload={"health": "ok"}, tenant_id="t1")
    assert env["schema_version"] == SCHEMA_VERSION
    assert env["kind"] == "status"
    assert env["tenant_id"] == "t1"


def test_matches_repo_schemas():
    repo = Path(__file__).resolve().parents[4]
    base = repo / "reports/five-products/modules/aiplat/contracts/schemas"
    hz_schema = json.loads((base / "healthz.schema.json").read_text(encoding="utf-8"))
    cp_schema = json.loads((base / "control_plane.schema.json").read_text(encoding="utf-8"))
    hz = to_aiplat_healthz(status="ok")
    cp = to_control_plane_v0(kind="status", payload={})
    for k in hz_schema.get("required") or []:
        assert k in hz
    for k in cp_schema.get("required") or []:
        assert k in cp
    assert hz["product_id"] == hz_schema["properties"]["product_id"]["const"]
    assert cp["schema_version"] == cp_schema["properties"]["schema_version"]["const"]
