from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from core.api.utils.governance import governance_links
from core.governance.changeset import record_changeset
from core.governance.gating import new_change_id
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas import (
    RepoChangesetPreviewRequest,
    RepoGitBranchRequest,
    RepoGitCommitRequest,
    RepoStagedPreviewRequest,
    RepoTestsRunRequest,
)


router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


def _approval_manager():
    rt = _rt()
    return getattr(rt, "approval_manager", None) if rt else None


def _is_approved(approval_mgr: Any, approval_request_id: str) -> bool:
    if not approval_mgr or not approval_request_id:
        return False
    from core.harness.infrastructure.approval.types import RequestStatus

    req = approval_mgr.get_request(str(approval_request_id))
    return bool(req) and req.status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED)


def _validate_git_repo(repo_root: str) -> None:
    p = Path(repo_root)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail="repo_root_not_found")
    if not (p / ".git").exists():
        raise HTTPException(status_code=400, detail="not_a_git_repo")


def _run_git(repo_root: str, args: list[str], timeout_s: int = 10) -> str:
    cp = subprocess.run(["git", "-C", repo_root, *args], capture_output=True, text=True, timeout=timeout_s)
    if cp.returncode != 0:
        raise RuntimeError((cp.stderr or cp.stdout or "git_failed")[:500])
    return (cp.stdout or "").strip()


def _is_high_risk(paths: list[str]) -> bool:
    # Conservative allowlist: treat core governance/auth/policy changes as high risk.
    for p in paths:
        ps = str(p or "")
        if not ps:
            continue
        if ps.endswith((".pem", ".key")):
            return True
        if "/.github/workflows/" in ps or ps.startswith(".github/workflows/"):
            return True
        if ps.startswith("aiPlat-core/core/server.py"):
            return True
        if "policy" in ps or "rbac" in ps or "permission" in ps:
            return True
        if "ops/" in ps or ps.startswith("aiPlat-management/management/api/"):
            return True
    return False


# ==================== Repo Changeset (repo-aware workflow MVP) ====================


@router.post("/diagnostics/repo/changeset/preview")
async def diagnostics_repo_changeset_preview(request: RepoChangesetPreviewRequest):
    """
    Repo-aware workflow MVP: summarize git working tree changes (no arbitrary commands).
    Returns status + numstat + hashes. Optionally includes full patch (include_patch=true).
    """
    repo_root = str(request.repo_root or "").strip()
    if not repo_root:
        raise HTTPException(status_code=400, detail="repo_root_required")
    _validate_git_repo(repo_root)

    def _run(args: list[str], timeout_s: int = 5) -> str:
        return _run_git(repo_root, args, timeout_s=timeout_s)

    try:
        head = _run(["rev-parse", "HEAD"])
    except Exception:
        head = ""
    try:
        branch = _run(["rev-parse", "--abbrev-ref", "HEAD"])
    except Exception:
        branch = ""

    last_commit: Dict[str, Any] = {}
    try:
        line = _run(["log", "-1", "--pretty=format:%H%x09%an%x09%ad%x09%s"])
        parts = (line or "").split("\t")
        if len(parts) >= 4:
            last_commit = {"sha": parts[0], "author": parts[1], "date": parts[2], "subject": "\t".join(parts[3:])}
    except Exception:
        last_commit = {}

    status = _run(["status", "--porcelain=v1"])
    numstat = _run(["diff", "--numstat"])
    staged_numstat = _run(["diff", "--cached", "--numstat"])

    patch = ""
    if bool(request.include_patch):
        patch = _run(["diff"], timeout_s=10)

    diff_hash = hashlib.sha256((patch or numstat or "").encode("utf-8")).hexdigest()

    def _summarize(ns: str) -> Dict[str, Any]:
        files = 0
        added = 0
        deleted = 0
        for line in (ns or "").splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            files += 1
            a, d = parts[0], parts[1]
            try:
                if a.isdigit():
                    added += int(a)
            except Exception:
                pass
            try:
                if d.isdigit():
                    deleted += int(d)
            except Exception:
                pass
        return {"files_changed": files, "lines_added": added, "lines_deleted": deleted}

    out: Dict[str, Any] = {
        "repo_root": repo_root,
        "branch": branch,
        "head": head,
        "last_commit": last_commit,
        "status_lines": len(status.splitlines()) if status else 0,
        "working_tree": _summarize(numstat),
        "staged": _summarize(staged_numstat),
        "diff_sha256": diff_hash,
    }
    if bool(request.include_patch):
        out["patch"] = patch
        out["patch_len"] = len(patch)
    return out


