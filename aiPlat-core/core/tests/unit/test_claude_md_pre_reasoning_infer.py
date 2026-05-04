from __future__ import annotations


def test_pre_reasoning_infers_repo_from_messages(tmp_path, monkeypatch):
    # Arrange: multi-repo workspace
    ws = tmp_path
    core = ws / "aiPlat-core"
    mgmt = ws / "aiPlat-management"
    core.mkdir()
    mgmt.mkdir()
    (core / "CLAUDE.md").write_text("core rules", encoding="utf-8")
    (mgmt / "CLAUDE.md").write_text("mgmt rules", encoding="utf-8")

    monkeypatch.setenv("AIPLAT_ENFORCE_CLAUDE_MD", "false")  # inference should not depend on enforcement

    import asyncio

    from core.harness.infrastructure.hooks.hook_manager import HookContext, HookManager, HookPhase
    from core.harness.kernel.execution_context import ActiveWorkspaceContext, get_active_workspace_context, reset_active_workspace_context, set_active_workspace_context

    token = set_active_workspace_context(ActiveWorkspaceContext(repo_root=str(ws)))
    try:
        hm = HookManager()

        async def _run():
            await hm.trigger(
                HookPhase.PRE_REASONING,
                HookContext(
                    phase=HookPhase.PRE_REASONING,
                    state={
                        "task": "请同时修改 aiPlat-core/core/server.py 和 aiPlat-management/frontend/src/services/apiClient.ts",
                        "messages": [{"role": "user", "content": "路径：aiPlat-core/core/server.py ; aiPlat-management/frontend/src/services/apiClient.ts"}],
                    },
                ),
            )
            wctx = get_active_workspace_context()
            return list(getattr(wctx, "claude_md_files", None) or []) if wctx else []

        files = asyncio.run(_run())
        assert any(p.endswith("aiPlat-core/CLAUDE.md") for p in files)
        assert any(p.endswith("aiPlat-management/CLAUDE.md") for p in files)
    finally:
        reset_active_workspace_context(token)

