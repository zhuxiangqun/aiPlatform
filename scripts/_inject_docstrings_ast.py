#!/usr/bin/env python3
# docstring-guard: skip-file
"""AST-safe docstring injector: inserts/replaces as first body statement only."""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

WORKSPACE = Path(__file__).resolve().parent.parent

PARAM_HINTS = {
    "tenant_id": "租户 ID",
    "run_id": "运行 ID",
    "request": "FastAPI Request",
    "response": "FastAPI Response",
    "body": "请求体",
    "payload": "载荷 dict",
    "actor": "操作者身份",
    "limit": "返回条数上限",
    "offset": "分页偏移",
    "path": "路径",
    "seed_dir": "种子目录；None 用默认",
    "gold_dir": "黄金集目录",
    "profile": "评测 profile",
    "query": "查询",
    "force": "是否强制",
    "dry_run": "是否仅演练",
    "enabled": "是否启用",
    "timeout": "超时秒数",
    "model": "模型名",
    "agent_id": "Agent ID",
    "skill_id": "Skill ID",
    "workspace_id": "工作区 ID",
    "session_id": "会话 ID",
    "user_id": "用户 ID",
    "auth": "鉴权依赖",
    "_auth": "鉴权依赖注入（通常未使用）",
}


def _hint(name: str) -> str:
    if name in PARAM_HINTS:
        return PARAM_HINTS[name]
    if name.startswith("_"):
        return _hint(name[1:]) + "（内部）" if name[1:] in PARAM_HINTS else f"{name} 参数"
    if name.endswith("_id"):
        return f"{name[:-3]} 标识"
    return f"{name} 参数"


def _params(node: ast.AST) -> List[str]:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    out = []
    a = node.args
    for x in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
        if x.arg in ("self", "cls"):
            continue
        out.append(x.arg)
    if a.vararg:
        out.append(a.vararg.arg)
    if a.kwarg:
        out.append(a.kwarg.arg)
    return out


def _summary(name: str, existing: str = "") -> str:
    if existing:
        first = existing.strip().splitlines()[0].strip().strip('"""').strip("'''").strip()
        if first:
            return first if first.endswith(("。", ".", "!", "？", "?")) else first + "。"
    if name.startswith("get_"):
        return f"获取 {name[4:]}。"
    if name.startswith("list_"):
        return f"列出 {name[5:]}。"
    if name.startswith("create_"):
        return f"创建 {name[7:]}。"
    if name.startswith("delete_"):
        return f"删除 {name[7:]}。"
    if name.startswith("update_"):
        return f"更新 {name[7:]}。"
    if name == "__init__":
        return "初始化。"
    return f"{name}。"


def _doc_block(summary: str, params: Sequence[str], indent: str) -> str:
    lines = [f'{indent}"""{summary}']
    if params:
        lines.append("")
        lines.append(f"{indent}Args:")
        for p in params:
            lines.append(f"{indent}    {p}: {_hint(p)}。")
    lines.append(f'{indent}"""')
    return "\n".join(lines) + "\n"


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def patch(path: Path) -> int:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        print(f"SKIP {path}: {e}")
        return 0
    lines = src.splitlines(keepends=True)
    # operations applied bottom-up: (kind, start, end|None, text)
    ops: List[Tuple[str, int, Optional[int], str]] = []
    touched = 0

    if not ast.get_docstring(tree):
        ops.append(("insert", 0, None, f'"""{path.stem}：模块接口。"""\n\n'))
        touched += 1

    def handle_fn(node: ast.AST) -> None:
        nonlocal touched
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return
        if node.name.startswith("_") and node.name not in ("__init__", "__call__"):
            return
        params = _params(node)
        existing = ast.get_docstring(node) or ""
        need_doc = not bool(existing.strip())
        need_args = bool(params) and ("Args:" not in existing and "参数:" not in existing)
        if not need_doc and not need_args:
            return
        def_ind = _indent(lines[node.lineno - 1])
        body_ind = def_ind + "    "
        summary = _summary(node.name, existing)
        block = _doc_block(summary, params if (need_args or need_doc) else [], body_ind)

        # one-line stub
        if node.end_lineno == node.lineno and "..." in lines[node.lineno - 1]:
            raw = lines[node.lineno - 1]
            sig = raw.split("):", 1)[0] + "):" if "):" in raw else raw[: raw.rfind(":") + 1]
            ops.append(
                (
                    "replace",
                    node.lineno - 1,
                    node.lineno,
                    f"{sig}\n{_doc_block(summary, params, body_ind)}{def_ind}    ...\n",
                )
            )
            touched += 1
            return

        if existing and isinstance(node.body[0], ast.Expr):
            # replace docstring expr
            start = node.body[0].lineno - 1
            end = node.body[0].end_lineno or node.body[0].lineno
            ops.append(("replace", start, end, block))
            touched += 1
            return

        # insert before first body stmt
        insert_at = node.body[0].lineno - 1
        ops.append(("insert", insert_at, None, block))
        touched += 1

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            if not ast.get_docstring(node):
                ind = _indent(lines[node.lineno - 1]) + "    "
                ops.append(("insert", node.body[0].lineno - 1, None, f'{ind}"""{node.name}。"""\n'))
                touched += 1
            for item in node.body:
                handle_fn(item)
        else:
            handle_fn(node)

    # apply bottom-up
    for kind, start, end, text in sorted(ops, key=lambda x: -x[1]):
        if kind == "replace":
            lines[start:end] = [text]
        else:
            lines.insert(start, text)

    out = "".join(lines)
    try:
        ast.parse(out)
    except SyntaxError as e:
        print(f"SKIP after-patch {path}: {e}")
        return 0
    path.write_text(out, encoding="utf-8")
    return touched


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", action="append", default=[])
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--only-failing", action="store_true")
    args = ap.parse_args(argv)

    files: List[Path] = []
    for d in args.dir:
        files.extend(sorted((WORKSPACE / d).rglob("*.py")))
    for f in args.files:
        files.append(WORKSPACE / f)

    if args.only_failing:
        sys.path.insert(0, str(WORKSPACE))
        from scripts.check_python_docstring_guard import check_file, _is_skipped_path

        kept = []
        for p in files:
            if not p.is_file():
                continue
            rel = str(p.relative_to(WORKSPACE))
            if _is_skipped_path(rel):
                continue
            hard = [
                f
                for f in check_file(p, None)
                if f.rule in ("module_doc", "public_doc", "args_doc", "noise_comment", "why_comment")
            ]
            if hard:
                kept.append(p)
        files = kept

    total = 0
    for p in files:
        if not p.is_file():
            continue
        n = patch(p)
        if n:
            print(f"patched {p.relative_to(WORKSPACE)} ~{n}")
            total += n
    print(f"done total~={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
