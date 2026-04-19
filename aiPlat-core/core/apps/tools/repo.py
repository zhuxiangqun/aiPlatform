"""
Repo Tool (P0: repo-aware developer workflow)

Provides a *safe-ish* git-oriented tool abstraction for repo-aware agents:
- status / diff / log / ls-files
- (mutating) add / checkout / commit / branch-create

Notes:
- Avoids shell=True to reduce injection risks.
- Operates inside an explicit repo_root (ActiveWorkspaceContext.repo_root) when provided.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.harness.interfaces import ToolConfig, ToolResult

from .base import BaseTool


@dataclass
class _GitResult:
    code: int
    out: str
    err: str


def _safe_repo_root(repo_root: Optional[str]) -> Path:
    """
    Resolve repo_root to an on-disk directory.
    - If None: use current working directory.
    - If relative: treat as relative to current working directory.
    - If absolute: accept.
    """
    base = Path.cwd()
    if not repo_root:
        return base
    p = Path(repo_root)
    if not p.is_absolute():
        p = (base / p)
    return p.resolve()


def _run_git(args: List[str], *, cwd: Path, env: Optional[Dict[str, str]] = None, timeout: float = 20.0) -> _GitResult:
    e = os.environ.copy()
    if env:
        e.update({k: str(v) for k, v in env.items()})
    # keep output bounded (best-effort)
    p = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=e,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    return _GitResult(code=int(p.returncode), out=out, err=err)


class RepoTool(BaseTool):
    def __init__(self, timeout: int = 20000):
        config = ToolConfig(
            name="repo",
            description="Repo-aware git workflow tool: status/diff/log/ls-files/add/checkout/commit",
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "description": "git operation: status|diff|log|ls_files|show|add|checkout|commit|branch_list|branch_create",
                    },
                    "repo_root": {"type": "string", "description": "repo root path (defaults to ActiveWorkspaceContext.repo_root or cwd)"},
                    "staged": {"type": "boolean", "description": "diff staged changes"},
                    "paths": {"type": "array", "items": {"type": "string"}, "description": "optional file paths"},
                    "n": {"type": "integer", "description": "log max entries"},
                    "rev": {"type": "string", "description": "revision for show (default HEAD)"},
                    "path": {"type": "string", "description": "single file path for show"},
                    "branch": {"type": "string", "description": "branch name"},
                    "from_ref": {"type": "string", "description": "branch create base ref (default HEAD)"},
                    "message": {"type": "string", "description": "commit message"},
                },
                "required": ["operation"],
            },
            metadata={
                # best-effort risk metadata used by approval/policy
                "risk_level": "medium",
                "risk_weight": 2,
            },
        )
        super().__init__(config)
        self._timeout_s = max(1.0, float(timeout) / 1000.0)

    def check_available(self) -> tuple[bool, Optional[str]]:
        if shutil.which("git") is None:
            return False, "git_not_found"
        return True, None

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        async def handler() -> ToolResult:
            op = str(params.get("operation") or "").strip()
            if not op:
                return ToolResult(success=False, error="missing operation")

            # Resolve repo root from params or ActiveWorkspaceContext
            repo_root = params.get("repo_root")
            if not repo_root:
                try:
                    from core.harness.kernel.execution_context import get_active_workspace_context

                    ws = get_active_workspace_context()
                    repo_root = getattr(ws, "repo_root", None) if ws else None
                except Exception:
                    repo_root = None

            cwd = _safe_repo_root(repo_root)
            if not cwd.exists() or not cwd.is_dir():
                return ToolResult(success=False, error=f"repo_root not found: {cwd}")

            # quick sanity: must be inside a git repo for most ops
            if op not in {"ls_files"}:
                res0 = await asyncio.to_thread(_run_git, ["rev-parse", "--is-inside-work-tree"], cwd=cwd, timeout=self._timeout_s)
                if res0.code != 0 or "true" not in (res0.out or ""):
                    return ToolResult(success=False, error=f"not a git repo: {cwd}")

            paths = params.get("paths") if isinstance(params.get("paths"), list) else None
            staged = bool(params.get("staged")) if params.get("staged") is not None else False
            n = int(params.get("n") or 20)

            if op == "status":
                r = await asyncio.to_thread(_run_git, ["status", "--porcelain=v1", "-b"], cwd=cwd, timeout=self._timeout_s)
                if r.code != 0:
                    return ToolResult(success=False, error=r.err or "git status failed")
                return ToolResult(success=True, output=r.out)

            if op == "diff":
                cmd = ["diff"]
                if staged:
                    cmd.append("--staged")
                cmd.append("--")
                if paths:
                    cmd.extend([str(p) for p in paths])
                r = await asyncio.to_thread(_run_git, cmd, cwd=cwd, timeout=self._timeout_s)
                if r.code not in (0, 1):  # git diff returns 1 when differences exist
                    return ToolResult(success=False, error=r.err or "git diff failed")
                return ToolResult(success=True, output=r.out)

            if op == "log":
                cmd = ["log", f"-n{max(1, min(n, 200))}", "--oneline", "--"]
                if paths:
                    cmd.extend([str(p) for p in paths])
                r = await asyncio.to_thread(_run_git, cmd, cwd=cwd, timeout=self._timeout_s)
                if r.code != 0:
                    return ToolResult(success=False, error=r.err or "git log failed")
                return ToolResult(success=True, output=r.out)

            if op == "ls_files":
                # tracked
                r1 = await asyncio.to_thread(_run_git, ["ls-files"], cwd=cwd, timeout=self._timeout_s)
                if r1.code != 0:
                    return ToolResult(success=False, error=r1.err or "git ls-files failed")
                # untracked but not ignored
                r2 = await asyncio.to_thread(_run_git, ["ls-files", "--others", "--exclude-standard"], cwd=cwd, timeout=self._timeout_s)
                out = {"tracked": r1.out.splitlines() if r1.out else [], "untracked": r2.out.splitlines() if r2.out else []}
                return ToolResult(success=True, output=out)

            if op == "show":
                rev = str(params.get("rev") or "HEAD")
                p = str(params.get("path") or "")
                if not p:
                    return ToolResult(success=False, error="missing path")
                r = await asyncio.to_thread(_run_git, ["show", f"{rev}:{p}"], cwd=cwd, timeout=self._timeout_s)
                if r.code != 0:
                    return ToolResult(success=False, error=r.err or "git show failed")
                return ToolResult(success=True, output=r.out)

            # ---------------- mutating operations ----------------
            if op == "add":
                if not paths:
                    return ToolResult(success=False, error="missing paths")
                cmd = ["add", "--"]
                cmd.extend([str(p) for p in paths])
                r = await asyncio.to_thread(_run_git, cmd, cwd=cwd, timeout=self._timeout_s)
                if r.code != 0:
                    return ToolResult(success=False, error=r.err or "git add failed")
                return ToolResult(success=True, output="ok")

            if op == "checkout":
                b = str(params.get("branch") or "").strip()
                if not b:
                    return ToolResult(success=False, error="missing branch")
                r = await asyncio.to_thread(_run_git, ["checkout", b], cwd=cwd, timeout=self._timeout_s)
                if r.code != 0:
                    return ToolResult(success=False, error=r.err or "git checkout failed")
                return ToolResult(success=True, output=r.out or "ok")

            if op == "commit":
                msg = str(params.get("message") or "").strip()
                if not msg:
                    return ToolResult(success=False, error="missing message")
                r = await asyncio.to_thread(_run_git, ["commit", "-m", msg], cwd=cwd, timeout=self._timeout_s)
                if r.code != 0:
                    return ToolResult(success=False, error=r.err or "git commit failed")
                return ToolResult(success=True, output=r.out or "ok")

            if op == "branch_list":
                r = await asyncio.to_thread(_run_git, ["branch", "--list"], cwd=cwd, timeout=self._timeout_s)
                if r.code != 0:
                    return ToolResult(success=False, error=r.err or "git branch failed")
                return ToolResult(success=True, output=r.out)

            if op == "branch_create":
                b = str(params.get("branch") or "").strip()
                if not b:
                    return ToolResult(success=False, error="missing branch")
                from_ref = str(params.get("from_ref") or "HEAD")
                r = await asyncio.to_thread(_run_git, ["branch", b, from_ref], cwd=cwd, timeout=self._timeout_s)
                if r.code != 0:
                    return ToolResult(success=False, error=r.err or "git branch create failed")
                return ToolResult(success=True, output="ok")

            return ToolResult(success=False, error=f"unsupported operation: {op}")

        return await self._call_with_tracking(params, handler, timeout=self._timeout_s + 5.0)

