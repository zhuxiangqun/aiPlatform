"""B1-L — dynamic execute → 503 + unified error body; process_split false."""
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


def test_skill_run_503_error_body(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    client = TestClient(create_app(_cfg(tmp_path)))
    r = client.post(
        "/api/platform/apps/eval/skill-evals/suites/s1/run",
        headers=_headers(),
        json={},
    )
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "execution_not_migrated"
    assert err["runner_id"] == "skill_suite"
    assert err["retryable"] is False
    assert "detail" in err


def test_prompt_eval_and_arena_503(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    client = TestClient(create_app(_cfg(tmp_path)))
    for path, rid in (
        ("/api/platform/apps/eval/prompts/eval/runs", "prompt_eval"),
        ("/api/platform/apps/eval/arena/run", "arena"),
        ("/api/platform/apps/eval/kb-eval/run", "kb_rag"),
    ):
        r = client.post(path, headers=_headers(), json={})
        assert r.status_code == 503, path
        assert r.json()["error"]["code"] == "execution_not_migrated"
        assert r.json()["error"]["runner_id"] == rid


def test_http_probe_sandbox_required(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    client = TestClient(create_app(_cfg(tmp_path)))
    r = client.post(
        "/api/platform/apps/eval/probes/http",
        headers=_headers(),
        json={},
    )
    assert r.status_code == 503
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
