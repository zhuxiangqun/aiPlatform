"""EVAL_V1 E2 — EvalStore schema + gold migration."""
from __future__ import annotations

from pathlib import Path

from core.apps.eval.service.store import (
    STORE_SCHEMA_VERSION,
    EvalStore,
    import_code_review_gold,
)


def test_eval_store_create_set_task_run(tmp_path):
    db = tmp_path / "eval.sqlite3"
    store = EvalStore(db_path=db)
    s = store.create_set(name="unit", version="0.1", split="dev", meta={"k": 1})
    assert s["id"]
    assert s["name"] == "unit"
    t = store.create_task(
        set_id=s["id"],
        input_data={"q": "hi"},
        expected={"a": "yo"},
        tags=["unit"],
    )
    assert t["set_id"] == s["id"]
    r = store.create_run(
        task_id=t["id"],
        target_kind="skill",
        target_ref="fixture",
        model="local",
        status="pending",
    )
    assert r["versions"]["model"] == "local"
    assert set(r["versions"]) >= {"dataset", "judge", "prompt", "model", "code_commit"}
    h = store.health()
    assert h["schema_version"] == STORE_SCHEMA_VERSION
    assert h["counts"]["eval_sets"] == 1
    assert h["counts"]["eval_tasks"] == 1
    assert h["counts"]["eval_runs"] == 1


def test_import_code_review_gold_from_workspace_seeds(tmp_path):
    db = tmp_path / "eval.sqlite3"
    seed = (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "eval"
        / "code_review_gold"
    )
    assert seed.is_dir(), seed
    out = import_code_review_gold(
        gold_dir=str(seed),
        tenant_id="e2-test",
        db_path=str(db),
    )
    assert out["ok"] is True
    assert out["imported"] >= 15, out  # batch_20 has 40 + 2 singles (dedupe by id)
    store = EvalStore(db_path=db)
    tasks = store.list_tasks(set_id=out["set_id"])
    assert len(tasks) >= 15
    assert any(t["id"].startswith("crg:") for t in tasks)


def test_eval_store_schema_file_exists():
    root = Path(__file__).resolve().parents[4]
    pkg = root / "packages/aiplat-evaluation/contracts/schemas/eval_store.schema.json"
    reports = (
        root
        / "reports/five-products/modules/evaluation/contracts/schemas/eval_store.schema.json"
    )
    assert pkg.is_file()
    assert reports.is_file()
    assert "eval.store.v0" in pkg.read_text(encoding="utf-8")
