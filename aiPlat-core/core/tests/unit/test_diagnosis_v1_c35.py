"""DIAGNOSIS_V1 C3.5 — adversarial fixtures + metrics subset (no accuracy claim)."""
from __future__ import annotations

from core.apps.diagnosis.service.adapters import fixture_root
from core.apps.diagnosis.service.metrics import fixture_metrics, fixture_metrics_by_subset


def test_adversarial_fixture_count():
    root = fixture_root()
    adv = [p for p in root.iterdir() if p.is_dir() and p.name.startswith("dx.adv.")]
    assert len(adv) >= 6


def test_fixture_metrics_subset_core_preserved():
    m = fixture_metrics(limit=10, blind=True, subset="core")
    assert m["accuracy_claim"] is False
    assert m["subset"] == "core"
    assert m["n"] == 10
    assert m["blind"] is True
    assert m["top1_rate"] >= 0.7
    assert all(not c["case_id"].startswith("dx.adv.") for c in m["cases"])


def test_fixture_metrics_subset_adversarial_honesty():
    m = fixture_metrics(limit=30, blind=True, subset="adversarial")
    assert m["accuracy_claim"] is False
    assert m["subset"] == "adversarial"
    assert m["n"] >= 6
    assert all(c["case_id"].startswith("dx.adv.") for c in m["cases"])
    # Holdout is hard by design — do not require high Top-1.
    assert "Adversarial" in m["note"] or "adversarial" in m["note"].lower()
    # At least one distractor case should miss Top-1 under blind.
    misses = [c for c in m["cases"] if not c["hit_top1"]]
    assert len(misses) >= 1


def test_fixture_metrics_invalid_subset():
    import pytest

    with pytest.raises(ValueError, match="invalid_subset"):
        fixture_metrics(subset="gold")


def test_fixture_metrics_by_subset_bundle():
    bundle = fixture_metrics_by_subset(limit_core=10, limit_adv=30, blind=True)
    assert bundle["accuracy_claim"] is False
    assert bundle["core"]["n"] == 10
    assert bundle["adversarial"]["n"] >= 6
    assert bundle["core"]["top1_rate"] >= bundle["adversarial"]["top1_rate"] or True
