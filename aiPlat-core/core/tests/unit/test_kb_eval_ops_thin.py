"""kb_eval_ops service — platform thin route backend."""
from __future__ import annotations

import os
from pathlib import Path


def test_kb_eval_ops_crud(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_KB_TENANTS_DIR", str(tmp_path))
    from core.apps.eval.service.kb_eval_ops import (
        kb_eval_create_sample,
        kb_eval_delete_sample,
        kb_eval_list_samples,
        kb_eval_import_csv_text,
        kb_eval_list_reports,
        kb_eval_reports_series,
        kb_eval_compare_reports,
    )

    created = kb_eval_create_sample(
        {"question": "What is 2+2?", "ground_truth": "4", "tags": ["math"]}
    )
    assert created["status"] == "created"
    listed = kb_eval_list_samples(tag="math")
    assert listed["total"] == 1
    assert listed["items"][0]["ground_truth"] == "4"

    csv = "question,ground_truth,doc_ids,tags\nQ2,A2,d1;d2,t1\n"
    imp = kb_eval_import_csv_text(csv)
    assert imp["imported"] == 1
    assert kb_eval_list_samples()["total"] == 2

    assert kb_eval_list_reports()["total"] == 0
    series = kb_eval_reports_series(days=7)
    assert "days" in series
    cmp_ = kb_eval_compare_reports()
    assert "session_a" in cmp_

    kb_eval_delete_sample(created["id"])
    assert kb_eval_list_samples()["total"] == 1


def test_platform_kb_eval_has_no_sqlite():
    root = Path(__file__).resolve().parents[3]  # aiPlat-core
    # platform lives sibling
    plat = root.parent / "aiPlat-platform" / "apps" / "eval" / "api" / "kb_eval.py"
    text = plat.read_text(encoding="utf-8")
    assert "sqlite3" not in text
    assert "kb_eval_list_samples" in text
