#!/usr/bin/env bash
# Kick off PG/HA staging live drill (OPS_HANDOFF first knife).
# Records unsigned live-*.json only when prerequisites look present.
# Never sets production_signed / checklist ✅ / cutover_authorized.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

STAMP="$(date -u +%Y%m%d)"
export AIPLAT_LIVE_DRILL_ID="${AIPLAT_LIVE_DRILL_ID:-pgha-live-${STAMP}}"
export AIPLAT_LIVE_DRILL_ENV="${AIPLAT_LIVE_DRILL_ENV:-staging}"
export AIPLAT_LIVE_DRILL_OPERATOR="${AIPLAT_LIVE_DRILL_OPERATOR:-${USER:-ops}}"
mkdir -p "$ROOT/reports/five-products/ops"
export AIPLAT_PGHA_RUNLOG="${AIPLAT_PGHA_RUNLOG:-$ROOT/reports/five-products/ops/PGHA_LIVE_RUNLOG.md}"

echo "== PG/HA live kickoff (does not authorize) =="

"$PY" - <<'PY'
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

root = Path(".").resolve()
runlog = Path(os.environ["AIPLAT_PGHA_RUNLOG"])
drill_id = os.environ["AIPLAT_LIVE_DRILL_ID"]
env_name = os.environ["AIPLAT_LIVE_DRILL_ENV"]
operator = os.environ["AIPLAT_LIVE_DRILL_OPERATOR"]
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

blockers: list[str] = []
notes: list[str] = []

dsn = (os.environ.get("AIPLAT_PG_DSN") or os.environ.get("DATABASE_URL") or "").strip()
if not dsn:
    blockers.append("missing AIPLAT_PG_DSN (or DATABASE_URL) for staging/prod-canary Postgres")
else:
    notes.append("DSN present (value redacted)")

oidc = (os.environ.get("AIPLAT_OIDC_ISSUER") or os.environ.get("OIDC_ISSUER") or "").strip()
if not oidc:
    blockers.append("missing AIPLAT_OIDC_ISSUER (or OIDC_ISSUER) for tenant login / MFA path")
else:
    notes.append("OIDC issuer present (value redacted)")

if env_name.lower() in {"scaffold", "local", "temp", "tmp", "docker-ephemeral", "lab"}:
    blockers.append(f"AIPLAT_LIVE_DRILL_ENV={env_name!r} is not a production-class environment")

docker_ok = bool(shutil.which("docker")) and subprocess.call(
    ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
) == 0
notes.append(f"docker_available={docker_ok} (local/docker ≠ live authorize evidence)")

can_record = len(blockers) == 0
record_path = None
if can_record:
    env = os.environ.copy()
    rc = subprocess.call(
        ["bash", "packages/aiplat-central/scripts/pg_ha_record_live_drill.sh"],
        env=env,
    )
    if rc != 0:
        blockers.append(f"pg_ha_record_live_drill.sh exited {rc}")
        can_record = False
    else:
        record_path = root / f"packages/aiplat-central/docs/pg_ha/drills/live-{drill_id}.json"

lines = [
    "# PG/HA Live Kickoff Runlog",
    "",
    f"- recorded_at: `{now}`",
    f"- drill_id: `{drill_id}`",
    f"- environment: `{env_name}`",
    f"- operator: `{operator}`",
    "- cutover_authorized: **false** (unchanged)",
    "",
    "## Prerequisites",
    "",
]
for n in notes:
    lines.append(f"- note: {n}")
if blockers:
    lines += [
        "",
        "## Blockers (must clear before live evidence / sign / authorize)",
        "",
    ]
    for b in blockers:
        lines.append(f"- [ ] {b}")
    lines += [
        "",
        "Set e.g.:",
        "",
        "```bash",
        "export AIPLAT_LIVE_DRILL_ENV=staging",
        "export AIPLAT_LIVE_DRILL_OPERATOR=$USER",
        "export AIPLAT_PG_DSN='postgresql://…@staging-host/aiplat'",
        "export AIPLAT_OIDC_ISSUER='https://…/realms/…'",
        "bash scripts/ops_pgha_live_kickoff.sh",
        "```",
    ]
else:
    lines += [
        "",
        "## Record",
        "",
        f"- live file: `{record_path}`",
        "- production_signed: false",
        "- next: fill items → `bash scripts/ops_live_sign.sh validate|sign <file>` → checklist ✅ → authorize",
    ]

lines += [
    "",
    "## Explicitly not done",
    "",
    "- no checklist 🟨→✅",
    "- no production_signed=true",
    "- no cutover authorize",
    "",
    "See [`OPS_HANDOFF.md`](../OPS_HANDOFF.md).",
    "",
]
runlog.write_text("\n".join(lines), encoding="utf-8")
print(runlog.read_text(encoding="utf-8"))

out = {
    "kind": "pgha_live_kickoff",
    "can_record": can_record,
    "blockers": blockers,
    "notes": notes,
    "runlog": str(runlog),
    "live_file": str(record_path) if record_path else None,
    "does_not_authorize": True,
}
print(json.dumps(out, indent=2, ensure_ascii=False))
raise SystemExit(0 if can_record else 2)
PY
