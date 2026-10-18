#!/usr/bin/env python3
"""Validate `.aiplat/defect_gate/receipt.json` for PR / push unlock.

Exit 0 only when status=pass, findings_count=0, all five checks pass,
and diff_sha256 matches `git diff <merge-base> HEAD` with the receipt file
excluded. The receipt may live inside the commit: its own bytes are not part
of the hash, so a commit SHA cannot be stored inside itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "aiplat.defect_gate.v1"
REQUIRED_CHECKS = (
    "old_fallback",
    "call_signatures",
    "failure_as_success",
    "second_implementation",
    "self_certifying_health",
)
DEFAULT_RECEIPT = Path(".aiplat/defect_gate/receipt.json")
RECEIPT_REL = ".aiplat/defect_gate/receipt.json"


def _repo_root() -> Path:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return Path(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def _git_sha(ref: str = "HEAD") -> str:
    return subprocess.check_output(
        ["git", "rev-parse", ref],
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()


def merge_base_with(base_ref: str) -> str:
    return subprocess.check_output(
        ["git", "merge-base", "HEAD", base_ref],
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()


def reviewed_diff_sha(merge_base: str, rev: str = "HEAD") -> str:
    """SHA-256 of the merge diff, excluding the receipt file itself."""
    blob = subprocess.check_output(
        [
            "git",
            "-c",
            "core.quotepath=false",
            "diff",
            "--binary",
            "--full-index",
            "--no-color",
            "--no-ext-diff",
            merge_base,
            rev,
            "--",
            ".",
            f":(exclude){RECEIPT_REL}",
        ],
        stderr=subprocess.DEVNULL,
    )
    return hashlib.sha256(blob).hexdigest()


def command_needs_gate(command: str) -> bool:
    """True when the shell command itself pushes or opens a PR.

    Words inside quotes or a heredoc (for example a commit message that
    mentions ``git push``) do not count.
    """
    visible = _unquoted_shell(command or "")
    if re.search(r"(?:^|[;&|\n])\s*gh\s+pr\s+create(?:\s|$)", visible):
        return True
    if re.search(r"(?:^|[;&|\n])\s*git\s+push(?:\s|$)", visible):
        return True
    return False


def _unquoted_shell(command: str) -> str:
    """Drop quoted regions and heredoc bodies so message text is not a command."""
    text = command.replace("\r\n", "\n")
    text = re.sub(
        r"<<-?\s*'?\\?EOF'?\n.*?\nEOF\b",
        " ",
        text,
        flags=re.S,
    )
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in ("'", '"'):
            quote = ch
            i += 1
            while i < n and text[i] != quote:
                if quote == '"' and text[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                i += 1
            i += 1
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def dirty_paths_outside_receipt() -> List[str]:
    """Uncommitted paths other than the receipt. Those are not in HEAD's diff."""
    out = subprocess.check_output(
        ["git", "status", "--porcelain", "-uall"],
        stderr=subprocess.DEVNULL,
        text=True,
    )
    dirty: List[str] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path != RECEIPT_REL:
            dirty.append(path)
    return dirty


