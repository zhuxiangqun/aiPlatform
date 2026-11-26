"""外援互通 X03/X01/X06 — claimed/verified + checksum + half_import。"""
from __future__ import annotations

from pathlib import Path

from core.harness.maintenance.asset_compat import (
    apply_majority_import_gate,
    enrich_compat_claim_tiers,
    finalize_skill_compat,
    normalize_asset_report_row,
    verified_compat_level,
)


def test_verified_level_never_auto_l2():
    assert verified_compat_level("prompt_ready", schedulable=True) == "L1"
    assert (
        verified_compat_level(
            "prompt_ready", schedulable=True, semantic_probe_passed=True
        )
        == "L2"
    )


def test_claimed_above_verified_marks_illegal(tmp_path: Path):
    d = tmp_path / "sk"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: sk\nexecution_type: prompt\n---\nbody\n",
        encoding="utf-8",
    )
    c = finalize_skill_compat(
        d,
        source={"compat_claim": "L2", "source": "unit-test"},
    )
    assert c["verified_tier"] in ("L0", "L1", "unknown")
    assert c["claimed_tier"] == "L2"
    assert c["compat_tier"] == c["verified_tier"]
    assert c.get("tier_claim_illegal") is True
    assert c.get("half_import") is True
    assert c.get("checksum", "").startswith("sha256:")
    assert any(
        (i or {}).get("code") == "interop.tier_claim_illegal"
        for i in (c.get("issues") or [])
    )


def test_half_import_fails_import_gate():
    row = normalize_asset_report_row(
        {
            "kind": "skill",
            "id": "bad",
            "tier": "prompt_ready",
            "schedulable": True,
            "claimed_tier": "L2",
            "verified_tier": "L1",
            "half_import": True,
            "tier_claim_illegal": True,
        }
    )
    gate = apply_majority_import_gate(assets=[row], warnings=[])
    assert gate["import_failed"] is True
    assert "bad" in gate["half_import_ids"]
    assert any("half_import_forbidden" in w for w in gate["warnings"])


def test_enrich_defaults_claimed_equals_verified():
    c = enrich_compat_claim_tiers(
        {"tier": "prompt_ready", "schedulable": True, "issues": []}
    )
    assert c["claimed_tier"] == c["verified_tier"] == "L1"
    assert not c.get("tier_claim_illegal")


def test_missing_skill_md_fail_closed_x02(tmp_path: Path):
    d = tmp_path / "broken"
    d.mkdir()
    c = finalize_skill_compat(d)
    assert c["tier"] == "blocked"
    assert c["schedulable"] is False
    assert c.get("half_import") is True
    assert any(
        (i or {}).get("code") == "interop.manifest_invalid"
        for i in (c.get("issues") or [])
    )


def test_invalid_frontmatter_fail_closed_x02(tmp_path: Path):
    d = tmp_path / "badfm"
    d.mkdir()
    (d / "SKILL.md").write_text("no frontmatter here\n", encoding="utf-8")
    from core.harness.maintenance.asset_compat import compute_skill_compat

    c = compute_skill_compat(d)
    assert c["tier"] == "blocked"
    assert any(
        (i or {}).get("code") == "interop.manifest_invalid"
        for i in (c.get("issues") or [])
    )
