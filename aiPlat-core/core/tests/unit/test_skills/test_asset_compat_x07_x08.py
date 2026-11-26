"""外援互通 Extended X07/X08 — L1 试跑 + L2 显式探针。"""
from __future__ import annotations

from pathlib import Path

from core.harness.maintenance.asset_compat import (
    finalize_skill_compat,
    run_l1_sandbox_trial,
    set_semantic_probe_result,
)


def _prompt_skill(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        "---\nname: x07s\nexecution_type: prompt\n---\nbody\n",
        encoding="utf-8",
    )


def test_l1_sandbox_trial_structure_only(tmp_path: Path):
    d = tmp_path / "prompt_sk"
    _prompt_skill(d)
    finalize_skill_compat(d)
    r = run_l1_sandbox_trial(d)
    assert r["ok"] is True
    assert r["schema"] == "aiplat.l1_sandbox_trial.v0"
    assert r["trial_kind"] == "structure_only"
    assert r["compat_level_hint"] == "L1"
    assert r["evidence_refs"]
    assert (d / "COMPAT.yaml").is_file()
    assert r["compat"]["compat_evidence_refs"]


def test_l1_sandbox_trial_static_handler(tmp_path: Path):
    d = tmp_path / "handler_sk"
    _prompt_skill(d)
    (d / "SKILL.md").write_text(
        "---\nname: hsk\nexecution_type: handler\n---\nRun.\n",
        encoding="utf-8",
    )
    (d / "handler.py").write_text(
        "def execute(**kwargs):\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    finalize_skill_compat(d)
    r = run_l1_sandbox_trial(d)
    assert r["ok"] is True
    assert r["trial_kind"] == "static_handler"
    assert r["compile_ok"] is True
    assert r["has_execute"] is True


def test_semantic_probe_requires_evidence(tmp_path: Path):
    d = tmp_path / "probe_sk"
    _prompt_skill(d)
    finalize_skill_compat(d)
    bad = set_semantic_probe_result(d, passed=True, evidence_refs=[])
    assert bad["ok"] is False
    assert bad["error"] == "interop.l2_probe_evidence_required"


def test_semantic_probe_promotes_to_l2_explicitly(tmp_path: Path):
    d = tmp_path / "l2_sk"
    _prompt_skill(d)
    c0 = finalize_skill_compat(d)
    assert c0.get("verified_tier") == "L1"
    r = set_semantic_probe_result(
        d,
        passed=True,
        evidence_refs=["probe:unit:1"],
        probe_id="unit-x08",
    )
    assert r["ok"] is True
    assert r["semantic_probe_passed"] is True
    assert r["verified_tier"] == "L2"
    assert r["compat"]["semantic_probe"]["explicit"] is True


def test_semantic_probe_clear_drops_l2(tmp_path: Path):
    d = tmp_path / "clear_sk"
    _prompt_skill(d)
    finalize_skill_compat(d)
    set_semantic_probe_result(d, passed=True, evidence_refs=["e1"])
    cleared = set_semantic_probe_result(d, passed=False, evidence_refs=[])
    assert cleared["ok"] is True
    assert cleared["semantic_probe_passed"] is False
    assert cleared["verified_tier"] == "L1"
