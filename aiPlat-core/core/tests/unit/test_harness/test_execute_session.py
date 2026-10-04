"""mint_execute_session_id + agent stream wall + CLAUDE inject mode + LLM stall."""
from __future__ import annotations

import pytest

from core.harness.utils.execute_session import (
    agent_stream_timeout_seconds,
    coerce_coding_delivery_text,
    emit_pre_llm_prep_close,
    has_progress_after_generate,
    llm_generate_event_stall_limit,
    llm_generate_stall_seconds,
    llm_timeout_seconds,
    mint_execute_session_id,
    pre_llm_prep_close_ids,
    resolve_skill_model_purpose,
    resolve_workspace_agent_model_purpose,
    skill_call_in_flight_after,
)


def test_preserves_explicit_session():
    assert mint_execute_session_id(kind="agent", target_id="a1", session_id="conv-9") == "conv-9"


def test_replaces_default_and_empty():
    a = mint_execute_session_id(kind="tool", target_id="echo", session_id="default")
    b = mint_execute_session_id(kind="tool", target_id="echo", session_id="")
    c = mint_execute_session_id(kind="agent", target_id="pm", session_id=None)
    assert a.startswith("tool-exec-echo-")
    assert b.startswith("tool-exec-echo-")
    assert c.startswith("agent-exec-pm-")
    assert a != b
    assert "default" not in a


def test_job_kind_prefix():
    sid = mint_execute_session_id(kind="job-skill", target_id="lint", session_id="default")
    assert sid.startswith("job-skill-exec-lint-")
    assert "default" not in sid


