"""Bind a completion claim to tool receipts. No LLM.

A DONE/FINAL answer may say the bug is fixed or name a file path. Those
sentences are sealed only when a successful tool receipt supports them.
Otherwise the stored answer is prefixed and the syscall status is
``unverified`` or ``failed``. The model text is kept underneath so the
original error is still visible.

Disable with ``AIPLAT_COMPLETION_RECEIPT=0``.
"""

from __future__ import annotations

import base64
import difflib
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from core.harness.utils.locale_markers import (  # noqa: E402
    FIX_CLAIM_RE as _FIX_CLAIM,
    PATH_CLAIM_RE as _PATH_CLAIM,
    SEAL_FAIL_LAST_TOOL,
    SEAL_FAIL_MEASURED,
    SEAL_FAIL_RECEIPT_PREFIX,
    SEAL_UNVERIFIED_NO_RECEIPT,
    SEAL_UNVERIFIED_PATH,
)


_TERMINAL_DONE_RE = re.compile(
    r"^(?:DONE|FINAL|FINISHED)(?:\s*[:：]|\s|$)",
    re.IGNORECASE,
)


def is_terminal_done_marker(text: Any) -> bool:
    """True when DONE/FINAL/FINISHED starts the text, not a mid-string mention."""
    raw = str(text or "").strip()
    if not raw:
        return False
    return _TERMINAL_DONE_RE.match(raw) is not None


def strip_terminal_done_marker(text: Any) -> str:
    """Remove a leading DONE/FINAL/FINISHED marker; return the remainder."""
    raw = str(text or "").strip()
    m = _TERMINAL_DONE_RE.match(raw)
    if not m:
        return raw
    return raw[m.end() :].strip()


