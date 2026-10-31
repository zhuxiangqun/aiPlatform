#!/usr/bin/env bash
# Evaluation A3 local rehearsal — SQLite backup/restore/rollback (NOT production split).
# Never sets process_split_authorized=true. Does NOT Accept ADR.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
DRILL_DIR="$ROOT/packages/aiplat-evaluation/docs/a3/drills"
mkdir -p "$DRILL_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="${AIPLAT_EVAL_A3_REHEARSAL_DIR:-$(mktemp -d /tmp/aiplat-eval-a3-rehearsal.XXXXXX)}"
mkdir -p "$WORK"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
echo "Evaluation A3 rehearsal workdir=$WORK"

export AIPLAT_REHEARSAL_WORK="$WORK"
export AIPLAT_REHEARSAL_STAMP="$STAMP"
export AIPLAT_REHEARSAL_DRILL_DIR="$DRILL_DIR"
export AIPLAT_A3_CHECKLIST="$ROOT/packages/aiplat-evaluation/docs/a3/SPLIT_CHECKLIST.md"

"$PY" - <<'PY'
import json
import os
import sqlite3
from pathlib import Path

work = Path(os.environ["AIPLAT_REHEARSAL_WORK"])
stamp = os.environ["AIPLAT_REHEARSAL_STAMP"]
drill_dir = Path(os.environ["AIPLAT_REHEARSAL_DRILL_DIR"])
checklist = Path(os.environ["AIPLAT_A3_CHECKLIST"])

cohost = work / "cohost_eval.sqlite3"
standalone = work / "standalone_eval.sqlite3"
bak = work / "backup.sql"
rolled = work / "rolled_eval.sqlite3"

conn = sqlite3.connect(cohost)
conn.execute(
    "CREATE TABLE eval_runs (id INTEGER PRIMARY KEY, task_id TEXT, status TEXT, protocol TEXT)"
)
conn.execute(
    "INSERT INTO eval_runs(task_id, status, protocol) VALUES ('a3-reh', 'passed', 'eval.protocol.v0')"
)
conn.commit()
conn.close()

# migrate copy to standalone
data = Path(cohost).read_bytes()
standalone.write_bytes(data)

with sqlite3.connect(standalone) as c, bak.open("w", encoding="utf-8") as f:
    for line in c.iterdump():
        f.write(line + "\n")
    n = c.execute("SELECT count(*) FROM eval_runs").fetchone()[0]
assert n == 1

# wipe then restore (= rollback rehearsal)
with sqlite3.connect(standalone) as c:
    c.execute("DELETE FROM eval_runs")
    c.commit()
if rolled.exists():
    rolled.unlink()
with sqlite3.connect(rolled) as c:
    c.executescript(bak.read_text(encoding="utf-8"))
    n2 = c.execute("SELECT count(*) FROM eval_runs").fetchone()[0]
assert n2 == 1

# active pointer back to cohost
pointer = work / "active_db.txt"
pointer.write_text(str(cohost.resolve()) + "\n", encoding="utf-8")

# install-prefix layout — switch to standalone sim then rollback
import shutil

pfx_co = work / "prefix" / "evaluation-cohost"
pfx_st = work / "prefix" / "evaluation-standalone"
for p, mode, db in (
    (pfx_co, "cohost", cohost),
    (pfx_st, "standalone_sim", rolled),
):
    p.mkdir(parents=True, exist_ok=True)
    (p / "INSTALL_META.json").write_text(
        json.dumps(
            {
                "capability_id": "evaluation",
                "mode": mode,
                "process_split_authorized": False,
                "a3_adr": "accepted_conditional",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    shutil.copy2(db, p / "eval.sqlite3")
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
            "kind": "evaluation_a3_sqlite_prefix_rehearsal_not_live",
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
print("OK evaluation a3 local rehearsal", out)
print("OK checklist #4 → 🟨 (split still false)")
PY

echo "PASS: evaluation a3_local_rehearsal stamp=$STAMP process_split_authorized=false"
