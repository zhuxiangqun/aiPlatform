#!/usr/bin/env bash
# Local rehearsal for backup/restore/rollback — honest labels.
# 1) Always: SQLite roundtrip (NOT production PG).
# 2) Optional: AIPLAT_PG_DSN + host psql/pg_dump.
# 3) Else if docker: ephemeral postgres:16 schema dump/restore (still NOT production).
# Never sets cutover_authorized=true.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
DRILL_DIR="$ROOT/packages/aiplat-central/docs/pg_ha/drills"
mkdir -p "$DRILL_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="${AIPLAT_PG_HA_REHEARSAL_DIR:-$(mktemp -d /tmp/aiplat-pgha-rehearsal.XXXXXX)}"
mkdir -p "$WORK"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
echo "Rehearsal workdir=$WORK"

export AIPLAT_REHEARSAL_WORK="$WORK"
export AIPLAT_REHEARSAL_STAMP="$STAMP"
export AIPLAT_REHEARSAL_DRILL_DIR="$DRILL_DIR"

"$PY" - <<'PY'
import json
import sqlite3
from pathlib import Path
import os

work = Path(os.environ["AIPLAT_REHEARSAL_WORK"])
stamp = os.environ["AIPLAT_REHEARSAL_STAMP"]
drill_dir = Path(os.environ["AIPLAT_REHEARSAL_DRILL_DIR"])

src = work / "src.sqlite3"
bak = work / "backup.sql"
rest = work / "restored.sqlite3"
rolled = work / "rolled.sqlite3"

conn = sqlite3.connect(src)
conn.execute("CREATE TABLE rehearsal (id INTEGER PRIMARY KEY, note TEXT)")
conn.execute("INSERT INTO rehearsal(note) VALUES ('pg-ha-local-rehearsal')")
conn.commit()
conn.close()

with sqlite3.connect(src) as c, bak.open("w", encoding="utf-8") as f:
    for line in c.iterdump():
        f.write(line + "\n")

if rest.exists():
    rest.unlink()
with sqlite3.connect(rest) as c:
    c.executescript(bak.read_text(encoding="utf-8"))
    n = c.execute("SELECT count(*) FROM rehearsal").fetchone()[0]
assert n == 1, n

with sqlite3.connect(rest) as c:
    c.execute("DELETE FROM rehearsal")
    c.commit()
if rolled.exists():
    rolled.unlink()
with sqlite3.connect(rolled) as c:
    c.executescript(bak.read_text(encoding="utf-8"))
    n2 = c.execute("SELECT count(*) FROM rehearsal").fetchone()[0]
assert n2 == 1, n2

