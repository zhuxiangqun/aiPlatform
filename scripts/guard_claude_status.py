#!/usr/bin/env python3
"""
guard_claude_status.py — 分流守卫（文档治理阶段二 P2a）

防止 CLAUDE.md 回到"只加不减"：拦截往 CLAUDE.md 新增「状态型 §5.NNN 小节」的行为。
Phase 状态应写入 docs/PHASE_STATUS.md，能力清单写入 AIPLAT_CAPABILITIES.md，
CLAUDE.md 只保留耐久治理规则。

复用 classify_claude_sections.classify 的确定性判据（STATUS = 日期/计数/Phase X.Y 且 0 条强制规则标记）。

两种模式：
  --staged   (pre-commit)  只看本次暂存的 CLAUDE.md diff 中"新增"的 §5.NNN 标题，
                            若为 STATUS 型 → 打印警告，退出码 1（WARNING，可用 --strict 升级为阻断）
  --check    (CI/doc_health) 全量扫描当前 CLAUDE.md，报告存量 STATUS 型 §5.NNN（回归监视）

用法:
  python3 scripts/guard_claude_status.py --staged
  python3 scripts/guard_claude_status.py --check
  python3 scripts/guard_claude_status.py --staged --strict   # 命中即阻断 (退出码 2)

退出码: 0=无新增状态节, 1=有(WARNING), 2=有且 --strict(阻断)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_claude_sections import parse_sections, classify  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[1]
CLAUDE_REL = "aiPlat-core/CLAUDE.md"
CLAUDE_MD = WORKSPACE / CLAUDE_REL

HEADING_RE = re.compile(r"^#{2,3} (5\.\d+)\s+(.*)$")


def _classify_current() -> list:
    if not CLAUDE_MD.exists():
        return []
    lines = CLAUDE_MD.read_text(encoding="utf-8").splitlines(keepends=True)
    secs = parse_sections(lines)
    for s in secs:
        classify(s)
    return secs


def _added_headings_staged() -> set:
    """§numbers whose heading line is ADDED in the staged CLAUDE.md diff."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--", CLAUDE_REL],
            cwd=str(WORKSPACE), capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception:
        return set()
    added = set()
    for line in out.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            m = HEADING_RE.match(line[1:])
            if m:
                added.add(m.group(1))
    return added


def run_staged(strict: bool) -> int:
    added = _added_headings_staged()
    if not added:
        return 0
    secs = {s.number: s for s in _classify_current()}
    offenders = [(n, secs[n]) for n in sorted(added) if n in secs and secs[n].tag == "STATUS"]
    if not offenders:
        return 0
    print("\n  ⚠ 分流守卫：CLAUDE.md 新增了「状态型」小节——应写入 docs/PHASE_STATUS.md，非 CLAUDE.md：")
    for n, s in offenders:
        print(f"      §{n}  {s.title[:50]}")
    print("      CLAUDE.md 只放耐久规则；Phase 状态 → docs/PHASE_STATUS.md；能力清单 → AIPLAT_CAPABILITIES.md")
    print("      （如确为规则，加入'强制/禁止/必须/红线'等约束词即可通过）\n")
    return 2 if strict else 1


def run_check() -> int:
    secs = _classify_current()
    status_secs = [s for s in secs if s.tag == "STATUS"]
    print(f"CLAUDE.md 存量 STATUS 型 §5.NNN: {len(status_secs)} 节")
    for s in status_secs:
        print(f"  §{s.number}  {s.title[:50]}  (行 {s.start}-{s.end})")
    if status_secs:
        print("\n  建议：将上列状态节迁至 docs/PHASE_STATUS.md（运行 scripts/extract_status_sections.py）")
        return 1
    print("  ✓ 无存量状态节，CLAUDE.md 保持规则聚焦")
    return 0


def main() -> int:
    strict = "--strict" in sys.argv
    if "--check" in sys.argv:
        return run_check()
    # default = staged
    return run_staged(strict)


if __name__ == "__main__":
    sys.exit(main())
