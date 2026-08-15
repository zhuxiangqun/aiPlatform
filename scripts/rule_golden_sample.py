#!/usr/bin/env python3
"""P0-C7: Rule Golden Sample Checker — 守卫规则自检。

检测 arch_guard_rules.yaml 中每条规则的 pattern 是否会被 Python re 正确执行。
防止"12 条 \\| 语法 bug"重演（grep BRE 的 OR 语法 \\| 在 Python re 中匹配字面竖线，
导致 grep_required 规则永远无法命中 → 恒误报）。

检查项：
1. pattern 是否含 \\| （反模式：grep BRE OR 语法，Python re 中语义错误）
2. pattern 是否能被 re.compile 编译（语法错误）
3. 可选：grep_required 规则是否在指定 paths 有真实命中（黄金样本验证）

用法：
  python3 scripts/rule_golden_sample.py           # 检查 1+2（快速，已接线 architecture_guard.sh 日常运行）
  python3 scripts/rule_golden_sample.py --verify  # 检查 1+2+3（慢，黄金样本完整验证，建议独立 CI job 运行）

设计：
  - 守卫日常（architecture_guard.sh）跑语法级检查（1+2）——防 \| 反模式/编译错误重演，0 成本
  - --verify（检查 3）会标记"规则要求但系统未达标"的真问题（如 meta_agent/caller_verify），
    这些是真合规缺口，应由对应 P0 修复（见 aiPlat问题总清单与行动纲领.md）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
RULES_YAML = WORKSPACE / "aiPlat-core/core/management/arch_guard_rules.yaml"


def load_rules() -> list[dict]:
    import yaml
    with open(RULES_YAML) as f:
        data = yaml.safe_load(f)
    return data.get("rules", [])


def check_backslash_pipe(pattern: str) -> bool:
    """检测 pattern 中的 \\| 反模式（grep BRE OR 语法误用于 Python re）。"""
    # 真实反模式是 \\| （YAML 转义后为 \|），即反斜杠+竖线
    return "\\|" in pattern


def check_compile(pattern: str) -> str | None:
    """检测 pattern 能否被 Python re 编译。返回错误信息或 None。"""
    try:
        re.compile(pattern)
        return None
    except re.error as e:
        return str(e)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true",
                        help="额外执行黄金样本验证（grep_required 规则必须有真实命中）")
    args = parser.parse_args()

    rules = load_rules()
    failures = []
    verify_failures = []

    for r in rules:
        check = r.get("check", {})
        ctype = check.get("type", "?")
        pattern = check.get("pattern", "")
        if not pattern:
            continue

        # 检查 1: \\| 反模式
        if check_backslash_pipe(pattern):
            failures.append(
                f"[{r.get('id','?')}] level={r.get('level','?')} type={ctype} "
                f"pattern 含 \\\\|（grep BRE OR 语法误用于 Python re）: {pattern[:60]}"
            )

        # 检查 2: re 编译
        err = check_compile(pattern)
        if err:
            failures.append(
                f"[{r.get('id','?')}] level={r.get('level','?')} pattern 编译失败: {err}"
            )

        # 检查 3（--verify）: grep_required 必须有真实命中
        if args.verify and ctype == "grep_required" and pattern:
            paths = check.get("paths", [])
            hits = _count_hits(pattern, paths, check.get("ext", [".py"]))
            min_matches = check.get("min_matches", 1)
            if hits < min_matches:
                verify_failures.append(
                    f"[{r.get('id','?')}] grep_required 黄金样本失败: pattern 在 paths 中命中 {hits} 次（需 ≥{min_matches}）: {pattern[:50]}"
                )

    print(f"规则总数: {len(rules)} | 含 pattern: {sum(1 for r in rules if r.get('check',{}).get('pattern'))}")
    print(f"检查1+2（语法级）: {len(failures)} 个问题")
    for f in failures:
        print(f"  ❌ {f}")

    if args.verify:
        print(f"检查3（黄金样本）: {len(verify_failures)} 个问题")
        for f in verify_failures[:20]:
            print(f"  ❌ {f}")

    # 汇总
    total = len(failures) + (len(verify_failures) if args.verify else 0)
    if total > 0:
        print(f"\n❌ 规则自检失败: {total} 个问题（修复后重跑）")
        return 1
    print("\n✅ 规则自检通过")
    return 0


def _count_hits(pattern: str, paths: list[str], ext: list[str]) -> int:
    """在指定 paths 中统计 pattern 命中数（复用守卫的扫描语义，简化版）。"""
    try:
        rx = re.compile(pattern)
    except re.error:
        return 0
    hits = 0
    for p in paths:
        base = WORKSPACE / p
        if not base.exists():
            continue
        files = list(base.rglob("*")) if base.is_dir() else [base]
        for fp in files:
            if not fp.is_file() or not fp.suffix in (ext or [".py"]):
                continue
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for line in content.split("\n"):
                if rx.search(line):
                    hits += 1
    return hits


if __name__ == "__main__":
    sys.exit(main())
