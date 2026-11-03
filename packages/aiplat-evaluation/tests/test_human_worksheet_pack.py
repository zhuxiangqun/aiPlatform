"""Human worksheet pack generator — blank A/B sheets without gold on annotators."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "human_worksheet_pack.py"


def test_pack_generates_g2b_and_preference(tmp_path: Path):
    out = tmp_path / "pack"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    fac = json.loads((out / "g2b_facilitator.json").read_text(encoding="utf-8"))
    assert fac["not_for_annotators"] is True
    assert fac["tasks"][0].get("gold_pass_hint") is not None
    a = json.loads((out / "g2b_annotator_a.json").read_text(encoding="utf-8"))
    b = json.loads((out / "g2b_annotator_b.json").read_text(encoding="utf-8"))
    assert a["annotator_id"] == "A"
    assert b["annotator_id"] == "B"
    assert len(a["labels"]) >= 30
    assert a["labels"][0]["pass"] is None
    assert "gold_pass_hint" not in a["labels"][0]
    pref_a = json.loads((out / "pref_annotator_a.json").read_text(encoding="utf-8"))
    assert len(pref_a["labels"]) >= 30
    assert pref_a["labels"][0]["preferred"] is None
    assert pref_a["labels"][0]["a"]
    assert pref_a["accuracy_claim"] is False

    assert (out / "model_outputs.json").is_file()
    # Prefer flat model_outputs.json (safe for newlines / quotes).
    outs = {"g2b-01": 'line1\nline2 {"k":1}'}
    (out / "model_outputs.json").write_text(
        json.dumps(outs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    proc2 = subprocess.run(
        [sys.executable, str(SCRIPT), "--from-outputs", str(out)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc2.returncode == 0, proc2.stderr
    a2 = json.loads((out / "g2b_annotator_a.json").read_text(encoding="utf-8"))
    assert a2["labels"][0]["model_output"] == 'line1\nline2 {"k":1}'
    fac2 = json.loads((out / "g2b_facilitator.json").read_text(encoding="utf-8"))
    assert fac2["tasks"][0]["model_output"] == 'line1\nline2 {"k":1}'
