"""PRD gate pack loader: builtins, seeds, user override merge."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.harness.execution.prd_gate_loader import (
    clear_prd_gate_pack_cache,
    load_prd_gate_packs,
)


@pytest.fixture(autouse=True)
def _isolate_user_prd_gates(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_PRD_GATES_DIR", str(tmp_path / "prd_gates"))
    clear_prd_gate_pack_cache()
    yield
    clear_prd_gate_pack_cache()


def test_load_includes_common_and_media():
    clear_prd_gate_pack_cache()
    packs = load_prd_gate_packs(force_reload=True)
    ids = [p.get("domain_id") for p in packs]
    assert "_common" in ids
    assert "media" in ids
    assert ids[0] == "_common"


def test_builtin_packs_are_kernel_only():
    """Vertical domains (media) must not live under prd_gate_packs/."""
    builtin = (
        Path(__file__).resolve().parents[3]
        / "harness"
        / "execution"
        / "prd_gate_packs"
    )
    yaml_names = {p.name for p in builtin.glob("*.yaml")}
    assert yaml_names == {"_common.yaml"}, yaml_names
    seeds = Path(__file__).resolve().parents[3] / "workspace_seeds" / "prd_gates"
    assert (seeds / "media.yaml").is_file()
    # Seeds are vertical-only — no duplicate kernel _common
    assert not (seeds / "_common.yaml").exists()


def test_common_excludes_media_vertical_rules():
    """Kernel _common must not own media-only checks (moved to media pack)."""
    clear_prd_gate_pack_cache()
    packs = {p["domain_id"]: p for p in load_prd_gate_packs(force_reload=True)}
    common_ids = {c.get("id") for c in (packs["_common"].get("checks") or [])}
    media_ids = {c.get("id") for c in (packs["media"].get("checks") or [])}
    for vertical in (
        "relative_report_latency_untestable",
        "modality_no_conflict_unverifiable",
        "asr_topic_contradiction",
    ):
        assert vertical not in common_ids
        assert vertical in media_ids
    assert "ssrf_guard_missing" in common_ids
    assert "encryption_without_key_mgmt" in common_ids


def test_user_dir_overrides_builtin(tmp_path, monkeypatch):
    override = tmp_path / "gates"
    override.mkdir()
    (override / "media.yaml").write_text(
        yaml.dump(
            {
                "domain_id": "media",
                "always": False,
                "triggers": ["视频"],
                "checks": [
                    {
                        "id": "user_override_marker",
                        "severity": "warning",
                        "when": {"all": [{"always": True}]},
                        "message": "from user dir",
                    }
                ],
                "repairs": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_PRD_GATES_DIR", str(override))
    clear_prd_gate_pack_cache()
    try:
        packs = load_prd_gate_packs(force_reload=True)
        media = next(p for p in packs if p.get("domain_id") == "media")
        check_ids = [c.get("id") for c in (media.get("checks") or [])]
        assert "user_override_marker" in check_ids
        # _common still present from builtin/seeds
        assert any(p.get("domain_id") == "_common" for p in packs)
    finally:
        # Process-wide cache must not leak stub packs into other tests.
        clear_prd_gate_pack_cache()


def test_seed_yaml_files_parse(tmp_path=None):
    roots = [
        Path(__file__).resolve().parents[3]
        / "harness"
        / "execution"
        / "prd_gate_packs",
        Path(__file__).resolve().parents[3] / "workspace_seeds" / "prd_gates",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob("*.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            assert isinstance(data, dict), path
            assert data.get("domain_id") or path.stem
            assert isinstance(data.get("checks", []), list)
            assert isinstance(data.get("repairs", []), list)
