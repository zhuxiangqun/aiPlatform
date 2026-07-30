#!/usr/bin/env python3
"""
CLAUDE.md evidence claim validator.

Extracts all grep-based evidence claims from CLAUDE.md files, re-executes
each grep command, and compares the actual output against the claimed result.

Usage:
  python3 scripts/verify_claude_md_evidence.py           # check all CLAUDE.md files
  python3 scripts/verify_claude_md_evidence.py --quick    # faster, skip slow checks
  python3 scripts/verify_claude_md_evidence.py --workspace  # only workspace root CLAUDE.md

Exit codes: 0 = all claims verified, 1 = one or more claims FAILED
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Patterns to extract evidence claims
# Matches lines like: （验证：grep -c '/api/core/fde' FdeDashboard.tsx → 0）
# or: （验证：grep -rn "tenant_id" retrieval.py | wc -l → >0）
EVIDENCE_RE = re.compile(
    r'[（(]验证[：:]\s*'
    r'(?P<cmd>grep\s+[^→]+?)'
    r'\s*→\s*'
    r'(?P<expected>[\d>]+)'
    r'\s*[）)]',
    re.IGNORECASE
)

# Also match the older format: 验证：`grep -c 'env-legacy' auto_trigger.py → 3`
EVIDENCE_BACKTICK_RE = re.compile(
    r'[（(]?验证[：:]\s*`\s*'
    r'(?P<cmd>grep\s+[^→]+?)'
    r'\s*→\s*'
    r'(?P<expected>[\d>]+)'
    r'\s*`\s*[）)]?',
    re.IGNORECASE
)


def resolve_path(rel_path: str, cmd_cwd: str) -> Path:
    """Resolve a relative path from a grep command against workspace root."""
    p = Path(rel_path)

    # Handle ~/ paths
    if rel_path.startswith('~/') or rel_path.startswith('~/'):
        return Path(os.path.expanduser(rel_path))

    if p.is_absolute():
        return p

    # Try relative to workspace root first
    candidate = ROOT / rel_path
    if candidate.exists() or '*' in rel_path:
        return candidate

    # Try relative to the directory of the CLAUDE.md file
    candidate = Path(cmd_cwd) / rel_path
    return candidate


def parse_grep_cmd(cmd_str: str, cmd_cwd: str) -> tuple[list[str], str, str] | None:
    """Parse a grep command string into argv, expected value, and operator."""
    cmd_str = cmd_str.strip()

    # Determine the expected value
    parts = cmd_str.split('|')
    if len(parts) > 1 and 'wc -l' in parts[-1]:
        # It's a piped command ending with wc -l
        pass
    else:
        # It's a direct grep -c (count)
        pass

    # Build the subprocess command
    # Replace grep with actual grep (using -E for portability)
    tokens = cmd_str.split()
    argv = []

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ('|', 'wc', '-l'):
            # We'll handle piping ourselves for wc -l cases
            break
        if tok == 'grep':
            argv.append('grep')
            argv.append('-E')  # Force -E for cross-platform compatibility
        elif tok.startswith('"') or tok.startswith("'"):
            # Quoted argument - strip quotes
            argv.append(tok.strip('"\''))
        else:
            argv.append(tok)
        i += 1

    return argv


def run_evidence(cmd_str: str, expected: str, line_num: int, claude_path: str, cmd_cwd: str) -> tuple[bool, str]:
    """Execute a grep command and compare against expected result.

    Returns (passed: bool, detail: str).
    """
    workspace_root = str(ROOT)

    # Replace path references relative to workspace
    # Detect the grep path argument (last non-flag argument)
    cmd_str_resolved = cmd_str.strip()

    # Parse expected value
    expected_val = expected.strip()
    operator = 'eq'
    if expected_val.startswith('>'):
        operator = 'gt'
        expected_val = expected_val[1:].strip()
    elif expected_val.startswith('<'):
        operator = 'lt'
        expected_val = expected_val[1:].strip()

    try:
        expected_num = int(expected_val)
    except ValueError:
        return False, f"Line {line_num}: Cannot parse expected value '{expected}'"

    # Execute the grep command from workspace root
    try:
        # Handle piped commands (grep ... | something)
        if '|' in cmd_str_resolved:
            # Use shell=True for piped commands
            result = subprocess.run(
                cmd_str_resolved,
                shell=True,
                capture_output=True,
                text=True,
                cwd=workspace_root,
                timeout=15,
            )
        else:
            # Split into argv
            parts = cmd_str_resolved.split()
            result = subprocess.run(
                parts,
                capture_output=True,
                text=True,
                cwd=workspace_root,
                timeout=15,
            )

        # Parse output
        stdout = result.stdout.strip() if result.stdout else ''

        if stdout == '':
            actual_num = 0
        else:
            # Extract first number from output
            nums = re.findall(r'\d+', stdout)
            actual_num = int(nums[0]) if nums else 0

        # Compare
        if operator == 'gt':
            passed = actual_num > expected_num
            detail = f"expected >{expected_num}, got {actual_num}"
        elif operator == 'lt':
            passed = actual_num < expected_num
            detail = f"expected <{expected_num}, got {actual_num}"
        else:
            passed = actual_num == expected_num
            detail = f"expected {expected_num}, got {actual_num}"

        return passed, detail

    except subprocess.TimeoutExpired:
        return False, f"Line {line_num}: Command timed out"
    except FileNotFoundError as e:
        return False, f"Line {line_num}: Command not found: {e}"
    except Exception as e:
        return False, f"Line {line_num}: Error executing: {e}"


def find_claude_md_files() -> list[Path]:
    """Find all CLAUDE.md files in the workspace."""
    files = []
    for pattern in ['CLAUDE.md', '*/CLAUDE.md', '*/*/CLAUDE.md']:
        for p in ROOT.glob(pattern):
            if p.is_file() and '.venv' not in str(p) and 'node_modules' not in str(p):
                files.append(p)
    return sorted(set(files))


def extract_claims(filepath: Path) -> list[dict]:
    """Extract all evidence claims from a CLAUDE.md file."""
    claims = []
    content = filepath.read_text(encoding='utf-8')
    lines = content.split('\n')
    cmd_cwd = str(filepath.parent)

    for i, line in enumerate(lines, 1):
        # Try both regex patterns
        for pattern in [EVIDENCE_RE, EVIDENCE_BACKTICK_RE]:
            for m in pattern.finditer(line):
                cmd = m.group('cmd').strip()
                expected = m.group('expected').strip()
                claims.append({
                    'line': i,
                    'file': str(filepath),
                    'cmd': cmd,
                    'expected': expected,
                    'raw_line': line.strip(),
                    'cmd_cwd': cmd_cwd,
                })

    return claims


def main() -> int:
    quick_mode = '--quick' in sys.argv
    workspace_only = '--workspace' in sys.argv

    if workspace_only:
        files = [ROOT / 'CLAUDE.md']
    else:
        files = find_claude_md_files()

    all_claims = []
    for f in files:
        all_claims.extend(extract_claims(f))

    if not all_claims:
        print("No evidence claims found in CLAUDE.md files.")
        return 0

    print(f"Found {len(all_claims)} evidence claims in {len(files)} CLAUDE.md file(s):")
    print()

    failures = 0
    passes = 0
    skipped = 0

    for claim in all_claims:
        fname = os.path.relpath(claim['file'], ROOT)
        print(f"  [{fname}:{claim['line']}] {claim['cmd'][:80]}...")

        if quick_mode and len(claim['cmd']) > 200:
            print(f"    ⏭ SKIP (quick mode, long command)")
            skipped += 1
            continue

        passed, detail = run_evidence(
            claim['cmd'],
            claim['expected'],
            claim['line'],
            claim['file'],
            claim['cmd_cwd'],
        )

        if passed:
            print(f"    ✅ PASS ({detail})")
            passes += 1
        else:
            print(f"    ❌ FAIL ({detail})")
            print(f"       Claim: '{claim['raw_line'][:120]}'")
            failures += 1

    print()
    print(f"Results: {passes} passed, {failures} failed, {skipped} skipped")

    if failures > 0:
        print(f"\n❌ {failures} evidence claim(s) are FALSE. CLAUDE.md is out of sync.")
        print("   Re-run without --quick for full details.")
        return 1

    print("\n✅ All evidence claims verified against actual code.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
