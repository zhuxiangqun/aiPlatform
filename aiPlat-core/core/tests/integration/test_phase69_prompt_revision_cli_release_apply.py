import subprocess
import time
from pathlib import Path

import pytest
from unittest.mock import AsyncMock


class CaptureModel:
    def __init__(self):
        self.last_messages = None

    async def generate(self, messages):
        self.last_messages = messages
        return type("R", (), {"content": "ok"})


class PromptingAgent:
    def __init__(self, model):
        self._model = model

    async def execute(self, context):
        from core.harness.interfaces.agent import AgentResult
        from core.harness.syscalls.llm import sys_llm_generate

        await sys_llm_generate(self._model, "BASE_PROMPT", trace_context={"trace_id": "t1", "run_id": "r1"})
        return AgentResult(success=True, output={"ok": True}, metadata={})


class DummyAgentInfo:
    def __init__(self):
        self.config = {"model": "gpt-4"}
        self.tools = []
        self.skills = []


@pytest.mark.asyncio
async def test_phase69_prompt_revision_cli_release_apply(tmp_path, monkeypatch):
    """
    Phase 6.9 acceptance:
    - Use learning_cli to create a prompt_revision artifact (draft)
    - Create a release candidate referencing it
    - Publish release without approval (status transitions)
    - Runtime applies the published prompt_revision when toggles enabled
    """
    repo_root = Path(__file__).resolve().parents[3]
    cli = repo_root / "scripts" / "learning_cli.py"
    db_path = tmp_path / "executions.sqlite3"

    # Create prompt revision artifact (draft)
    p1 = subprocess.run(
        [
            "python3",
            str(cli),
            "--db",
            str(db_path),
            "create-prompt-revision-artifact",
            "--target-type",
            "agent",
            "--target-id",
            "a1",
            "--version",
            "pr-1",
            "--prepend",
            "PRE",
            "--append",
            "POST",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p1.returncode == 0, p1.stderr
    pr_id = p1.stdout.strip()
    assert pr_id

    # Create release candidate referencing the prompt revision
    p2 = subprocess.run(
        [
            "python3",
            str(cli),
            "--db",
            str(db_path),
            "create-release-candidate",
            "--target-type",
            "agent",
            "--target-id",
            "a1",
            "--version",
            "rc-1",
            "--artifact-ids",
            pr_id,
            "--summary",
            "apply prompt",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p2.returncode == 0, p2.stderr
    cand_id = p2.stdout.strip()
    assert cand_id

    # Publish release (no approval), should mark candidate + referenced artifact published
    p3 = subprocess.run(
        [
            "python3",
            str(cli),
            "--db",
            str(db_path),
            "publish-release",
            "--candidate-id",
            cand_id,
            "--user-id",
            "u1",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p3.returncode == 0, p3.stderr
    assert p3.stdout.strip() == "published"

    # Now run harness with apply toggles
    monkeypatch.setenv("AIPLAT_ENABLE_LEARNING_APPLIER", "true")
    monkeypatch.setenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "true")
    monkeypatch.setenv("AIPLAT_APPLY_PROMPT_REVISIONS", "true")

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.services.trace_service import TraceService
    from core.harness.integration import HarnessIntegration, HarnessConfig, KernelRuntime
    from core.harness.kernel.types import ExecutionRequest
    from core.apps.tools.permission import get_permission_manager, Permission
    from core.harness.infrastructure.approval.manager import ApprovalManager

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()
    trace_service = TraceService(execution_store=store)

    agent_manager = AsyncMock()
    agent_manager.get_agent = AsyncMock(return_value=DummyAgentInfo())
    runtime = KernelRuntime(
        agent_manager=agent_manager,
        execution_store=store,
        trace_service=trace_service,
        approval_manager=ApprovalManager(execution_store=store),
    )

    model = CaptureModel()
    agent = PromptingAgent(model)
    import core.apps.agents as agents_mod

    monkeypatch.setattr(agents_mod, "get_agent_registry", lambda: {"a1": agent})
    perm_mgr = get_permission_manager()
    perm_mgr.grant_permission("u1", "a1", Permission.EXECUTE)

    harness = HarnessIntegration.initialize(HarnessConfig(enable_observability=False, enable_feedback_loops=False))
    harness.attach_runtime(runtime)

    res = await harness.execute(
        ExecutionRequest(
            kind="agent",
            target_id="a1",
            user_id="u1",
            session_id="s1",
            payload={"messages": [{"role": "user", "content": "hi"}], "session_id": "s1", "context": {}},
        )
    )
    assert res.ok is True

    assert isinstance(model.last_messages, list)
    content = model.last_messages[0]["content"]
    assert content.startswith("PRE\n")
    assert content.endswith("\nPOST")