def receipt_bind_enabled() -> bool:
    return os.getenv("AIPLAT_COMPLETION_RECEIPT", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def infer_receipt_status(action_result: Any) -> str:
    """ok or failed from the tool observation head. Empty is failed.

    Avoid false fails on benign tool text such as ``Pattern not found`` or
    ``error_count: 0`` — only treat clear failure prefixes / policy denials.
    """
    text = str(action_result or "")
    if not text.strip():
        return "failed"
    head = text.lstrip()[:240].lower()
    if (
        head.startswith("skill error:")
        or head.startswith("denied:")
        or head.startswith("error:")
        or head.startswith("traceback")
        or head.startswith("404")
        or "policy_denied" in head
        or "aiplat_tool_execute_failed" in head
        or "aiplat_tool_execute_approval_required" in head
        or "aiplat_approval_wait_denied" in head
        or "aiplat_unattended_wait_denied" in head
        or "approval_required" in head
        or "handler_missing" in head
        or "invalid_skill_name" in head
    ):
        return "failed"
    # Explicit tool/file miss — not grep-style "Pattern not found".
    if head.startswith("file not found") or head.startswith("tool not found:"):
        return "failed"
    return "ok"


def record_tool_receipt(
    context: Dict[str, Any],
    *,
    tool: str,
    status: str,
    detail: str = "",
) -> None:
    """Append one tool receipt. ``status`` is ``ok`` or ``failed``."""
    if not isinstance(context, dict):
        return
    seal = "ok" if str(status).strip().lower() in ("ok", "completed", "success") else "failed"
    row = {
        "tool": str(tool or "")[:80],
        "status": seal,
        "detail": str(detail or "")[:500],
    }
    if context.pop("_repair_verify_mark_next", None):
        row["repair_verify"] = True
    receipts = context.get("_tool_receipts")
    if not isinstance(receipts, list):
        receipts = []
        context["_tool_receipts"] = receipts
    receipts.append(row)
    if len(receipts) > 20:
        del receipts[:-20]
    context["_last_tool_receipt_status"] = seal
    try:
        from core.harness.utils.task_model_lock import note_tool_outcome
        note_tool_outcome(seal, row["detail"])
    except Exception:
        logger.debug("task model outcome skipped", exc_info=True)


def bind_completion_to_receipts(text: str, context: Dict[str, Any]) -> Tuple[str, str]:
    """Return ``(answer, seal_status)``. ``seal_status`` is ok | unverified | failed."""
    raw = str(text or "")
    if not receipt_bind_enabled() or not isinstance(context, dict):
        return raw, "ok"
    receipts: List[Dict[str, Any]] = [
        r for r in (context.get("_tool_receipts") or []) if isinstance(r, dict)
    ]
    multi = context.get("_repair_candidates")
    if (
        (context.get("_repair_candidate_selected") or context.get("_repair_pre_selection_stamped"))
        and isinstance(multi, list)
        and len(multi) >= 2
    ):
        receipts = [r for r in receipts if not r.get("pre_selection")]
    ok_blob = "\n".join(
        str(r.get("detail") or "") for r in receipts if r.get("status") == "ok"
    )
    last_failed = bool(receipts) and receipts[-1].get("status") != "ok"
    claims_fix = bool(_FIX_CLAIM.search(raw))
    pred = context.get("_prediction_receipt")
    if claims_fix and isinstance(pred, dict) and pred.get("actual_pass") is False:
        return f"{SEAL_FAIL_MEASURED}\n{raw}", "failed"
    paths = _PATH_CLAIM.findall(raw)
    unsupported = [p for p in paths if p not in ok_blob]

    if claims_fix and (not receipts or last_failed or not ok_blob):
        if last_failed:
            detail = str(receipts[-1].get("detail") or "").strip()
            head = SEAL_FAIL_LAST_TOOL
            if detail:
                head = f"{head} {SEAL_FAIL_RECEIPT_PREFIX}{detail[:300]}"
            return f"{head}\n{raw}", "failed"
        return f"{SEAL_UNVERIFIED_NO_RECEIPT}\n{raw}", "unverified"

    if unsupported:
        shown = ", ".join(unsupported[:3])
        return f"{SEAL_UNVERIFIED_PATH}{shown}\n{raw}", "unverified"
    return raw, "ok"


def select_repair_candidate(
    candidates: Any,
    *,
    min_score: float = 0.5,
) -> Dict[str, Any]:
    """Pick the highest-scored repair. Score is caller-supplied, not a world model.

    Only the chosen candidate should be executed. Others are listed as skipped.
    ``predicted_pass`` is true when the chosen score is at least ``min_score``.
    """
    rows: List[Dict[str, Any]] = []
    items = candidates if isinstance(candidates, list) else []
    for i, raw in enumerate(items):
        if isinstance(raw, str):
            raw = {"id": str(i), "text": raw, "score": 0.0}
        if not isinstance(raw, dict):
            continue
        try:
            score = float(raw.get("score") if raw.get("score") is not None else 0.0)
        except (TypeError, ValueError):
            score = 0.0
        rows.append({
            "id": str(raw.get("id") or i)[:80],
            "text": str(raw.get("text") or raw.get("patch") or ""),
            "score": score,
        })
    if not rows:
        return {"error": "no repair candidates", "chosen": None, "skipped": [], "predicted_pass": False}
    rows.sort(key=lambda row: (-float(row["score"]), str(row["id"])))
    chosen = dict(rows[0])
    chosen["predicted_pass"] = float(chosen["score"]) >= float(min_score)
    return {
        "chosen": chosen,
        "skipped": [str(row["id"]) for row in rows[1:]],
        "predicted_pass": chosen["predicted_pass"],
    }


_CANDIDATE_BLOCK = re.compile(
    r"##\s*REPAIR_CANDIDATES\s*\n```(?:json)?\s*\n(\[[\s\S]*?\])\s*\n```",
    re.IGNORECASE,
)


def ingest_repair_candidates(context: Dict[str, Any]) -> None:
    """Read ``## REPAIR_CANDIDATES`` from output when the list is not already set.

    Scores stay caller-supplied. This does not rank with a world model.
    """
    if not isinstance(context, dict):
        return
    existing = context.get("_repair_candidates")
    if isinstance(existing, list) and existing:
        return
    match = _CANDIDATE_BLOCK.search(str(context.get("output") or ""))
    if not match:
        return
    try:
        rows = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError, ValueError):
        return
    if isinstance(rows, list) and rows:
        context["_repair_candidates"] = rows