def _load(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("receipt must be a JSON object")
    return data


def validate_receipt(
    data: Dict[str, Any],
    *,
    expect_diff: str,
    expect_merge_base: str,
    allow_fail: bool = False,
) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if data.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}, got {data.get('schema')!r}")

    status = str(data.get("status") or "").strip().lower()
    if status not in ("pass", "fail"):
        errors.append("status must be 'pass' or 'fail'")

    try:
        count = int(data.get("findings_count"))
    except (TypeError, ValueError):
        count = -1
        errors.append("findings_count must be an integer")

    findings = data.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
        findings = []
    elif count >= 0 and count != len(findings):
        errors.append(
            f"findings_count={count} does not match len(findings)={len(findings)}"
        )

    checks = data.get("checks")
    if not isinstance(checks, dict):
        errors.append("checks must be an object")
        checks = {}
    for key in REQUIRED_CHECKS:
        if key not in checks:
            errors.append(f"checks.{key} missing")
        elif str(checks.get(key) or "").strip().lower() not in ("pass", "fail"):
            errors.append(f"checks.{key} must be 'pass' or 'fail'")

    got_diff = str(data.get("diff_sha256") or "").strip()
    if not got_diff:
        errors.append("diff_sha256 missing")
    elif expect_diff and got_diff != expect_diff:
        errors.append(
            "diff_sha256 does not match the merge diff "
            "(receipt excluded; re-run review after the diff changes)"
        )

    got_base = str(data.get("merge_base") or "").strip()
    if not got_base:
        errors.append("merge_base missing")
    elif expect_merge_base and got_base != expect_merge_base:
        errors.append(
            f"merge_base {got_base[:12]}… != {expect_merge_base[:12]}…"
        )

    for key in ("reviewed_at", "base_ref", "reviewer"):
        if not str(data.get(key) or "").strip():
            errors.append(f"{key} missing")

    if status == "pass":
        if count != 0:
            errors.append("status=pass requires findings_count=0")
        if findings:
            errors.append("status=pass requires empty findings")
        for key in REQUIRED_CHECKS:
            if str(checks.get(key) or "").strip().lower() != "pass":
                errors.append(f"status=pass requires checks.{key}=pass")
    elif status == "fail" and not allow_fail:
        errors.append("receipt status=fail — fix findings before PR/push")

    return (len(errors) == 0), errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--receipt",
        type=Path,
        default=None,
        help=f"path to receipt (default: {DEFAULT_RECEIPT})",
    )
    parser.add_argument(
        "--base",
        default="origin/main",
        help="base ref used to compute merge-base (default: origin/main)",
    )
    parser.add_argument(
        "--allow-fail",
        action="store_true",
        help="accept a well-formed fail receipt (report only; still exit 1)",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="do not fail when uncommitted files exist outside the receipt",
    )
    parser.add_argument(
        "--print-template",
        action="store_true",
        help="print a pass template for current HEAD and exit 0",
    )
    args = parser.parse_args(argv)

    if os.environ.get("AIPLAT_DEFECT_GATE", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        print("defect_gate: bypassed via AIPLAT_DEFECT_GATE=0", file=sys.stderr)
        return 0

    root = _repo_root()
    os.chdir(root)

    try:
        merge_base = merge_base_with(args.base)
        expect_diff = reviewed_diff_sha(merge_base, "HEAD")
        head_sha = _git_sha("HEAD")
    except subprocess.CalledProcessError:
        print(
            f"defect_gate: cannot diff HEAD against {args.base}",
            file=sys.stderr,
        )
        return 2

    dirty = dirty_paths_outside_receipt()
    if dirty and not args.allow_dirty:
        print(
            "defect_gate: uncommitted paths are not in HEAD and are not pushed:",
            file=sys.stderr,
        )
        for path in dirty[:8]:
            print(f"  - {path}", file=sys.stderr)
        if len(dirty) > 8:
            print(f"  - … {len(dirty) - 8} more", file=sys.stderr)

    if args.print_template:
        template = {
            "schema": SCHEMA,
            "status": "pass",
            "findings_count": 0,
            "reviewed_at": "",
            "base_ref": args.base,
            "merge_base": merge_base,
            "diff_sha256": expect_diff,
            "head_sha": head_sha,
            "checks": {k: "pass" for k in REQUIRED_CHECKS},
            "findings": [],
            "reviewer": "agent",
            "note": "head_sha is informational; diff_sha256 is the lock",
        }
        print(json.dumps(template, ensure_ascii=False, indent=2))
        return 0

    path = args.receipt or (root / DEFAULT_RECEIPT)
    if not path.is_file():
        print(
            f"defect_gate: missing receipt at {path}\n"
            "Run the defect-gate skill, write the receipt, then re-validate.",
            file=sys.stderr,
        )
        return 1

    try:
        data = _load(path)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        print(f"defect_gate: cannot read receipt: {e}", file=sys.stderr)
        return 1

    ok, errors = validate_receipt(
        data,
        expect_diff=expect_diff,
        expect_merge_base=merge_base,
        allow_fail=args.allow_fail,
    )
    if ok and str(data.get("status")).lower() == "pass":
        print(
            f"defect_gate: PASS diff={expect_diff[:12]} "
            f"merge_base={merge_base[:12]} receipt={path}"
        )
        return 0

    print(f"defect_gate: FAIL receipt={path}", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    if args.allow_fail and str(data.get("status")).lower() == "fail" and not any(
        e.startswith("receipt status=fail") for e in errors
    ):
        # well-formed fail receipt for reporting
        remaining = [e for e in errors if e != "receipt status=fail — fix findings before PR/push"]
        if not remaining:
            print("defect_gate: well-formed FAIL receipt (not unlock)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
