"""Preference v0 pairwise scoring — accuracy_claim stays false."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.scoring.preference import preference_agreement, preference_dimension

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ROOT / "docs/a3/preference_pairs.v0.json"
SCRIPT = ROOT / "scripts/preference_v0_report.py"


def test_pairs_pack_size():
    pack = json.loads(PAIRS.read_text(encoding="utf-8"))
    assert pack["accuracy_claim"] is False
    assert len(pack["pairs"]) >= 30


def test_preference_dimension_and_agreement():
    dim = preference_dimension(
        pairs_n=4,
        preferred=["a", "b", "tie", "a"],
        annotator_id="A",
    )
    assert dim["accuracy_claim"] is False
    assert dim["coverage"] == 1.0
    st = preference_agreement(["a", "b", "a", "tie"], ["a", "b", "b", "tie"])
    assert st["n"] == 4
    assert st["agreement"] == 0.75
    assert st["accuracy_claim"] is False


def test_cli_report(tmp_path: Path):
    pack = json.loads(PAIRS.read_text(encoding="utf-8"))
    ids = [p["id"] for p in pack["pairs"][:32]]

    def sheet(name: str, flip: bool = False) -> Path:
        labels = []
        for i, pid in enumerate(ids):
            pref = "b" if flip and i < 4 else "a"
            labels.append({"pair_id": pid, "preferred": pref})
        path = tmp_path / name
        path.write_text(
            json.dumps({"annotator_id": name, "labels": labels}),
            encoding="utf-8",
        )
        return path

    a = sheet("a.json")
    b = sheet("b.json", flip=True)
    out = tmp_path / "pref.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--pairs",
            str(PAIRS),
            "--a",
            str(a),
            "--b",
            str(b),
            "--out",
            str(out),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["accuracy_claim"] is False
    assert payload["inter_annotator"]["n"] >= 30
