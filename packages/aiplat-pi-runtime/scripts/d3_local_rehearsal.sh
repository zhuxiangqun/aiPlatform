#!/usr/bin/env bash
# Pi D3 local rehearsal — manifest + checksum roundtrip + rollback pointer (NOT production SOC).
# Never sets d3_production_authorized=true.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=d1_lib.sh
source "$SCRIPT_DIR/d1_lib.sh"

ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DRILL_DIR="$ROOT/packages/aiplat-pi-runtime/docs/d3/drills"
mkdir -p "$DRILL_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="${AIPLAT_PI_D3_REHEARSAL_DIR:-$(mktemp -d /tmp/aiplat-pi-d3-rehearsal.XXXXXX)}"
mkdir -p "$WORK"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
echo "Pi D3 rehearsal workdir=$WORK"

SAMPLE="$(d1_repo_pkg)/fixtures/sample-app"
export AIPLAT_REHEARSAL_WORK="$WORK"
export AIPLAT_REHEARSAL_STAMP="$STAMP"
export AIPLAT_REHEARSAL_DRILL_DIR="$DRILL_DIR"
export AIPLAT_REHEARSAL_SAMPLE="$SAMPLE"
export AIPLAT_D3_CHECKLIST="$ROOT/packages/aiplat-pi-runtime/docs/d3/D3_CHECKLIST.md"

"$PY" - <<'PY'
import hashlib
import json
import os
import shutil
from pathlib import Path

work = Path(os.environ["AIPLAT_REHEARSAL_WORK"])
stamp = os.environ["AIPLAT_REHEARSAL_STAMP"]
drill_dir = Path(os.environ["AIPLAT_REHEARSAL_DRILL_DIR"])
sample = Path(os.environ["AIPLAT_REHEARSAL_SAMPLE"])
checklist = Path(os.environ["AIPLAT_D3_CHECKLIST"])

assert (sample / "agent_manifest.json").is_file()
v1 = work / "bundles" / "v1"
v2 = work / "bundles" / "v2"
v1.mkdir(parents=True)
shutil.copytree(sample, v1, dirs_exist_ok=True)
# checksum inventory
lines = []
for p in sorted(v1.rglob("*")):
    if p.is_file():
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        lines.append(f"{digest}  {p.relative_to(v1).as_posix()}")
(v1 / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
# verify
for line in (v1 / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    digest, rel = line.split(None, 1)
    assert hashlib.sha256((v1 / rel).read_bytes()).hexdigest() == digest

shutil.copytree(v1, v2)
# corrupt then detect
(v2 / "agent_manifest.json").write_text("{}", encoding="utf-8")
bad = False
for line in (v1 / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    digest, rel = line.split(None, 1)
    if rel == "agent_manifest.json":
        if hashlib.sha256((v2 / rel).read_bytes()).hexdigest() != digest:
            bad = True
assert bad

# rollback pointer to v1
current = work / "bundles" / "current"
if current.exists() or current.is_symlink():
    current.unlink()
current.symlink_to(v1.resolve())
assert (current / "agent_manifest.json").is_file()

out = drill_dir / f"local-rehearsal-{stamp}.json"
out.write_text(
    json.dumps(
        {
            "kind": "pi_d3_local_rehearsal_not_production",
            "at": stamp,
            "bundle_checksum": True,
            "corruption_detected": True,
            "rollback_pointer": True,
            "soc_live": False,
            "d3_production": False,
            "workdir": str(work),
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)

text = checklist.read_text(encoding="utf-8")
text = text.replace(
    "| 3 | Bundle 完整性策略文档 + 本地校验演练 | 平台 | ⬜ |",
    "| 3 | Bundle 完整性策略文档 + 本地校验演练 | 平台 | 🟨 |",
)
text = text.replace(
    "| 4 | 运维面 healthz/证据约定文档 | 平台 | ⬜ |",
    "| 4 | 运维面 healthz/证据约定文档 | 平台 | 🟨 |",
)
text = text.replace(
    "| 6 | N-1 升级/回滚 live 或等价演练 | 运维 | ⬜ |",
    "| 6 | N-1 升级/回滚 live 或等价演练 | 运维 | 🟨 |",
)
assert "d3_production_authorized: false" in text
checklist.write_text(text, encoding="utf-8")
print("OK pi d3 local rehearsal", out)
print("OK checklist #3/#4/#6 → 🟨 (d3_production still false)")
PY

echo "PASS: pi d3_local_rehearsal stamp=$STAMP d3_production_authorized=false"
