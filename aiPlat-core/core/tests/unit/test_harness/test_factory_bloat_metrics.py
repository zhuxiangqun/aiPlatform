"""F5a: LOC / new_deps / new_files bloat metrics (no abstraction_count)."""
from __future__ import annotations

from core.harness.execution.factory_bloat_metrics import (
    STATE_BLOAT_KEY,
    compare_bloat,
    compute_bloat_from_files,
    compute_bloat_from_state,
    extract_file_blocks,
    write_bloat_metrics,
)


SAMPLE = """
## FILE: app/main.py
import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}

## FILE: requirements.txt
fastapi==0.110.0
uvicorn>=0.27

## FILE: package.json
{
  "dependencies": {
    "react": "^18.0.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}
"""


def test_extract_and_count_files():
    files = extract_file_blocks(SAMPLE)
    assert len(files) == 3
    assert files[0]["path"].endswith("main.py")
    m = compute_bloat_from_files(files)
    assert m["new_files"] == 3
    assert m["loc"] >= 5
    assert m["loc_non_import"] < m["loc"]  # imports excluded from loc_non_import
    assert m["new_deps"] >= 3  # fastapi, uvicorn, react, typescript
    assert "abstraction_count" not in m


def test_compute_from_state_and_write():
    state = {
        "code": {"raw_output": SAMPLE},
        "prd": {"raw_output": "no files here"},
    }
    m = compute_bloat_from_state(state)
    assert m["new_files"] == 3
    assert m["schema_version"] == "f5a.1"
    assert "code" in m["sources"]
    out = write_bloat_metrics(state)
    assert state[STATE_BLOAT_KEY]["loc"] == out["loc"]


def test_compare_baseline_delta():
    cur = {"loc": 100, "loc_non_import": 80, "new_files": 5, "new_deps": 2}
    base = {"loc": 90, "loc_non_import": 70, "new_files": 4, "new_deps": 2}
    d = compare_bloat(cur, base)
    assert d["has_baseline"] is True
    assert d["delta_loc"] == 10
    assert d["delta_new_files"] == 1
    assert d["delta_new_deps"] == 0
    assert compare_bloat(cur, None)["has_baseline"] is False


def test_write_with_baseline():
    state = {"code": {"raw_output": SAMPLE}}
    base = {"loc": 1, "new_files": 1, "new_deps": 0}
    m = write_bloat_metrics(state, baseline=base)
    assert m["vs_baseline"]["has_baseline"] is True
    assert m["vs_baseline"]["delta_new_files"] == 2
