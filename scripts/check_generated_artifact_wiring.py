"""check_generated_artifact_wiring.py — 平台能力生成物适用性守卫（2026-08-27）。

背景（根因治理）：评测侧闭环/通用基础设施（经验回写、断线续跑、消息总线等）
落地时未评估应用工厂生成物的适用性——平台与产物"两张皮"。本守卫强制：
  每个 aiPlat-platform/governance/ 能力模块，AIPLAT_CAPABILITIES.md 必须有
  含该模块路径的条目，且条目必须含"生成物"适用性评估声明（适用/不适用+理由）。

判定：
  Rule A: governance/<mod> 在 CAPABILITIES 中有条目（路径匹配）
  Rule B: 该条目含"生成物"字样
  任一违反 → violation（--ci 时退出码 1；本地默认 warning 不阻断）

用法：
  python3 scripts/check_generated_artifact_wiring.py            # 检查（违规退出码 1）
  python3 scripts/check_generated_artifact_wiring.py --ci       # CI 模式
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
GOVERNANCE_DIR = WORKSPACE / "aiPlat-platform" / "governance"
CAPABILITIES = WORKSPACE / "AIPLAT_CAPABILITIES.md"

# 排除：非"能力模块"的文件（包导出/配置）
_SKIP = {"__init__.py", "__pycache__"}


def discover_modules() -> list[str]:
    """governance/ 下能力模块：顶层 .py（去扩展名）+ 含 __init__.py 的子目录。"""
    mods = []
    if not GOVERNANCE_DIR.is_dir():
        return mods
    for p in sorted(GOVERNANCE_DIR.iterdir()):
        if p.name in _SKIP:
            continue
        if p.is_file() and p.suffix == ".py":
            mods.append(p.stem)
        elif p.is_dir() and (p / "__init__.py").exists():
            mods.append(p.name)
    return mods


def check(caps_text: str, mods: list[str]) -> list[str]:
    violations = []
    for mod in mods:
        path_ref = f"governance/{mod}"
        entry_found = any(path_ref in line for line in caps_text.splitlines()
                          if line.strip().startswith("|"))
        if not entry_found:
            violations.append(f"Rule A: governance/{mod} 无 CAPABILITIES 条目（新增平台能力必须登记）")
            continue
        entry = next(line for line in caps_text.splitlines()
                     if line.strip().startswith("|") and path_ref in line)
        if "生成物" not in entry:
            violations.append(
                f"Rule B: governance/{mod} 的 CAPABILITIES 条目缺「生成物」适用性评估声明"
                f"（适用/不适用+理由，防平台-产物脱节）")
    return violations


def main() -> int:
    ci = "--ci" in sys.argv
    if not CAPABILITIES.exists():
        print("CAPABILITIES 不存在，跳过")
        return 0
    mods = discover_modules()
    if not mods:
        print("governance/ 无能力模块，跳过")
        return 0
    caps_text = CAPABILITIES.read_text(encoding="utf-8")
    violations = check(caps_text, mods)
    if not violations:
        print(f"✅ generated-artifact wiring: {len(mods)} governance 模块均含生成物适用性评估")
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