def test_agent_stream_timeout_respects_floor_and_ceil(monkeypatch):
    monkeypatch.delenv("AIPLAT_STREAM_STALL_SECONDS", raising=False)
    monkeypatch.setenv("AIPLAT_LLM_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("AIPLAT_AGENT_STREAM_ORPHAN_SECONDS", "1200")
    monkeypatch.setenv("AIPLAT_AGENT_STREAM_ORPHAN_MAX_SECONDS", "2400")
    assert agent_stream_timeout_seconds(2) == 1200.0
    # 10 steps × per_step (stall*0.85) may hit ceil (stall floor 360 → raw 3060 → 2400)
    got = agent_stream_timeout_seconds(10)
    assert 1200.0 <= got <= 2400.0
    raw = 10 * max(180 * 1.25, llm_generate_stall_seconds() * 0.85)
    assert got == min(2400.0, max(1200.0, raw))


def test_agent_stream_timeout_scales_with_steps(monkeypatch):
    monkeypatch.delenv("AIPLAT_STREAM_STALL_SECONDS", raising=False)
    monkeypatch.setenv("AIPLAT_LLM_TIMEOUT_SECONDS", "100")
    monkeypatch.setenv("AIPLAT_AGENT_STREAM_ORPHAN_SECONDS", "100")
    monkeypatch.setenv("AIPLAT_AGENT_STREAM_ORPHAN_MAX_SECONDS", "5000")
    got = agent_stream_timeout_seconds(4)
    assert got >= 100.0
    assert got <= 5000.0
    assert got >= 4 * 100 * 1.25


def test_llm_generate_stall_above_timeout_single_attempt(monkeypatch):
    monkeypatch.delenv("AIPLAT_STREAM_STALL_SECONDS", raising=False)
    monkeypatch.setenv("AIPLAT_LLM_TIMEOUT_SECONDS", "180")
    # TimeoutError is never retried — stall is one wait_for + slack, not N×timeout.
    # +180 slack / floor 360 covers local to_thread overrun (run-b6f2/run-870f ~337–359s).
    assert llm_generate_stall_seconds() == max(360.0, 180.0 + 180.0)
    assert llm_generate_stall_seconds() >= llm_timeout_seconds() + 180.0
    assert llm_generate_stall_seconds() < 540.0


def test_llm_generate_stall_override(monkeypatch):
    monkeypatch.setenv("AIPLAT_STREAM_STALL_SECONDS", "500")
    monkeypatch.setenv("AIPLAT_LLM_TIMEOUT_SECONDS", "180")
    assert llm_generate_stall_seconds() == 500.0


def test_llm_generate_event_stall_backup_after_declared_wait_for():
    fallback = 540.0
    # Declared wait_for must NOT shrink orphan below global floor (run-b6f2: 337s generate).
    assert llm_generate_event_stall_limit(
        {"args": {"timeout_seconds": 180}}, fallback=fallback
    ) == fallback  # max(540, 360) → 540
    assert llm_generate_event_stall_limit(
        {"args": {"timeout_seconds": 400}}, fallback=fallback
    ) == 580.0  # max(540, 580) → 580
    assert llm_generate_event_stall_limit(
        {"args": {"timeout_seconds": 500}}, fallback=fallback
    ) == 680.0  # max(540, 680) → 680
    # No per-call timeout → keep global floor.
    assert llm_generate_event_stall_limit({"args": {}}, fallback=fallback) == fallback
    assert llm_generate_event_stall_limit(
        {"args": {"timeout_seconds": 30}}, fallback=fallback
    ) == fallback
    # Low fallback still gets at least ev_to+180.
    assert llm_generate_event_stall_limit(
        {"args": {"timeout_seconds": 180}}, fallback=200.0
    ) == 360.0

def test_resolve_workspace_agent_model_purpose_prefers_skill_model_purpose():
    agent = type("A", (), {
        "metadata": {"skill_model_purpose": "agent", "loop_type": "react"},
        "config": {},
        "loop_type": "react",
        "agent_type": "conversational",
    })()
    assert resolve_workspace_agent_model_purpose(agent) == "agent"


def test_resolve_workspace_agent_model_purpose_react_loop_fallback():
    agent = type("A", (), {
        "metadata": {},
        "config": {},
        "loop_type": "react",
        "agent_type": "conversational",
    })()
    assert resolve_workspace_agent_model_purpose(agent) == "agent"


def test_resolve_skill_model_purpose_from_metadata():
    cfg = type("C", (), {"metadata": {"skill_model_purpose": "reasoning"}})()
    skill = type("S", (), {"_config": cfg})()
    assert resolve_skill_model_purpose(skill) == "reasoning"
    assert resolve_skill_model_purpose(type("S", (), {"_config": None})()) == "skill_execution"


def test_skill_call_in_flight_after_route_without_terminal():
    """run-c32ebc4df1eb: skill_route selected, no kind=skill yet → still in flight."""
    items = [
        {
            "kind": "llm",
            "name": "generate",
            "status": "success",
            "start_time": 100.0,
            "end_time": 122.0,
        },
        {
            "kind": "routing",
            "name": "skill_route",
            "status": "selected",
            "start_time": 122.1,
            "end_time": 122.2,
        },
    ]
    assert skill_call_in_flight_after(items, after_ts=122.0) is True


def test_has_progress_after_generate_counts_observation_under_500ms():
    """architect run-e51daea7e4e4: observation +73ms must not look like a zombie."""
    gen_end = 1791045402.1551418
    items = [
        {
            "kind": "llm",
            "name": "generate",
            "status": "success",
            "end_time": gen_end,
        },
        {
            "kind": "skill",
            "name": "architecture_design",
            "status": "success",
            "end_time": gen_end + 0.048,
        },
        {
            "kind": "observe",
            "name": "observation",
            "status": "ok",
            "start_time": gen_end + 0.073,
            "end_time": None,
        },
    ]
    assert has_progress_after_generate(items, gen_end) is True
    assert has_progress_after_generate(items, gen_end + 10.0) is False


def test_skill_call_in_flight_clears_when_skill_terminal():
    items = [
        {
            "kind": "routing",
            "name": "skill_route",
            "status": "selected",
            "start_time": 122.1,
            "end_time": 122.2,
        },
        {
            "kind": "skill",
            "name": "code_generation",
            "status": "success",
            "start_time": 122.1,
            "end_time": 200.0,
        },
    ]
    assert skill_call_in_flight_after(items, after_ts=122.0) is False


def test_skill_call_in_flight_false_without_route():
    items = [
        {"kind": "llm", "name": "generate", "status": "success", "end_time": 50.0},
        {"kind": "routing", "name": "routing_decision", "status": "decision", "end_time": 51.0},
    ]
    assert skill_call_in_flight_after(items, after_ts=50.0) is False


def test_coerce_coding_delivery_text_unwraps_python_repr_envelope():
    """run-c896745b: str({code, language}) must not be sealed as opaque text dump."""
    body = "## FILE: frontend/src/types.ts\nexport type X = string;\nDONE"
    wrapped = repr({"code": body, "language": "typescript", "_language_locked": True})
    assert coerce_coding_delivery_text(wrapped) == body
    assert coerce_coding_delivery_text(body) == body
    assert coerce_coding_delivery_text("plain prose") == "plain prose"


def test_persist_startable_scaffold_writes_run_workspace(tmp_path, monkeypatch):
    from core.harness.utils.execute_session import persist_startable_scaffold_delivery

    home = tmp_path / "aiplat-home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS", str(home))
    inp = (
        "【单独测·可启动骨架】不要写业务 CRUD。使用 `## FILE:` 交付。\n"
        "不要用本机能否 `npm run dev` / uvicorn 代替交齐文件。\n"
        "FastAPI main.py + Vite frontend/package.json。调用 code_generation → DONE。"
    )
    out = (
        "## FILE: main.py\n```python\nfrom fastapi import FastAPI\napp = FastAPI()\n```\n"
        "## FILE: frontend/package.json\n```json\n{\"name\":\"fe\"}\n```\n"
        "## FILE: frontend/vite.config.ts\n```ts\nexport default {}\n```\n"
    )
    info = persist_startable_scaffold_delivery(
        run_id="run-persist-test", input_text=inp, output_text=out
    )
    assert info.get("disk_persist") == "ok"
    root = info.get("persisted_root") or ""
    assert str(home) in root
    assert (tmp_path / "aiplat-home" / "run_workspaces" / "run-persist-test" / "main.py").is_file()
    assert "from fastapi import FastAPI" in (
        tmp_path / "aiplat-home" / "run_workspaces" / "run-persist-test" / "main.py"
    ).read_text()


