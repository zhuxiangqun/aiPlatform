"""P2-0 human calibration pack — stratified samples; accuracy_claim false."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from calibration_human_pack import (  # noqa: E402
    _sample_arena,
    _sample_g2b,
    _sample_preference,
    main as pack_main,
)
import random


def test_g2b_sample_balanced():
    rows = _sample_g2b(random.Random(20261106), n_each=10)
    assert len(rows) == 20
    pos = sum(1 for r in rows if r["original_conclusion"] == "PASS")
    neg = sum(1 for r in rows if r["original_conclusion"] == "FAIL")
    assert pos == 10 and neg == 10
    assert all(r["recheck"] == "" for r in rows)


def test_arena_and_preference_sizes():
    rows_a = _sample_arena(random.Random(20261106), n=20)
    rows_p = _sample_preference(random.Random(20261106), n=20)
    assert len(rows_a) == 20
    assert len(rows_p) == 20


def test_pack_writes_csvs(tmp_path: Path):
    assert pack_main(["--out", str(tmp_path), "--seed", "20261106"]) == 0
    dest = next(tmp_path.iterdir())
    meta = json.loads((dest / "meta.json").read_text(encoding="utf-8"))
    assert meta["accuracy_claim"] is False
    assert meta["counts"] == {"g2b": 20, "arena": 20, "preference": 20}
    for name in ("calibration_g2b.csv", "calibration_arena.csv", "calibration_preference.csv"):
        rows = list(csv.DictReader((dest / name).open(encoding="utf-8-sig")))
        assert len(rows) == 20
        assert all(not (r.get("recheck") or "").strip() for r in rows)
