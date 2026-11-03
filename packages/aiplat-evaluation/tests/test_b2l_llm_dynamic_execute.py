"""B2 — prompt_eval dynamic path via LLM stub through Worker process_once.

Honesty: accuracy_claim=false; stub is not live infra proof; Central URL refused.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.llm.client import assert_provider_independence, estimate_cost, looks_like_central_llm_url
from app.store.jobs import enqueue_job, get_job
from app.store.migrate import apply_migrations
from app.worker.claim import process_once


def _db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'llm_dyn.sqlite3'}"
    apply_migrations(url)
    return url


def test_estimate_cost_and_central_url_guard(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_LLM_COST_PER_1K", "0.002")
    assert estimate_cost(tokens_in=500, tokens_out=500) == 0.002
    assert looks_like_central_llm_url("http://127.0.0.1:8000/v1") is True
    assert looks_like_central_llm_url("http://127.0.0.1:11434/v1") is False
    with pytest.raises(ValueError, match="central"):
        assert_provider_independence("http://127.0.0.1:8000/api/core/llm")


def test_process_once_prompt_eval_stub_dynamic(tmp_path: Path, monkeypatch):
    db = _db(tmp_path)
    monkeypatch.setenv("AIPLAT_EVAL_LLM", "stub")
    monkeypatch.setenv("AIPLAT_EVAL_LLM_STUB_OUTPUT", "hello")
    monkeypatch.setenv("AIPLAT_EVAL_LLM_COST_PER_1K", "0.01")
    enqueue_job(
        db,
        runner_id="prompt_eval",
        tenant_id="t",
        payload={"prompt": "say hi", "expected": "hello"},  # no actual → LLM fills
    )
    out = process_once(db, worker_id="w-llm")
    assert out is not None
    assert out["status"] == "succeeded"
    assert out["result"]["accuracy_claim"] is False
    assert out["result"]["mode"] == "llm_stub"
    assert out["result"]["evidence"]["llm"]["central_http"] is False
    assert out["result"]["evidence"]["llm"]["cost_estimate"] > 0
    assert out["result"]["scoring"]["composite"]["score"] is not None
    stored = get_job(db, out["job_id"])
    assert stored["status"] == "succeeded"


def test_http_llm_refuses_central_base(tmp_path: Path, monkeypatch):
    db = _db(tmp_path)
    monkeypatch.setenv("AIPLAT_EVAL_LLM", "http")
    monkeypatch.setenv("AIPLAT_EVAL_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    enqueue_job(
        db,
        runner_id="prompt_eval",
        tenant_id="t",
        payload={"prompt": "x", "expected": "y"},
    )
    out = process_once(db, worker_id="w-bad")
    assert out["status"] == "failed"
    assert out["result"]["ok"] is False
    detail = str(out["result"].get("evidence", {}).get("llm", {}).get("detail") or "")
    assert "central" in detail.lower() or "runner_forbidden" in detail.lower()
