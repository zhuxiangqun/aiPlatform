#!/usr/bin/env bash
# Diagnosis A3 local rehearsal — SQLite backup/restore/rollback (NOT production split).
# Never sets process_split_authorized=true. Does NOT Accept ADR.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
DRILL_DIR="$ROOT/packages/aiplat-diagnosis/docs/a3/drills"
mkdir -p "$DRILL_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="${AIPLAT_DIAGNOSIS_A3_REHEARSAL_DIR:-$(mktemp -d /tmp/aiplat-diagnosis-a3-rehearsal.XXXXXX)}"
mkdir -p "$WORK"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
echo "Diagnosis A3 rehearsal workdir=$WORK"

export AIPLAT_REHEARSAL_WORK="$WORK"
export AIPLAT_REHEARSAL_STAMP="$STAMP"
export AIPLAT_REHEARSAL_DRILL_DIR="$DRILL_DIR"
export AIPLAT_A3_CHECKLIST="$ROOT/packages/aiplat-diagnosis/docs/a3/SPLIT_CHECKLIST.md"

"$PY" - <<'PY'
import json
import os
import shutil
import sqlite3
from pathlib import Path

work = Path(os.environ["AIPLAT_REHEARSAL_WORK"])
stamp = os.environ["AIPLAT_REHEARSAL_STAMP"]
drill_dir = Path(os.environ["AIPLAT_REHEARSAL_DRILL_DIR"])
checklist = Path(os.environ["AIPLAT_A3_CHECKLIST"])

cohost = work / "cohost_diagnosis.sqlite3"
standalone = work / "standalone_diagnosis.sqlite3"
bak = work / "backup.sql"
rolled = work / "rolled_diagnosis.sqlite3"

conn = sqlite3.connect(cohost)
conn.execute(
    "CREATE TABLE diagnosis_cases (id TEXT PRIMARY KEY, scenario TEXT, subject_ref TEXT)"
)
conn.execute(
    "INSERT INTO diagnosis_cases(id, scenario, subject_ref) VALUES ('a3-reh', 'run_failure', 'run/fixture')"
)
conn.commit()
conn.close()

standalone.write_bytes(Path(cohost).read_bytes())

with sqlite3.connect(standalone) as c, bak.open("w", encoding="utf-8") as f:
    for line in c.iterdump():
        f.write(line + "\n")
    n = c.execute("SELECT count(*) FROM diagnosis_cases").fetchone()[0]
assert n == 1

with sqlite3.connect(standalone) as c:
    c.execute("DELETE FROM diagnosis_cases")
    c.commit()
if rolled.exists():
    rolled.unlink()
with sqlite3.connect(rolled) as c:
    c.executescript(bak.read_text(encoding="utf-8"))
    n2 = c.execute("SELECT count(*) FROM diagnosis_cases").fetchone()[0]
assert n2 == 1

pointer = work / "active_db.txt"
pointer.write_text(str(cohost.resolve()) + "\n", encoding="utf-8")

pfx_co = work / "prefix" / "diagnosis-cohost"
pfx_st = work / "prefix" / "diagnosis-standalone"
for p, mode, db in (
    (pfx_co, "cohost", cohost),
    (pfx_st, "standalone_sim", rolled),
):
    p.mkdir(parents=True, exist_ok=True)
    (p / "INSTALL_META.json").write_text(
        json.dumps(
            {
                "capability_id": "diagnosis",
                "mode": mode,
                "process_split_authorized": False,
                "a3_adr": "draft",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    shutil.copy2(db, p / "diagnosis.sqlite3")
active_pfx = work / "prefix" / "current"
if active_pfx.exists() or active_pfx.is_symlink():
    active_pfx.unlink()
active_pfx.symlink_to(pfx_st.resolve())
active_pfx.unlink()
active_pfx.symlink_to(pfx_co.resolve())
assert json.loads((active_pfx / "INSTALL_META.json").read_text(encoding="utf-8"))["mode"] == "cohost"

out = drill_dir / f"local-rehearsal-{stamp}.json"
out.write_text(
    json.dumps(
        {
            "kind": "diagnosis_a3_sqlite_prefix_rehearsal_not_live",
            "at": stamp,
            "backup_restore": True,
            "rollback_to_cohost_pointer": True,
            "install_prefix_switch": True,
            "production_split": False,
            "note": "Local SQLite+prefix only; checklist #4 🟨 until live drills; split unauthorized.",
            "workdir": str(work),
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)

text = checklist.read_text(encoding="utf-8")
text = text.replace(
    "| 4 | 备份恢复 + 回滚演练（切回共宿） | 运维 | ⬜ |",
    "| 4 | 备份恢复 + 回滚演练（切回共宿） | 运维 | 🟨 |",
)
assert "process_split_authorized: false" in text
checklist.write_text(text, encoding="utf-8")
print("OK diagnosis a3 local rehearsal", out)
print("OK checklist #4 → 🟨 (split still false)")
PY

echo "PASS: diagnosis a3_local_rehearsal stamp=$STAMP process_split_authorized=false"
