#!/usr/bin/env python3
"""Code-review gold eval CLI — Precision/Recall for autoreview (ReviewBench-style).

Usage:
  # Matcher-only (cases with embedded ``predicted`` fixtures; no LLM)
  python3 scripts/eval_code_review_gold.py --match-only \\
    --gold-dir aiPlat-core/workspace_seeds/eval/code_review_gold

  # Live autoreview against gold targets (needs git targets in cases)
  python3 scripts/eval_code_review_gold.py --profile balanced

  # List noise tiers
  python3 scripts/eval_code_review_gold.py --list-profiles
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "aiPlat-core"))


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="autoreview gold Precision/Recall")
    parser.add_argument("--profile", default="balanced", choices=["low_noise", "balanced", "high_coverage"])
    parser.add_argument("--gold-dir", default="", help="default: ~/.aiplat/eval/code_review_gold")
    parser.add_argument("--match-only", action="store_true", help="score embedded predicted fixtures only")
    parser.add_argument("--case-id", action="append", default=[], help="filter case id (repeatable)")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--tenant-id", default="", help="tenant-scoped gold/report dirs")
    parser.add_argument("--no-persist", action="store_true", help="do not append JSONL report")
    parser.add_argument("--record-novel", action="store_true", help="P0/P1 unmatched → shared_memory (not gold)")
    parser.add_argument("--list-profiles", action="store_true")
    parser.add_argument(
        "--install-seeds",
        action="store_true",
        help="copy workspace_seeds/eval/code_review_gold → ~/.aiplat/eval/code_review_gold",
    )
    parser.add_argument("--json", action="store_true", help="print full JSON")
    args = parser.parse_args(argv)

    from core.harness.evaluation.code_review_gold import list_profiles, run_code_review_gold_eval

    if args.list_profiles:
        print(json.dumps(list_profiles(), indent=2, ensure_ascii=False))
        return 0

    if args.install_seeds:
        import shutil

        src = _ROOT / "aiPlat-core" / "workspace_seeds" / "eval" / "code_review_gold"
        try:
            from core.utils.paths import get_aiplat_data_dir

            dest = Path(get_aiplat_data_dir("eval/code_review_gold"))
        except Exception:
            dest = Path.home() / ".aiplat" / "eval" / "code_review_gold"
        dest.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in sorted(src.glob("*.yaml")):
            shutil.copy2(f, dest / f.name)
            n += 1
        print(f"installed {n} seed files → {dest}")
        return 0 if n else 1

    out = asyncio.run(
        run_code_review_gold_eval(
            profile=args.profile,
            gold_dir=args.gold_dir or None,
            case_ids=args.case_id or None,
            match_only=args.match_only,
            limit=args.limit,
            tenant_id=args.tenant_id,
            persist=not args.no_persist,
            record_novel=args.record_novel,
        )
    )

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(
            f"profile={out.get('profile')} scored={out.get('scored_count')}/{out.get('case_count')} "
            f"P={out.get('precision')} R={out.get('recall')} P0_R={out.get('p0_recall')} "
            f"avg_comments={out.get('avg_comment_count')} novel={out.get('novel_count')} "
            f"elapsed={out.get('elapsed_sec')}s"
        )
        for c in out.get("cases") or []:
            status = "ok" if c.get("ok") else c.get("reason") or "fail"
            print(
                f"  - {c.get('id')}: {status} P={c.get('precision')} R={c.get('recall')} "
                f"P0_R={c.get('p0_recall')} comments={c.get('comment_count')}"
            )

    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