def apply_repair_selection(context: Dict[str, Any]) -> Optional[str]:
    """Select once from ``_repair_candidates`` and replace ``output`` with the winner."""
    if not isinstance(context, dict) or context.get("_repair_candidate_selected"):
        return None
    remember_repair_candidates(context)
    ingest_repair_candidates(context)
    candidates = context.get("_repair_candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    picked = select_repair_candidate(candidates)
    if picked.get("error"):
        return str(picked["error"])
    context["_repair_candidate_selected"] = picked
    text = str((picked.get("chosen") or {}).get("text") or "")
    if not text:
        return "repair candidate chosen text is empty"
    context["output"] = text
    _stamp_pre_selection_verifies(context)
    revert_skipped_repair_writes(context)
    return None


_VERIFY_TOOLS = frozenset({"code", "code_execution"})
_SHELL_TOOLS = frozenset({"shell", "bash", "shell_exec", "process", "terminal"})
_VERIFY_SKILLS = frozenset(
    {"test_executor", "canary_runner", "e2e_test", "acceptance_checker"}
)
_VERIFY_NAMES = _VERIFY_TOOLS | _VERIFY_SKILLS
_WRITE_TOOLS = frozenset({
    "file_operations",
    "write",
    "sys_file_write",
    "edit",
    "sys_file_edit",
})
_PYTHON_PATCH = re.compile(r"^python3?\b", re.IGNORECASE)
# Shell redirects that write files count as repair patch paths (not exploration).
_SHELL_REDIRECT = re.compile(r"(?:^|[;&|]\s*)(?:.+?)\s*(?:>>?|tee(?:\s+-a)?)\s+\S+", re.I)


def _parse_candidate_rows(text: Any) -> Optional[list]:
    match = _CANDIDATE_BLOCK.search(str(text or ""))
    if not match:
        return None
    try:
        rows = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if isinstance(rows, list) and rows:
        return rows
    return None


def _stamp_pre_selection_verifies(context: Dict[str, Any]) -> None:
    """code receipts from before the candidate list do not prove the winner."""
    if not isinstance(context, dict) or context.get("_repair_pre_selection_stamped"):
        return
    context["_repair_pre_selection_stamped"] = True
    receipts = context.get("_tool_receipts")
    if not isinstance(receipts, list):
        return
    for row in receipts:
        if not isinstance(row, dict):
            continue
        tool = str(row.get("tool") or "").strip().lower()
        if tool in _VERIFY_NAMES or tool in _SHELL_TOOLS or row.get("repair_verify"):
            row["pre_selection"] = True


def remember_repair_candidates(context: Dict[str, Any]) -> None:
    """Keep a multi-candidate block after this turn's reasoning is replaced.

    A later ``code`` call still sees the list. Scores stay caller-supplied.
    """
    if not isinstance(context, dict) or context.get("_repair_candidate_selected"):
        return
    existing = context.get("_repair_candidates")
    if isinstance(existing, list) and len(existing) >= 2:
        _stamp_pre_selection_verifies(context)
        return
    rows = _parse_candidate_rows(context.get("reasoning"))
    if rows is None:
        rows = _parse_candidate_rows(context.get("output"))
    if isinstance(rows, list) and len(rows) >= 2:
        context["_repair_candidates"] = rows
    kept = context.get("_repair_candidates")
    if isinstance(kept, list) and len(kept) >= 2:
        _stamp_pre_selection_verifies(context)


def _tool_args_text(tool_args: Any) -> str:
    if tool_args is None:
        return ""
    if isinstance(tool_args, str):
        return tool_args
    if isinstance(tool_args, dict):
        parts = [_tool_args_text(value) for value in tool_args.values()]
    elif isinstance(tool_args, list):
        parts = [_tool_args_text(value) for value in tool_args]
    else:
        parts = [str(tool_args)]
    try:
        parts.append(json.dumps(tool_args, ensure_ascii=False))
    except (TypeError, ValueError):
        pass  # noqa: cleanup-best-effort — non-JSON args already stringified above
    return "\n".join(parts)


def _script_includes_skipped(blob: str, texts: List[str]) -> bool:
    body = str(blob or "")
    for text in texts:
        piece = str(text or "").strip()
        if len(piece) >= 40 and piece in body:
            return True
        if piece and body.strip() == piece:
            return True
    return False


def _verify_code_body(tool_args: Any) -> str:
    if isinstance(tool_args, dict):
        for key in ("code", "command", "script"):
            value = tool_args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return _tool_args_text(tool_args).strip()


def _write_body(tool_args: Any) -> str:
    if isinstance(tool_args, dict):
        for key in ("content", "new_string", "newString", "code", "script"):
            value = tool_args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return _tool_args_text(tool_args).strip()


# Bare ``python`` / ``python -c`` is a patch path, not a check command.
_SHELL_CHECK = re.compile(
    r"^(?:pytest|ruff|mypy|py_compile|npm|pnpm|yarn|npx|go test|cargo test|"
    r"python3?\s+-m\s+(?:pytest|ruff|mypy))\b",
    re.IGNORECASE,
)


def _is_shell_check(body: str) -> bool:
    line = str(body or "").strip().splitlines()
    if not line:
        return False
    return bool(_SHELL_CHECK.match(line[0].strip()))


def _is_repair_shell_body(body: str) -> bool:
    """Shell commands that count as repair verify/patch (not ls/cat exploration)."""
    text = str(body or "").strip()
    if not text:
        return False
    if _is_shell_check(text):
        return True
    if _SHELL_REDIRECT.search(text):
        return True
    return bool(_PYTHON_PATCH.match(text.splitlines()[0].strip()))


def maybe_note_repair_fs_delta(context: Dict[str, Any]) -> None:
    """After a tool returns, note cwd writes if a repair baseline was captured."""
    note_repair_writes_from_fs_delta(context)


def _hold_divergent_verify(context: Dict[str, Any], tool_args: Any) -> Optional[str]:
    """Before a candidate block exists, refuse a second script that is a different patch.

    Check commands such as ``pytest`` or ``python -m pytest`` still run.
    ``python -c`` and other scripts are compared. A small edit of the same script still runs.
    """
    body = _verify_code_body(tool_args)
    if not body or _is_shell_check(body):
        return None
    previous = context.get("_repair_verify_bodies")
    if not isinstance(previous, list):
        previous = []
    for prior in previous:
        if not isinstance(prior, str) or not prior:
            continue
        if difflib.SequenceMatcher(None, prior, body).ratio() < 0.92:
            return "emit ## REPAIR_CANDIDATES before verifying another patch"
    kept = [item for item in previous if isinstance(item, str)]
    kept.append(body[:4000])
    context["_repair_verify_bodies"] = kept[-5:]
    context["_repair_active_script"] = body[:4000]
    note_repair_writes_from_code(context, tool_args)
    capture_repair_fs_baseline(context)
    return None


def note_repair_write(
    context: Dict[str, Any],
    *,
    path: str,
    content: str,
    existed: Optional[bool] = None,
    checkpoint_id: str = "",
    prior_content: Optional[str] = None,
    prior_b64: str = "",
    binary: bool = False,
    source_script: str = "",
) -> None:
    """Remember a write so a later selection can drop a skipped candidate file."""
    if not isinstance(context, dict):
        return
    rows = context.get("_repair_writes")
    if not isinstance(rows, list):
        rows = []
        context["_repair_writes"] = rows
    script = str(source_script or context.get("_repair_active_script") or "")[:4000]
    row = {
        "path": str(path or "")[:500],
        "content": str(content or "")[:8000],
        "existed": existed,
        "checkpoint_id": str(checkpoint_id or ""),
        "reverted": False,
        "binary": bool(binary),
        "source_script": script,
        "prior_b64": str(prior_b64 or "")[:12000],
    }
    if prior_content is not None:
        row["prior_content"] = str(prior_content)[:8000]
    if prior_b64:
        row["prior_b64"] = str(prior_b64)
    rows.append(row)
    if len(rows) > 40:
        del rows[:-40]


def _repair_workdir(context: Dict[str, Any]) -> str:
    """Prefer explicit cwd, then deploy/output roots, then process cwd."""
    if not isinstance(context, dict):
        return ""
    for key in ("cwd", "workdir", "_deploy_files_dir", "output_dir", "workspace_root"):
        raw = str(context.get(key) or "").strip()
        if raw and os.path.isdir(raw):
            return os.path.realpath(raw)
    try:
        cwd = os.getcwd()
    except OSError:
        return ""
    if cwd and os.path.isdir(cwd):
        return os.path.realpath(cwd)
    return ""


def _resolve_repair_path(context: Dict[str, Any], path: str) -> str:
    """Resolve a repair write path; must stay under the task workdir."""
    raw = str(path or "").strip()
    if not raw:
        return ""
    base = _repair_workdir(context)
    if not base:
        return ""
    if os.path.isabs(raw):
        candidate = os.path.realpath(raw)
    else:
        candidate = os.path.realpath(os.path.join(base, raw))
    try:
        common = os.path.commonpath([base, candidate])
    except ValueError:
        return ""
    if common != base:
        logger.warning(
            "repair path rejected (outside workdir): path=%s base=%s",
            raw,
            base,
        )
        return ""
    return candidate


def _snapshot_and_note_write(context: Dict[str, Any], path: str, content: str) -> None:
    target = _resolve_repair_path(context, path)
    body = str(content or "")
    if not target or not body:
        return
    existed = os.path.isfile(target)
    prior = None
    prior_b64 = ""
    binary = False
    checkpoint_id = ""
    if existed:
        try:
            with open(target, "r", encoding="utf-8") as handle:
                text = handle.read()
            if "\x00" in text:
                binary = True
                with open(target, "rb") as handle:
                    prior_b64 = base64.b64encode(handle.read()).decode("ascii")
            else:
                prior = text
        except (OSError, UnicodeDecodeError):
            binary = True
            try:
                with open(target, "rb") as handle:
                    prior_b64 = base64.b64encode(handle.read()).decode("ascii")
            except OSError:
                prior_b64 = ""
        try:
            from core.harness.execution.file_checkpoint import checkpoint_file

            checkpoint_id = str(
                checkpoint_file(
                    target,
                    session_id=str(context.get("session_id") or ""),
                    reason="repair_write",
                )
                or ""
            )
        except Exception:
            logger.debug("repair write checkpoint skipped", exc_info=True)
    note_repair_write(
        context,
        path=target,
        content=body,
        existed=existed,
        checkpoint_id=checkpoint_id,
        prior_content=prior,
        prior_b64=prior_b64,
        binary=binary,
    )


_LITERAL_FILE_WRITES = (
    re.compile(
        r"Path\s*\(\s*(?:[rRuUbBfF]{0,2})(['\"])(?P<path>[^'\"]+)\1\s*\)\s*\.\s*write_text\s*\(\s*"
        r"(?:[rRuUbBfF]{0,2})(?P<q>'''|\"\"\"|'|\")(?P<body>.*?)(?P=q)",
        re.DOTALL,
    ),
    # open("p", "w").write(...) and open("p", "w", encoding=...).write(...)
    re.compile(
        r"open\s*\(\s*(?:[rRuUbBfF]{0,2})(['\"])(?P<path>[^'\"]+)\1\s*,\s*(['\"])w\3[^)]*\)\s*\.\s*write\s*\(\s*"
        r"(?:[rRuUbBfF]{0,2})(?P<q>'''|\"\"\"|'|\")(?P<body>.*?)(?P=q)",
        re.DOTALL,
    ),
    # with open("p", "w") as f: f.write(...)
    re.compile(
        r"with\s+open\s*\(\s*(?:[rRuUbBfF]{0,2})(['\"])(?P<path>[^'\"]+)\1\s*,\s*(['\"])w\3[^)]*\)\s+"
        r"as\s+(?P<fh>\w+)\s*:\s*(?:[ \t]*#.*\n)*[ \t]*(?P=fh)\.write\s*\(\s*"
        r"(?:[rRuUbBfF]{0,2})(?P<q>'''|\"\"\"|'|\")(?P<body>.*?)(?P=q)",
        re.DOTALL,
    ),
)


def note_repair_writes_from_code(context: Dict[str, Any], tool_args: Any = None) -> None:
    """Record literal Path.write_text / open().write / with-open write targets."""
    if not isinstance(context, dict):
        return
    body = _verify_code_body(tool_args)
    if not body or _is_shell_check(body):
        return
    for pattern in _LITERAL_FILE_WRITES:
        for match in pattern.finditer(body):
            _snapshot_and_note_write(context, match.group("path"), match.group("body"))


_SKIP_FS_DIRS = frozenset({
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "dist",
    "build",
})


def capture_repair_fs_baseline(context: Dict[str, Any]) -> None:
    """Snapshot cwd before a code tool runs so variable writes can be noted after."""
    if not isinstance(context, dict):
        return
    root = _repair_workdir(context)
    if not root:
        context.pop("_repair_fs_baseline", None)
        return
    # Keep later delta/path resolution on the same root even if keys were empty.
    if not str(context.get("cwd") or "").strip():
        context["cwd"] = root
    snap: Dict[str, Dict[str, Any]] = {}
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in _SKIP_FS_DIRS and not name.startswith(".")]
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > 6:
            dirnames[:] = []
            continue
        for name in filenames:
            if count >= 400:
                context["_repair_fs_baseline"] = snap
                return
            if name.startswith("."):
                continue
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            row: Dict[str, Any] = {"mtime": st.st_mtime_ns, "size": st.st_size}
            if st.st_size <= 8000:
                text = None
                try:
                    with open(path, "r", encoding="utf-8") as handle:
                        text = handle.read()
                except (OSError, UnicodeDecodeError):
                    text = None
                # NUL can still decode as UTF-8; treat as binary so restore keeps bytes.
                if text is not None and "\x00" not in text:
                    row["content"] = text
                else:
                    row["binary"] = True
                    try:
                        with open(path, "rb") as handle:
                            row["prior_b64"] = base64.b64encode(handle.read()).decode("ascii")
                    except OSError:
                        pass  # noqa: cleanup-best-effort — binary baseline optional
            else:
                # Large files: best-effort on-disk checkpoint (may be unavailable in sandbox).
                try:
                    from core.harness.execution.file_checkpoint import checkpoint_file

                    cid = checkpoint_file(
                        path,
                        session_id=str(context.get("session_id") or ""),
                        reason="repair_fs_baseline",
                    )
                    if cid:
                        row["checkpoint_id"] = str(cid)
                        row["binary"] = True
                except Exception:
                    logger.debug("repair fs baseline checkpoint skipped", exc_info=True)
            snap[path] = row
            count += 1
    context["_repair_fs_baseline"] = snap


