"""
Constitution test: system_prompt flow integrity.

Verifies that an agent's system_prompt configured in config JSON
flows correctly through the entire execution pipeline:
  config.system_prompt → run_workspace_agent → StageRunner → ReActLoop → LLM
"""

import json
import os
import pytest


@pytest.mark.constitution
class TestSystemPromptFlow:
    """Verify system_prompt survives the full execution pipeline."""

    def test_run_workspace_agent_reads_system_prompt_from_config(self):
        """core_facade.run_workspace_agent must extract system_prompt from agent_info.config."""
        import inspect
        from core.api.core_facade import run_workspace_agent

        source = inspect.getsource(run_workspace_agent)
        # Must read system_prompt from config
        assert "system_prompt" in source, (
            "run_workspace_agent does not reference system_prompt. "
            "It must extract system_prompt from agent_info.config and inject it into the prompt/state."
        )

    def test_stage_runner_passes_system_prompt_to_loopstate(self):
        """StageRunner must pass system_prompt from incoming state to LoopState context."""
        import inspect
        from core.harness.execution.langgraph.stage_runner import StageRunner

        source = inspect.getsource(StageRunner.run)
        assert ("_sys_prompt" in source or "system_prompt" in source), (
            "StageRunner.run() does not reference system_prompt or _sys_prompt. "
            "It must read system_prompt from the incoming state dict and inject it "
            "into LoopState context so the ReActLoop can use it as a system message."
        )

    def test_react_loop_reads_system_prompt_from_context(self):
        """ReActLoop._reason must read system_prompt from context and send as system role.

        P0-A7: _reason delegates to inference.reason (extracted from loop.py).
        The system_prompt injection lives in the delegation target — verify both.
        """
        import inspect
        from core.harness.execution.loop import ReActLoop
        from core.harness.execution.loop import inference

        source = inspect.getsource(ReActLoop._reason)
        reason_src = inspect.getsource(inference.reason)
        combined = source + reason_src
        assert ("system_prompt" in combined or "_sys_prompt" in combined), (
            "ReActLoop._reason / inference.reason does not reference system_prompt or _sys_prompt. "
            "It must read the system_prompt from LoopState context and inject it "
            "as a role='system' message before calling the LLM."
        )
        # The actual injection must produce a role='system' message
        assert "role" in reason_src and "system" in reason_src, (
            "inference.reason must inject system_prompt as role='system' message."
        )


@pytest.mark.constitution
class TestHardcodedSystemPrompts:
    """Detect hardcoded system role messages that override agent identity."""

    HARDCODED_EXEMPTIONS = [
        # Allow test code and bootstrap
        "/tests/",
        "/test_",
        "_test.",
        "#",
    ]

    def test_no_hardcoded_agent_identity_in_prompt_assembler(self):
        """PromptAssembler must not hardcode a specific agent identity."""
        import inspect
        from core.harness.assembly import PromptAssembler

        source = inspect.getsource(
            PromptAssembler.build_react_reasoning_messages
        )
        lines = [l.strip() for l in source.split("\n")]

        hardcoded_identities = []
        for i, line in enumerate(lines):
            # Allow _sync_resolve / _async_prompt_resolve calls (centrally managed templates)
            if "_sync_resolve" in line or "_async_prompt_resolve" in line:
                continue
            if '"system"' in line and (
                "你是" in line
                or "浏览器自动化" in line
                or "助手" in line
                or "assistant" in line
            ):
                hardcoded_identities.append(f"line {i + 1}: {line[:120]}")

        assert len(hardcoded_identities) == 0, (
            f"PromptAssembler contains hardcoded agent identity messages "
            f"that override the agent's configured system_prompt:\n"
            + "\n".join(hardcoded_identities)
            + "\n\nThese must be removed. Agent identity must come from "
            "agent_info.config.system_prompt, not from hardcoded strings."
        )


@pytest.mark.constitution
class TestExecutePathUniqueness:
    """Verify each resource type has exactly one execute entry point."""

    def test_agent_execute_path_count(self):
        """Agent execution should have at most 2 entry points (engine + workspace)."""
        import subprocess

        result = subprocess.run(
            [
                "grep", "-rn",
                r"agents.*execute\|execute.*agent.*{agent_id}",
                "aiPlat-core/core/api/routers/",
                "--include=*.py",
            ],
            capture_output=True, text=True,
        )
        routes = [
            l for l in result.stdout.strip().split("\n")
            if "@router" in l and l.strip()
        ]
        assert len(routes) <= 2, (
            f"Found {len(routes)} agent execute routes, expected ≤ 2 "
            f"(engine + workspace). Multiple paths for the same capability "
            f"may diverge in behavior:\n" + "\n".join(routes)
        )
