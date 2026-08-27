#!/usr/bin/env python3
"""
CLAUDE.md evidence claim validator — enhanced v2.

Extracts grep-based evidence claims from CLAUDE.md, re-executes each grep,
and compares against claimed results.

Supported formats:
  1. （验证：grep -c 'pattern' file → 0）
  2. 验证：`grep -c 'pattern' file → 3`  
  3. <!-- verify: cmd: grep ... expect: 0 operator: eq desc: ... -->

--strict mode: requires every ✅ claim to have a verify block.

Usage:
  python3 scripts/verify_claude_md_evidence.py           # check all CLAUDE.md files
  python3 scripts/verify_claude_md_evidence.py --quick    # skip slow checks
  python3 scripts/verify_claude_md_evidence.py --workspace  # root CLAUDE.md only
  python3 scripts/verify_claude_md_evidence.py --strict   # require verify blocks

Exit codes: 0 = all claims verified, 1 = one or more FAILED
"""
from __future__ import annotations

import os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Pattern 1: （验证：grep ... → N）
EVIDENCE_RE = re.compile(
    r'[（(]验证[：:]\s*'
    r'(?P<cmd>grep\s+[^→]+?)'
    r'\s*→\s*'
    r'(?P<expected>[\d>]+)'
    r'\s*[）)]', re.IGNORECASE)

# ── Pattern 2: 验证：`grep ... → N`  
EVIDENCE_BACKTICK_RE = re.compile(
    r'[（(]?验证[：:]\s*`\s*'
    r'(?P<cmd>grep\s+[^→]+?)'
    r'\s*→\s*'
    r'(?P<expected>[\d>]+)'
    r'\s*`\s*[）)]?', re.IGNORECASE)

# ── Pattern 3: <!-- verify: cmd: ... expect: ... operator: ... -->
HTML_VERIFY_RE = re.compile(
    r'<!--\s*verify:\s*'
    r'cmd:\s*(?P<cmd>[^\n]+?)'
    r'\s*expect:\s*(?P<expected>[\d>]+)'
    r'(?:\s*operator:\s*(?P<operator>eq|gt|lt))?'
    r'(?:\s*desc:\s*(?P<desc>[^\n]+?))?'
    r'\s*-->', re.IGNORECASE)

# ── --strict: unverified ✅ claims
STRICT_RE = re.compile(
    r'✅\s*(?:已修复|已完成|已解决|已实现|已验证|已合入|已部署|已清理|已迁移|已删除)',
    re.IGNORECASE)


def find_claude_md_files() -> list[Path]:
    files = []
    for d in [ROOT] + [ROOT / d for d in ('aiPlat-core', 'aiPlat-platform', 'aiPlat-infra', 'aiPlat-management')]:
        if not d.exists():
            continue
        for f in d.rglob('CLAUDE.md'):
            if '.venv' not in str(f) and 'node_modules' not in str(f):
                files.append(f)
    return files


def extract_claims(filepath: Path) -> list[dict]:
    """Extract all evidence claims from a CLAUDE.md file."""
    content = filepath.read_text(encoding='utf-8')
    lines = content.split('\n')
    claims = []

    # Pattern 1 & 2: inline grep claims
    for i, line in enumerate(lines, 1):
        for pattern in [EVIDENCE_RE, EVIDENCE_BACKTICK_RE]:
            for m in pattern.finditer(line):
                claims.append({
                    'line': i, 'file': str(filepath),
                    'cmd': m.group('cmd').strip(),
                    'expected': m.group('expected').strip(),
                    'operator': 'eq',
                    'raw_line': line.strip(),
                    'format': 'inline',
                })

    # Pattern 3: HTML comment blocks (multi-line)
    for m in HTML_VERIFY_RE.finditer(content):
        line_num = content[:m.start()].count('\n') + 1
        claims.append({
            'line': line_num, 'file': str(filepath),
            'cmd': m.group('cmd').strip(),
            'expected': m.group('expected').strip(),
            'operator': m.group('operator') or 'eq',
            'desc': (m.group('desc') or '').strip(),
            'raw_line': f"<!-- verify: {m.group('desc') or ''} -->",
            'format': 'html',
        })

    return claims


def extract_unverified_strict(filepath: Path) -> list[dict]:
    """In --strict mode: find ✅ claims that lack a verify block on the same or next line."""
    content = filepath.read_text(encoding='utf-8')
    lines = content.split('\n')
    unverified = []
    has_verify_nearby = set()

    # First pass: mark lines that HAVE verification nearby
    for i, line in enumerate(lines):
        if HTML_VERIFY_RE.search(line):
            # This line and the line before it (the claim) are covered
            for offset in range(-2, 3):
                has_verify_nearby.add(i + offset)
        if EVIDENCE_RE.search(line) or EVIDENCE_BACKTICK_RE.search(line):
            has_verify_nearby.add(i)

    # Second pass: find ✅ claims without verification
    for i, line in enumerate(lines):
        if not STRICT_RE.search(line):
            continue
        if i not in has_verify_nearby:
            # Check ±2 lines for verify block
            nearby = False
            for offset in (-2, -1, 1, 2):
                if 0 <= i + offset < len(lines):
                    if '验证' in lines[i + offset] and ('grep' in lines[i + offset] or 'verify:' in lines[i + offset]):
                        nearby = True
                        break
            if not nearby and not any('注' in line[l:l+3] for l in range(len(line)) if line[l:l+2] == '✅'):
                unverified.append({
                    'line': i + 1, 'file': str(filepath),
                    'raw_line': line.strip()[:150],
                })

    return unverified


