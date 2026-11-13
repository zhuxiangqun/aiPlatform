#!/usr/bin/env python3
"""Generate Arena blind annotator sheets (A/B/Tie) — P1b scaffold.

Honesty: strips model names; randomizes left/right; accuracy_claim=false;
length_heuristic winner must never appear on annotator sheets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCHEMA_ANNOTATOR = "eval.arena.blind.worksheet.v0"
SCHEMA_FACILITATOR = "eval.arena.blind.facilitator.v0"
JUDGE_VERSION = "arena.blind.v1"


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _swap_side(pair_id: str, salt: str) -> bool:
    """Deterministic swap: True → put response_b on Left."""
    digest = hashlib.sha256(f"{salt}:{pair_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 2 == 1


def build_facilitator_rows(
    pairs: Sequence[Mapping[str, Any]],
    *,
    salt: str,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for raw in pairs:
        pid = str(raw.get("pair_id") or "").strip()
        if not pid:
            continue
        swap = _swap_side(pid, salt)
        left_is = "b" if swap else "a"
        right_is = "a" if swap else "b"
        a = str(raw.get("response_a") or "")
        b = str(raw.get("response_b") or "")
        left = b if swap else a
        right = a if swap else b
        rows.append(
            {
                "pair_id": pid,
                "prompt": raw.get("prompt"),
                "left": left,
                "right": right,
                "left_is": left_is,
                "right_is": right_is,
                "model_a": raw.get("model_a"),
                "model_b": raw.get("model_b"),
                "swap": swap,
            }
        )
    return rows


def build_annotator_sheet(
    facilitator_rows: Sequence[Dict[str, Any]],
    *,
    annotator_id: str,
) -> Dict[str, Any]:
    labels: List[Dict[str, Any]] = []
    for row in facilitator_rows:
        labels.append(
            {
                "pair_id": row["pair_id"],
                "prompt": row.get("prompt"),
                "left": row.get("left"),
                "right": row.get("right"),
                # Annotator MUST set A|B|Tie (null = unlabeled).
                "label": None,
                "notes": "",
            }
        )
    return {
        "schema": SCHEMA_ANNOTATOR,
        "accuracy_claim": False,
        "judge_version": JUDGE_VERSION,
        "annotator_id": annotator_id,
        "blind": True,
        "instructions": (
            "For each pair_id: read prompt + Left + Right. "
            "Set label to A (prefer Left), B (prefer Right), or Tie. "
            "Do not estimate length winners. Do not share labels with other annotators. "
            "Follow ARENA_BLIND_RUBRIC_V1."
        ),
        "labels": labels,
    }


def build_facilitator_pack(
    facilitator_rows: Sequence[Dict[str, Any]],
    *,
    salt: str,
) -> Dict[str, Any]:
    return {
        "schema": SCHEMA_FACILITATOR,
        "accuracy_claim": False,
        "judge_version": JUDGE_VERSION,
        "not_for_annotators": True,
        "salt": salt,
        "instructions": (
            "Coordinator only. Never send this file to annotators. "
            "left_is/right_is map sheet sides back to response_a/response_b. "
            "Length heuristic winner must not be shown to annotators."
        ),
        "pairs": list(facilitator_rows),
    }


def collect_model_names(pairs: Sequence[Mapping[str, Any]]) -> List[str]:
    """Model ids that must never appear in annotator-facing files."""
    names: List[str] = []
    seen = set()
    for raw in pairs:
        if not isinstance(raw, Mapping):
            continue
        for key in ("model_a", "model_b"):
            val = str(raw.get(key) or "").strip()
            if val and val not in seen:
                seen.add(val)
                names.append(val)
    return names


def assert_annotator_bundle_blind(annotator_dir: Path, forbidden: Sequence[str]) -> None:
    """Fail closed if annotator bundle contains model ids (2026-11-05 SEND leak)."""
    if not annotator_dir.is_dir():
        raise SystemExit(f"missing annotator dir: {annotator_dir}")
    needles = [n for n in forbidden if n]
    if not needles:
        return
    for path in sorted(annotator_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".md", ".csv", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle in text:
                raise SystemExit(
                    f"blind leak: {path.name} contains model id {needle!r} "
                    f"(keep model names only under facilitator_only/)"
                )


def check_send_ready(pack_dir: Path) -> Dict[str, Any]:
    """Engineering SEND readiness for a stamped Arena pack (≠ QA overall_pass).

    Honesty: does not set accuracy_claim / does not replace length smoke /
    does not invent human QA signatures.
    """
    pack_dir = pack_dir.resolve()
    ann = pack_dir / "for_annotators"
    fac = pack_dir / "facilitator_only"
    gaps: List[str] = []
    if not ann.is_dir():
        gaps.append("missing_for_annotators")
    if not fac.is_dir():
        gaps.append("missing_facilitator_only")
    send_ann = ann / "ARENA_BLIND_SEND_ANNOTATOR.md"
    rubric = ann / "ARENA_BLIND_RUBRIC_V1.md"
    if ann.is_dir() and not send_ann.is_file():
        gaps.append("missing_send_annotator_md")
    if ann.is_dir() and not rubric.is_file():
        gaps.append("missing_rubric_md")
    ann_sheets = sorted(ann.glob("annotator_*.json")) if ann.is_dir() else []
    if len(ann_sheets) < 2:
        gaps.append("need_ge_2_annotator_sheets")
    fac_json = fac / "facilitator.json"
    if fac.is_dir() and not fac_json.is_file():
        gaps.append("missing_facilitator_json")

    forbidden: List[str] = []
    if fac_json.is_file():
        try:
            fac_doc = json.loads(fac_json.read_text(encoding="utf-8"))
            pairs = fac_doc.get("pairs") if isinstance(fac_doc, dict) else None
            if isinstance(pairs, list):
                forbidden = collect_model_names(pairs)
        except (OSError, json.JSONDecodeError) as exc:
            gaps.append(f"facilitator_unreadable:{exc}")
    leak_ok = True
    if ann.is_dir() and forbidden:
        try:
            assert_annotator_bundle_blind(ann, forbidden)
        except SystemExit as exc:
            leak_ok = False
            gaps.append(str(exc))
    elif ann.is_dir():
        # Always block raw model_a/model_b keys in annotator bundle.
        try:
            assert_annotator_bundle_blind(ann, ["model_a", "model_b"])
        except SystemExit as exc:
            leak_ok = False
            gaps.append(str(exc))

    root_fac = pack_dir / "facilitator.json"
    facilitator_isolated = fac_json.is_file() and (
        not root_fac.is_file()
        or "not_for_annotators" in root_fac.read_text(encoding="utf-8")
    )
    do_not_send = (pack_dir / "DO_NOT_SEND.md").is_file() or (
        pack_dir / "DO_NOT_SEND.txt"
    ).is_file()
    if root_fac.is_file() and not do_not_send:
        gaps.append("root_facilitator_without_do_not_send")

    for_annotators_has_send_split = (
        ann.is_dir()
        and send_ann.is_file()
        and rubric.is_file()
        and len(ann_sheets) >= 2
        and fac.is_dir()
    )
    send_ready = leak_ok and for_annotators_has_send_split and not gaps
    return {
        "schema": "eval.arena.blind.send_ready.v0",
        "accuracy_claim": False,
        "replaces_length_smoke": False,
        "qa_overall_pass": False,
        "pack_dir": str(pack_dir),
        "leak_guard_pass": leak_ok,
        "for_annotators_has_send_split": for_annotators_has_send_split,
        "facilitator_isolated": facilitator_isolated,
        "do_not_send_marker": do_not_send,
        "annotator_sheet_n": len(ann_sheets),
        "gaps": gaps,
        "send_ready": send_ready,
        "honesty": (
            "Engineering SEND hygiene only; human QA overall_pass still required; "
            "accuracy_claim=false; length smoke not replaced."
        ),
    }


def write_pack(
    pairs_path: Path,
    out_root: Path,
    *,
    annotators: Sequence[str],
    salt: str,
) -> Path:
    data = _load(pairs_path)
    pairs = data.get("pairs") if isinstance(data.get("pairs"), list) else []
    rows = build_facilitator_rows(pairs, salt=salt)
    stamp = _stamp()
    dest = out_root / stamp
    ann_dir = dest / "for_annotators"
    fac_dir = dest / "facilitator_only"
    ann_dir.mkdir(parents=True, exist_ok=True)
    fac_dir.mkdir(parents=True, exist_ok=True)

    fac = build_facilitator_pack(rows, salt=salt)
    (fac_dir / "facilitator.json").write_text(
        json.dumps(fac, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # legacy alias at pack root for older tooling (still facilitator-only semantics)
    (dest / "facilitator.json").write_text(
        json.dumps(fac, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for aid in annotators:
        sheet = build_annotator_sheet(rows, annotator_id=aid)
        name = f"annotator_{aid}.json"
        (ann_dir / name).write_text(
            json.dumps(sheet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        # root alias for smoke tests / existing callers
        (dest / name).write_text(
            json.dumps(sheet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    docs_a3 = Path(__file__).resolve().parents[1] / "docs" / "a3"
    send_ann = docs_a3 / "ARENA_BLIND_SEND_ANNOTATOR.md"
    send_fac = docs_a3 / "ARENA_BLIND_SEND_FACILITATOR.md"
    rubric = docs_a3 / "ARENA_BLIND_RUBRIC_V1.md"
    if send_ann.is_file():
        (ann_dir / send_ann.name).write_text(send_ann.read_text(encoding="utf-8"), encoding="utf-8")
    if rubric.is_file():
        (ann_dir / rubric.name).write_text(rubric.read_text(encoding="utf-8"), encoding="utf-8")
    if send_fac.is_file():
        (fac_dir / send_fac.name).write_text(send_fac.read_text(encoding="utf-8"), encoding="utf-8")

    forbidden = collect_model_names(pairs)
    assert_annotator_bundle_blind(ann_dir, forbidden)

    (dest / "DO_NOT_SEND.md").write_text(
        (
            "# DO NOT SEND this pack root to annotators\n\n"
            "- **Send only** `for_annotators/` (+ its SEND/rubric copies).\n"
            "- **Never send** `facilitator_only/`, root `facilitator.json`, or any file with model names.\n"
            "- `accuracy_claim=false` · length smoke is **not** replaced by this pack.\n"
        ),
        encoding="utf-8",
    )

    meta = {
        "schema": "eval.arena.blind.pack.meta.v0",
        "accuracy_claim": False,
        "judge_version": JUDGE_VERSION,
        "stamp": stamp,
        "pairs_source": str(pairs_path),
        "pair_count": len(rows),
        "annotators": list(annotators),
        "rubric": "docs/a3/ARENA_BLIND_RUBRIC_V1.md",
        "pilot": "docs/a3/ARENA_BLIND_PILOT.md",
        "for_annotators": "for_annotators/",
        "facilitator_only": "facilitator_only/",
        "send_annotator": "docs/a3/ARENA_BLIND_SEND_ANNOTATOR.md",
        "send_facilitator": "docs/a3/ARENA_BLIND_SEND_FACILITATOR.md",
        "do_not_send": "DO_NOT_SEND.md",
        "note": (
            "Send only for_annotators/ to reviewers. Never send facilitator_only/ "
            "or files that name model_a/model_b. accuracy_claim=false; length smoke not replaced."
        ),
    }
    (dest / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return dest


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        type=Path,
        default=None,
        help="Check SEND readiness of an existing stamped pack (no rewrite)",
    )
    ap.add_argument(
        "--pairs",
        type=Path,
        default=Path("docs/a3/arena_blind_pairs.v0.json"),
        help="Pairs JSON (facilitator source)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("docs/a3/human_pack/arena_blind"),
        help="Output root for stamped pack dirs",
    )
    ap.add_argument(
        "--annotators",
        type=str,
        default="r1,r2",
        help="Comma-separated annotator ids",
    )
    ap.add_argument(
        "--salt",
        type=str,
        default="arena.blind.v1",
        help="Deterministic left/right shuffle salt",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)
    if args.check is not None:
        report = check_send_ready(Path(args.check))
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get("send_ready") else 2
    aids = [a.strip() for a in str(args.annotators).split(",") if a.strip()]
    if len(aids) < 2:
        raise SystemExit("need at least two annotator ids")
    dest = write_pack(args.pairs, args.out, annotators=aids, salt=str(args.salt))
    print(f"OK wrote {dest} pairs={len(list(dest.glob('annotator_*.json')))} annotators")
    return 0


def _wire_pack() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Same-file caller for method_verify."""
    rows = build_facilitator_rows(
        [
            {
                "pair_id": "arena-x",
                "prompt": "p",
                "response_a": "aa",
                "response_b": "bbb",
                "model_a": "m1",
                "model_b": "m2",
            }
        ],
        salt="t",
    )
    return build_facilitator_pack(rows, salt="t"), build_annotator_sheet(
        rows, annotator_id="r1"
    )


if __name__ == "__main__":
    raise SystemExit(main())
