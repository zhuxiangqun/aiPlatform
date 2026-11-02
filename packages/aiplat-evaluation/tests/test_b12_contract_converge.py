"""B1/B2 contract converge — standalone surface (≠ staging authorize)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth import mint_local_token
from app.config import EvalServiceConfig
from app.contract.b12 import (
    assert_error_envelope,
    count_temporary_proxy_markers,
    proxied_store_suffixes,
    residual_central_cohost_note,
)
from app.errors import (
    execution_error,
    execution_not_migrated_response,
    runner_forbidden_response,
    sandbox_required_response,
)
from app.main import create_app
from app.store.jobs import enqueue_job, get_job
from app.store.migrate import apply_migrations
from app.worker.allowlist_guard import admit_job_for_execute, reject_forged_job


def _cfg(tmp_path: Path) -> EvalServiceConfig:
    return EvalServiceConfig(
        mode="standalone",
        host="127.0.0.1",
        port=8010,
        db_url=f"sqlite:///{tmp_path / 'b12.sqlite3'}",
        version="0.1.0",
        protocol="eval.protocol.v0",
        require_auth=True,
    )


def _headers() -> dict:
    return {"Authorization": f"Bearer {mint_local_token(tenant_id='tenant-local')}"}


def test_error_envelope_fields():
    body = execution_error(
        code="sandbox_required",
        runner_id="skill_suite",
        detail="needs sandbox",
        retryable=False,
    )
    err = assert_error_envelope(body)
    assert err["code"] == "sandbox_required"
    assert err["retryable"] is False
    with pytest.raises(ValueError, match="missing_error"):
        assert_error_envelope({"oops": True})


def test_error_response_helpers_shape():
    for resp in (
        execution_not_migrated_response(runner_id="skill_suite"),
        sandbox_required_response(runner_id="http_probe"),
        runner_forbidden_response(runner_id="unknown_runner"),
    ):
        assert resp.status_code in (503, 422)
        assert_error_envelope(json.loads(resp.body.decode("utf-8")))


def test_temporary_proxy_cleared_in_package():
    n = count_temporary_proxy_markers()
    assert n == 0, f"temporary_proxy=true markers must be 0, got {n}"


def test_proxied_suffixes_are_store_only():
    paths = proxied_store_suffixes()
    assert all(p.startswith("/store/") for p in paths)
    joined = " ".join(paths)
    assert "skill-evals" not in joined
    assert "prompts/eval" not in joined
    assert "arena" not in joined


def test_api_skill_and_probe_error_bodies(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    client = TestClient(create_app(_cfg(tmp_path)))
    skill = client.post(
        "/api/platform/apps/eval/skill-evals/suites/s1/run",
        headers=_headers(),
        json={},
    )
    assert skill.status_code == 422
    err = assert_error_envelope(skill.json())
    assert err["code"] == "sandbox_required"
    assert err["runner_id"] == "skill_suite"
    assert err["retryable"] is False

    probe = client.post(
        "/api/platform/apps/eval/probes/http",
        headers=_headers(),
        json={},
    )
    # http_probe without sandbox backend → sandbox_required
    assert probe.status_code == 422
    err2 = assert_error_envelope(probe.json())
    assert err2["code"] == "sandbox_required"
    assert err2["runner_id"] == "http_probe"

    hz = client.get("/healthz")
    assert hz.status_code == 200
    assert hz.json()["process_split_authorized"] is False


def test_dual_point_worker_rejects_forged_skill(tmp_path: Path):
    db = f"sqlite:///{tmp_path / 'forge.sqlite3'}"
    apply_migrations(db)
    forged = enqueue_job(
        db, runner_id="skill_suite", tenant_id="t", payload={"bypass": True}
    )
    ok, code, _ = admit_job_for_execute(forged)
    assert ok is False
    assert code == "sandbox_required"
    out = reject_forged_job(db, forged["job_id"])
    assert out is not None
    assert out["admitted"] is False
    assert out["status"] == "dead_letter"
    assert out["error_code"] == "sandbox_required"
    stored = get_job(db, forged["job_id"])
    assert stored is not None
    assert stored["status"] == "dead_letter"


def test_residual_note_mentions_cohost_not_authorize():
    note = residual_central_cohost_note()
    assert "cohost" in note.lower()
    assert "process_split_authorized=false" in note
    assert "temporary_proxy" in note.lower()
