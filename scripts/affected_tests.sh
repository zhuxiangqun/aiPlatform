#!/usr/bin/env bash
# affected_tests.sh — Find test files affected by code changes
# Uses code_graph.blast() for forward impact analysis.
# Usage:
#   bash scripts/affected_tests.sh src/auth.py       # single file
#   git diff --name-only | bash scripts/affected_tests.sh --stdin  # pipe from git

set -euo pipefail

TEST_PATTERNS="${AIPLAT_TEST_PATTERNS:-test_*Test*.py *Test*.tsx *Test*.ts}"
STDIN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --stdin) STDIN=true; shift ;;
        --test-pattern) TEST_PATTERNS="$2"; shift 2 ;;
        *) break ;;
    esac
done

if $STDIN; then
    FILES=$(cat)
else
    FILES="$*"
fi

if [ -z "$FILES" ]; then
    echo "Usage: $0 [--stdin] <file1> [file2...]" >&2
    echo "  or:  git diff --name-only | $0 --stdin" >&2
    exit 1
fi

# Use python to compute blast radius and match test patterns
python3 -c "
import sys, os, fnmatch
sys.path.insert(0, os.path.join(os.path.dirname('$0'), '..', 'aiPlat-core'))

try:
    from core.harness.knowledge.code_graph import repo_root, build_graph, blast, default_roots
    repo = repo_root()
    roots = default_roots()
    abs_roots = [(repo / r).resolve() for r in roots]
    nodes, _, _ = build_graph(repo, abs_roots)

    affected = set()
    files = [f.strip() for f in '''$FILES'''.split('\n') if f.strip()]
    for f in files:
        if f in nodes:
            affected.add(f)
            for reachable in blast(nodes, f):
                affected.add(reachable)

    # Match test patterns
    patterns = '''${TEST_PATTERNS}'''.split()
    test_files = []
    for f in affected:
        for pat in patterns:
            if fnmatch.fnmatch(os.path.basename(f), pat):
                test_files.append(f)
                break
        # Also match files in test directories
        if '/tests/' in f or '/test/' in f or '__tests__' in f:
            if f not in test_files:
                test_files.append(f)

    for f in sorted(set(test_files)):
        print(f)

    if not test_files:
        print('No test files found in blast radius', file=sys.stderr)
        sys.exit(0)

except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
" | sort -u
