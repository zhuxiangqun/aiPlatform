#!/usr/bin/env bash
# Ontology A3 local rehearsal — file-tree dual-write + rollback (NOT production split).
# Never sets process_split_authorized=true. Does NOT Accept ADR.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(d1_repo_root)"
DRILL_DIR="$ROOT/packages/aiplat-ontology/docs/a3/drills"
mkdir -p "$DRILL_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="${AIPLAT_ONTOLOGY_A3_REHEARSAL_DIR:-$(mktemp -d /tmp/aiplat-ontology-a3-rehearsal.XXXXXX)}"
mkdir -p "$WORK"

d1_require_python
PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
echo "Ontology A3 rehearsal workdir=$WORK"

export AIPLAT_REHEARSAL_WORK="$WORK"
export AIPLAT_REHEARSAL_STAMP="$STAMP"
export AIPLAT_REHEARSAL_DRILL_DIR="$DRILL_DIR"
export AIPLAT_A3_CHECKLIST="$ROOT/packages/aiplat-ontology/docs/a3/SPLIT_CHECKLIST.md"

"$PY" - <<'PY'
import json
import os
import shutil
from pathlib import Path

work = Path(os.environ["AIPLAT_REHEARSAL_WORK"])
stamp = os.environ["AIPLAT_REHEARSAL_STAMP"]
drill_dir = Path(os.environ["AIPLAT_REHEARSAL_DRILL_DIR"])
checklist = Path(os.environ["AIPLAT_A3_CHECKLIST"])

cohost = work / "cohost" / "ontologies"
standalone = work / "standalone" / "ontologies"
backup = work / "backup" / "ontologies"
cohost.mkdir(parents=True)
(cohost / "demo-domain.yaml").write_text(
    "domain_id: demo-domain\nversion: 0.1.0\nentities: []\n",
    encoding="utf-8",
)

if standalone.exists():
    shutil.rmtree(standalone)
shutil.copytree(cohost, standalone)
assert (standalone / "demo-domain.yaml").is_file()

if backup.exists():
    shutil.rmtree(backup)
shutil.copytree(standalone, backup)

shutil.rmtree(standalone)
standalone.mkdir(parents=True)
(standalone / "broken.yaml").write_text("broken: true\n", encoding="utf-8")
shutil.rmtree(standalone)
shutil.copytree(backup, standalone)
assert (standalone / "demo-domain.yaml").is_file()
assert not (standalone / "broken.yaml").exists()

pointer = work / "active_root.txt"
pointer.write_text(str(cohost.resolve()) + "\n", encoding="utf-8")
assert pointer.read_text(encoding="utf-8").strip() == str(cohost.resolve())

# install-prefix layout (Thin D1 style) — simulate switch then rollback
pfx_co = work / "prefix" / "ontology-cohost"
pfx_st = work / "prefix" / "ontology-standalone"
for p, mode in ((pfx_co, "cohost"), (pfx_st, "standalone_sim")):
    p.mkdir(parents=True, exist_ok=True)
    (p / "INSTALL_META.json").write_text(
        json.dumps(
            {
                "capability_id": "ontology",
                "mode": mode,
                "process_split_authorized": False,
                "a3_adr": "accepted_conditional",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    dest = p / "ontologies"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(cohost if mode == "cohost" else standalone, dest)
active_pfx = work / "prefix" / "current"
if active_pfx.exists() or active_pfx.is_symlink():
    active_pfx.unlink()
active_pfx.symlink_to(pfx_st.resolve())
assert (active_pfx / "INSTALL_META.json").is_file()
active_pfx.unlink()
active_pfx.symlink_to(pfx_co.resolve())  # rollback to cohost prefix
assert json.loads((active_pfx / "INSTALL_META.json").read_text(encoding="utf-8"))["mode"] == "cohost"

out = drill_dir / f"local-rehearsal-{stamp}.json"
out.write_text(
    json.dumps(
        {
            "kind": "ontology_a3_file_prefix_rehearsal_not_live",
            "at": stamp,
            "dual_write_copy": True,
            "rollback_to_cohost_pointer": True,
            "install_prefix_switch": True,
            "production_split": False,
            "note": "Local file+prefix only; checklist #3/#5 🟨 until live drills; split unauthorized.",
            "workdir": str(work),
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)

text = checklist.read_text(encoding="utf-8")
text = text.replace(
    "| 3 | 存储迁移/回填 + 双写或只读切换演练 | 运维 | ⬜ |",
    "| 3 | 存储迁移/回填 + 双写或只读切换演练 | 运维 | 🟨 |",
)
text = text.replace(
    "| 5 | 回滚演练（切回共宿 D1） | 运维 | ⬜ |",
    "| 5 | 回滚演练（切回共宿 D1） | 运维 | 🟨 |",
)
assert "process_split_authorized: false" in text
checklist.write_text(text, encoding="utf-8")
print("OK ontology a3 local rehearsal", out)
print("OK checklist #3/#5 → 🟨 (split still false)")
PY

echo "PASS: ontology a3_local_rehearsal stamp=$STAMP process_split_authorized=false"
