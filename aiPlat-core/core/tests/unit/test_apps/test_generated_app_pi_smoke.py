"""generated_app_pi_ops — offline sample export smoke (no pi CLI required)."""
from __future__ import annotations

from core.apps.eval.service.generated_app_pi_ops import run_generated_app_pi_smoke


def test_sample_offline_export_structural():
    out = run_generated_app_pi_smoke(source="sample", live=False)
    # Actual host not invoked → fixture; target delivery still pi
    assert out.get("runtime_tier") == "fixture"
    assert out.get("target_runtime") == "pi"
    assert out.get("runtime_claim") is False
    assert out.get("accuracy_claim") is False
    assert out.get("ok") is True, out
    assert out.get("pi_bundle")
    structural = out.get("structural") or {}
    assert structural.get("ok") is True, structural


def test_project_missing_fails_honestly():
    out = run_generated_app_pi_smoke(
        source="project", project_id="__no_such_project__", live=False
    )
    assert out.get("ok") is False
    assert out.get("runtime_tier") == "fixture"
    assert out.get("target_runtime") == "pi"
    assert out.get("runtime_claim") is False
