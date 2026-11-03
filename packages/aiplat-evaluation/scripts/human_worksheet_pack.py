#!/usr/bin/env python3
"""Generate blank human worksheets for G2b + preference (A/B).

Honesty: packs are for blind labeling only — never copy gold into annotator sheets;
accuracy_claim stays false; fixture solo ≠ human κ.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _load(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"Invalid JSON in {path}: {e}\n"
            "Tip: do not paste multi-line / quoted model answers into "
            "g2b_facilitator.json by hand. Edit model_outputs.json "
            '(flat map {"g2b-01": "..."}) then run:\n'
            f"  python3 scripts/human_worksheet_pack.py --from-outputs {path.parent}"
        ) from e


def build_g2b_annotator(
    tasks: List[Dict[str, Any]],
    *,
    annotator_id: str,
) -> Dict[str, Any]:
    labels: List[Dict[str, Any]] = []
    for t in tasks:
        tid = str(t.get("id") or "").strip()
        if not tid:
            continue
        labels.append(
            {
                "task_id": tid,
                "family": t.get("family"),
                "prompt": t.get("prompt"),
                "rubric": t.get("rubric"),
                # Facilitator fills before send, or annotator pastes from shared outputs file.
                "model_output": "",
                # Annotator MUST set true|false (null = unlabeled).
                "pass": None,
                "notes": "",
            }
        )
    return {
        "schema": "eval.g2b.worksheet.v0",
        "accuracy_claim": False,
        "annotator_id": annotator_id,
        "blind": True,
        "instructions": (
            "For each task_id: read prompt + rubric + model_output. "
            "Set pass=true if the output meets the rubric; pass=false otherwise. "
            "Do not share with the other annotator. Do not look at gold_pass_hint."
        ),
        "labels": labels,
    }


def build_g2b_facilitator(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Coordinator-only pack — includes gold hints; never send to annotators."""
    rows: List[Dict[str, Any]] = []
    for t in tasks:
        tid = str(t.get("id") or "").strip()
        if not tid:
            continue
        rows.append(
            {
                "task_id": tid,
                "family": t.get("family"),
                "prompt": t.get("prompt"),
                "rubric": t.get("rubric"),
                "gold_pass_hint": t.get("gold_pass_hint"),
                "model_output": "",
            }
        )
    return {
        "schema": "eval.g2b.facilitator.v0",
        "accuracy_claim": False,
        "not_for_annotators": True,
        "instructions": (
            "Fill model_output for each task (same candidate model). "
            "Copy model_output into BOTH annotator sheets before send. "
            "Never send this file (or gold_pass_hint) to annotators."
        ),
        "tasks": rows,
    }


def build_preference_annotator(
    pairs: List[Dict[str, Any]],
    *,
    annotator_id: str,
) -> Dict[str, Any]:
    labels: List[Dict[str, Any]] = []
    for p in pairs:
        pid = str(p.get("id") or "").strip()
        if not pid:
            continue
        labels.append(
            {
                "pair_id": pid,
                "prompt": p.get("prompt"),
                "a": p.get("a"),
                "b": p.get("b"),
                # Annotator MUST set a|b|tie (null = unlabeled).
                "preferred": None,
                "notes": "",
            }
        )
    return {
        "schema": "eval.preference.worksheet.v0",
        "accuracy_claim": False,
        "annotator_id": annotator_id,
        "blind": True,
        "instructions": (
            "For each pair_id: read prompt and answers a/b. "
            "Set preferred to a, b, or tie. Do not share with the other annotator."
        ),
        "labels": labels,
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _apply_output_map(pack_dir: Path, by_id: Dict[str, str]) -> Dict[str, Any]:
    """Write outputs into facilitator + both annotator sheets."""
    fac_path = pack_dir / "g2b_facilitator.json"
    if not fac_path.is_file():
        raise SystemExit(f"missing {fac_path}")
    fac = _load(fac_path)
    for t in fac.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("task_id") or "")
        if tid in by_id:
            t["model_output"] = by_id[tid]
    write_json(fac_path, fac)

    filled = 0
    empty = 0
    for name in ("g2b_annotator_a.json", "g2b_annotator_b.json"):
        path = pack_dir / name
        sheet = _load(path)
        for row in sheet.get("labels") or []:
            if not isinstance(row, dict):
                continue
            tid = str(row.get("task_id") or "")
            out = by_id.get(tid, str(row.get("model_output") or ""))
            if tid in by_id:
                out = by_id[tid]
            row["model_output"] = out
            if str(out).strip():
                filled += 1
            else:
                empty += 1
        write_json(path, sheet)
    return {
        "gate": "ok",
        "pack_dir": str(pack_dir),
        "label_slots_touched": filled + empty,
        "nonempty_model_output_slots": filled,
        "empty_model_output_slots": empty,
        "note": "annotator pass fields unchanged; still need two humans to label",
    }