def note_repair_writes_from_fs_delta(context: Dict[str, Any]) -> None:
    """After a code tool returns, note new or changed files under cwd."""
    if not isinstance(context, dict):
        return
    baseline = context.pop("_repair_fs_baseline", None)
    if not isinstance(baseline, dict):
        return
    root = _repair_workdir(context)
    if not root:
        context.pop("_repair_active_script", None)
        return
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in _SKIP_FS_DIRS and not name.startswith(".")]
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > 6:
            dirnames[:] = []
            continue
        for name in filenames:
            if seen >= 400:
                context.pop("_repair_active_script", None)
                return
            if name.startswith("."):
                continue
            path = os.path.join(dirpath, name)
            seen += 1
            try:
                st = os.stat(path)
            except OSError:
                continue
            prior = baseline.get(path)
            if isinstance(prior, dict) and prior.get("mtime") == st.st_mtime_ns and prior.get("size") == st.st_size:
                continue
            content = ""
            binary = False
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    content = handle.read()
            except (OSError, UnicodeDecodeError):
                binary = True
            if not content and not binary:
                continue
            existed = isinstance(prior, dict)
            prior_b64 = ""
            if existed and isinstance(prior, dict):
                prior_b64 = str(prior.get("prior_b64") or "")
                if not prior_b64 and binary and "content" in prior:
                    # Baseline mistook NUL-bearing bytes as text; re-encode for restore.
                    try:
                        prior_b64 = base64.b64encode(
                            str(prior.get("content") or "").encode("utf-8")
                        ).decode("ascii")
                    except (UnicodeEncodeError, ValueError):
                        prior_b64 = ""
            note_repair_write(
                context,
                path=path,
                content=content,
                existed=existed,
                checkpoint_id=(
                    str(prior.get("checkpoint_id") or "")
                    if existed and isinstance(prior, dict)
                    else ""
                ),
                prior_content=(
                    str(prior.get("content"))
                    if existed and isinstance(prior, dict) and "content" in prior and not binary
                    else None
                ),
                binary=binary or bool(isinstance(prior, dict) and prior.get("binary")),
                prior_b64=prior_b64,
            )
    context.pop("_repair_active_script", None)


