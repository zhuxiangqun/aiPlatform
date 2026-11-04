"""local_chaos_sqlite — crash/wipe/partial restore stay honest."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "local_chaos_sqlite",
    ROOT / "scripts" / "local_chaos_sqlite.py",
)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(mod)


def test_run_chaos_gate_and_honesty(tmp_path: Path):
    payload = mod.run_chaos(tmp_path / "work")
    assert payload["accuracy_claim"] is False
    assert payload["process_split_authorized"] is False
    assert payload["not_staging_evidence"] is True
    assert payload["gate_ok"] is True
    ids = {s["id"] for s in payload["scenarios"]}
    assert "crash_unlink_restore" in ids
    assert "wipe_restore" in ids
    assert "partial_then_full_restore" in ids
    assert all(s["ok"] for s in payload["scenarios"])
