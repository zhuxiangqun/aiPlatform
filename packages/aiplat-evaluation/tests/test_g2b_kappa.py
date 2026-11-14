"""G2b inter-annotator κ — honesty: accuracy_claim stays false."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "g2b_kappa.py"
TASKS_FULL = ROOT / "docs/a3/g2b_tasks.v0.json"
# CI subset: κ gate uses 30-task pack; full n=100 remains closeout-only.
TASKS_CI30 = ROOT / "docs/a3/fixtures/g2b_tasks.ci30.v0.json"


def test_task_pack_has_30():
    pack = json.loads(TASKS_FULL.read_text(encoding="utf-8"))
    assert pack["accuracy_claim"] is False
    assert len(pack["tasks"]) >= 30
    ids = [t["id"] for t in pack["tasks"]]
    assert len(ids) == len(set(ids))
    ci = json.loads(TASKS_CI30.read_text(encoding="utf-8"))
    assert ci["accuracy_claim"] is False
    assert len(ci["tasks"]) == 30


def test_cohen_perfect_and_chance():
    import importlib.util

    spec = importlib.util.spec_from_file_location("g2b_kappa", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    perfect = [(True, True), (False, False), (True, True)]
    st = mod.cohen_kappa_binary(perfect)
    assert st["agreement"] == 1.0
    assert st["inter_annotator_kappa"] == 1.0
    mixed = [(True, True), (True, False), (True, True), (True, False)]
    st2 = mod.cohen_kappa_binary(mixed)
    assert st2["n"] == 4
    assert st2["inter_annotator_kappa"] is not None


def test_cli_pairs_30(tmp_path: Path):
    pack = json.loads(TASKS_CI30.read_text(encoding="utf-8"))
    ids = [t["id"] for t in pack["tasks"]]
    assert len(ids) == 30

    def sheet(name: str, flip: bool = False) -> Path:
        labels = []
        for i, tid in enumerate(ids):
            # gold_pass_hint mostly true; B flips first 5 if flip
            p = True
            if flip and i < 5:
                p = False
            labels.append({"task_id": tid, "pass": p})
        path = tmp_path / name
        path.write_text(
            json.dumps({"schema": "eval.g2b.worksheet.v0", "annotator_id": name, "labels": labels}),
            encoding="utf-8",
        )
        return path

    a = sheet("a.json")
    b = sheet("b.json", flip=True)
    out = tmp_path / "kappa.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--a",
            str(a),
            "--b",
            str(b),
            "--tasks",
            str(TASKS_CI30),
            "--out",
            str(out),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["accuracy_claim"] is False
    assert payload["kappa_kind"] == "inter_annotator"
    assert payload["n"] == 30
    assert payload["inter_annotator_kappa"] is not None