def _write_payload(tool_name: str, tool_args: Any) -> Tuple[str, str]:
    if not isinstance(tool_args, dict):
        return "", ""
    path = str(tool_args.get("path") or tool_args.get("filePath") or "")
    if str(tool_name or "").strip().lower() in ("edit", "sys_file_edit"):
        content = str(tool_args.get("new_string") or tool_args.get("newString") or "")
    else:
        content = str(tool_args.get("content") or "")
    return path, content


def _write_tied_to_skipped(row: Dict[str, Any], skipped_texts: List[str]) -> bool:
    content = str(row.get("content") or "")
    if _script_includes_skipped(content, skipped_texts):
        return True
    script = str(row.get("source_script") or "")
    if not script:
        return False
    if _script_includes_skipped(script, skipped_texts):
        return True
    for text in skipped_texts:
        piece = str(text or "").strip()
        if len(piece) < 40:
            continue
        if difflib.SequenceMatcher(None, script, piece).ratio() >= 0.92:
            return True
    return False


def revert_skipped_repair_writes(context: Dict[str, Any]) -> List[str]:
    """Drop skipped-candidate writes from disk after selection.

    Matches by file body or by the code script that produced the write.
    New files are removed. Overwrites are restored from a checkpoint id or the
    prior content captured at note time. Scores stay caller-supplied.
    """
    if not isinstance(context, dict) or not context.get("_repair_candidate_selected"):
        return []
    picked = context.get("_repair_candidate_selected")
    skipped_ids = set()
    if isinstance(picked, dict):
        skipped_ids = {str(item) for item in (picked.get("skipped") or [])}
    candidates = context.get("_repair_candidates")
    skipped_texts = [
        str(row.get("text") or "")
        for row in candidates
        if isinstance(candidates, list) and isinstance(row, dict) and str(row.get("id") or "") in skipped_ids
    ]
    writes = context.get("_repair_writes")
    if not isinstance(writes, list) or not skipped_texts:
        return []
    reverted: List[str] = []
    for row in writes:
        if not isinstance(row, dict) or row.get("reverted"):
            continue
        content = str(row.get("content") or "")
        path = str(row.get("path") or "")
        if not path or not _write_tied_to_skipped(row, skipped_texts):
            continue
        cid = str(row.get("checkpoint_id") or "")
        if cid:
            try:
                from core.harness.execution.file_checkpoint import restore_file_checkpoint

                result = restore_file_checkpoint(
                    cid, session_id=str(context.get("session_id") or "")
                )
            except Exception:
                logger.debug("restore skipped repair write failed", exc_info=True)
                result = {"success": False}
            if result.get("success"):
                row["reverted"] = True
                reverted.append(path)
                continue
        prior_b64 = str(row.get("prior_b64") or "")
        if prior_b64:
            try:
                with open(path, "wb") as handle:
                    handle.write(base64.b64decode(prior_b64.encode("ascii")))
            except (OSError, ValueError):
                logger.debug("restore prior binary skipped repair write failed", exc_info=True)
                continue
            row["reverted"] = True
            reverted.append(path)
            continue
        # New files created while running a skipped script: remove even if body drifted.
        if row.get("existed") is False:
            if not os.path.isfile(path):
                continue
            try:
                os.remove(path)
            except OSError:
                logger.debug("remove skipped repair write failed", exc_info=True)
                continue
            row["reverted"] = True
            reverted.append(path)
            continue
        if row.get("binary"):
            # Overwrite without checkpoint / prior bytes cannot be restored safely.
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                current = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        if content and current != content and current.strip() != content.strip():
            continue
        if "prior_content" in row:
            try:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(str(row.get("prior_content") or ""))
            except OSError:
                logger.debug("restore prior skipped repair write failed", exc_info=True)
                continue
            row["reverted"] = True
            reverted.append(path)
            continue
    if reverted:
        context["_repair_reverted_writes"] = reverted
    return reverted


