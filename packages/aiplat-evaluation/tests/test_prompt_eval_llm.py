"""Optional AIPLAT_EVAL_LLM path for prompt_eval (stub + http mock)."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

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


def test_http_complete_against_local_server(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            _ = self.rfile.read(length)
            body = {
                "choices": [{"message": {"content": "pong"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            }
            raw = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("AIPLAT_EVAL_LLM", "http")
        monkeypatch.setenv("AIPLAT_EVAL_LLM_BASE_URL", f"http://127.0.0.1:{port}/v1")
        monkeypatch.setenv("AIPLAT_EVAL_LLM_MODEL", "test-model")
        result = complete_text("ping", job_id="j3", tenant_id="t", purpose="prompt_eval")
        assert result["ok"] is True
        assert result["text"] == "pong"
        assert result["audit"]["model"] == "test-model"
        assert result["audit"]["tokens_in"] == 3
        assert result["audit"]["central_http"] is False

        out = run_prompt_eval(
            {
                "job_id": "j4",
                "tenant_id": "t",
                "payload": {"prompt": "ping", "expected": "pong"},
            }
        )
        assert out["ok"] is True
        assert out["mode"] == "llm_http"
    finally:
        server.shutdown()
