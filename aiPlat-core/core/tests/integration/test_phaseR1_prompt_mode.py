import os

import pytest


@pytest.mark.integration
def test_prompt_mode_minimal_skips_ephemeral_injection(tmp_path, monkeypatch):
    db_path = tmp_path / "executions.sqlite3"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "AGENTS.md").write_text("PROJECT RULES", encoding="utf-8")

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.harness.integration import KernelRuntime
    from core.harness.kernel.runtime import set_kernel_runtime
    from core.harness.kernel.execution_context import (
        ActiveRequestContext,
        ActiveWorkspaceContext,
        set_active_request_context,
        set_active_workspace_context,
        reset_active_request_context,
        reset_active_workspace_context,
    )
    from core.harness.assembly import PromptAssembler

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    import anyio

    anyio.run(store.init)
    runtime = KernelRuntime(execution_store=store)
    set_kernel_runtime(runtime)

    # Seed session memory (would be injected if full mode)
    async def _seed():
        await store.add_memory_message(session_id="sess-old", user_id="u1", role="user", content="I like kittens", metadata={})

    anyio.run(_seed)

    monkeypatch.setenv("AIPLAT_ENABLE_SESSION_SEARCH", "true")

    w_token = set_active_workspace_context(ActiveWorkspaceContext(repo_root=str(repo_root)))
    r_token = set_active_request_context(ActiveRequestContext(user_id="u1", session_id="sess-new", entrypoint="subagent"))
    try:
        prompt = [{"role": "system", "content": "SYSTEM BASE"}, {"role": "user", "content": "kittens"}]
        assembled = PromptAssembler().assemble(prompt, metadata={"target_type": "agent", "target_id": "a1"})
        # Minimal mode should keep stable project context but skip session search overlay
        assert "# Project Context" in assembled.stable_system_prompt
        assert "PROJECT RULES" in assembled.stable_system_prompt
        assert "# Session Search" not in assembled.ephemeral_overlay
        assert assembled.metadata.get("prompt_mode") == "minimal"
        cs = assembled.metadata.get("context_status") or {}
        assert cs.get("prompt_mode") == "minimal"
    finally:
        reset_active_workspace_context(w_token)
        reset_active_request_context(r_token)
        os.environ.pop("AIPLAT_ENABLE_SESSION_SEARCH", None)


@pytest.mark.integration
def test_prompt_mode_none_disables_all_context_injection(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "AGENTS.md").write_text("PROJECT RULES", encoding="utf-8")

    from core.harness.kernel.execution_context import ActiveWorkspaceContext, set_active_workspace_context, reset_active_workspace_context
    from core.harness.assembly import PromptAssembler

    w_token = set_active_workspace_context(ActiveWorkspaceContext(repo_root=str(repo_root)))
    try:
        prompt = [{"role": "user", "content": "hi"}]
        assembled = PromptAssembler().assemble(prompt, metadata={"prompt_mode": "none", "target_type": "agent", "target_id": "a1"})
        assert "# Project Context" not in assembled.stable_system_prompt
        cs = assembled.metadata.get("context_status") or {}
        assert cs.get("prompt_mode") == "none"
    finally:
        reset_active_workspace_context(w_token)

