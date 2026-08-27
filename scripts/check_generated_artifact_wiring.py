"""check_generated_artifact_wiring.py — 平台能力生成物适用性守卫（2026-08-27）。

背景（根因治理）：评测侧闭环/通用基础设施（经验回写、断线续跑、消息总线等）
落地时未评估应用工厂生成物的适用性——平台与产物"两张皮"。本守卫强制：
  每个平台能力族（governance/*、apps/*、builder、kb），AIPLAT_CAPABILITIES.md
  必须有含该能力族路径的条目，且至少一条含"生成物"适用性评估声明（适用/不适用+理由）。

判定：
  Rule A: <family> 在 CAPABILITIES 中有条目（路径匹配）
  Rule B: 该 family 至少一条含"生成物"字样
  任一违反 → violation（--ci 时退出码 1；本地默认 warning 不阻断）

用法：
  python3 scripts/check_generated_artifact_wiring.py            # 检查（违规退出码 1）
  python3 scripts/check_generated_artifact_wiring.py --ci       # CI 模式
"""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
PLATFORM = WORKSPACE / "aiPlat-platform"
CAPABILITIES = WORKSPACE / "AIPLAT_CAPABILITIES.md"

# 排除：非"能力模块"的文件（包导出/配置）
_SKIP = {"__init__.py", "__pycache__"}


def discover_families() -> list[str]:
    """平台能力族：governance 模块（顶层 .py + 有 __init__.py 的子目录）
    + apps/* 子模块 + builder + kb。"""
    families = []

    def _gov() -> None:
        gov = PLATFORM / "governance"
        if not gov.is_dir():
            return
        for p in sorted(gov.iterdir()):
            if p.name in _SKIP:
                continue
            if p.is_file() and p.suffix == ".py":
                families.append(f"governance/{p.stem}")
            elif p.is_dir() and (p / "__init__.py").exists():
                families.append(f"governance/{p.name}")

    def _apps() -> None:
        apps = PLATFORM / "apps"
        if not apps.is_dir():
            return
        for p in sorted(apps.iterdir()):
            if p.name in _SKIP or p.name == "common_schemas":
                continue
            # 能力族：有 __init__.py 或 api/ 目录（namespace 子模块如 prompt/value/misc）
            if p.is_dir() and ((p / "__init__.py").exists() or (p / "api").is_dir()):
                families.append(f"apps/{p.name}")

    def _top() -> None:
        for name in ("builder", "kb"):
            if (PLATFORM / name).is_dir():
                families.append(name)

    _gov()
    _apps()
    _top()
    return families


def check(caps_text: str, families: list[str]) -> list[str]:
    violations = []
    for fam in families:
        lines = [line for line in caps_text.splitlines() if line.strip().startswith("|")]
        entry_found = any(fam in line for line in lines)
        if not entry_found:
            violations.append(f"Rule A: {fam} 无 CAPABILITIES 条目（新增平台能力必须登记）")
            continue
        family_lines = [line for line in lines if fam in line]
        if not any("生成物" in line for line in family_lines):
            violations.append(
                f"Rule B: {fam} 的 CAPABILITIES 条目缺「生成物」适用性评估声明"
                f"（适用/不适用+理由，防平台-产物脱节）")
    return violations


def main() -> int:
    ci = "--ci" in sys.argv
    if not CAPABILITIES.exists():
        print("CAPABILITIES 不存在，跳过")
        return 0
    families = discover_families()
    if not families:
        print("未发现平台能力族，跳过")
        return 0
    caps_text = CAPABILITIES.read_text(encoding="utf-8")
    violations = check(caps_text, families)
    if not violations:
        print(f"✅ generated-artifact wiring: {len(families)} 平台能力族均含生成物适用性评估")
        return 0
    print(f"⚠️ generated-artifact wiring: {len(violations)} violation(s):")
    for v in violations:
        print(f"  - {v}")
    if ci:
        return 1
    print("  (本地不阻断；CI 强制)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
