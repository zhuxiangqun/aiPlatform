"""B1-L/B2-L — execute routes: deny sandbox runners; allowlist enqueue (B2)."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.auth import mint_local_token
from app.config import EvalServiceConfig
from app.main import create_app


def _cfg(tmp_path: Path) -> EvalServiceConfig:
    return EvalServiceConfig(
        mode="standalone",
        host="127.0.0.1",
        port=8010,
        db_url=f"sqlite:///{tmp_path / 'b1l.sqlite3'}",
        version="0.1.0",
        protocol="eval.protocol.v0",
        require_auth=True,
    )


def _headers() -> dict:
    return {"Authorization": f"Bearer {mint_local_token(tenant_id='tenant-local')}"}


def test_skill_run_sandbox_required(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    client = TestClient(create_app(_cfg(tmp_path)))
    r = client.post(
        "/api/platform/apps/eval/skill-evals/suites/s1/run",
        headers=_headers(),
        json={},
    )
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "sandbox_required"
    assert err["runner_id"] == "skill_suite"
    assert err["retryable"] is False


def test_prompt_eval_and_arena_enqueue(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    client = TestClient(create_app(_cfg(tmp_path)))
    for path, rid in (
        ("/api/platform/apps/eval/prompts/eval/runs", "prompt_eval"),
        ("/api/platform/apps/eval/arena/run", "arena"),
        ("/api/platform/apps/eval/kb-eval/run", "kb_rag"),
    ):
        r = client.post(path, headers=_headers(), json={})
        assert r.status_code == 202, path
        body = r.json()
        assert body["runner_id"] == rid
        assert body["status"] == "queued"
        assert body["process_split_authorized"] is False


def test_http_probe_sandbox_required(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    client = TestClient(create_app(_cfg(tmp_path)))
    r = client.post(
        "/api/platform/apps/eval/probes/http",
        headers=_headers(),
        json={},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "sandbox_required"
    assert r.json()["error"]["runner_id"] == "http_probe"


def test_healthz_local_not_split(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "0")
    client = TestClient(create_app(_cfg(tmp_path)))
    hz = client.get("/healthz")
    assert hz.status_code == 200
    body = hz.json()
    assert body["process_split_authorized"] is False
    assert body["environment"] == "local"
    assert body["b1l_execution_stubs"] is True
    assert body["b2l_allowlist_enqueue"] is True
    assert body["b2l_claim_lease"] is True
    assert body["b2l_runner_execute"] is True
    assert body["b2l_worker_loop"] is True