def apply_facilitator_outputs(pack_dir: Path) -> Dict[str, Any]:
    """Copy facilitator model_output → both G2b annotator sheets (in place)."""
    fac_path = pack_dir / "g2b_facilitator.json"
    if not fac_path.is_file():
        raise SystemExit(f"missing {fac_path}")
    fac = _load(fac_path)
    by_id = {
        str(t.get("task_id")): str(t.get("model_output") or "")
        for t in (fac.get("tasks") or [])
        if isinstance(t, dict) and t.get("task_id")
    }
    return _apply_output_map(pack_dir, by_id)


def apply_from_outputs_file(pack_dir: Path) -> Dict[str, Any]:
    """Load flat model_outputs.json map and sync into facilitator + annotators.

    Format::
        {"g2b-01": "4", "g2b-02": "…"}
    Safe for multi-line strings and embedded quotes — edit this file, not facilitator.
    """
    path = pack_dir / "model_outputs.json"
    if not path.is_file():
        raise SystemExit(
            f"missing {path}\n"
            "Create a flat JSON object mapping task_id → model_output string."
        )
    data = _load(path)
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must be a JSON object {{task_id: output}}")
    by_id = {str(k): str(v if v is not None else "") for k, v in data.items()}
    result = _apply_output_map(pack_dir, by_id)
    result["source"] = str(path)
    return result


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description="Generate G2b/preference blank worksheets for humans")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (default: docs/a3/human_pack/<utc-stamp>)",
    )
    ap.add_argument(
        "--tasks",
        type=Path,
        default=root / "docs/a3/g2b_tasks.v0.json",
    )
    ap.add_argument(
        "--pairs",
        type=Path,
        default=root / "docs/a3/preference_pairs.v0.json",
    )
    ap.add_argument("--skip-g2b", action="store_true")
    ap.add_argument("--skip-preference", action="store_true")
    ap.add_argument(
        "--apply-facilitator-outputs",
        type=Path,
        default=None,
        metavar="PACK_DIR",
        help="copy g2b_facilitator.json model_output into both annotator sheets",
    )
    ap.add_argument(
        "--from-outputs",
        type=Path,
        default=None,
        metavar="PACK_DIR",
        help="load pack_dir/model_outputs.json (flat map) into facilitator + annotators",
    )
    args = ap.parse_args()

    if args.from_outputs is not None:
        result = apply_from_outputs_file(args.from_outputs)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.apply_facilitator_outputs is not None:
        result = apply_facilitator_outputs(args.apply_facilitator_outputs)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out or (root / "docs/a3/human_pack" / stamp)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "schema": "eval.human_worksheet_pack.v0",
        "accuracy_claim": False,
        "process_split_authorized": False,
        "recorded_at": stamp,
        "out_dir": str(out_dir),
        "files": [],
        "next_steps": [
            "1) Facilitator: fill g2b_facilitator.json model_output (same model for all tasks).",
            "2) Copy those model_output values into g2b_annotator_a.json and g2b_annotator_b.json.",
            "3) Send only *_annotator_*.json to two different humans (blind).",
            "4) After return: run g2b_kappa.py + preference_v0_gate.sh with AIPLAT_EVAL_PREF_A/B.",
        ],
        "honesty": (
            "Blank pack only — not human κ until two annotators fill and gates run; "
            "never claim accuracy_claim=true from κ alone"
        ),
    }

    if not args.skip_g2b:
        pack = _load(args.tasks)
        tasks = [t for t in (pack.get("tasks") or []) if isinstance(t, dict)]
        if len(tasks) < 30:
            raise SystemExit(f"g2b tasks need ≥30, got {len(tasks)}")
        fac = out_dir / "g2b_facilitator.json"
        a = out_dir / "g2b_annotator_a.json"
        b = out_dir / "g2b_annotator_b.json"
        write_json(fac, build_g2b_facilitator(tasks))
        write_json(a, build_g2b_annotator(tasks, annotator_id="A"))
        write_json(b, build_g2b_annotator(tasks, annotator_id="B"))
        # Flat map — safe place to paste multi-line / JSON-looking model answers.
        outputs_stub = {str(t.get("id")): "" for t in tasks if t.get("id")}
        outputs_path = out_dir / "model_outputs.json"
        write_json(outputs_path, outputs_stub)
        readme_g2b = out_dir / "G2B_SEND.md"
        readme_g2b.write_text(
            "\n".join(
                [
                    "# G2b send checklist",
                    "",
                    "1. Edit **`model_outputs.json`** only (flat `{task_id: answer}`).",
                    "   Do **not** hand-paste multi-line answers into `g2b_facilitator.json`.",
                    "2. Sync:",
                    "",
                    "```bash",
                    "python3 packages/aiplat-evaluation/scripts/human_worksheet_pack.py \\",
                    f"  --from-outputs {out_dir}",
                    "```",
                    "",
                    "- **Send to annotators**: `g2b_annotator_a.json`, `g2b_annotator_b.json` only",
                    "- **Keep private**: `g2b_facilitator.json` / `model_outputs.json` (gold hints)",
                    "- After fill: `scripts/g2b_kappa.py --a … --b … --tasks docs/a3/g2b_tasks.v0.json`",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        manifest["files"].extend(
            [
                str(fac.name),
                str(a.name),
                str(b.name),
                str(outputs_path.name),
                str(readme_g2b.name),
            ]
        )
        manifest["g2b_task_n"] = len(tasks)

    if not args.skip_preference:
        pack = _load(args.pairs)
        pairs = [p for p in (pack.get("pairs") or []) if isinstance(p, dict)]
        if len(pairs) < 30:
            raise SystemExit(f"preference pairs need ≥30, got {len(pairs)}")
        a = out_dir / "pref_annotator_a.json"
        b = out_dir / "pref_annotator_b.json"
        write_json(a, build_preference_annotator(pairs, annotator_id="A"))
        write_json(b, build_preference_annotator(pairs, annotator_id="B"))
        readme_p = out_dir / "PREFERENCE_SEND.md"
        readme_p.write_text(
            "\n".join(
                [
                    "# Preference send checklist",
                    "",
                    "- Send `pref_annotator_a.json` / `pref_annotator_b.json` to two humans",
                    "- Each sets `preferred` to `a` | `b` | `tie` (replace null)",
                    "- Gate:",
                    "",
                    "```bash",
                    "AIPLAT_EVAL_PREF_A=…/pref_annotator_a.json \\",
                    "AIPLAT_EVAL_PREF_B=…/pref_annotator_b.json \\",
                    "  bash packages/aiplat-evaluation/scripts/preference_v0_gate.sh",
                    "```",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        manifest["files"].extend([str(a.name), str(b.name), str(readme_p.name)])
        manifest["preference_pair_n"] = len(pairs)

    man_path = out_dir / "MANIFEST.json"
    write_json(man_path, manifest)
    print(json.dumps({"gate": "ok", "out_dir": str(out_dir), "files": manifest["files"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