def test_persist_skips_isolated_coding_slice(tmp_path, monkeypatch):
    from core.harness.utils.execute_session import persist_startable_scaffold_delivery

    home = tmp_path / "aiplat-home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS", str(home))
    inp = (
        "【单独测·可组装切片】本用例测业务模块，不是 Vite 工程。"
        "不要生成 package.json；无 project_scaffold。禁止 FastAPI。"
    )
    out = (
        "## FILE: frontend/src/types.ts\n```ts\nexport type X = string;\n```\n"
        "## FILE: frontend/src/api/apiClient.ts\n```ts\nexport async function f() {}\n```\n"
    )
    info = persist_startable_scaffold_delivery(
        run_id="run-isolated", input_text=inp, output_text=out
    )
    assert info.get("disk_persist") == "skip"
    assert not (home / "run_workspaces" / "run-isolated").exists()


def test_persist_uses_aiplat_home_when_allowlist_unset(tmp_path, monkeypatch):
    from core.harness.utils.execute_session import persist_startable_scaffold_delivery

    home = tmp_path / "aiplat-home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.delenv("AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS", raising=False)
    inp = "【单独测·可启动骨架】FastAPI main.py + Vite frontend/package.json。调用 code_generation → DONE。"
    out = (
        "## FILE: main.py\n```python\nfrom fastapi import FastAPI\napp = FastAPI()\n```\n"
        "## FILE: frontend/package.json\n```json\n{\"name\":\"fe\"}\n```\n"
        "## FILE: frontend/vite.config.ts\n```ts\nexport default {}\n```\n"
    )
    info = persist_startable_scaffold_delivery(
        run_id="run-home-default", input_text=inp, output_text=out
    )
    assert info.get("disk_persist") == "ok"
    assert (home / "run_workspaces" / "run-home-default" / "main.py").is_file()


def test_pre_llm_prep_close_ids_covers_legacy_and_step():
    ids = pre_llm_prep_close_ids(
        "run-124d89d5ef3f",
        step_count=2,
        parent_span_id="step:qa_agent:2",
    )
    assert "run-124d89d5ef3f:pre_llm_prep" in ids
    assert "run-124d89d5ef3f:pre_llm_prep:2" in ids
    assert "run-124d89d5ef3f:pre_llm_prep:1" in ids


def test_pre_llm_prep_close_ids_from_parent_only():
    ids = pre_llm_prep_close_ids("run-x", parent_span_id="step:architect_agent:3")
    assert "run-x:pre_llm_prep:3" in ids
    assert "run-x:pre_llm_prep:2" in ids


@pytest.mark.asyncio
async def test_emit_pre_llm_prep_close_upserts_stepped_id():
    from unittest.mock import AsyncMock

    store = type("S", (), {})()
    store.add_syscall_event = AsyncMock()
    store.close_running_syscall_events = AsyncMock(return_value=1)
    await emit_pre_llm_prep_close(
        store,
        "run-qa",
        status="ok",
        step_count=2,
        parent_span_id="step:qa_agent:2",
        reason="eager_finalize:reason_auto_done",
    )
    ids = [c.args[0]["id"] for c in store.add_syscall_event.await_args_list]
    assert "run-qa:pre_llm_prep" in ids
    assert "run-qa:pre_llm_prep:2" in ids
    store.close_running_syscall_events.assert_awaited_once()
    kwargs = store.close_running_syscall_events.await_args.kwargs
    assert kwargs["kind"] == "context"
    assert kwargs["name"] == "pre_llm_prep"
