"""外援互通 Extended X09 — 资产目录。"""
from __future__ import annotations

from pathlib import Path

from core.harness.maintenance.asset_compat import (
    build_interop_asset_catalog,
    finalize_skill_compat,
    normalize_interop_catalog_row,
)


def test_normalize_catalog_row_enriches_tiers():
    row = normalize_interop_catalog_row(
        kind="skill",
        asset_id="s1",
        compat={"tier": "prompt_ready", "schedulable": True, "issues": []},
    )
    assert row["schema"] == "aiplat.interop_asset_catalog_row.v0"
    assert row["verified_tier"] == "L1"
    assert row["claimed_tier"] == "L1"


def test_build_catalog_from_path(tmp_path: Path):
    d = tmp_path / "sk"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: sk\nexecution_type: prompt\n---\nbody\n",
        encoding="utf-8",
    )
    finalize_skill_compat(d)
    cat = build_interop_asset_catalog(
        [{"kind": "skill", "asset_id": "sk", "path": str(d)}]
    )
    assert cat["count"] == 1
    assert cat["by_kind"]["skill"] == 1
    assert cat["items"][0]["verified_tier"] == "L1"
