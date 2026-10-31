#!/usr/bin/env bash
# Docker ephemeral HA failover + failback rehearsal — NOT production Patroni/VIP.
# Marks checklist #4 as 🟨 only. Never sets cutover_authorized=true.
# Skip: AIPLAT_PG_HA_SKIP_DOCKER=1 or no docker daemon.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
DRILL_DIR="$ROOT/packages/aiplat-central/docs/pg_ha/drills"
mkdir -p "$DRILL_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="${AIPLAT_PG_HA_HA_REHEARSAL_DIR:-$(mktemp -d /tmp/aiplat-pgha-ha.XXXXXX)}"
mkdir -p "$WORK"
IMG="${AIPLAT_PG_HA_DOCKER_IMAGE:-postgres:16-alpine}"
PRIMARY="aiplat-pgha-pri-${STAMP}"
STANDBY="aiplat-pgha-stb-${STAMP}"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"

cleanup() {
  docker rm -f "$PRIMARY" "$STANDBY" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [[ "${AIPLAT_PG_HA_SKIP_DOCKER:-0}" == "1" ]]; then
  echo "NOTE: AIPLAT_PG_HA_SKIP_DOCKER=1 — skip HA failover rehearsal"
  exit 0
fi
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "NOTE: docker unavailable — skip HA failover rehearsal (checklist #4 stays ⬜)"
  exit 0
fi

echo "HA rehearsal workdir=$WORK image=$IMG"

start_pg() {
  local name="$1"
  docker run -d --rm --name "$name" \
    -e POSTGRES_PASSWORD=aiplat_reh \
    -e POSTGRES_USER=aiplat \
    -e POSTGRES_DB=aiplat_reh \
    "$IMG" >/dev/null
  local i
  for i in $(seq 1 40); do
    if docker exec "$name" pg_isready -U aiplat -d aiplat_reh >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "FAIL: $name not ready" >&2
  return 1
}

pg_sql() {
  local name="$1"
  shift
  docker exec -i "$name" psql -U aiplat -d aiplat_reh -v ON_ERROR_STOP=1 "$@"
}

echo "== Primary seed =="
start_pg "$PRIMARY"
pg_sql "$PRIMARY" <<'SQL'
CREATE TABLE ha_rehearsal (id serial PRIMARY KEY, note text);
INSERT INTO ha_rehearsal(note) VALUES ('primary-seed');
SQL
docker exec "$PRIMARY" pg_dump -U aiplat -d aiplat_reh -t ha_rehearsal -f /tmp/ha.sql
docker cp "$PRIMARY:/tmp/ha.sql" "$WORK/ha.sql"

echo "== Standby hydrate from dump =="
start_pg "$STANDBY"
docker cp "$WORK/ha.sql" "$STANDBY:/tmp/ha.sql"
pg_sql "$STANDBY" -f /tmp/ha.sql
N_STB="$(docker exec "$STANDBY" psql -U aiplat -d aiplat_reh -Atc "SELECT count(*) FROM ha_rehearsal;")"
[[ "$N_STB" == "1" ]] || { echo "FAIL standby n=$N_STB" >&2; exit 1; }

ACTIVE="$WORK/active_endpoint.txt"
echo "primary:$PRIMARY" >"$ACTIVE"

echo "== Failover: stop primary, point to standby =="
docker rm -f "$PRIMARY" >/dev/null
echo "standby:$STANDBY" >"$ACTIVE"
N_FO="$(docker exec "$STANDBY" psql -U aiplat -d aiplat_reh -Atc "SELECT count(*) FROM ha_rehearsal;")"
[[ "$N_FO" == "1" ]] || { echo "FAIL after failover n=$N_FO" >&2; exit 1; }
docker exec "$STANDBY" psql -U aiplat -d aiplat_reh -v ON_ERROR_STOP=1 -c "INSERT INTO ha_rehearsal(note) VALUES ('after-failover');" >/dev/null

echo "== Failback: new primary from standby dump, switch pointer =="
docker exec "$STANDBY" pg_dump -U aiplat -d aiplat_reh -t ha_rehearsal -f /tmp/ha_fb.sql
docker cp "$STANDBY:/tmp/ha_fb.sql" "$WORK/ha_failback.sql"
# recycle primary name
start_pg "$PRIMARY"
docker cp "$WORK/ha_failback.sql" "$PRIMARY:/tmp/ha_fb.sql"
pg_sql "$PRIMARY" -f /tmp/ha_fb.sql
N_FB="$(docker exec "$PRIMARY" psql -U aiplat -d aiplat_reh -Atc "SELECT count(*) FROM ha_rehearsal;")"
[[ "$N_FB" == "2" ]] || { echo "FAIL failback n=$N_FB" >&2; exit 1; }
echo "primary:$PRIMARY" >"$ACTIVE"
docker rm -f "$STANDBY" >/dev/null
# leave primary for trap cleanup

"$PY" - <<PY
import json
from pathlib import Path
out = Path("$DRILL_DIR") / "ha-rehearsal-$STAMP.json"
out.write_text(
    json.dumps(
        {
            "kind": "ha_failover_docker_ephemeral_not_production",
            "at": "$STAMP",
            "failover": True,
            "failback": True,
            "streaming_replication": False,
            "vip": False,
            "production_ha": False,
            "image": "$IMG",
            "note": "Logical dump failover/failback only; checklist #4 partial until live HA.",
            "workdir": "$WORK",
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
path = Path("$ROOT/packages/aiplat-central/docs/pg_ha/CUTOVER_CHECKLIST.md")
t = path.read_text(encoding="utf-8")
t = t.replace(
    "| 4 | HA failover + 回切演练记录 | 运维 | ⬜ |",
    "| 4 | HA failover + 回切演练记录 | 运维 | 🟨 |",
)
assert "cutover_authorized: false" in t
path.write_text(t, encoding="utf-8")
print("OK HA rehearsal", out)
print("OK checklist #4 → 🟨 (cutover still false)")
PY

echo "PASS: pg_ha_ha_failover_rehearsal stamp=$STAMP cutover_authorized=false"
