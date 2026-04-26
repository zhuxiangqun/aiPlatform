import os
import subprocess
import pytest


@pytest.mark.asyncio
async def test_repo_tool_attaches_status_snapshot(tmp_path, monkeypatch):
    db_path = tmp_path / "exec.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "skills"))
    monkeypatch.setenv("AIPLAT_SYSCALL_ENFORCE_APPROVAL", "true")

    # create a tiny git repo with one modified file
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True, text=True)
    (repo / "a.txt").write_text("v1\n", encoding="utf-8")
    (repo / "b.txt").write_text("v1\n", encoding="utf-8")
    # keep it uncommitted (no user.name/email required); status should still list the file.

    import core.server as srv
    from fastapi.testclient import TestClient
    from core.harness.syscalls.tool import sys_tool_call
    from core.apps.tools.repo import RepoTool
    from core.harness.kernel.execution_context import (
        set_active_request_context,
        ActiveRequestContext,
        ActiveWorkspaceContext,
        set_active_workspace_context,
        ActiveChangeContract,
        set_active_change_contract,
    )

    with TestClient(srv.app) as client:
        client.get("/api/core/permissions/stats")

        set_active_workspace_context(ActiveWorkspaceContext(repo_root=str(repo)))
        set_active_request_context(ActiveRequestContext(tenant_id="default", actor_id="u1"))
        set_active_change_contract(
            ActiveChangeContract(source_skill="dummy", changed_files=["a.txt"], unrelated_changes=False, updated_at=0.0)
        )

        # repo add is mutating => approval_required; we only verify metadata snapshot in syscall event.
        await sys_tool_call(
            RepoTool(),
            {"operation": "add", "paths": ["b.txt"], "repo_root": str(repo)},
            user_id="u1",
            session_id="s1",
            trace_context={"tenant_id": "default", "run_id": "r1", "routing_decision_id": "rtd_x", "coding_policy_profile": "karpathy_v1"},
        )

        ev = await srv._execution_store.list_syscall_events(limit=50, offset=0, tenant_id=None, kind="tool", name="repo")
        items = ev.get("items") or []
        assert items, "expected tool syscall events"
        # find approval_required event
        tgt = next((x for x in items if x.get("status") == "approval_required"), items[0])
        tool_args = ((tgt.get("args") or {}).get("tool_args") or {})
        assert tool_args.get("_coding_policy_profile") == "karpathy_v1"
        assert tool_args.get("_repo_status_count") is not None
        # declared contract should be attached and used to flag mismatch
        assert tool_args.get("_declared_unrelated_changes") is False
        assert tool_args.get("_policy_reason") in ("repo_add_paths_out_of_contract", "changed_files_out_of_contract")
        assert isinstance(tool_args.get("_out_of_contract_files"), list)
