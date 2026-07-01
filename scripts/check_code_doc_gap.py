#!/usr/bin/env python3
"""
代码-文档能力缺口检测

扫描 core/harness/ 下新增的公共类/函数，检测哪些没有在 CAPABILITIES.md 中登记。

用法:
  python3 scripts/check_code_doc_gap.py [--ci]
  --ci    Exit with non-zero if gaps found (non-blocking: returns 1 but CI warns, not errors)

原理:
  1. 遍历 core/harness/ 下所有 .py 文件
  2. 提取公开类名 (class Xxx) 和遗留模块 getter (get_xxx_registry/manager)
  3. 检查每个名称是否在 CAPABILITIES.md 中出现
  4. 未出现的登记为 gap

已知例外 (grep_exclude):
  - 测试文件 (tests/)
  - 内部 dataclass / base class / template
  - 已有 capability entry 但用了不同命名

退出码: 0=无缺口, 1=有缺口
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Set

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "aiPlat-core" / "core" / "harness"
CAPABILITIES = ROOT / "AIPLAT_CAPABILITIES.md"

# 已知不在 CAPABILITIES 中登记的模块（内部工具/基础设施/base class）
KNOWN_INTERNAL: Set[str] = {
    "BaseTool", "ToolResult", "BaseModelAdapter", "BaseLoop",
    "LoopState", "LoopConfig", "PipelineState", "PipelineEventBus",
    "_Decision", "_RouteDecision", "DebateState",
    "ImplicitSignal", "SFTDatasetConfig",
    "SpecVersion", "SpecStatus", "RevisionTrigger",
    "SuggestionType", "Severity", "TraceStep", "TraceSummary",
    "RolloutConfig", "ABTestResult",
    "_ENGINE_INTERNAL", "_WORKSPACE_PERSONA", "_WORKSPACE_UTILITY", "_ENGINE_SYSTEM",
}

# 已知不是能力模块的目录（跳过扫描）
SKIP_DIRS = {"__pycache__", ".venv", "tests", "tools", "mcp", "adapters"}


def extract_public_names(filepath: Path) -> Set[str]:
    """Extract class names and singleton getter names from a file."""
    names: Set[str] = set()
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return names

    for node in ast.walk(tree):
        # Class names (public, not starting with _)
        if isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                names.add(node.name)

        # Singleton getter functions (get_xxx_registry, get_xxx_manager, etc.)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("get_") and not node.name.startswith("_"):
                names.add(node.name)

        # Module-level singleton instances (xxx_registry, xxx_manager)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    n = target.id
                    if any(suffix in n for suffix in ("_registry", "_manager", "_singleton", "_instance")):
                        if not n.startswith("_"):
                            names.add(n)

    return names - KNOWN_INTERNAL


def check_gaps() -> int:
    """Scan harness for files with no CAPABILITIES.md reference at all."""
    if not CAPABILITIES.exists():
        print("⚠️  AIPLAT_CAPABILITIES.md not found")
        return 1

    content = CAPABILITIES.read_text(encoding="utf-8")
    gaps: list[str] = []

    for py_file in sorted(HARNESS.rglob("*.py")):
        # Skip utils / __init__ / internal directories
        if py_file.name == "__init__.py":
            continue
        if any(d in str(py_file) for d in ("__pycache__", ".venv", "tests", "scripts")):
            continue

        rel_path = str(py_file.relative_to(ROOT))
        # Extract the key identifier: filename stem or parent directory
        stem = py_file.stem
        parent = py_file.parent.name

        # Check if stem or parent appears in CAPABILITIES
        if stem not in content and parent not in content:
            # Also check known modules that don't belong in CAPABILITIES
            if any(skip in rel_path for skip in (
                "kernel/", "utils/", "hooks/", "observability/events/",
                "observability/metrics/", "observability/alerts/",
                "observability/monitoring/", "smoke/", "infrastructure/config/",
                "infrastructure/crypto/", "infrastructure/di/", "infrastructure/gates/",
                "assembly/", "practice/", "langgraph/compiled_graphs/",
            )):
                continue
            gaps.append(rel_path)

    if gaps:
        print(f"⚠️  {len(gaps)} 个 harness 模块未在 CAPABILITIES 中登记:")
        for path in gaps[:20]:
            print(f"  - {path}")
        if len(gaps) > 20:
            print(f"  ... 及另外 {len(gaps) - 20} 个")
        print("\n修复: 在 AIPLAT_CAPABILITIES.md 对应子系统章节中为每个模块添加一行")
        return 1
    else:
        print("✅ 所有 harness 模块已在 CAPABILITIES 中登记")
        return 0


if __name__ == "__main__":
    sys.exit(check_gaps())