def block_skipped_repair_write(
    context: Dict[str, Any],
    tool_name: str,
    tool_args: Any = None,
) -> Optional[str]:
    """Refuse writing a skipped repair candidate after selection.

    Read/list/delete are left alone. Scores stay caller-supplied.
    """
    if not isinstance(context, dict):
        return None
    name = str(tool_name or "").strip().lower()
    if name not in _WRITE_TOOLS:
        return None
    if name == "file_operations":
        op = ""
        if isinstance(tool_args, dict):
            op = str(tool_args.get("operation") or tool_args.get("action") or "").strip().lower()
        if op and op not in ("write", "create", "append"):
            return None
    remember_repair_candidates(context)
    candidates = context.get("_repair_candidates")
    if isinstance(candidates, list) and len(candidates) >= 2:
        if not context.get("_repair_candidate_selected"):
            err = apply_repair_selection(context)
            if err:
                return err
        picked = context.get("_repair_candidate_selected")
        skipped_ids = set()
        if isinstance(picked, dict):
            skipped_ids = {str(item) for item in (picked.get("skipped") or [])}
        skipped_texts = [
            str(row.get("text") or "")
            for row in candidates
            if isinstance(row, dict) and str(row.get("id") or "") in skipped_ids
        ]
        if _script_includes_skipped(_tool_args_text(tool_args), skipped_texts):
            return "write still includes a skipped repair candidate"
    path, content = _write_payload(name, tool_args)
    if path and content:
        _snapshot_and_note_write(context, path, content)
    return None