out = drill_dir / f"sqlite-rehearsal-{stamp}.json"
out.write_text(
    json.dumps(
        {
            "kind": "sqlite_rehearsal_not_pg",
            "at": stamp,
            "backup_restore": True,
            "rollback_from_backup": True,
            "production_pg": False,
            "note": "Local SQLite only; checklist #3/#7 partial until live PG drills.",
            "workdir": str(work),
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print("OK sqlite rehearsal", out)
PY

PG_OK=0
PG_KIND="skipped"

run_pg_schema_via_dsn() {
  local dsn="$1"
  local schema="aiplat_rehearsal_${STAMP}"
  local dump="$WORK/pg_dump.sql"
  psql "$dsn" -v ON_ERROR_STOP=1 <<SQL
CREATE SCHEMA ${schema};
CREATE TABLE ${schema}.rehearsal (id serial PRIMARY KEY, note text);
INSERT INTO ${schema}.rehearsal(note) VALUES ('pg-dsn-rehearsal');
SQL
  pg_dump "$dsn" --schema="$schema" -f "$dump"
  psql "$dsn" -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS ${schema} CASCADE;"
  psql "$dsn" -v ON_ERROR_STOP=1 -f "$dump"
  local n
  n="$(psql "$dsn" -Atc "SELECT count(*) FROM ${schema}.rehearsal;")"
  [[ "$n" == "1" ]] || { echo "FAIL pg restore n=$n" >&2; return 1; }
  psql "$dsn" -v ON_ERROR_STOP=1 -c "DROP SCHEMA ${schema} CASCADE;"
  "$PY" -c "import json; from pathlib import Path; Path(r'$DRILL_DIR/pg-rehearsal-$STAMP.json').write_text(json.dumps({'kind':'pg_schema_rehearsal_dsn','at':'$STAMP','backup_restore':True,'ha_failover':False,'production_pg':False}, indent=2)+chr(10))"
}

run_pg_schema_via_docker() {
  local name="aiplat-pgha-reh-${STAMP}"
  local schema="aiplat_rehearsal"
  local dump="$WORK/pg_dump.sql"
  local img="${AIPLAT_PG_HA_DOCKER_IMAGE:-postgres:16-alpine}"
  echo "== Docker ephemeral PG schema rehearsal ($img) =="
  if ! docker info >/dev/null 2>&1; then
    echo "WARN: docker unavailable (daemon/socket); skip ephemeral PG" >&2
    return 1
  fi
  docker rm -f "$name" >/dev/null 2>&1 || true
  if ! docker run -d --rm --name "$name" \
    -e POSTGRES_PASSWORD=aiplat_reh \
    -e POSTGRES_USER=aiplat \
    -e POSTGRES_DB=aiplat_reh \
    "$img" >/dev/null; then
    echo "WARN: docker run failed" >&2
    return 1
  fi
  local i ready=0
  for i in $(seq 1 40); do
    if docker exec "$name" pg_isready -U aiplat -d aiplat_reh >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 1
  done
  if [[ "$ready" != "1" ]]; then
    echo "WARN: postgres container not ready" >&2
    docker rm -f "$name" >/dev/null 2>&1 || true
    return 1
  fi

  docker exec -i "$name" psql -U aiplat -d aiplat_reh -v ON_ERROR_STOP=1 <<SQL
CREATE SCHEMA ${schema};
CREATE TABLE ${schema}.rehearsal (id serial PRIMARY KEY, note text);
INSERT INTO ${schema}.rehearsal(note) VALUES ('pg-docker-rehearsal');
SQL
  docker exec "$name" pg_dump -U aiplat -d aiplat_reh --schema="$schema" -f /tmp/pg_dump.sql
  docker cp "$name:/tmp/pg_dump.sql" "$dump"
  docker exec -i "$name" psql -U aiplat -d aiplat_reh -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS ${schema} CASCADE;"
  docker exec -i "$name" psql -U aiplat -d aiplat_reh -v ON_ERROR_STOP=1 -f /tmp/pg_dump.sql
  local n
  n="$(docker exec "$name" psql -U aiplat -d aiplat_reh -Atc "SELECT count(*) FROM ${schema}.rehearsal;")"
  [[ "$n" == "1" ]] || { echo "FAIL docker pg restore n=$n" >&2; docker rm -f "$name" >/dev/null 2>&1 || true; return 1; }
  docker rm -f "$name" >/dev/null 2>&1 || true
  "$PY" -c "import json; from pathlib import Path; Path(r'$DRILL_DIR/pg-rehearsal-$STAMP.json').write_text(json.dumps({'kind':'pg_schema_rehearsal_docker_ephemeral','at':'$STAMP','backup_restore':True,'ha_failover':False,'production_pg':False,'image':'$img'}, indent=2)+chr(10))"
}

if [[ -n "${AIPLAT_PG_DSN:-}" ]] && command -v psql >/dev/null 2>&1 && command -v pg_dump >/dev/null 2>&1; then
  echo "== Optional PG schema rehearsal (AIPLAT_PG_DSN) =="
  if run_pg_schema_via_dsn "$AIPLAT_PG_DSN"; then
    PG_OK=1
    PG_KIND="dsn"
    echo "OK PG schema dump/restore (DSN)"
  fi
elif [[ "${AIPLAT_PG_HA_SKIP_DOCKER:-0}" != "1" ]] && command -v docker >/dev/null 2>&1; then
  if run_pg_schema_via_docker; then
    PG_OK=1
    PG_KIND="docker_ephemeral"
    echo "OK PG schema dump/restore (docker ephemeral; NOT production)"
  else
    echo "WARN: docker PG rehearsal failed; continuing with SQLite-only" >&2
  fi
else
  echo "NOTE: skip PG schema (need AIPLAT_PG_DSN+psql/pg_dump, or docker; set AIPLAT_PG_HA_SKIP_DOCKER=1 to force skip)"
fi

CHECKLIST="$ROOT/packages/aiplat-central/docs/pg_ha/CUTOVER_CHECKLIST.md"
STATUS="$ROOT/packages/aiplat-central/docs/pg_ha/PREP_STATUS.json"
export AIPLAT_REH_PG_OK="$PG_OK"
export AIPLAT_REH_PG_KIND="$PG_KIND"
export AIPLAT_REH_CHECKLIST="$CHECKLIST"
export AIPLAT_REH_STATUS="$STATUS"
"$PY" - <<'PY'
from pathlib import Path
import json, os
p = Path(os.environ["AIPLAT_REH_CHECKLIST"])
t = p.read_text(encoding="utf-8")
t = t.replace("| 3 | 备份恢复演练记录 | 运维 | ⬜ |", "| 3 | 备份恢复演练记录 | 运维 | 🟨 |")
t = t.replace("| 7 | 回滚演练一次 | 运维 | ⬜ |", "| 7 | 回滚演练一次 | 运维 | 🟨 |")
if os.environ.get("AIPLAT_REH_PG_OK") == "1":
    t = t.replace("| 2 | PG 迁移演练记录（环境/日期/结果） | 运维 | ⬜ |", "| 2 | PG 迁移演练记录（环境/日期/结果） | 运维 | 🟨 |")
assert "cutover_authorized: false" in t
p.write_text(t, encoding="utf-8")
sp = Path(os.environ["AIPLAT_REH_STATUS"])
data = json.loads(sp.read_text(encoding="utf-8")) if sp.is_file() else {"items": {}, "cutover_authorized": False}
data.setdefault("items", {})
data["items"]["3_backup_sqlite_rehearsal"] = {"ok": True, "detail": "sqlite dump/restore"}
data["items"]["7_rollback_sqlite_rehearsal"] = {"ok": True, "detail": "restore after wipe"}
data["items"]["2_pg_schema_rehearsal"] = {
    "ok": os.environ.get("AIPLAT_REH_PG_OK") == "1",
    "detail": os.environ.get("AIPLAT_REH_PG_KIND", "skipped"),
}
data["cutover_authorized"] = False
data["manual_still_required"] = [
    "2_pg_migration_production_like",
    "3_backup_restore_production_pg",
    "4_ha_failover_live_drill",
    "7_rollback_production_like",
    "1_oidc_full_regression",
]
sp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("OK checklist+status (cutover still false)")
PY

echo "PASS: pg_ha_local_rehearsal stamp=$STAMP pg=$PG_OK kind=$PG_KIND cutover_authorized=false"