@router.post("/diagnostics/repo/tests/run")
async def diagnostics_repo_tests_run(request: RepoTestsRunRequest):
    """
    Repo-aware workflow MVP: run repo tests with an allowlisted command.
    Security: command is controlled by env AIPLAT_REPO_TEST_CMD, not user input.
    """
    store = _store()
    repo_root = str(request.repo_root or "").strip()
    if not repo_root:
        raise HTTPException(status_code=400, detail="repo_root_required")
    _validate_git_repo(repo_root)

    cmd = str(os.getenv("AIPLAT_REPO_TEST_CMD", "")).strip()
    if not cmd:
        raise HTTPException(status_code=400, detail="AIPLAT_REPO_TEST_CMD_not_set")

    import shlex

    args = shlex.split(cmd)
    t0 = time.time()
    try:
        cp = subprocess.run(args, cwd=repo_root, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - t0) * 1000)
        if store:
            await record_changeset(
                store=store,
                name="repo_tests_run",
                target_type="repo",
                target_id=repo_root,
                status="failed",
                args={"cmd": cmd, "note": str(request.note or "").strip()},
                error="timeout",
                result={"duration_ms": duration_ms},
                user_id="admin",
            )
        raise HTTPException(status_code=408, detail="tests_timeout")
    duration_ms = int((time.time() - t0) * 1000)

    def _tail(s: str, n: int = 8000) -> str:
        s = s or ""
        return s[-n:] if len(s) > n else s

    stdout_tail = _tail(cp.stdout or "")
    stderr_tail = _tail(cp.stderr or "")
    out = {
        "cmd": cmd,
        "exit_code": int(cp.returncode),
        "duration_ms": duration_ms,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "stdout_sha256": hashlib.sha256(stdout_tail.encode("utf-8")).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr_tail.encode("utf-8")).hexdigest(),
    }
    if store:
        await record_changeset(
            store=store,
            name="repo_tests_run",
            target_type="repo",
            target_id=repo_root,
            status="success" if cp.returncode == 0 else "failed",
            args={"cmd": cmd, "note": str(request.note or "").strip()},
            error=None if cp.returncode == 0 else f"exit_code:{cp.returncode}",
            result={
                "exit_code": int(cp.returncode),
                "duration_ms": duration_ms,
                "stdout_sha256": out["stdout_sha256"],
                "stderr_sha256": out["stderr_sha256"],
                "stdout_tail_len": len(stdout_tail),
                "stderr_tail_len": len(stderr_tail),
            },
            user_id="admin",
        )
    return {"status": "ok", "result": out}


