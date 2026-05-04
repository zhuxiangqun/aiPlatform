from __future__ import annotations


def test_context_engine_injects_claude_md(tmp_path):
    # Arrange
    (tmp_path / "CLAUDE.md").write_text("# Rules\n\n- do X\n", encoding="utf-8")

    from core.harness.context.engine import DefaultContextEngine

    eng = DefaultContextEngine()
    msgs = [{"role": "user", "content": "hi"}]

    # Act
    res = eng.apply(messages=msgs, metadata={}, repo_root=str(tmp_path))

    # Assert: injected as first system message
    assert res.messages[0]["role"] == "system"
    assert "# Project Guidelines (CLAUDE.md)" in str(res.messages[0].get("content", ""))
    assert "CLAUDE.md" in str(res.metadata.get("claude_md_file") or "")
    assert isinstance(res.status.get("claude_md"), dict)
    assert res.status["claude_md"].get("injected") is True


def test_contract_hook_denies_when_claude_md_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_ENFORCE_CLAUDE_MD", "true")

    import asyncio

    from core.harness.infrastructure.hooks.hook_manager import HookContext, HookManager, HookPhase
    from core.harness.kernel.execution_context import ActiveWorkspaceContext, reset_active_workspace_context, set_active_workspace_context

    token = set_active_workspace_context(ActiveWorkspaceContext(repo_root=str(tmp_path)))
    try:
        hm = HookManager()
        results = asyncio.run(
            hm.trigger(
                HookPhase.PRE_CONTRACT_CHECK,
                HookContext(phase=HookPhase.PRE_CONTRACT_CHECK, state={"config": {}, "state": {}}),
            )
        )
    finally:
        reset_active_workspace_context(token)

    deny = None
    for r in results:
        if isinstance(r, dict) and r.get("allow") is False:
            deny = r
            break
    assert deny is not None
    assert "CLAUDE.md" in str(deny.get("reason") or "")


def test_contract_hook_allows_when_claude_md_present(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_ENFORCE_CLAUDE_MD", "true")
    (tmp_path / "CLAUDE.md").write_text("ok", encoding="utf-8")

    import asyncio

    from core.harness.infrastructure.hooks.hook_manager import HookContext, HookManager, HookPhase
    from core.harness.kernel.execution_context import ActiveWorkspaceContext, reset_active_workspace_context, set_active_workspace_context

    token = set_active_workspace_context(ActiveWorkspaceContext(repo_root=str(tmp_path)))
    try:
        hm = HookManager()
        results = asyncio.run(
            hm.trigger(
                HookPhase.PRE_CONTRACT_CHECK,
                HookContext(phase=HookPhase.PRE_CONTRACT_CHECK, state={"config": {}, "state": {}}),
            )
        )
    finally:
        reset_active_workspace_context(token)

    assert not any(isinstance(r, dict) and r.get("allow") is False for r in results)


def test_pre_approval_hook_selects_nearest_repo_root(monkeypatch, tmp_path):
    """
    When a tool args contains file paths under different repos, the hook should
    set active_workspace_context.claude_md_files so prompt injection can include
    both guidelines.
    """
    monkeypatch.setenv("AIPLAT_ENFORCE_CLAUDE_MD", "true")

    # Create two repos under a workspace
    ws = tmp_path
    core = ws / "aiPlat-core"
    mgmt = ws / "aiPlat-management"
    core.mkdir()
    mgmt.mkdir()
    (core / "CLAUDE.md").write_text("core rules", encoding="utf-8")
    (mgmt / "CLAUDE.md").write_text("mgmt rules", encoding="utf-8")
    f1 = core / "x.py"
    f2 = mgmt / "y.ts"
    f1.write_text("print('x')", encoding="utf-8")
    f2.write_text("export {}", encoding="utf-8")

    import asyncio

    from core.harness.infrastructure.hooks.hook_manager import HookContext, HookManager, HookPhase
    from core.harness.kernel.execution_context import ActiveWorkspaceContext, get_active_workspace_context, reset_active_workspace_context, set_active_workspace_context

    token = set_active_workspace_context(ActiveWorkspaceContext(repo_root=str(ws)))
    try:
        hm = HookManager()
        loop = asyncio.new_event_loop()
        try:
            async def _run():
                results = await hm.trigger(
                    HookPhase.PRE_APPROVAL_CHECK,
                    HookContext(
                        phase=HookPhase.PRE_APPROVAL_CHECK,
                        state={"tool_name": "edit", "tool_args": {"file_paths": [str(f1), str(f2)]}, "context": {}},
                    ),
                )
                wctx = get_active_workspace_context()
                files = list(getattr(wctx, "claude_md_files", None) or []) if wctx else []
                return results, files

            results, files = loop.run_until_complete(_run())
        finally:
            loop.close()
        assert not any(isinstance(r, dict) and r.get("allow") is False for r in results)
        # both should be included
        assert any(p.endswith("aiPlat-core/CLAUDE.md") for p in files)
        assert any(p.endswith("aiPlat-management/CLAUDE.md") for p in files)
    finally:
        reset_active_workspace_context(token)