def run_evidence(cmd_str: str, expected: str, operator: str = 'eq',
                 line_num: int = 0, claude_path: str = '') -> tuple[bool, str, int, str]:
    """Run one evidence command. Returns (passed, detail, actual_num, actual_raw)."""
    workspace_root = str(ROOT)
    cmd_str_resolved = cmd_str.strip()

    # Parse expected value — handle >N and <N prefixes
    exp_val = expected.strip()
    op = operator
    if exp_val.startswith('>'):
        op = 'gt'
        exp_val = exp_val[1:].strip()
    elif exp_val.startswith('<'):
        op = 'lt'
        exp_val = exp_val[1:].strip()
    elif exp_val in ('空', '不存在', 'none', 'None'):
        exp_val = '0'

    try:
        expected_num = int(exp_val)
    except ValueError:
        return False, f"Line {line_num}: Cannot parse expected '{expected}'", -1, ''

    try:
        if '|' in cmd_str_resolved:
            result = subprocess.run(cmd_str_resolved, shell=True,
                                    capture_output=True, text=True,
                                    cwd=workspace_root, timeout=15)
        else:
            parts = cmd_str_resolved.split()
            result = subprocess.run(parts, capture_output=True, text=True,
                                    cwd=workspace_root, timeout=15)

        stdout = result.stdout.strip() if result.stdout else ''
        actual_num = int(stdout) if stdout.isdigit() else (len(stdout.split('\n')) if stdout else 0)

        if op == 'gt':
            passed = actual_num > expected_num
            detail = f"got {actual_num} (need >{expected_num})"
        elif op == 'lt':
            passed = actual_num < expected_num
            detail = f"got {actual_num} (need <{expected_num})"
        else:
            passed = actual_num == expected_num
            detail = f"got {actual_num} (expected {expected_num})"

        return passed, detail, actual_num, stdout
    except subprocess.TimeoutExpired:
        return False, f"Line {line_num}: Command timed out after 15s", -1, ''
    except Exception as e:
        return False, f"Line {line_num}: Error: {e}", -1, ''


def build_evidence_tree(files: list[Path], quick_mode: bool = False) -> dict:
    """Build a hierarchical evidence tree (HarnessEval Evidence Tree pattern).

    Structure: root → per-file branch → per-claim sub_branch → evidence leaf.
    Includes route_reason (why this check was enabled), verdict per node, and
    known_gaps (✅ claims without verification — the evaluator's explicit blind spots).
    """
    all_claims = []
    for f in files:
        all_claims.extend(extract_claims(f))

    by_file: dict[str, list[dict]] = {}
    for c in all_claims:
        by_file.setdefault(c['file'], []).append(c)

    branches = []
    totals = {'pass': 0, 'fail': 0, 'skip': 0}
    for fpath in sorted(by_file):
        fname = os.path.relpath(fpath, ROOT)
        sub = []
        file_pass = True
        for claim in by_file[fpath]:
            node = {
                'claim': claim.get('desc') or claim['cmd'][:80],
                'skill': 'claude_md_evidence.grep',
                'route_reason': (
                    f"{'HTML 注释' if claim['format'] == 'html' else '内联'}证据声明"
                    f"（{fname}:L{claim['line']}）"
                ),
                'evidence': [],
                'verdict': 'pass',
            }
            if quick_mode and len(claim['cmd']) > 200:
                node['verdict'] = 'skipped'
                node['evidence'].append({
                    'tool': 'shell',
                    'input': claim['cmd'][:200],
                    'expect': claim['expected'],
                    'operator': claim.get('operator', 'eq'),
                    'status': 'skipped',
                    'note': 'quick 模式跳过长命令',
                })
                totals['skip'] += 1
                sub.append(node)
                continue

            passed, detail, actual_num, actual_raw = run_evidence(
                claim['cmd'], claim['expected'], claim.get('operator', 'eq'),
                claim['line'], claim['file'])
            node['evidence'].append({
                'tool': 'shell:grep',
                'input': claim['cmd'],
                'expect': claim['expected'],
                'operator': claim.get('operator', 'eq'),
                'actual': actual_num,
                'raw': actual_raw[:200],
                'status': 'pass' if passed else 'fail',
                'detail': detail,
            })
            node['verdict'] = 'pass' if passed else 'fail'
            if passed:
                totals['pass'] += 1
            else:
                totals['fail'] += 1
                file_pass = False
            sub.append(node)

        branches.append({
            'claim': f"CLAUDE.md 文件 {fname} 的证据声明全部通过",
            'skill': 'claude_md_evidence.file_verify',
            'route_reason': '文件包含（验证：grep …）或 <!-- verify: --> 证据声明',
            'sub_branches': sub,
            'verdict': 'pass' if file_pass else 'fail',
        })

    # ── known_gaps: ✅ claims without verification (evaluator's explicit blind spots) ──
    known_gaps = []
    for f in files:
        for u in extract_unverified_strict(f):
            known_gaps.append({
                'claim': u['raw_line'][:150],
                'file': os.path.relpath(u['file'], ROOT),
                'line': u['line'],
                'gap': '✅ 声明未附带可执行验证（缺少 grep/验证命令）',
            })

    total = totals['pass'] + totals['fail'] + totals['skip']
    verdict = 'pass' if totals['fail'] == 0 else 'fail'
    return {
        'case_id': f"claude-md-evidence@{__import__('datetime').date.today().isoformat()}",
        'harness': 'verify_claude_md_evidence.py',
        'verdict': {
            'score': 1.0 if verdict == 'pass' else 0.0,
            'confidence': 'high' if totals['fail'] == 0 and not known_gaps else 'medium',
            'summary': (f"{totals['pass']} passed, {totals['fail']} failed, "
                        f"{totals['skip']} skipped, {len(known_gaps)} known_gaps"),
        },
        'branches': branches,
        'known_gaps': known_gaps,
    }


