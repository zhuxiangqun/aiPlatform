"""Materialize Agent ## FILE deliveries into a temp git worktree for stock autoreview.

Engine ``autoreview`` only understands ``load_diff(target)``. Harness stages
inline skill output as a real worktree and passes the path via skill param
``_git_work_tree`` — **not** via process-global ``GIT_DIR`` / ``GIT_WORK_TREE``.

Mutating ``os.environ`` for the duration of an LLM call was the root hang class:
concurrent coroutines / other git ops saw the wrong repo, and a lock held across
``await`` could wedge the event loop.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from typing import Iterator, List, Optional, Tuple

_log = logging.getLogger(__name__)


def extract_file_sections(inline_code: str) -> List[Tuple[str, str]]:
    """Parse ``## FILE: path`` sections → [(path, body), ...]."""
    text = str(inline_code or "")
    if not text.strip():
        return []
    if "\\n" in text and text.count("\n") < 2:
        text = text.replace("\\n", "\n").replace("\\t", "\t")
    matches = list(re.finditer(r"(?m)^##\s*FILE:\s*(\S+)\s*$", text))
    if not matches:
        return []
    out: List[Tuple[str, str]] = []
    for i, m in enumerate(matches):
        path = m.group(1).strip().strip("`\"'")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if path:
            out.append((path, _strip_code_fence(body)))
    return out


def _strip_code_fence(body: str) -> str:
    s = str(body or "").strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def inline_code_to_review_blob(inline_code: str) -> str:
    """Pseudo unified-diff for tests / diagnostics (engine no longer owns this)."""
    text = str(inline_code or "").strip()
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
    return [p for p, _ in extract_file_sections(inline_code)][:50]


def coerce_inline_delivery_text(raw: object) -> str:
    """Normalize skill output → text that may contain ``## FILE`` sections.

    ``str(dict)`` escapes newlines and breaks ``^## FILE`` parsing; unwrap common
    payload keys first.
    """
    if raw is None:
        return ""
    if isinstance(raw, dict):
        for k in ("code", "text", "output", "content", "markdown", "answer"):
            v = raw.get(k)
            if isinstance(v, str) and v.strip():
                return v
            if isinstance(v, dict):
                nested = coerce_inline_delivery_text(v)
                if nested.strip():
                    return nested
        # Structured skill products (test_executor report, architecture JSON)
        # have no code/text key — empty return made skill_delivery_once skip
        # finalize and hang on a second LLM (run-74a19d55326c).
        try:
            import json as _json_co

            dumped = _json_co.dumps(raw, ensure_ascii=False)
        except Exception:
            dumped = str(raw)
        return dumped if dumped.strip() and dumped not in ("{}", "[]") else ""
    if isinstance(raw, (list, tuple)):
        parts = [coerce_inline_delivery_text(x) for x in raw]
        return "\n\n".join(p for p in parts if p.strip())
    text = str(raw or "")
    # Best-effort: JSON object string with a code field
    s = text.strip()
    if s.startswith("{") and ("## FILE" in s or "```" in s):
        try:
            import json

            obj = json.loads(s)
            if isinstance(obj, dict):
                return coerce_inline_delivery_text(obj) or text
        except Exception:
            pass  # noqa: cleanup-best-effort
    return text


def _safe_rel_path(path: str) -> str:
    p = str(path or "").replace("\\", "/").lstrip("/")
    parts = [x for x in p.split("/") if x and x not in (".", "..")]
    return "/".join(parts) or "inline_delivery"


def _file_op_allowed_roots() -> List[str]:
    raw = os.environ.get("AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS", "").strip()
    out: List[str] = []
    if raw:
        for chunk in raw.split(os.pathsep):
            for p in chunk.split(","):
                s = str(p or "").strip()
                if s:
                    out.append(os.path.realpath(os.path.expanduser(s)))
    if out:
        return out
    # Same default as start.sh: empty env must not disable harness persist.
    # file_operations *tool* still refuses writes in apps/tools/base.py when env is empty.
    home = os.path.realpath(
        os.path.expanduser(os.environ.get("AIPLAT_HOME") or "~/.aiplat")
    )
    return [home] if home else []


def _path_under_allowed_roots(abs_path: str) -> bool:
    target = os.path.realpath(os.path.expanduser(str(abs_path or "")))
    for root in _file_op_allowed_roots():
        if target == root or target.startswith(root + os.sep):
            return True
    return False


def resolve_run_persist_root(run_id: str) -> str:
    """Durable workspace for a run: ``$AIPLAT_HOME/run_workspaces/{run_id}``.

    Must sit under ``AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS`` (same gate as
    ``file_operations``). Never writes into the git repo unless that repo is
    the only allowed root.
    """
    rid = re.sub(r"[^A-Za-z0-9._-]+", "_", str(run_id or "").strip())[:80] or "run"
    home = os.path.realpath(
        os.path.expanduser(os.environ.get("AIPLAT_HOME") or "~/.aiplat")
    )
    candidate = os.path.join(home, "run_workspaces", rid)
    roots = _file_op_allowed_roots()
    if not roots:
        raise PermissionError(
            "file_operations is disabled: AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS is empty"
        )
    if _path_under_allowed_roots(candidate):
        return candidate
    return os.path.join(roots[0], "run_workspaces", rid)


