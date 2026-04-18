import os

import pytest


@pytest.mark.integration
def test_prompt_assembler_stable_vs_ephemeral_and_cache(tmp_path, monkeypatch):
    """
    Roadmap R1-1:
    - PromptAssembler splits stable_system_prompt vs ephemeral_overlay
    - stable cache key exists and can hit on repeated assembly

    Roadmap R4-2:
    - Session search injection contributes to ephemeral overlay (layer=ephemeral)
    """

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
    # init tables
    import anyio

    anyio.run(store.init)

    runtime = KernelRuntime(execution_store=store)
    set_kernel_runtime(runtime)

    # Seed session memory for cross-session search
    async def _seed():
        await store.add_memory_message(
            session_id="sess-old",
            user_id="u1",
            role="user",
            content="I like kittens very much",
            metadata={"note": "seed"},
        )

    anyio.run(_seed)

    monkeypatch.setenv("AIPLAT_ENABLE_SESSION_SEARCH", "true")

    w_token = set_active_workspace_context(ActiveWorkspaceContext(repo_root=str(repo_root)))
    r_token = set_active_request_context(ActiveRequestContext(user_id="u1", session_id="sess-new"))
    try:
        prompt = [{"role": "system", "content": "SYSTEM BASE"}, {"role": "user", "content": "kittens"}]
        assembled1 = PromptAssembler().assemble(prompt, metadata={"target_type": "agent", "target_id": "a1"})

        assert "# Project Context" in assembled1.stable_system_prompt
        assert "PROJECT RULES" in assembled1.stable_system_prompt
        assert "SYSTEM BASE" in assembled1.stable_system_prompt

        # Session search must be injected and classified as ephemeral
        assert "# Session Search" in assembled1.ephemeral_overlay
        assert assembled1.metadata.get("session_search_hits", 0) >= 1
        assert assembled1.stable_cache_key
        assert assembled1.metadata.get("stable_cache_hit") is False

        assembled2 = PromptAssembler().assemble(prompt, metadata={"target_type": "agent", "target_id": "a1"})
        assert assembled2.stable_cache_key == assembled1.stable_cache_key
        assert assembled2.metadata.get("stable_cache_hit") is True

    finally:
        reset_active_workspace_context(w_token)
        reset_active_request_context(r_token)
        os.environ.pop("AIPLAT_ENABLE_SESSION_SEARCH", None)
