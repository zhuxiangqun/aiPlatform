#!/usr/bin/env bash
# G2b n=100 facilitator pack: generate worksheets + optional model_outputs run.
# Does NOT invent A/B labels. accuracy_claim stays false.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

STAMP="${G2B_PACK_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${G2B_PACK_OUT:-$ROOT/docs/a3/human_pack/${STAMP}-n100}"
TASKS="$ROOT/docs/a3/g2b_tasks.v0.json"
SEED_A="$ROOT/docs/a3/evidence/g2b_annotator_a.labels.v1.json"
SEED_B="$ROOT/docs/a3/evidence/g2b_annotator_b.labels.v1.json"
RUN_MODEL="${G2B_RUN_MODEL:-0}"

echo "== G2b n=100 pack → $OUT =="
python3 - <<PY
import json
from pathlib import Path
tasks = json.loads(Path("$TASKS").read_text(encoding="utf-8"))["tasks"]
assert len(tasks) == 100, len(tasks)
print(f"task_pack_ok n={len(tasks)}")
PY

PYTHONPATH=. python3 "$ROOT/scripts/human_worksheet_pack.py" --out "$OUT" --skip-preference

if [[ "$RUN_MODEL" == "1" ]]; then
  echo "== run model_outputs (AIPLAT_EVAL_LLM must be on) =="
  # Seed 01-30 from prior pack outputs when present
  PRIOR="$ROOT/docs/a3/human_pack/20261103T130302Z/model_outputs.json"
  if [[ -f "$PRIOR" ]]; then
    cp "$PRIOR" "$OUT/model_outputs.json"
  else
    echo '{}' >"$OUT/model_outputs.json"
  fi
  python3 "$ROOT/scripts/g2b_run_model_outputs.py" \
    --tasks "$TASKS" \
    --out "$OUT/model_outputs.json" \
    --resume
  PYTHONPATH=. python3 "$ROOT/scripts/human_worksheet_pack.py" --from-outputs "$OUT"
fi

# Seed A/B labels for g2b-01..30 from committed evidence; leave 31-100 as null.
python3 - <<PY
import json
from pathlib import Path

out = Path("$OUT")
seed_a = json.loads(Path("$SEED_A").read_text(encoding="utf-8"))
seed_b = json.loads(Path("$SEED_B").read_text(encoding="utf-8"))
sa = {r["task_id"]: r for r in seed_a.get("labels") or [] if isinstance(r, dict)}
sb = {r["task_id"]: r for r in seed_b.get("labels") or [] if isinstance(r, dict)}

def merge(path: Path, seed: dict, annotator: str) -> None:
    ws = json.loads(path.read_text(encoding="utf-8"))
    filled = 0
    pending = 0
    for row in ws.get("labels") or []:
        tid = row.get("task_id")
        src = seed.get(tid)
        if src and isinstance(src.get("pass"), bool):
            row["pass"] = src["pass"]
            if src.get("notes") is not None:
                row["notes"] = src.get("notes") or ""
            if src.get("model_output") and not row.get("model_output"):
                row["model_output"] = src["model_output"]
            filled += 1
        else:
            # keep null for expand set
            if row.get("pass") is None:
                pending += 1
    ws["source_pack"] = out.name
    ws["n100_expand"] = {
        "seeded_from_evidence_01_30": True,
        "seeded_n": filled,
        "pending_dual_human_n": pending,
        "accuracy_claim": False,
        "note": "g2b-31..100 must be labeled by two distinct humans before n=100 closeout",
    }
    path.write_text(json.dumps(ws, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"annotator": annotator, "seeded": filled, "pending": pending}))

merge(out / "g2b_annotator_a.json", sa, "A")
merge(out / "g2b_annotator_b.json", sb, "B")
PY

cat >"$OUT/G2B_N100_SEND.md" <<EOF
# G2b n=100 expand — send sheet

1. Confirm \`model_outputs.json\` has 100 non-empty answers (run with \`G2B_RUN_MODEL=1\` if needed).
2. Send **only** \`g2b_annotator_a.json\` / \`g2b_annotator_b.json\` to two distinct humans.
3. They must fill \`pass\` for **g2b-31..g2b-100** (01–30 already seeded from prior dual-human evidence).
4. Blind: no gold_pass_hint, no sharing between A/B.
5. After both return, run κ + accuracy closeout (see \`docs/a3/G2B_N100.md\`).
6. \`accuracy_claim\` stays **false** until product-owner attestation.
EOF

echo "G2b n=100 pack READY at $OUT (dual-human pending for 31-100; accuracy_claim=false)"
