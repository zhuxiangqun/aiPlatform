"""guard_undefined_names.py — AST 级"函数内未定义符号"守卫（2026-08-19 新增）。

背景：ruff F821 被 pyproject.toml ignore（eval/exec 误报），py_compile 只查语法
→ pipeline_execution.py 的 PipelineConfig 未 import（NameError）长期未被发现，
导致应用工厂 rebuild 无输出。

本脚本用 AST 扫描 api/routers + platform 代码中「函数/闭包内使用的大写类名/
常量，但无任何 import 或定义」——即运行时 NameError 隐患。

误报豁免：
- builtins（Exception/ValueError 等）
- 嵌套类/函数内 lazy import/函数内赋值（本作用域或父作用域可解析）
- 小写风格常量（BATCH 等）

用法：
  python3 scripts/guard_undefined_names.py            # 扫描 + 基线对比（仅新增阻断）
  python3 scripts/guard_undefined_names.py --rebuild  # 重建基线
  python3 scripts/guard_undefined_names.py --all      # 全量输出（含存量）
"""
from __future__ import annotations

import ast
import builtins
import json
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
BASELINE_FILE = WORKSPACE_ROOT / "scripts" / "baselines" / "undefined_names_baseline.json"

BUILTINS = set(dir(builtins))

SCAN_DIRS = [
    WORKSPACE_ROOT / "aiPlat-core/core/api/routers",
    WORKSPACE_ROOT / "aiPlat-platform/api/routers",
    WORKSPACE_ROOT / "aiPlat-platform/apps",
    WORKSPACE_ROOT / "aiPlat-platform/builder",
]

# 已知误报豁免（经过人工核实的模式）
KNOWN_FP = {
    # (relpath, name) — 确认是误报（嵌套定义/动态引用等）
}


def check_file(fp: Path) -> list:
    """返回该文件 (name, lineno) 列表——函数内使用但无 import/定义的大写符号。"""
    try:
        tree = ast.parse(fp.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                imported.add(a.asname or a.name)

    defined = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defined.add(t.id)
        elif isinstance(node, (ast.AnnAssign,)):
            if isinstance(node.target, ast.Name):
                defined.add(node.target.id)
    module_scope = imported | defined

    issues = []

    def walk_scope(node, scope_names, path_str):
        local = set(scope_names)
        # 递归收集所有后代定义（含 if/for/try 块内嵌套类/函数/局部 import/赋值）
        for n in ast.walk(node):
            if n is node:
                continue
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                local.add(n.name)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    local.add(a.asname or a.name.split(".")[0])
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    local.add(a.asname or a.name)
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        local.add(t.id)
        for n in ast.walk(node):
            if (isinstance(n, ast.Name) and n.id[:1].isupper() and n.id not in local
                    and n.id not in module_scope and n.id not in BUILTINS):
                issues.append((path_str, n.id, n.lineno))
        for n in ast.iter_child_nodes(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk_scope(n, local, path_str + "::" + n.name)

    walk_scope(tree, set(), str(fp.relative_to(WORKSPACE_ROOT)))
    return issues


def main() -> int:
    show_all = "--all" in sys.argv
    rebuild = "--rebuild" in sys.argv

    findings = []
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for fp in d.rglob("*.py"):
            if "__pycache__" in str(fp):
                continue
            for path_str, name, lineno in check_file(fp):
                key = (path_str, name)
                if key in KNOWN_FP:
                    continue
                findings.append({"file": path_str, "symbol": name, "line": lineno})

    if rebuild:
        BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_FILE.write_text(json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"baseline rebuilt: {len(findings)} findings")
        return 0

    baseline = []
    if BASELINE_FILE.exists():
        try:
            baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        except Exception:
            baseline = []

    baseline_keys = {(f["file"], f["symbol"]) for f in baseline}
    new_findings = [f for f in findings if (f["file"], f["symbol"]) not in baseline_keys]

    print(f"=== guard_undefined_names: {len(findings)} total, {len(new_findings)} new ===")
    if show_all:
        for f in findings:
            print(f"  ⚠️  {f['file']}:{f['line']}: {f['symbol']}")
    for f in new_findings:
        print(f"  ❌ NEW {f['file']}:{f['line']}: {f['symbol']}")

    if new_findings:
        print("\n❌ FAIL: 新增函数内未定义符号（NameError 隐患）——请补 import 或定义")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