@router.post("/diagnostics/repo/staged/preview")
async def diagnostics_repo_staged_preview(request: RepoStagedPreviewRequest):
    """Preview staged changes and suggest a deterministic commit message."""
    repo_root = str(request.repo_root or "").strip()
    if not repo_root:
        raise HTTPException(status_code=400, detail="repo_root_required")
    _validate_git_repo(repo_root)

    staged_numstat = _run_git(repo_root, ["diff", "--cached", "--numstat"], timeout_s=10)
    staged_files: list[str] = []
    adds = 0
    dels = 0
    for line in (staged_numstat or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, d, path = parts[0], parts[1], parts[2]
        staged_files.append(path)
        if a.isdigit():
            adds += int(a)
        if d.isdigit():
            dels += int(d)

    patch = ""
    if bool(request.include_patch):
        patch = _run_git(repo_root, ["diff", "--cached"], timeout_s=10)
    patch_sha = hashlib.sha256((patch or staged_numstat or "").encode("utf-8")).hexdigest()

    scope = "repo"
    if any(f.startswith("aiPlat-core/") for f in staged_files):
        scope = "core"
    elif any(f.startswith("aiPlat-management/") for f in staged_files):
        scope = "management"
    elif any(f.startswith("docs/") or f.endswith(".md") for f in staged_files):
        scope = "docs"

    if len(staged_files) == 1:
        subject = f"update {staged_files[0].split('/')[-1]}"
    elif len(staged_files) > 1:
        subject = f"update {len(staged_files)} files"
    else:
        subject = "no staged changes"
    suggested = f"chore({scope}): {subject}"

    out: Dict[str, Any] = {
        "repo_root": repo_root,
        "staged": {"files_changed": len(staged_files), "lines_added": adds, "lines_deleted": dels},
        "staged_files": staged_files,
        "patch_sha256": patch_sha,
        "suggested_commit_message": suggested,
    }
    if bool(request.include_patch):
        out["patch"] = patch
        out["patch_len"] = len(patch)
    return out


@router.post("/diagnostics/repo/changeset/record")
async def diagnostics_repo_changeset_record(request: RepoChangesetPreviewRequest):
    """
    Record the repo changeset summary as a first-class change (changeset syscall),
    so it can be reviewed in Change Control.
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    preview = await diagnostics_repo_changeset_preview(request)
    staged_preview: dict | None = None
    try:
        staged_preview = await diagnostics_repo_staged_preview(RepoStagedPreviewRequest(repo_root=request.repo_root, include_patch=False))
    except Exception:
        staged_preview = None

    tests_summary = None
    try:
        if bool(getattr(request, "run_tests", False)):
            tr = await diagnostics_repo_tests_run(RepoTestsRunRequest(repo_root=request.repo_root, note=request.note))
            tests_summary = (tr or {}).get("result") if isinstance(tr, dict) else None
    except Exception as e:
        try:
            await record_changeset(
                store=store,
                name="repo_changeset_record",
                target_type="repo",
                target_id=str(preview.get("repo_root") or ""),
                status="failed",
                args={"branch": preview.get("branch"), "head": preview.get("head"), "note": str(request.note or "").strip()},
                error=f"tests_exception:{type(e).__name__}",
                result={
                    "diff_sha256": preview.get("diff_sha256"),
                    "staged_patch_sha256": (staged_preview or {}).get("patch_sha256") if isinstance(staged_preview, dict) else None,
                    "staged_files_count": len((staged_preview or {}).get("staged_files") or []) if isinstance(staged_preview, dict) else 0,
                    "staged_files_sample": ((staged_preview or {}).get("staged_files") or [])[:20] if isinstance(staged_preview, dict) else [],
                    "tests": {"error": str(e)[:200]},
                },
                user_id="admin",
            )
        except Exception:
            pass
        raise

    # ==================== governance: approval when high-risk / non-local ====================
    from core.apps.exec_drivers.registry import get_exec_backend
    from core.harness.infrastructure.approval.manager import ApprovalManager
    from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

    approval_mgr = _approval_manager() or ApprovalManager(execution_store=store)
    backend = "local"
    try:
        backend = await get_exec_backend()
    except Exception:
        backend = "local"

    staged_files = (staged_preview or {}).get("staged_files") if isinstance(staged_preview, dict) else []
    if not isinstance(staged_files, list):
        staged_files = []

    require_approval = bool(getattr(request, "require_approval", True))
    approval_needed = bool(require_approval) and (str(backend) != "local" or _is_high_risk([str(x) for x in staged_files]))
    approval_request_id = str(getattr(request, "approval_request_id", "") or "").strip() or None
    user_id = str(getattr(request, "user_id", "") or "").strip() or "admin"

    change_id = new_change_id()
    if approval_needed:
        if not _approval_manager():
            raise HTTPException(status_code=503, detail="Approval manager not available")
        if approval_request_id and _is_approved(approval_mgr, approval_request_id):
            pass
        else:
            if not approval_request_id:
                rule = ApprovalRule(
                    rule_id="repo_changeset_record",
                    rule_type=RuleType.SENSITIVE_OPERATION,
                    name="Repo changeset 记录审批",
                    description="repo changeset（非本地执行或高风险变更）需要审批后才能进入后续流程",
                    priority=1,
                    metadata={"sensitive_operations": ["repo:changeset_record"]},
                )
                _approval_manager().register_rule(rule)  # type: ignore[union-attr]
                ctx = ApprovalContext(
                    user_id=user_id,
                    operation="repo:changeset_record",
                    operation_context={
                        "repo_root": str(preview.get("repo_root") or ""),
                        "branch": preview.get("branch"),
                        "head": preview.get("head"),
                        "backend": str(backend),
                        "diff_sha256": preview.get("diff_sha256"),
                        "staged_files": staged_files[:50],
                        "details": str(request.note or "").strip(),
                    },
                    metadata={"kind": "repo_changeset", "change_id": str(change_id)},
                )
                req = _approval_manager().create_request(ctx, rule=rule)  # type: ignore[union-attr]
                approval_request_id = req.request_id
                try:
                    await _approval_manager()._persist(req)  # type: ignore[union-attr]
                except Exception:
                    pass

            try:
                await record_changeset(
                    store=store,
                    name="repo_changeset_record",
                    target_type="change",
                    target_id=str(change_id),
                    status="approval_required",
                    args={
                        "operation": "repo_changeset_record",
                        "repo_root": str(preview.get("repo_root") or ""),
                        "branch": preview.get("branch"),
                        "head": preview.get("head"),
                        "backend": str(backend),
                        "note": str(request.note or "").strip(),
                    },
                    result={
                        "working_tree": preview.get("working_tree"),
                        "staged": preview.get("staged"),
                        "diff_sha256": preview.get("diff_sha256"),
                        "staged_patch_sha256": (staged_preview or {}).get("patch_sha256") if isinstance(staged_preview, dict) else None,
                        "staged_files_count": len(staged_files),
                        "staged_files_sample": staged_files[:20],
                        "suggested_commit_message": (staged_preview or {}).get("suggested_commit_message") if isinstance(staged_preview, dict) else None,
                        "patch_available": True,
                        "tests": {
                            "exit_code": (tests_summary or {}).get("exit_code") if isinstance(tests_summary, dict) else None,
                            "duration_ms": (tests_summary or {}).get("duration_ms") if isinstance(tests_summary, dict) else None,
                            "stdout_sha256": (tests_summary or {}).get("stdout_sha256") if isinstance(tests_summary, dict) else None,
                            "stderr_sha256": (tests_summary or {}).get("stderr_sha256") if isinstance(tests_summary, dict) else None,
                        },
                    },
                    approval_request_id=str(approval_request_id) if approval_request_id else None,
                    user_id=user_id,
                )
            except Exception:
                pass
            return {
                "status": "approval_required",
                "approval_request_id": approval_request_id,
                "change_id": change_id,
                "links": governance_links(change_id=change_id, approval_request_id=str(approval_request_id) if approval_request_id else None),
                "preview": preview,
                "tests": tests_summary,
                "staged": staged_preview,
                "backend": backend,
            }

    try:
        await record_changeset(
            store=store,
            name="repo_changeset_record",
            target_type="change",
            target_id=str(change_id),
            args={
                "operation": "repo_changeset_record",
                "repo_root": str(preview.get("repo_root") or ""),
                "branch": preview.get("branch"),
                "head": preview.get("head"),
                "note": str(request.note or "").strip(),
            },
            result={
                "working_tree": preview.get("working_tree"),
                "staged": preview.get("staged"),
                "diff_sha256": preview.get("diff_sha256"),
                "staged_patch_sha256": (staged_preview or {}).get("patch_sha256") if isinstance(staged_preview, dict) else None,
                "staged_files_count": len((staged_preview or {}).get("staged_files") or []) if isinstance(staged_preview, dict) else 0,
                "staged_files_sample": ((staged_preview or {}).get("staged_files") or [])[:20] if isinstance(staged_preview, dict) else [],
                "suggested_commit_message": (staged_preview or {}).get("suggested_commit_message") if isinstance(staged_preview, dict) else None,
                "patch_available": True,
                "tests": {
                    "exit_code": (tests_summary or {}).get("exit_code") if isinstance(tests_summary, dict) else None,
                    "duration_ms": (tests_summary or {}).get("duration_ms") if isinstance(tests_summary, dict) else None,
                    "stdout_sha256": (tests_summary or {}).get("stdout_sha256") if isinstance(tests_summary, dict) else None,
                    "stderr_sha256": (tests_summary or {}).get("stderr_sha256") if isinstance(tests_summary, dict) else None,
                },
            },
            approval_request_id=str(approval_request_id) if approval_request_id else None,
            user_id=user_id,
        )
    except Exception:
        pass
    return {
        "status": "recorded",
        "change_id": change_id,
        "approval_request_id": approval_request_id,
        "links": governance_links(change_id=change_id, approval_request_id=str(approval_request_id) if approval_request_id else None),
        "preview": preview,
        "tests": tests_summary,
        "staged": staged_preview,
        "backend": backend,
    }


@router.post("/diagnostics/repo/git/branch")
async def diagnostics_repo_git_branch(request: RepoGitBranchRequest):
    """Create/switch branch (git)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    repo_root = str(request.repo_root or "").strip()
    if not repo_root:
        raise HTTPException(status_code=400, detail="repo_root_required")
    branch = str(request.branch or "").strip()
    if not branch:
        raise HTTPException(status_code=400, detail="branch_required")
    _validate_git_repo(repo_root)

    from core.apps.exec_drivers.registry import get_exec_backend
    from core.harness.infrastructure.approval.manager import ApprovalManager
    from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

    backend = "local"
    try:
        backend = await get_exec_backend()
    except Exception:
        backend = "local"

    require_approval = bool(getattr(request, "require_approval", True))
    approval_request_id = str(getattr(request, "approval_request_id", "") or "").strip() or None
    user_id = str(getattr(request, "user_id", "") or "").strip() or "admin"
    change_id = str(getattr(request, "change_id", "") or "").strip() or new_change_id()
    details = str(getattr(request, "details", "") or "").strip()

    approval_needed = bool(require_approval) and (str(backend) != "local")
    if approval_needed:
        approval_mgr = _approval_manager() or ApprovalManager(execution_store=store)
        if not _approval_manager():
            raise HTTPException(status_code=503, detail="Approval manager not available")
        if not approval_request_id:
            rule = ApprovalRule(
                rule_id="repo_git_branch",
                rule_type=RuleType.SENSITIVE_OPERATION,
                name="Repo git branch 操作审批",
                description="非本地执行 backend 时进行 git branch 操作需要审批",
                priority=1,
                metadata={"sensitive_operations": ["repo:git_branch"]},
            )
            _approval_manager().register_rule(rule)  # type: ignore[union-attr]
            ctx = ApprovalContext(
                user_id=user_id,
                operation="repo:git_branch",
                operation_context={
                    "repo_root": repo_root,
                    "branch": branch,
                    "base": str(getattr(request, "base", "") or "").strip() or None,
                    "checkout": bool(getattr(request, "checkout", True)),
                    "backend": str(backend),
                    "details": details,
                },
                metadata={"kind": "repo_git", "change_id": str(change_id)},
            )
            req = _approval_manager().create_request(ctx, rule=rule)  # type: ignore[union-attr]
            approval_request_id = req.request_id
            try:
                await _approval_manager()._persist(req)  # type: ignore[union-attr]
            except Exception:
                pass
        if approval_request_id and not _is_approved(approval_mgr, approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="repo_git_branch",
                    target_type="change",
                    target_id=str(change_id),
                    status="approval_required",
                    args={
                        "operation": "repo_git_branch",
                        "repo_root": repo_root,
                        "branch": branch,
                        "base": str(getattr(request, "base", "") or "").strip() or None,
                        "checkout": bool(getattr(request, "checkout", True)),
                        "backend": str(backend),
                        "details": details,
                    },
                    approval_request_id=str(approval_request_id),
                    user_id=user_id,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": approval_request_id, "change_id": change_id, "links": governance_links(change_id=change_id, approval_request_id=str(approval_request_id)), "backend": backend}

    base = str(getattr(request, "base", "") or "").strip() or None
    checkout = bool(getattr(request, "checkout", True))
    try:
        if base:
            _run_git(repo_root, ["checkout", "-b", branch, base], timeout_s=20)
        else:
            _run_git(repo_root, ["checkout", "-b", branch], timeout_s=20)
    except Exception:
        if checkout:
            _run_git(repo_root, ["checkout", branch], timeout_s=20)
        else:
            raise

    head = _run_git(repo_root, ["rev-parse", "HEAD"], timeout_s=10).strip()
    cur_branch = _run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"], timeout_s=10).strip()
    try:
        await record_changeset(
            store=store,
            name="repo_git_branch",
            target_type="change",
            target_id=str(change_id),
            status="success",
            args={"operation": "repo_git_branch", "repo_root": repo_root, "branch": branch, "base": base, "checkout": checkout, "backend": str(backend)},
            result={"current_branch": cur_branch, "head": head},
            approval_request_id=str(approval_request_id) if approval_request_id else None,
            user_id=user_id,
        )
    except Exception:
        pass

    # Keep backward-compatible response fields with the legacy server.py implementation.
    return {
        "status": "ok",
        "change_id": change_id,
        "approval_request_id": approval_request_id,
        "links": governance_links(change_id=change_id, approval_request_id=str(approval_request_id) if approval_request_id else None),
        "backend": backend,
        "commit_sha": head,
        "branch": cur_branch,
        "current_branch": cur_branch,
        "head": head,
    }


@router.post("/diagnostics/repo/git/commit")
async def diagnostics_repo_git_commit(request: RepoGitCommitRequest):
    """Commit staged changes with commit message (with governance checks)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    repo_root = str(request.repo_root or "").strip()
    if not repo_root:
        raise HTTPException(status_code=400, detail="repo_root_required")
    msg = str(request.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="commit_message_required")
    _validate_git_repo(repo_root)

    from core.apps.exec_drivers.registry import get_exec_backend
    from core.harness.infrastructure.approval.manager import ApprovalManager
    from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

    backend = "local"
    try:
        backend = await get_exec_backend()
    except Exception:
        backend = "local"

    staged_numstat = _run_git(repo_root, ["diff", "--cached", "--numstat"], timeout_s=10)
    staged_files: list[str] = []
    for line in (staged_numstat or "").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            staged_files.append(parts[2])

    require_approval = bool(getattr(request, "require_approval", True))
    approval_request_id = str(getattr(request, "approval_request_id", "") or "").strip() or None
    user_id = str(getattr(request, "user_id", "") or "").strip() or "admin"
    change_id = str(getattr(request, "change_id", "") or "").strip() or new_change_id()
    details = str(getattr(request, "details", "") or "").strip()

    approval_needed = bool(require_approval) and (str(backend) != "local" or _is_high_risk(staged_files))
    if approval_needed:
        approval_mgr = _approval_manager() or ApprovalManager(execution_store=store)
        if not _approval_manager():
            raise HTTPException(status_code=503, detail="Approval manager not available")
        if not approval_request_id:
            rule = ApprovalRule(
                rule_id="repo_git_commit",
                rule_type=RuleType.SENSITIVE_OPERATION,
                name="Repo git commit 操作审批",
                description="高风险变更或非本地 backend 时进行 git commit 需要审批",
                priority=1,
                metadata={"sensitive_operations": ["repo:git_commit"]},
            )
            _approval_manager().register_rule(rule)  # type: ignore[union-attr]
            ctx = ApprovalContext(
                user_id=user_id,
                operation="repo:git_commit",
                operation_context={"repo_root": repo_root, "message": msg[:200], "backend": str(backend), "staged_files": staged_files[:50], "details": details},
                metadata={"kind": "repo_git", "change_id": str(change_id)},
            )
            req = _approval_manager().create_request(ctx, rule=rule)  # type: ignore[union-attr]
            approval_request_id = req.request_id
            try:
                await _approval_manager()._persist(req)  # type: ignore[union-attr]
            except Exception:
                pass
        if approval_request_id and not _is_approved(approval_mgr, approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="repo_git_commit",
                    target_type="change",
                    target_id=str(change_id),
                    status="approval_required",
                    args={"operation": "repo_git_commit", "repo_root": repo_root, "backend": str(backend), "details": details, "staged_files_sample": staged_files[:20]},
                    approval_request_id=str(approval_request_id),
                    user_id=user_id,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": approval_request_id, "change_id": change_id, "links": governance_links(change_id=change_id, approval_request_id=str(approval_request_id)), "backend": backend}

    # Execute commit
    _run_git(repo_root, ["commit", "-m", msg], timeout_s=30)
    head = _run_git(repo_root, ["rev-parse", "HEAD"], timeout_s=10).strip()
    cur_branch = _run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"], timeout_s=10).strip()
    try:
        await record_changeset(
            store=store,
            name="repo_git_commit",
            target_type="change",
            target_id=str(change_id),
            status="success",
            args={"operation": "repo_git_commit", "repo_root": repo_root, "backend": str(backend), "message": msg[:200], "staged_files_count": len(staged_files)},
            result={"current_branch": cur_branch, "head": head},
            approval_request_id=str(approval_request_id) if approval_request_id else None,
            user_id=user_id,
        )
    except Exception:
        pass
    # Keep backward-compatible response fields with the legacy server.py implementation.
    return {
        "status": "ok",
        "change_id": change_id,
        "approval_request_id": approval_request_id,
        "links": governance_links(change_id=change_id, approval_request_id=str(approval_request_id) if approval_request_id else None),
        "backend": backend,
        "commit_sha": head,
        "branch": cur_branch,
        "current_branch": cur_branch,
        "head": head,
    }
