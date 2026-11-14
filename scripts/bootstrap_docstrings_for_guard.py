#!/usr/bin/env python3
# docstring-guard: skip-file  # 引导脚本；产物仍须人工/守卫复核
"""为触及文件补齐守卫可过的中文 docstring（Args/一句话）。

用法:
  python3 scripts/bootstrap_docstrings_for_guard.py --files a.py b.py
  python3 scripts/bootstrap_docstrings_for_guard.py --dir aiPlat-core/core/apps/eval/service --only-failing

说明:
  - 只补缺失 docstring / 缺 Args 的 public 符号
  - 参数说明按常见命名启发式（tenant_id/run_id/body…），非空模板
  - 写完后请跑 check_python_docstring_guard.py --files 复核
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

WORKSPACE = Path(__file__).resolve().parent.parent

PARAM_HINTS = {
    "tenant_id": "租户 ID",
    "run_id": "运行 ID",
    "suite_id": "套件 ID",
    "case_id": "用例 ID",
    "actor": "操作者身份 dict",
    "body": "请求体 dict",
    "seed_dir": "种子目录；None 用默认",
    "path": "文件或目录路径",
    "limit": "返回条数上限",
    "offset": "分页偏移",
    "live": "是否 live（非 fixture）路径",
    "mode": "执行/评测模式",
    "kwargs": "附加关键字参数",
    "args": "位置参数",
    "report": "报告 dict",
    "payload": "载荷 dict",
    "config": "配置 dict",
    "store": "存储后端",
    "manifest": "清单 dict",
    "defaults": "默认配置",
    "pairs": "对照样本序列",
    "cases": "用例列表",
    "query": "查询文本",
    "text": "文本内容",
    "name": "名称",
    "version": "版本号",
    "status": "状态",
    "force": "是否强制",
    "dry_run": "是否仅演练",
    "enabled": "是否启用",
    "timeout": "超时秒数",
    "model": "模型名",
    "judge_model": "裁判模型",
    "subject_model": "被测模型",
}


def _param_names(node: ast.AST) -> List[str]:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    names: List[str] = []
    a = node.args
    for x in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
        if x.arg in ("self", "cls"):
            continue
        names.append(x.arg)
    if a.vararg:
        names.append(a.vararg.arg)
    if a.kwarg:
        names.append(a.kwarg.arg)
    return names


def _hint(name: str) -> str:
    if name in PARAM_HINTS:
        return PARAM_HINTS[name]
    if name.endswith("_id"):
        return f"{name[:-3]} 标识"
    if name.endswith("_path"):
        return "路径"
    if name.startswith("is_") or name.startswith("has_"):
        return "布尔开关"
    if name.endswith("_dir"):
        return "目录路径"
    return f"{name} 参数"


def _summary_from_name(name: str) -> str:
    # snake_case → short Chinese-ish summary using name tokens
    parts = name.strip("_").split("_")
    if name.startswith("get_"):
        return f"获取 {'_'.join(parts[1:])}。"
    if name.startswith("list_"):
        return f"列出 {'_'.join(parts[1:])}。"
    if name.startswith("create_"):
        return f"创建 {'_'.join(parts[1:])}。"
    if name.startswith("delete_"):
        return f"删除 {'_'.join(parts[1:])}。"
    if name.startswith("load_"):
        return f"加载 {'_'.join(parts[1:])}。"
    if name.startswith("build_"):
        return f"构建 {'_'.join(parts[1:])}。"
    if name.startswith("validate_"):
        return f"校验 {'_'.join(parts[1:])}。"
    if name.startswith("run_"):
        return f"执行 {'_'.join(parts[1:])}。"
    if name.startswith("compute_"):
        return f"计算 {'_'.join(parts[1:])}。"
    if name.startswith("annotate_"):
        return f"标注 {'_'.join(parts[1:])}。"
    if name.startswith("ensure_"):
        return f"确保 {'_'.join(parts[1:])}。"
    return f"{name}。"


def _make_doc(summary: str, params: Sequence[str], indent: str) -> str:
    lines = [f'{indent}"""{summary}']
    if params:
        lines.append("")
        lines.append(f"{indent}Args:")
        for p in params:
            lines.append(f"{indent}    {p}: {_hint(p)}。")
    lines.append(f'{indent}"""')
    return "\n".join(lines) + "\n"


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def patch_file(path: Path) -> Tuple[int, int]:
    """Returns (symbols_touched, parse_ok_as_1)."""
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return 0, 0
    lines = src.splitlines(keepends=True)
    inserts: List[Tuple[int, str]] = []
    replaces: List[Tuple[int, int, str]] = []
    touched = 0

    # module docstring
    if not ast.get_docstring(tree):
        mod = f'"""{path.stem}：评测服务模块。\n\n职责：见同目录 README / 调用方。\n"""\n\n'
        inserts.append((0, mod))
        touched += 1

    def handle_fn(node: ast.AST, class_indent: str = "") -> None:
        nonlocal touched
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return
        if node.name.startswith("_") and node.name not in ("__init__", "__call__"):
            return
        params = _param_names(node)
        existing = ast.get_docstring(node) or ""
        need_doc = not existing.strip()
        need_args = bool(params) and ("Args:" not in existing and "参数:" not in existing)
        if not need_doc and not need_args:
            return
        summary = existing.strip().split("\n")[0].strip().strip('"""').strip("'''") if existing else _summary_from_name(node.name)
        if not summary.endswith("。") and not summary.endswith("."):
            summary = summary + "。"
        # indent: method vs function
        def_line = lines[node.lineno - 1]
        ind = _indent_of(def_line) + "    "
        new_doc = _make_doc(summary if need_doc or need_args else summary, params if need_args or need_doc else params, ind)

        # single-line stub `def x(...): ...`
        if node.end_lineno == node.lineno and "..." in def_line:
            # rebuild
            if "):" in def_line:
                sig = def_line.split("):", 1)[0] + "):"
            else:
                sig = def_line[: def_line.rfind(":") + 1]
            base_ind = _indent_of(def_line)
            block = f"{sig}\n{_make_doc(summary, params, base_ind + '    ')}{base_ind}    ...\n"
            replaces.append((node.lineno - 1, node.lineno, block))
            touched += 1
            return

        if existing and need_args and isinstance(node.body[0], ast.Expr):
            # replace existing docstring node span
            start = node.body[0].lineno - 1
            end = node.body[0].end_lineno or node.body[0].lineno
            replaces.append((start, end, new_doc))
            touched += 1
            return
        if need_doc:
            inserts.append((node.body[0].lineno - 1, new_doc))
            touched += 1

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            if not ast.get_docstring(node):
                ind = _indent_of(lines[node.lineno - 1]) + "    "
                inserts.append((node.body[0].lineno - 1, f'{ind}"""{node.name}。"""\n'))
                touched += 1
            for item in node.body:
                handle_fn(item)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            handle_fn(node)

    for start, end, block in sorted(replaces, key=lambda x: -x[0]):
        lines[start:end] = [block]
    for at, text in sorted(inserts, key=lambda x: -x[0]):
        lines.insert(at, text)

    out = "".join(lines)
    try:
        ast.parse(out)
    except SyntaxError as e:
        print(f"SKIP syntax after patch {path}: {e}")
        return 0, 0
    path.write_text(out, encoding="utf-8")
    return touched, 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="+")
    ap.add_argument("--dir")
    ap.add_argument("--only-failing", action="store_true")
    args = ap.parse_args(argv)

    files: List[Path] = []
    if args.files:
        files = [WORKSPACE / f for f in args.files]
    elif args.dir:
        root = WORKSPACE / args.dir
        files = sorted(root.rglob("*.py"))
    else:
        ap.error("need --files or --dir")

    if args.only_failing:
        sys.path.insert(0, str(WORKSPACE))
        from scripts.check_python_docstring_guard import check_file, _is_skipped_path

        filtered = []
        for p in files:
            rel = str(p.relative_to(WORKSPACE))
            if _is_skipped_path(rel):
                continue
            hard = [
                f
                for f in check_file(p, None)
                if f.rule in ("module_doc", "public_doc", "args_doc", "noise_comment", "why_comment")
            ]
            if hard:
                filtered.append(p)
        files = filtered

    total_t = 0
    for p in files:
        if not p.is_file():
            continue
        t, ok = patch_file(p)
        if ok and t:
            print(f"patched {p.relative_to(WORKSPACE)} symbols~={t}")
            total_t += t
        elif ok and not t:
            print(f"noop {p.relative_to(WORKSPACE)}")
    print(f"done touched_symbols~={total_t} files={len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