def main() -> int:
    quick_mode = '--quick' in sys.argv
    workspace_only = '--workspace' in sys.argv
    strict_mode = '--strict' in sys.argv
    tree_mode = '--tree' in sys.argv
    tree_out = ''
    if '--out' in sys.argv:
        idx = sys.argv.index('--out')
        if idx + 1 < len(sys.argv):
            tree_out = sys.argv[idx + 1]

    if workspace_only:
        files = [ROOT / 'CLAUDE.md']
        if not files[0].exists():
            files = []
    else:
        files = find_claude_md_files()

    # ── Evidence Tree mode: hierarchical JSON (HarnessEval pattern) ──
    if tree_mode:
        import json
        tree = build_evidence_tree(files, quick_mode)
        payload = json.dumps(tree, ensure_ascii=False, indent=2)
        if tree_out:
            Path(tree_out).parent.mkdir(parents=True, exist_ok=True)
            Path(tree_out).write_text(payload, encoding='utf-8')
            print(f"Evidence tree written to {tree_out}")
            print(f"  {tree['verdict']['summary']}")
        else:
            print(payload)
        return 0 if tree['verdict']['score'] == 1.0 else 1

    # ── Strict: find unverified claims ──
    strict_failures = 0
    if strict_mode:
        for f in files:
            uv = extract_unverified_strict(f)
            if uv:
                fname = os.path.relpath(f, ROOT)
                print(f"[STRICT] {fname}: {len(uv)} unverified ✅ claims:")
                for u in uv[:10]:
                    print(f"  L{u['line']}: {u['raw_line'][:120]}")
                strict_failures += len(uv)
        if strict_failures:
            print(f"\n❌ --strict: {strict_failures} claims lack verification. Add <!-- verify: --> blocks.")
            return 1

    # ── Normal: run evidence ──
    all_claims = []
    for f in files:
        all_claims.extend(extract_claims(f))

    if not all_claims:
        print("No evidence claims found in CLAUDE.md files.")
        return 0 if not strict_failures else 1

    print(f"Found {len(all_claims)} evidence claims in {len(files)} CLAUDE.md file(s):\n")

    failures, passes, skipped = 0, 0, 0
    for claim in all_claims:
        fname = os.path.relpath(claim['file'], ROOT)
        label = claim.get('desc') or claim['cmd'][:80]
        print(f"  [{fname}:{claim['line']}] {label}")

        if quick_mode and len(claim['cmd']) > 200:
            print(f"    ⏭ SKIP (quick mode, long command)")
            skipped += 1
            continue

        passed, detail, actual_num, actual_raw = run_evidence(
            claim['cmd'], claim['expected'], claim.get('operator', 'eq'),
            claim['line'], claim['file'])
        if passed:
            print(f"    ✅ PASS ({detail})")
            passes += 1
        else:
            print(f"    ❌ FAIL ({detail})")
            print(f"       Cmd: {claim['cmd'][:120]}")
            failures += 1

    print(f"\nResults: {passes} passed, {failures} failed, {skipped} skipped")
    if strict_failures:
        print(f"Strict: {strict_failures} unverified claims")
    if failures:
        print("\n❌ CLAUDE.md is out of sync.")
        return 1
    print("\n✅ All evidence claims verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
