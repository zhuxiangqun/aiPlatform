"""B0–B2 coding intensity: lite|full|ultra + hard floor; karpathy_v1 alias."""
from __future__ import annotations

from core.harness.utils.coding_intensity import (
    INTENSITY_FULL,
    INTENSITY_LITE,
    INTENSITY_ULTRA,
    build_coding_policy_block,
    default_intensity_for_factory_mode,
    intensity_to_policy_profile,
    is_strict_coding_profile,
    normalize_coding_intensity,
    ponytail_overlay_for_intensity,
    resolve_coding_intensity,
    resolve_ponytail_mode,
)


def test_normalize_aliases():
    assert normalize_coding_intensity("karpathy_v1") == INTENSITY_FULL
    assert normalize_coding_intensity("LITE") == INTENSITY_LITE
    assert normalize_coding_intensity("ultra") == INTENSITY_ULTRA
    assert normalize_coding_intensity("") == INTENSITY_FULL


def test_hard_constraints_in_all_active_tiers():
    for tier in (INTENSITY_LITE, INTENSITY_FULL, INTENSITY_ULTRA, "karpathy_v1"):
        block = build_coding_policy_block(tier)
        assert "硬约束" in block or "安全" in block
        assert "except Exception" in block or "静默" in block
    assert build_coding_policy_block("off") == ""
    assert build_coding_policy_block("") == ""


def test_ultra_has_more_than_full():
    full = build_coding_policy_block("full")
    ultra = build_coding_policy_block("ultra")
    lite = build_coding_policy_block("lite")
    assert len(ultra) > len(full) > len(lite)
    assert "over_engineering" in full or "过度设计" in full
    assert "新文件" in ultra or "新依赖" in ultra


def test_intensity_to_policy_profile_compat():
    assert intensity_to_policy_profile("full") == "karpathy_v1"
    assert intensity_to_policy_profile("lite") == "lite"
    assert intensity_to_policy_profile("off") == "off"


def test_strict_profiles_never_drop_lite():
    assert is_strict_coding_profile("lite")
    assert is_strict_coding_profile("full")
    assert is_strict_coding_profile("karpathy_v1")
    assert is_strict_coding_profile("ultra")
    assert not is_strict_coding_profile("off")


def test_factory_mode_defaults():
    assert default_intensity_for_factory_mode("code") == INTENSITY_FULL
    assert default_intensity_for_factory_mode("hybrid") == INTENSITY_FULL
    assert default_intensity_for_factory_mode("agent") == INTENSITY_LITE


def test_resolve_order(monkeypatch):
    monkeypatch.delenv("AIPLAT_CODING_INTENSITY", raising=False)
    monkeypatch.delenv("AIPLAT_CODING_POLICY_PROFILE_ENGINE", raising=False)
    assert resolve_coding_intensity(explicit="ultra") == INTENSITY_ULTRA
    assert resolve_coding_intensity(state={"coding_intensity": "lite"}) == INTENSITY_LITE
    monkeypatch.setenv("AIPLAT_CODING_INTENSITY", "ultra")
    assert resolve_coding_intensity() == INTENSITY_ULTRA


def test_ponytail_mode_env_typo_fallback(monkeypatch):
    monkeypatch.delenv("PONYTAIL_MODE", raising=False)
    monkeypatch.setenv("PONytail_MODE", "lite")
    assert resolve_ponytail_mode() == INTENSITY_LITE
    assert "lite" in ponytail_overlay_for_intensity("lite").lower()
