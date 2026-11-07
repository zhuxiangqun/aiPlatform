"""External http_chat_pull exam — registry SSRF + mock live pull."""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "aiplat_home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.setenv("AIPLAT_EXTERNAL_EVAL_ALLOW_PRIVATE", "1")
    return home


def test_write_without_workspace_id_requires_explicit(tmp_path, monkeypatch):
    home = tmp_path / "home_req"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.delenv("AIPLAT_WORKSPACE_WRITE_DEFAULT_COMPAT", raising=False)

    from core.harness.named_workspace.errors import WorkspaceRequired
    from core.harness.named_workspace.resolve import resolve_named_workspace

    with pytest.raises(WorkspaceRequired):
        resolve_named_workspace(None, method="POST")


def test_ssrf_blocks_private_without_allow(tmp_path, monkeypatch):
    home = tmp_path / "home2"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.delenv("AIPLAT_EXTERNAL_EVAL_ALLOW_PRIVATE", raising=False)

    from core.apps.eval.service.external_targets import upsert_external_target

    with pytest.raises(ValueError, match="ssrf_blocked"):
        upsert_external_target(
            "default",
            target_id="bad_local",
            base_url="http://127.0.0.1:9",
            path="/v1/chat",
        )


def test_register_and_list_isolated_by_workspace(isolated_home):
    from core.apps.eval.service.external_targets import (
        list_external_targets,
        targets_path_for_workspace,
        upsert_external_target,
    )
    from core.harness.named_workspace.registry import create_local_workspace

    create_local_workspace("ws_a", label="A")
    upsert_external_target(
        "default",
        target_id="t_default",
        base_url="http://127.0.0.1:18080",
        path="/v1/chat",
    )
    upsert_external_target(
        "ws_a",
        target_id="t_a",
        base_url="http://127.0.0.1:18081",
        path="/v1/chat",
    )

    assert any(t["target_id"] == "t_default" for t in list_external_targets("default"))
    assert not any(t["target_id"] == "t_a" for t in list_external_targets("default"))
    assert any(t["target_id"] == "t_a" for t in list_external_targets("ws_a"))
    assert targets_path_for_workspace("default") == Path(isolated_home) / "external_targets.yaml"
    assert (
        targets_path_for_workspace("ws_a")
        == Path(isolated_home) / "workspaces" / "ws_a" / "external_targets.yaml"
    )


