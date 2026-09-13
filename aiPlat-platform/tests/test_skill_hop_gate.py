"""Phase B W4: skill hop schema gate."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "aiPlat-platform"))

from builder.skill_hop_gate import (  # noqa: E402
    build_hop_handoff,
    gate_skill_hop,
    validate_skill_hop_params,
)


def test_field_map_missing_required():
    schema = {
        "url": {"type": "string", "required": True, "description": "视频 URL"},
        "tenant_id": {"type": "string", "required": False},
    }
    violations = validate_skill_hop_params({}, schema)
    assert any("url" in v for v in violations)


def test_field_map_passes():
    schema = {
        "url": {"type": "string", "required": True},
    }
    assert validate_skill_hop_params({"url": "https://x"}, schema) == []


def test_empty_schema_passes():
    assert validate_skill_hop_params({}, {}) == []
    assert validate_skill_hop_params({"a": 1}, None) == []


def test_json_schema_like():
    schema = {
        "type": "object",
        "required": ["q"],
        "properties": {"q": {"type": "string"}},
    }
    assert any("q" in v for v in validate_skill_hop_params({}, schema))
    assert validate_skill_hop_params({"q": "hi"}, schema) == []


def test_gate_skill_hop_no_file_ok_without_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    r = gate_skill_hop("missing_skill_xyz", {"a": 1})
    assert r["ok"] is True  # no schema on disk → pass


def test_handoff_envelope():
    h = build_hop_handoff(skill="s1", agent="a1", ok=False, known_issues=["x"])
    assert set(h.keys()) >= {"summary", "artifact_ref", "verify", "known_issues", "next"}
    assert h["known_issues"] == ["x"]
