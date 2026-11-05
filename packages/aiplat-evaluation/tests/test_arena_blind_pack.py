"""Arena blind pack — strip models; shuffle sides; accuracy_claim false."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from arena_blind_pack import (  # noqa: E402
    JUDGE_VERSION,
    build_annotator_sheet,
    build_facilitator_rows,
    write_pack,
)


def test_annotator_has_no_model_fields(tmp_path: Path):
    pairs = ROOT / "docs" / "a3" / "arena_blind_pairs.v0.json"
    dest = write_pack(
        pairs, tmp_path, annotators=["r1", "r2"], salt="arena.blind.v1"
    )
    sheet = json.loads((dest / "annotator_r1.json").read_text(encoding="utf-8"))
    assert sheet["accuracy_claim"] is False
    assert sheet["judge_version"] == JUDGE_VERSION
    blob = json.dumps(sheet)
    assert "model_a" not in blob
    assert "model_b" not in blob
    assert "fixture-a" not in blob
    assert "left_is" not in blob
    for row in sheet["labels"]:
        assert row["label"] is None
        assert "left" in row and "right" in row


def test_facilitator_maps_sides():
    rows = build_facilitator_rows(
        [
            {
                "pair_id": "arena-01",
                "prompt": "p",
                "response_a": "AAA",
                "response_b": "BBB",
                "model_a": "m1",
                "model_b": "m2",
            }
        ],
        salt="arena.blind.v1",
    )
    assert len(rows) == 1
    row = rows[0]
    if row["swap"]:
        assert row["left"] == "BBB" and row["left_is"] == "b"
    else:
        assert row["left"] == "AAA" and row["left_is"] == "a"
    sheet = build_annotator_sheet(rows, annotator_id="r1")
    assert sheet["labels"][0]["left"] == row["left"]