class _EchoHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = {}
        user = str(body.get("user_input") or "")
        # Echo must_contain-friendly fixed token for lexical gold papers.
        text = f"ACK external eval marker-alpha for: {user[:80]}"
        out = json.dumps(
            {
                "schema": "aiplat.external_eval.chat_pull.v0",
                "output_text": text,
                "trajectory": None,
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *_args):  # silence
        return


@pytest.fixture()
def mock_chat_server():
    server = HTTPServer(("127.0.0.1", 0), _EchoHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.mark.asyncio
async def test_live_external_exam_persists_under_workspace(
    isolated_home, mock_chat_server, monkeypatch
):
    from core.apps.eval.service.external_exam_ops import run_external_exam
    from core.apps.eval.service.external_targets import upsert_external_target
    from core.harness.named_workspace.resolve import (
        NamedWorkspaceContext,
        set_active_named_workspace,
        reset_active_named_workspace,
    )
    from core.harness.evaluation.eval_runner import load_agent_eval_results

    # Tiny synthetic set via monkeypatch of load_eval_set
    from core.harness.evaluation import eval_types as et

    tiny = et.EvalSet(
        set_id="ext_smoke/mini",
        category="smoke",
        description="external smoke",
        tasks=[
            et.EvalTask(
                task_id="t1",
                agent_id="ignored",
                user_input="say hello",
                success_criteria={"must_contain": ["marker-alpha"]},
            )
        ],
    )
    monkeypatch.setattr(
        "core.apps.eval.service.external_exam_ops.load_eval_set",
        lambda _sid: tiny,
    )

    upsert_external_target(
        "default",
        target_id="mock_echo",
        label="Mock",
        base_url=mock_chat_server,
        path="/v1/chat",
    )

    eval_dir = Path(isolated_home) / "eval_results"
    eval_dir.mkdir(parents=True, exist_ok=True)
    ctx = NamedWorkspaceContext(
        workspace_id="default",
        kind="local",
        label="Default",
        agents_dir=str(Path(isolated_home) / "agents"),
        eval_results_dir=str(eval_dir),
        root_dir=str(isolated_home),
    )
    token = set_active_named_workspace(ctx)
    try:
        out = await run_external_exam(
            workspace_id="default",
            target_id="mock_echo",
            set_id="ext_smoke/mini",
            live=True,
            persist=True,
            probe=False,
        )
    finally:
        reset_active_named_workspace(token)

    assert out.get("ok") is True
    assert out.get("accuracy_claim") is False
    assert out.get("agent_id") == "ext:mock_echo"
    assert out.get("composite_score") is not None
    gold = (out.get("result") or {}).get("gold") or {}
    assert gold.get("fact_support_rate") is not None or gold.get("tasks_with_fact_gold")

    hist = load_agent_eval_results("ext:mock_echo", limit=5)
    assert hist, "expected persisted eval_results for ext:mock_echo"
    assert any(Path(isolated_home / "eval_results").glob("ext:mock_echo_*.json"))
    # v0 response: no trajectory scored
    assert gold.get("trajectory_scored") is False
    assert "仅对话文本" in str(out.get("honesty") or "")


class _TrajHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = {}
        user = str(body.get("user_input") or "")
        text = f"ACK with tools marker-alpha for: {user[:40]}"
        out = json.dumps(
            {
                "schema": "aiplat.external_eval.chat_pull.v1",
                "output_text": text,
                "trajectory": {
                    "tool_calls": [
                        {"name": "lookup", "ok": True},
                        {"name": "extra_noise", "ok": True},
                        {"name": "summarize", "ok": True},
                    ]
                },
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *_args):
        return


@pytest.fixture()
def mock_traj_server():
    server = HTTPServer(("127.0.0.1", 0), _TrajHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_parse_trajectory_lenient_malformed():
    from core.apps.eval.service.external_chat_pull import parse_trajectory_tool_names

    assert parse_trajectory_tool_names(None) == []
    assert parse_trajectory_tool_names("bad") == []
    assert parse_trajectory_tool_names({"tool_calls": "x"}) == []
    assert parse_trajectory_tool_names(
        {"tool_calls": [{"name": "a"}, "b", {"name": ""}, 3]}
    ) == ["a", "b"]


@pytest.mark.asyncio
async def test_live_external_exam_scores_in_order_trajectory(
    isolated_home, mock_traj_server, monkeypatch
):
    from core.apps.eval.service.external_exam_ops import run_external_exam
    from core.apps.eval.service.external_targets import upsert_external_target
    from core.harness.evaluation import eval_types as et

    tiny = et.EvalSet(
        set_id="ext_smoke/traj",
        category="smoke",
        description="traj",
        tasks=[
            et.EvalTask(
                task_id="t1",
                agent_id="ignored",
                user_input="lookup then summarize",
                expected_tools=["lookup", "summarize"],
                success_criteria={"must_contain": ["marker-alpha"]},
            )
        ],
    )
    monkeypatch.setattr(
        "core.apps.eval.service.external_exam_ops.load_eval_set",
        lambda _sid: tiny,
    )
    upsert_external_target(
        "default",
        target_id="mock_traj",
        base_url=mock_traj_server,
        path="/v1/chat",
    )
    out = await run_external_exam(
        workspace_id="default",
        target_id="mock_traj",
        set_id="ext_smoke/traj",
        live=True,
        persist=False,
        probe=False,
    )
    assert out.get("ok") is True
    assert out.get("accuracy_claim") is False
    gold = (out.get("result") or {}).get("gold") or {}
    assert gold.get("trajectory_scored") is True
    assert gold.get("trajectory_match_mode") == "in_order"
    assert gold.get("tool_gold_match_rate") == 1.0
    traj = (out.get("result") or {}).get("trajectory") or {}
    assert traj.get("matched") is True
    assert "工具序" in str(out.get("honesty") or "")
