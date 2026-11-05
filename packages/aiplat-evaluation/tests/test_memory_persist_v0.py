"""P2-2 memory_persist v0 — fixture store + Recall@k."""
from __future__ import annotations

import json
from pathlib import Path

from app.scoring.memory_persist import KINDS, apply_ops, recall, score_case, score_pack
from app.worker.runners import execute_runner

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs/a3/memory_tasks.v0.json"


def test_kinds_cover_six_axes():
    assert len(KINDS) == 6
    assert "recall_at_k" in KINDS
    assert "tenant_isolation" in KINDS


def test_store_ops_and_recall_filters():
    store = apply_ops(
        [
            {"op": "write", "id": "a", "tenant_id": "t1", "text": "alpha beta"},
            {"op": "write", "id": "b", "tenant_id": "t2", "text": "alpha beta"},
            {"op": "write", "id": "c", "tenant_id": "t1", "text": "alpha beta polluted", "polluted": True},
            {"op": "delete", "id": "a"},
        ]
    )
    assert store["a"]["status"] == "deleted"
    hits = recall(store, query="alpha", tenant_id="t1", k=5)
    ids = [h["id"] for h in hits]
    assert "a" not in ids
    assert "b" not in ids
    assert "c" not in ids


def test_score_case_fail_path():
    bad = score_case(
        {
            "case_id": "x",
            "kind": "tenant_isolation",
            "tenant_id": "t1",
            "k": 3,
            "ops": [
                {"op": "write", "id": "a", "tenant_id": "t1", "text": "same phrase"},
                {"op": "write", "id": "b", "tenant_id": "t2", "text": "same phrase"},
            ],
            "query": "same phrase",
            "expect_ids": ["a"],
            "forbid_ids": ["b"],
        }
    )
    assert bad["ok"] is True
    leak = score_case(
        {
            "case_id": "y",
            "kind": "delete_no_recall",
            "tenant_id": "t1",
            "k": 3,
            "ops": [{"op": "write", "id": "z", "tenant_id": "t1", "text": "keep me"}],
            "query": "keep me",
            "forbid_ids": ["z"],
        }
    )
    assert leak["ok"] is False


def test_pack_and_runner():
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    dim = score_pack(pack["cases"], pack_id=pack["schema"])
    assert dim["memory_pass"] is True
    assert dim["accuracy_claim"] is False
    assert not dim["kinds_missing"]

    out = execute_runner(
        {
            "job_id": "mem-pack",
            "runner_id": "memory_persist",
            "payload": {"cases": pack["cases"], "pack_id": "v0"},
        }
    )
    assert out["ok"] is True
    assert out["mode"] == "memory_persist_v0"
    assert out["accuracy_claim"] is False
