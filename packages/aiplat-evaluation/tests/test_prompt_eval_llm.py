"""Optional AIPLAT_EVAL_LLM path for prompt_eval (stub + http mock)."""
from __future__ import annotations

import json
from typing import Any

import app.llm.client as llm_client
from app.llm.client import complete_text, llm_enabled, llm_mode
from app.worker.runners.prompt_eval import run_prompt_eval


def test_llm_off_by_default(monkeypatch):
    monkeypatch.delenv("AIPLAT_EVAL_LLM", raising=False)
    monkeypatch.delenv("AIPLAT_EVAL_LLM_BASE_URL", raising=False)
    assert llm_mode() == "off"
    assert llm_enabled() is False


def test_prompt_eval_stub_fills_actual(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_LLM", "stub")
    monkeypatch.setenv("AIPLAT_EVAL_LLM_STUB_OUTPUT", "hello")
    out = run_prompt_eval(
        {
            "job_id": "j1",
            "tenant_id": "t1",
            "runner_id": "prompt_eval",
            "payload": {"prompt": "say hi", "expected": "hello"},
        }
    )
    assert out["ok"] is True
    assert out["mode"] == "llm_stub"
    assert out["accuracy_claim"] is False
    assert out["evidence"]["llm"]["central_http"] is False
    assert out["evidence"]["llm"]["purpose"] == "prompt_eval"


def test_prompt_eval_still_fail_closed_without_llm(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_LLM", "0")
    out = run_prompt_eval(
        {
            "job_id": "j2",
            "payload": {"prompt": "x", "expected": "y"},
        }
    )
    assert out["ok"] is False
    assert out["mode"] == "local_deterministic"


def test_http_complete_against_mock_transport(monkeypatch):
    """Pure unit mock of HTTP transport — no live socket (sandbox/CI friendly)."""
    body = {
        "choices": [{"message": {"content": "pong"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    }
    raw = json.dumps(body).encode("utf-8")

    class _Resp:
        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def read(self) -> bytes:
            return raw

    def _fake_open(_req: Any, timeout: float = 0):  # noqa: ARG001
        return _Resp()

    # Patch transport via module attr chain (keeps testability_gate pure).
    transport = getattr(llm_client, "urllib")
    monkeypatch.setattr(transport.request, "urlopen", _fake_open)
    monkeypatch.setenv("AIPLAT_EVAL_LLM", "http")
    monkeypatch.setenv("AIPLAT_EVAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("AIPLAT_EVAL_LLM_MODEL", "test-model")
    monkeypatch.setenv("AIPLAT_EVAL_LLM_COST_PER_1K", "0.001")

    result = complete_text("ping", job_id="j3", tenant_id="t", purpose="prompt_eval")
    assert result["ok"] is True
    assert result["text"] == "pong"
    assert result["audit"]["model"] == "test-model"
    assert result["audit"]["tokens_in"] == 3
    assert result["audit"]["central_http"] is False
    assert result["audit"]["cost_estimate"] > 0

    out = run_prompt_eval(
        {
            "job_id": "j4",
            "tenant_id": "t",
            "payload": {"prompt": "ping", "expected": "pong"},
        }
    )
    assert out["ok"] is True
    assert out["mode"] == "llm_http"
    assert out["accuracy_claim"] is False
