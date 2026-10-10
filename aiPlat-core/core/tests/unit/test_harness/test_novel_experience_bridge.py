"""Novel → experience_feedback pending bridge."""

from __future__ import annotations

import json

from core.harness.evaluation.novel_experience_bridge import register_novel_as_experience


def test_register_novel_writes_pending(tmp_path, monkeypatch):
    path = tmp_path / "exp.json"
    monkeypatch.setenv("AIPLAT_EXPERIENCE_FILE", str(path))
    novels = [
        {"case_id": "sql", "file": "a.py", "severity": "P0", "description": "sql inject"},
        {"case_id": "sql", "file": "b.py", "severity": "P1", "description": "log pwd"},
    ]
    out = register_novel_as_experience(novels)
    assert len(out) == 2
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert len(rows) == 2
    p0 = next(r for r in rows if r["risk"] == "high")
    assert p0["status"] == "pending"
    assert p0["require_review"] is True


def test_register_novel_merges(tmp_path, monkeypatch):
    path = tmp_path / "exp.json"
    monkeypatch.setenv("AIPLAT_EXPERIENCE_FILE", str(path))
    n = [{"case_id": "x", "file": "f.py", "severity": "P0", "description": "once"}]
    register_novel_as_experience(n)
    register_novel_as_experience(n)
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert rows[0]["occurrences"] == 2
