"""Harness-side adapters so Agent ## FILE bodies can be reviewed without
patching engine ``autoreview/handler.py``.

Strategy: materialize the delivery into a disposable git repo, point
``GIT_DIR`` / ``GIT_WORK_TREE`` at it, and use ``target=commit:<sha>`` so
stock ``load_diff`` works unchanged.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional, Tuple

_log = logging.getLogger(__name__)

# load_diff reads process env; serialize concurrent autoreview materializations.
_GIT_ENV_LOCK = threading.Lock()


def inline_code_to_review_blob(inline_code: str) -> str:
    """Turn Agent ## FILE / fenced code into a pseudo unified-diff (tests / debug)."""
    text = (inline_code or "").strip()
    if not text:
        return ""
    if text.startswith("diff --git ") or text.lstrip().startswith("--- "):
        return text[:120000]
    lines_out = [
        "diff --git a/inline_delivery b/inline_delivery",
        "--- /dev/null",
        "+++ b/inline_delivery",
        "@@ -0,0 +1 @@",
    ]
    for line in text.splitlines():
        lines_out.append("+" + line)
    return "\n".join(lines_out)[:120000]


def extract_file_names_from_inline(inline_code: str) -> List[str]:
    names: List[str] = []
    for m in re.finditer(r"(?m)^##\s*FILE:\s*(\S+)", inline_code or ""):
        names.append(m.group(1).strip().strip("`\"'"))
    return names[:50]


def _parse_file_sections(inline_code: str) -> Dict[str, str]:
    """Map relative path → body for ``## FILE:`` sections."""
    text = (inline_code or "").replace("\\n", "\n") if (
        "\\n" in (inline_code or "") and (inline_code or "").count("\n") < 2
    ) else (inline_code or "")
    text = text.strip()
    if not text:
        return {}
    parts = re.split(r"(?m)^##\s*FILE:\s*", text)
    out: Dict[str, str] = {}
    for part in parts[1:]:
        lines = part.splitlines()
        if not lines:
            continue
        path = lines[0].strip().strip("`\"'")
        if not path or path.startswith("..") or path.startswith("/"):
            # keep relative only; skip absolute / traversal
            continue
        body = "\n".join(lines[1:]).strip()
        # drop wrapping fence if present
        if body.startswith("```"):
            body_lines = body.splitlines()
            if body_lines and body_lines[0].startswith("```"):
                body_lines = body_lines[1:]
            if body_lines and body_lines[-1].strip() == "```":
                body_lines = body_lines[:-1]
            body = "\n".join(body_lines).strip()
        if path:
            out[path] = body + ("\n" if body and not body.endswith("\n") else "")
    return out


def _git(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.email=aiplat@local", "-c", "user.name=aiplat", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def materialize_inline_delivery_repo(inline_code: str) -> Tuple[str, str]:
    """Create a temp git repo with one commit of the delivery. Returns (work_tree, sha)."""
    files = _parse_file_sections(inline_code)
    if not files:
        # Single blob fallback — still reviewable as one file
        blob = (inline_code or "").strip()
        if not blob:
            raise ValueError("empty inline_code")
        files = {"inline_delivery": blob if blob.endswith("\n") else blob + "\n"}

    tmp = tempfile.mkdtemp(prefix="aiplat-ar-")
    try:
        r = _git(tmp, "init")
        if r.returncode != 0:
            raise RuntimeError(r.stderr or "git init failed")
        r = _git(tmp, "commit", "--allow-empty", "-m", "base")
        if r.returncode != 0:
            raise RuntimeError(r.stderr or "empty commit failed")
        for rel, content in files.items():
            abs_path = os.path.normpath(os.path.join(tmp, rel))
            if not abs_path.startswith(os.path.abspath(tmp) + os.sep) and abs_path != os.path.abspath(tmp):
                continue
            os.makedirs(os.path.dirname(abs_path) or tmp, exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
        r = _git(tmp, "add", "-A")
        if r.returncode != 0:
            raise RuntimeError(r.stderr or "git add failed")
        r = _git(tmp, "commit", "-m", "inline_delivery")
        if r.returncode != 0:
            raise RuntimeError(r.stderr or "delivery commit failed")
        r = _git(tmp, "rev-parse", "HEAD")
        sha = (r.stdout or "").strip()
        if not sha:
            raise RuntimeError("rev-parse HEAD failed")
        return tmp, sha
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


@contextmanager
def autoreview_inline_git_env(inline_code: str) -> Iterator[str]:
    """Yield ``commit:<sha>`` target while GIT_* points at a temp delivery repo.

    Restores env and deletes the temp tree on exit. Serializes via a process lock
    because stock ``load_diff`` inherits process environment.
    """
    text = (inline_code or "").strip()
    if not text:
        yield ""
        return

    _GIT_ENV_LOCK.acquire()
    tmp = ""
    old_dir = os.environ.get("GIT_DIR")
    old_work = os.environ.get("GIT_WORK_TREE")
    try:
        tmp, sha = materialize_inline_delivery_repo(text)
        os.environ["GIT_DIR"] = os.path.join(tmp, ".git")
        os.environ["GIT_WORK_TREE"] = tmp
        yield f"commit:{sha}"
    finally:
        if old_dir is None:
            os.environ.pop("GIT_DIR", None)
        else:
            os.environ["GIT_DIR"] = old_dir
        if old_work is None:
            os.environ.pop("GIT_WORK_TREE", None)
        else:
            os.environ["GIT_WORK_TREE"] = old_work
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        _GIT_ENV_LOCK.release()


def _prepare_autoreview_args_for_inline(
    skill_args: Dict,
    inline_body: str,
) -> Tuple[Dict, Optional[object]]:
    """If ``inline_body`` is set, return (args, contextmanager) for GIT env wrapping.

    Caller must enter the contextmanager around ``sys_skill_call``. When body is
    empty, returns (args unchanged, None).
    """
    args = dict(skill_args or {})
    body = str(inline_body or args.get("inline_code") or args.get("code") or "").strip()
    if not body:
        return args, None
    # Prefer harness materialization over engine inline_code handling.
    args.pop("inline_code", None)
    args.pop("code", None)
    cm = autoreview_inline_git_env(body)

    class _Wrap:
        def __enter__(self):
            self._target = cm.__enter__()
            if self._target:
                args["target"] = self._target
            elif not str(args.get("target") or "").strip():
                args["target"] = "diff"
            return args

        def __exit__(self, *exc):
            return cm.__exit__(*exc)

    return args, _Wrap()
