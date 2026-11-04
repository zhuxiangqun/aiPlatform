"""Worksheet pack facilitation — generate/list; accuracy_claim always false."""
from __future__ import annotations

import json
from pathlib import Path

from core.apps.eval.service.worksheet_pack import (
    worksheet_pack_file,
    worksheet_pack_generate,
    worksheet_pack_status,
)


def test_worksheet_pack_generate_and_list(tmp_path: Path, monkeypatch):
    # Redirect pack root via generate out_dir override through module generate.
    from core.apps.eval.service import worksheet_pack as wp

    out = tmp_path / "pack"
    mod = wp._load_pack_module()
    result = mod.generate_human_worksheet_pack(out_dir=out)
    assert result["accuracy_claim"] is False
    assert result["gate"] == "ok"
    assert (out / "g2b_annotator_a.json").is_file()
    assert (out / "pref_annotator_b.json").is_file()
    assert (out / "g2b_facilitator.json").is_file()
    fac = json.loads((out / "g2b_facilitator.json").read_text(encoding="utf-8"))
    assert fac.get("not_for_annotators") is True
    assert any(
        isinstance(t, dict) and "gold_pass_hint" in t for t in (fac.get("tasks") or [])
    )
    # Gold field must not be on annotator label rows (instructions may mention the name).
    a = json.loads((out / "g2b_annotator_a.json").read_text(encoding="utf-8"))
    for row in a.get("labels") or []:
        assert isinstance(row, dict)
        assert "gold_pass_hint" not in row


def test_worksheet_pack_status_and_facade():
    st = worksheet_pack_status(limit=5)
    assert st["ok"] is True
    assert st["accuracy_claim"] is False
    assert st["process_split_authorized"] is False
    from core.api.core_facade import eval_worksheet_pack_status

    st2 = eval_worksheet_pack_status()
    assert st2["accuracy_claim"] is False


def test_worksheet_pack_file_rejects_bad_names():
    meta, text = worksheet_pack_file("../x", "a.json")
    assert meta["ok"] is False
    assert text is None
    meta2, _ = worksheet_pack_file("20260101T000000Z", "../a.json")
    assert meta2["ok"] is False