def persist_inline_delivery(inline_code: str, dest_root: str) -> dict:
    """Write ``## FILE:`` bodies under ``dest_root``. Returns a status dict.

    Skips empty deliveries. Refuses paths outside the file_operations allowlist
    or with denylist segments (``.git``, ``.env``, …).
    """
    text = coerce_inline_delivery_text(inline_code).strip()
    sections = extract_file_sections(text)
    root = os.path.realpath(os.path.expanduser(str(dest_root or "").strip()))
    if not sections:
        return {"ok": False, "root": root, "files": [], "error": "no_file_sections"}
    if not _path_under_allowed_roots(root):
        return {
            "ok": False,
            "root": root,
            "files": [],
            "error": "persist_root_not_allowed",
        }
    deny_raw = os.environ.get(
        "AIPLAT_FILE_OPERATIONS_DENYLIST_SEGMENTS",
        ".ssh,.git,.env,.venv,node_modules,__pycache__,id_rsa,id_ed25519,secrets",
    )
    deny = {s.strip() for s in str(deny_raw).split(",") if s.strip()}
    written: List[str] = []
    try:
        os.makedirs(root, exist_ok=True)
        for rel, body in sections:
            safe = _safe_rel_path(rel)
            abs_path = os.path.join(root, *safe.split("/"))
            abs_resolved = os.path.realpath(abs_path)
            parent = os.path.dirname(abs_resolved)
            if not _path_under_allowed_roots(abs_resolved) and not _path_under_allowed_roots(
                parent
            ):
                return {
                    "ok": False,
                    "root": root,
                    "files": written,
                    "error": f"path_not_allowed:{safe}",
                }
            parts = set(abs_resolved.split(os.sep))
            if deny and (parts & deny):
                return {
                    "ok": False,
                    "root": root,
                    "files": written,
                    "error": f"denied_segment:{safe}",
                }
            os.makedirs(os.path.dirname(abs_path) or root, exist_ok=True)
            payload = body if str(body).endswith("\n") else str(body) + "\n"
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(payload)
            written.append(safe)
        return {"ok": True, "root": root, "files": written, "error": ""}
    except Exception as exc:
        _log.warning("persist_inline_delivery failed root=%s", root, exc_info=True)
        return {
            "ok": False,
            "root": root,
            "files": written,
            "error": str(exc)[:300],
        }


def _git(cwd: str, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _diff_nonempty(cwd: str) -> bool:
    """True if staged/unstaged changes vs HEAD are visible to load_diff('diff')."""
    for args in (
        ["git", "diff", "--unified=3", "HEAD"],
        ["git", "diff", "--cached", "--unified=3"],
    ):
        try:
            probe = subprocess.run(
                args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception:
            continue
        if (probe.stdout or "").strip():
            return True
    return False


def stage_inline_delivery(inline_code: str) -> Optional[str]:
    """Create a temp git worktree with inline files. Returns path or None.

    Caller owns cleanup (``shutil.rmtree``). Does **not** touch ``os.environ``.
    """
    text = coerce_inline_delivery_text(inline_code).strip()
    if not text:
        return None

    sections = extract_file_sections(text)
    if not sections:
        sections = [("inline_delivery", _strip_code_fence(text))]

    tmp = tempfile.mkdtemp(prefix="aiplat-ar-")
    try:
        _git(tmp, "init")
        _git(tmp, "config", "user.email", "aiplat@local")
        _git(tmp, "config", "user.name", "aiplat")
        _git(tmp, "commit", "--allow-empty", "-m", "base")
        for rel, body in sections:
            safe = _safe_rel_path(rel)
            abs_path = os.path.join(tmp, *safe.split("/"))
            parent = os.path.dirname(abs_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(body if body.endswith("\n") else body + "\n")
        _git(tmp, "add", "-A")
        if not _diff_nonempty(tmp):
            _log.warning("inline autoreview worktree produced empty git diff")
            shutil.rmtree(tmp, ignore_errors=True)
            return None
        return tmp
    except Exception:
        _log.warning("inline autoreview worktree setup failed", exc_info=True)
        shutil.rmtree(tmp, ignore_errors=True)
        return None


@contextmanager
def staged_inline_worktree(inline_code: str) -> Iterator[Optional[str]]:
    """Stage inline delivery; yield worktree path; always clean up. No env mutation."""
    wt = stage_inline_delivery(inline_code)
    try:
        yield wt
    finally:
        if wt:
            shutil.rmtree(wt, ignore_errors=True)


# Back-compat alias used by older tests / callers.
@contextmanager
def autoreview_git_env_for_inline(inline_code: str) -> Iterator[Optional[str]]:
    """Deprecated name: stages worktree only (no GIT_* env mutation)."""
    with staged_inline_worktree(inline_code) as wt:
        yield wt
