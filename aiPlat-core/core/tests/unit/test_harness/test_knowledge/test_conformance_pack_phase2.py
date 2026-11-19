"""W10 Conformance / 认证证据包：N24 目录 + 结构门槛门。"""
from __future__ import annotations

from pathlib import Path

import yaml

from core.harness.knowledge_pipeline import conformance_pack as cp


def test_repo_catalog_has_exactly_24_and_gate_passes():
    pack = cp.build_conformance_pack()
    assert pack["ok"] is True
    assert pack["n24"]["actual"] == 24
    assert pack["certified"] is False
    assert pack["n24_full_conformance"] is False
    gate = cp.evaluate_conformance_gate()
    assert gate["pass"] is True, gate
    assert gate["certified"] is False
    assert gate["n24_full_conformance"] is False
    counts = gate["n24_counts"]
    assert counts["exists"] + counts["partial"] + counts["missing"] == 24
    # Core 12 项 Core-scoped exists 后 partial 下降；仍不应回到 missing 主导
    assert counts["exists"] >= 12
    assert counts["missing"] <= 6


def test_repo_catalog_slots_filled_no_explicit_missing_warning():
    """Batch F1：slo/exception_adr 已填 path；结构门不再发 explicit-missing warning。"""
    gate = cp.evaluate_conformance_gate()
    assert gate["pass"] is True, gate
    assert "slo_and_exception_adr_explicitly_missing" not in (gate.get("warnings") or [])
    assert gate["certified"] is False
    slots = {
        s["id"]: s
        for s in ((gate.get("pack") or {}).get("certification") or {}).get("slots") or []
    }
    for sid in ("slo", "exception_adr"):
        assert sid in slots
        assert slots[sid].get("present") is True
        assert "slot_explicitly_missing" not in (slots[sid].get("issues") or [])


def test_gate_fails_when_claimed_evidence_missing(tmp_path):
    cat = {
        "standard": "test",
        "standard_section": "N",
        "pilot_domain": "pilot-domain",
        "measured_at": "2026-11-16",
        "items": [
            {
                "id": f"N{i:02d}",
                "title": f"t{i}",
                "status": "missing" if i > 1 else "partial",
                "evidence": ["reports/does-not-exist-xyz.md"] if i == 1 else [],
                "note": "",
            }
            for i in range(1, 25)
        ],
        "certification_slots": [
            {"id": s, "title": s, "path": ""} for s in cp.REQUIRED_CERT_SLOTS
        ],
    }
    # 补齐：第一条 partial 需要存在的路径才不因 path_missing 失败——此处故意坏路径
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.dump(cat, allow_unicode=True), encoding="utf-8")
    gate = cp.evaluate_conformance_gate(catalog_path=str(path))
    assert gate["pass"] is False
    assert any("evidence_path_missing" in x for x in gate["issues"])


def test_gate_fails_when_not_24_items(tmp_path):
    cat = {
        "items": [
            {"id": "N01", "title": "x", "status": "missing", "evidence": []}
        ],
        "certification_slots": [
            {"id": s, "title": s, "path": ""} for s in cp.REQUIRED_CERT_SLOTS
        ],
    }
    path = tmp_path / "thin.yaml"
    path.write_text(yaml.dump(cat), encoding="utf-8")
    gate = cp.evaluate_conformance_gate(catalog_path=str(path))
    assert gate["pass"] is False
    assert "n24_count_not_24" in gate["issues"]


def test_missing_item_may_hang_nonexistent_explanatory_path(tmp_path):
    """missing 可挂说明性路径；路径不存在不阻断结构门。"""
    cat = {
        "items": [
            {
                "id": f"N{i:02d}",
                "title": f"t{i}",
                "status": "missing",
                "evidence": (
                    ["reports/does-not-exist-explanatory.md"] if i == 1 else []
                ),
            }
            for i in range(1, 25)
        ],
        "certification_slots": [
            {"id": s, "title": s, "path": ""} for s in cp.REQUIRED_CERT_SLOTS
        ],
    }
    path = tmp_path / "missing_hang.yaml"
    path.write_text(yaml.dump(cat, allow_unicode=True), encoding="utf-8")
    gate = cp.evaluate_conformance_gate(catalog_path=str(path))
    assert gate["pass"] is True, gate
    assert not any("evidence_path_missing" in x for x in gate["issues"])


def test_honesty_flags_never_auto_certify(tmp_path, monkeypatch):
    """即便 24 exists，本切片也不自动 certified=True。"""
    repo = Path(cp._repo_root())
    # 用真实存在的 README 当证据
    ok_ref = "reports/products/knowledge-system/v4.3.1/README.md"
    assert (repo / ok_ref).is_file()
    cat = {
        "items": [
            {
                "id": f"N{i:02d}",
                "title": f"t{i}",
                "status": "exists",
                "evidence": [ok_ref],
            }
            for i in range(1, 25)
        ],
        "certification_slots": [
            {"id": s, "title": s, "path": ok_ref if s != "slo" else ""}
            for s in cp.REQUIRED_CERT_SLOTS
        ],
    }
    path = tmp_path / "full.yaml"
    path.write_text(yaml.dump(cat), encoding="utf-8")
    gate = cp.evaluate_conformance_gate(catalog_path=str(path))
    assert gate["pass"] is True, gate
    assert gate["certified"] is False
    assert gate["n24_full_conformance"] is False
    assert gate["accuracy_claim"] is False
