#!/usr/bin/env bash
# verify_capability_counts.sh
# Phase 42: Prevent capability count drift across documents.
#
# Extracts the authoritative count from AIPLAT_CAPABILITIES.md statistics table,
# then verifies no other document hardcodes a different number.
#
# Exit 0 = clean, exit 1 = drift detected (with diff to fix).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CAP_FILE="$ROOT/AIPLAT_CAPABILITIES.md"

if ! [ -f "$CAP_FILE" ]; then
    echo "ERROR: AIPLAT_CAPABILITIES.md not found at $CAP_FILE" >&2
    exit 1
fi

# Extract authoritative count from statistics table
# Pattern: | **总计** | **776** | **0** | **776** |
AUTH_COUNT=$(grep '总计' "$CAP_FILE" | head -1 | grep -oE '[0-9]{3,4}' | head -1)

if [ -z "$AUTH_COUNT" ] || ! [[ "$AUTH_COUNT" =~ ^[0-9]+$ ]]; then
    echo "ERROR: Could not extract authoritative count from CAPABILITIES.md stats table" >&2
    exit 1
fi

echo "[verify] Authoritative capability count: $AUTH_COUNT"

VIOLATIONS=0

# Check for hardcoded counts in other files (only check committed doc files)
for f in CLAUDE.md README.md AIPLAT_ROADMAP.md; do
    if ! [ -f "$ROOT/$f" ]; then continue; fi
    # Find lines with "X项" patterns that look like hardcoded capability counts
    HARDCODED=$(grep -n '[0-9][0-9][0-9]项' "$ROOT/$f" | grep -v 'CAPABILITIES\|能力计数\|计数见\|唯一真相' || true)
    if [ -n "$HARDCODED" ]; then
        echo "[VIOLATION] $f has hardcoded capability references that may drift:"
        echo "$HARDCODED" | while read -r line; do
            echo "  $line"
        done
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
done

# Check docs/ for hardcoded counts
for f in docs/DOCUMENT_SYSTEM.md docs/reports/AIPLAT_ARCHITECTURE_REPORT.md docs/architecture/comparison.md; do
    if ! [ -f "$ROOT/$f" ]; then continue; fi
    HARDCODED=$(grep -n '[0-9][0-9][0-9]项' "$ROOT/$f" | grep -v 'CAPABILITIES\|能力计数\|计数见\|唯一真相\|grep.*✅' || true)
    if [ -n "$HARDCODED" ]; then
        echo "[VIOLATION] $f has hardcoded capability references that may drift:"
        echo "$HARDCODED" | while read -r line; do
            echo "  $line"
        done
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
done

if [ "$VIOLATIONS" -gt 0 ]; then
    echo ""
    echo "❌ $VIOLATIONS file(s) with hardcoded capability counts."
    echo "   Fix: Replace hardcoded numbers with '详见 AIPLAT_CAPABILITIES.md' or verify they match $AUTH_COUNT."
    exit 1
fi
echo "✅ All documents reference AIPLAT_CAPABILITIES.md — no capability count drift."

# ── Phase 42: FDE doc stale version markers ──
FDE_DIR="$ROOT/docs/manuals/fde"
if [ -d "$FDE_DIR" ]; then
    FDE_STALE=$(grep -rn 'v2\.[0-9]\|v2\.[0-9]+.*\：' "$FDE_DIR" --include='*.md' | grep -v '_archive\|examples/\|templates/' || true)
    if [ -n "$FDE_STALE" ]; then
        echo ""
        echo "⚠️  FDE docs contain stale version markers (consider removing for sync):"
        echo "$FDE_STALE" | while read -r line; do
            echo "  $line"
        done
        echo "  Fix: Remove version stamps like 'v2.7' 'v2.5+' from section titles and descriptions."
        echo "       Version history belongs in the whitepaper, not operational manuals."
        echo "  (This is a WARNING — not a blocking error. Set BLOCK_FDE_STALE_VERSIONS=1 to block.)"
        if [ "${BLOCK_FDE_STALE_VERSIONS:-}" = "1" ]; then
            exit 1
        fi
    else
        echo "✅ FDE docs clean — no stale version markers."
    fi
fi

exit 0
