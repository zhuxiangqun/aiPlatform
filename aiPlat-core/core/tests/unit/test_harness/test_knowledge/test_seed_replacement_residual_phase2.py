"""N02 seed authority residual：certified / seed_replacement_complete 恒 false。"""
from __future__ import annotations

from pathlib import Path

from core.api.core_facade import (
    apply_published_seed_authority,
    evaluate_seed_replacement_gate,
    run_seed_replacement_suite,
)
from core.harness.knowledge_pipeline.object_type_publish import (
    apply_published_seed_authority as _apply,
    evaluate_seed_replacement_gate as _gate,
    run_seed_replacement_suite as _suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_suite_and_gate_honesty():
    suite = _suite()
    assert suite["ok"] is True
    assert suite["passed"] == 3
    assert suite["certified"] is False
    assert suite["seed_replacement_complete"] is False
    assert suite.get("n02_object_type_freeze") is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "seed_replacement_unavailable" in ids
    assert "seed_replacement_opt_in" in ids
    assert "honesty_certified_false" in ids
    gate = _gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = _gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    bad2 = dict(suite)
    bad2["seed_replacement_complete"] = True
    honesty2 = _gate(bad2)
    assert honesty2["ok"] is False
    assert "honesty_seed_replacement_complete_forbidden" in honesty2["issues"]


def test_facade_suite():
    suite = run_seed_replacement_suite()
    assert suite["ok"] is True
    gate = evaluate_seed_replacement_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["seed_replacement_complete"] is False


def test_unavailable_default():
    r = _apply(
        tenant_id="t1",
        seed_path=str(
            ROOT
            / "aiPlat-core"
            / "workspace_seeds"
            / "ontologies"
            / "lock-service-object-types.json"
        ),
        object_type_ids=["InstallOrder"],
    )
    assert r["status"] == "seed_replacement_unavailable"
    assert r["certified"] is False
    assert r["seed_replacement_complete"] is False
    fr = apply_published_seed_authority(
        tenant_id="t1",
        seed_path=str(
            ROOT
            / "aiPlat-core"
            / "workspace_seeds"
            / "ontologies"
            / "lock-service-object-types.json"
        ),
        object_type_ids=["InstallOrder"],
    )
    assert fr["status"] == "seed_replacement_unavailable"


def test_docs_and_wiring_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "object_type_publish.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "apply_published_seed_authority" in text
    assert "run_seed_replacement_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "apply_published_seed_authority" in facade.read_text(encoding="utf-8")
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "object_type_publish_routes.py"
    )
    assert "seed-authority" in routes.read_text(encoding="utf-8")
    cat = (
        ROOT
        / "reports"
        / "products"
        / "knowledge-system"
        / "v4.3.1"
        / "n24-conformance-catalog.yaml"
    )
    assert "n02_object_type_freeze" in cat.read_text(encoding="utf-8")
