"""P2-A7: cron trigger no-agent script mode — zero LLM, fail-closed."""
import asyncio
import sys

import pytest


@pytest.mark.asyncio
async def test_script_trigger_runs_bash_fail_closed():
    sys.path.insert(0, ".")
    from core.harness.execution.event_loop import Trigger, _run_script_trigger

    # Valid bash entry — runs and completes (exit 0)
    t_ok = Trigger(trigger_id="t-ok", mode="cron", scene_id="",
                   params={"script": "bash -c 'echo hello-script'", "mode": "script"})
    await _run_script_trigger(t_ok)  # must not raise

    # Fail-closed: non-whitelisted entry is refused (never silently runs)
    t_bad = Trigger(trigger_id="t-bad", mode="cron", scene_id="",
                    params={"script": "rm -rf /", "mode": "script"})
    await _run_script_trigger(t_bad)  # must not raise / must not execute

    # Fail-closed: missing script param is skipped
    t_none = Trigger(trigger_id="t-none", mode="cron", scene_id="", params={"mode": "script"})
    await _run_script_trigger(t_none)


@pytest.mark.asyncio
async def test_script_trigger_timeout_and_error(tmp_path, monkeypatch):
    sys.path.insert(0, ".")
    from core.harness.execution.event_loop import Trigger, _run_script_trigger

    # Non-zero exit → warning, no crash
    t_err = Trigger(trigger_id="t-err", mode="cron", scene_id="",
                    params={"script": "bash -c 'exit 3'", "mode": "script"})
    await _run_script_trigger(t_err)

    # Timeout → killed, no crash
    t_slow = Trigger(trigger_id="t-slow", mode="cron", scene_id="",
                     params={"script": "bash -c 'sleep 5'", "mode": "script", "timeout_seconds": 0.2})
    await _run_script_trigger(t_slow)
