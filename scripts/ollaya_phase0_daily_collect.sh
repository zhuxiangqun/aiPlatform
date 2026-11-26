#!/usr/bin/env bash
# Ollaya Phase 0 — daily route-stats + decision_shadow status scrape.
#
# Purpose: keep a ≥7-day observation window ledger for 0.6 Go/No-Go.
# Honesty: scrape ≠ sampling Go; enabled must stay false; ≠ hang classify; ≠ 1b.
#
# Usage:
#   CORE_BASE=http://127.0.0.1:8002 ENV_LABEL=dev \
#     bash scripts/ollaya_phase0_daily_collect.sh
#   CORE_BASE=https://staging.example/core ENV_LABEL=staging \
#     bash scripts/ollaya_phase0_daily_collect.sh
#
# Cron example (local):
#   15 9 * * * cd /path/to/aiPlatform && CORE_BASE=… ENV_LABEL=staging \
#     bash scripts/ollaya_phase0_daily_collect.sh >>.aiplat/ollaya_phase0/cron.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CORE_BASE="${CORE_BASE:-http://127.0.0.1:8002}"
ENV_LABEL="${ENV_LABEL:-dev}"
# 本地运行时目录（已 gitignore；台账在 reports/…/ollaya-window-ledger.md）
OUT_DIR="${OLLAYA_PHASE0_DIR:-.aiplat/ollaya_phase0}"
mkdir -p "$OUT_DIR"

TS_UTC="$(date -u +"%Y-%m-%dT%H:%MZ")"
TS_LOCAL="$(date +"%Y-%m-%dT%H:%M%z")"
WINDOW="${WINDOW_LABEL:-${TS_LOCAL} daily}"

echo "# ollaya daily collect env=${ENV_LABEL} base=${CORE_BASE} at=${TS_LOCAL}"

PYTHONPATH="${PYTHONPATH:-}:aiPlat-core:aiPlat-infra:aiPlat-platform" \
  python3 scripts/collect_domain_router_route_stats.py \
    --base "$CORE_BASE" \
    --env "$ENV_LABEL" \
    --window "$WINDOW" \
    --jsonl "$OUT_DIR/route_stats.jsonl" \
  | tee "$OUT_DIR/last_route_stats.md"

SHADOW_URL="${CORE_BASE%/}/api/core/diagnostics/decision-shadow/status"
SHADOW_JSON="$OUT_DIR/decision_shadow_status.jsonl"
if curl -fsS -m 5 "$SHADOW_URL" -o "$OUT_DIR/last_decision_shadow.json"; then
  python3 - <<PY
import json
from pathlib import Path
p = Path("$OUT_DIR/last_decision_shadow.json")
d = json.loads(p.read_text(encoding="utf-8"))
d["_scraped_from"] = "$SHADOW_URL"
d["_scraped_at"] = "$TS_UTC"
d["_env"] = "$ENV_LABEL"
with Path("$SHADOW_JSON").open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(d, ensure_ascii=False) + "\n")
enabled = d.get("enabled")
wired = d.get("classify_hook_wired")
print(f"shadow ok={d.get('ok')} enabled={enabled} classify_hook_wired={wired}")
if enabled is True or wired is True:
    raise SystemExit("honesty fail: shadow enabled or classify hooked during prep window")
PY
else
  echo "WARN: decision-shadow status unreachable: $SHADOW_URL" >&2
fi

LEDGER="${LEDGER_PATH:-reports/architecture/human-gates/ollaya-window-ledger.md}"
if [[ -f "$LEDGER" ]]; then
  ROW=$(tail -n 1 "$OUT_DIR/last_route_stats.md" || true)
  if [[ "$ROW" == \|* ]]; then
    # Idempotent-ish: skip if exact window already present
    if ! grep -F "| ${ENV_LABEL} | ${WINDOW} |" "$LEDGER" >/dev/null 2>&1; then
      # Insert before the ## Honesty section if present, else append
      if grep -q '^## Honesty' "$LEDGER"; then
        python3 - <<PY
from pathlib import Path
ledger = Path("$LEDGER")
text = ledger.read_text(encoding="utf-8")
row = """$ROW""".strip()
marker = "## Honesty"
if row in text:
    print("ledger: skip duplicate")
elif marker not in text:
    print("ledger: skip (no Honesty marker)")
else:
    # 插在 Honesty 前；若表尾有空行则吃掉，保持 markdown 表连续
    idx = text.index(marker)
    head, tail = text[:idx].rstrip("\n"), text[idx:]
    ledger.write_text(head + "\n" + row + "\n\n" + tail, encoding="utf-8")
    print(f"ledger: appended row under table → {ledger}")
PY
      else
        echo "$ROW" >>"$LEDGER"
        echo "ledger: appended → $LEDGER"
      fi
    else
      echo "ledger: skip duplicate window row"
    fi
  fi
fi

echo "done: jsonl=$OUT_DIR/route_stats.jsonl shadow=$SHADOW_JSON"
echo "honesty: scrape≠sampling Go; keep enabled=false; staging URL still required for Go"
