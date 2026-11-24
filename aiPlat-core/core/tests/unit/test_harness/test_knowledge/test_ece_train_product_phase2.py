"""N13 样本 ECE 训练产品面：默认可用；accuracy / certified 恒 false。"""
from __future__ import annotations

import os
from pathlib import Path

from core.api.core_facade import (
    compute_ece_from_samples,
    compute_ece_from_samples_product,
    evaluate_ece_train_product_gate,
    run_ece_train_product_suite,
)
from core.harness.knowledge_pipeline.confidence_calibration import (
    evaluate_ece_train_product_gate as _gate,
    run_ece_train_product_suite as _suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_product_suite_and_gate_honesty():
    suite = _suite()
    assert suite["ok"] is True
    assert suite["passed"] == 3
    assert suite["certified"] is False
    assert suite["accuracy_claim"] is False
    assert suite["ece_train_product_surface"] is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "ece_train_product_eval" in ids
    assert "ece_train_product_unavailable" in ids
    assert "honesty_product_certified_false" in ids
    gate = _gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = _gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    bad2 = dict(suite)
    bad2["accuracy_claim"] = True
    honesty2 = _gate(bad2)
    assert honesty2["ok"] is False
    assert "honesty_accuracy_claim_forbidden" in honesty2["issues"]


def test_facade_product_suite():
    suite = run_ece_train_product_suite()
    assert suite["ok"] is True
    gate = evaluate_ece_train_product_gate(suite)
    assert gate["ok"] is True
    assert gate["ece_train_product_surface"] is True
    assert gate["accuracy_claim"] is False


def test_product_without_residual_env():
    os.environ.pop("AIPLAT_KNOWLEDGE_ECE_TRAIN", None)
    residual = compute_ece_from_samples([{"confidence": 0.9, "correct": True}])
    assert residual["status"] == "ece_training_unavailable"
    assert residual.get("via") == "env_disabled"
    assert residual.get("ece_train_product_surface") is False

    perfect = (
        [{"confidence": 0.7, "correct": True}] * 70
        + [{"confidence": 0.7, "correct": False}] * 30
    )
    product = compute_ece_from_samples_product(perfect, n_bins=10)
    assert product["status"] == "ok"
    assert product.get("via") == "product"
    assert product["ece_train_product_surface"] is True
    assert product["accuracy_claim"] is False
    assert product["certified"] is False
    assert product.get("ece") is not None
    assert float(product["ece"]) <= 0.05


def test_docs_and_wiring_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "confidence_calibration.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "compute_ece_from_samples_product" in text
    assert "run_ece_train_product_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "compute_ece_from_samples_product" in facade.read_text(encoding="utf-8")
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "confidence_calibration_routes.py"
    )
    assert "confidence-calibrations/product/ece-train" in routes.read_text(
        encoding="utf-8"
    )
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "EceTrainPanel.tsx"
    )
    assert "confidence-calibrations/product/ece-train" in panel.read_text(
        encoding="utf-8"
    )
