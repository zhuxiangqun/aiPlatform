#!/usr/bin/env python3
"""小朱策展学习闭环：统计 / 导出 / 达标后提交微调任务。

用法:
  python3 scripts/digital_human_curated_learn.py --dry-run
  python3 scripts/digital_human_curated_learn.py --submit
  python3 scripts/digital_human_curated_learn.py --submit --force

环境:
  AIPLAT_DH_SFT_MIN_SAMPLES   默认 10
  AIPLAT_DH_SFT_AUTO_SUBMIT   默认 1；0=只导出不提交
  AIPLAT_DH_SFT_BASE_MODEL    可选；未设则 best_model_for_purpose(chat)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "aiPlat-core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))


def main() -> int:
    """CLI：策展轨迹达标后 dry-run/提交小朱 SFT（不切生产路由）。"""
    parser = argparse.ArgumentParser(description="Digital human curated SFT loop")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只导出并统计，不建 dataset/job",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="尝试提交微调（默认行为；与 --dry-run 互斥时 dry-run 优先）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略指纹防抖强制再提交",
    )
    args = parser.parse_args()
    # 默认走 maybe_submit（仍受 AIPLAT_DH_SFT_AUTO_SUBMIT 约束）；--dry-run 只统计
    dry = bool(args.dry_run)

    from core.harness.digital_human.consultant_sft_loop import (
        maybe_submit_digital_human_sft,
    )

    result = maybe_submit_digital_human_sft(force=args.force, dry_run=dry)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("reason") in ("need_more", "need_more_after_convert"):
        return 2
    if str(result.get("reason") or "").startswith("error:"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