def _last_post_selection_verify_status(context: Dict[str, Any]) -> Optional[str]:
    receipts = context.get("_tool_receipts")
    if not isinstance(receipts, list):
        return None
    for row in reversed(receipts):
        if not isinstance(row, dict) or row.get("pre_selection"):
            continue
        tool = str(row.get("tool") or "").strip().lower()
        if tool in _VERIFY_NAMES or row.get("repair_verify"):
            return str(row.get("status") or "").strip().lower()
    return None


def block_extra_repair_verify(
    context: Dict[str, Any],
    tool_name: str,
    tool_args: Any = None,
) -> Optional[str]:
    """Allow one successful verify after multiple candidates; refuse the rest.

    Scores stay caller-supplied. The gate does not rank with a world model.
    A failed measurement may be retried on the same winner. A script that still
    contains a skipped candidate is not executed. Shell/bash only count when the
    command is a check (``pytest``/…) or a ``python`` patch — not ``ls``/``cat``.
    """
    if not isinstance(context, dict):
        return None
    name = str(tool_name or "").strip().lower()
    body = _verify_code_body(tool_args)
    is_shell_tool = name in _SHELL_TOOLS
    if is_shell_tool and not _is_repair_shell_body(body):
        return None
    is_verify_tool = name in _VERIFY_TOOLS or is_shell_tool
    is_verify_skill = name in _VERIFY_SKILLS
    if not is_verify_tool and not is_verify_skill:
        return None
    blob = _tool_args_text(tool_args)
    pending = context.get("_repair_candidates")
    if not (isinstance(pending, list) and len(pending) >= 2):
        rows = _parse_candidate_rows(blob)
        if isinstance(rows, list) and len(rows) >= 2:
            context["_repair_candidates"] = rows
            _stamp_pre_selection_verifies(context)
    remember_repair_candidates(context)
    candidates = context.get("_repair_candidates")
    if not isinstance(candidates, list) or len(candidates) < 2:
        # Skill runners do not carry the patch body; only code/shell scripts are compared.
        if is_verify_tool:
            return _hold_divergent_verify(context, tool_args)
        return None
    if context.get("_repair_verify_used"):
        last = _last_post_selection_verify_status(context)
        if last == "ok":
            return "repair verify already spent on the selected candidate"
        if last == "failed":
            # Same winner may be measured again after a failed run.
            context["_repair_verify_used"] = False
        else:
            # Flag set but no receipt yet — treat as in flight.
            return "repair verify already spent on the selected candidate"
    if not context.get("_repair_candidate_selected"):
        err = apply_repair_selection(context)
        if err:
            return err
    if is_verify_tool:
        picked = context.get("_repair_candidate_selected")
        skipped_ids = set()
        if isinstance(picked, dict):
            skipped_ids = {str(item) for item in (picked.get("skipped") or [])}
        skipped_texts = [
            str(row.get("text") or "")
            for row in candidates
            if isinstance(row, dict) and str(row.get("id") or "") in skipped_ids
        ]
        if _script_includes_skipped(blob, skipped_texts):
            return "verify script still includes a skipped repair candidate"
        if body and not _is_shell_check(body):
            context["_repair_active_script"] = body[:4000]
        note_repair_writes_from_code(context, tool_args)
        capture_repair_fs_baseline(context)
    context["_repair_verify_used"] = True
    context["_repair_verify_mark_next"] = True
    return None


def note_prediction_outcome(
    context: Dict[str, Any],
    *,
    predicted_pass: bool,
    actual_pass: bool,
    candidate_id: str = "",
) -> None:
    """Store predicted-vs-actual. A failed measurement is also a tool receipt."""
    if not isinstance(context, dict) or context.get("_prediction_receipt"):
        return
    row = {
        "predicted_pass": bool(predicted_pass),
        "actual_pass": bool(actual_pass),
        "matched": bool(predicted_pass) == bool(actual_pass),
        "candidate_id": str(candidate_id or "")[:80],
    }
    context["_prediction_receipt"] = row
    record_tool_receipt(
        context,
        tool="prediction_receipt",
        status="ok" if row["actual_pass"] else "failed",
        detail=(
            f"predicted_pass={row['predicted_pass']} actual_pass={row['actual_pass']} "
            f"candidate={row['candidate_id']}"
        ),
    )
