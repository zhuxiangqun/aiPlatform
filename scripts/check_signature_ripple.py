#!/usr/bin/env python3
"""CoreFacade 签名涟漪检测 — 函数签名变更 → 发现未同步的调用者。

工作原理：
  1. 解析 CoreFacade 提取所有 def 签名 → {函数名: 参数结构}
  2. 与基线比对，识别"破坏性变更"（新增必填参数 / 删除参数 / 改名）
  3. 扫描 platform/app 层所有 .py 文件，找到变更函数的调用点
  4. AST 匹配调用点参数是否与新签名兼容
  5. 输出不兼容的调用点列表

破坏性变更（3 类）：
  - 新增必填参数（无默认值）→ 旧调用点缺参数
  - 删除参数               → 旧调用点多传了参数
  - 参数改名（keyword-only）→ 旧调用点 key 对不上

安全变更（不告警）：
  - 新增带默认值的参数
  - 新增 *args / **kwargs
  - _ 前缀函数签名变更（非公共 API）

用法：
  python3 scripts/check_signature_ripple.py --update   # 保存基线
  python3 scripts/check_signature_ripple.py --check    # 比较检测
  python3 scripts/check_signature_ripple.py --json     # CI JSON 输出
"""

import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

WORKSPACE = Path(__file__).resolve().parent.parent
FACADE_PATH = WORKSPACE / "aiPlat-core" / "core" / "api" / "core_facade.py"
BASELINE_PATH = WORKSPACE / "scripts" / "baselines" / "core_facade_signatures.json"
PLATFORM_DIR = WORKSPACE / "aiPlat-platform"
APP_DIR = WORKSPACE / "aiPlat-app"


@dataclass
class Param:
    name: str
    has_default: bool = False
    is_kw_only: bool = False


@dataclass
class Signature:
    name: str
    params: List[Param] = field(default_factory=list)
    lineno: int = 0

    @property
    def required_params(self) -> List[str]:
        return [p.name for p in self.params
                if not p.has_default and p.name not in ("self", "cls")]

    @property
    def kw_only_params(self) -> List[str]:
        return [p.name for p in self.params if p.is_kw_only]


@dataclass
class Breakage:
    func_name: str
    change_type: str  # added_required | removed_param | renamed_param | removed_function
    detail: str


def extract_signatures(filepath: Path) -> Dict[str, Signature]:
    """解析 Python 文件，提取所有非 _ 前缀的 def 函数签名。"""
    tree = ast.parse(filepath.read_text(encoding="utf-8"))
    sigs: Dict[str, Signature] = {}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue

        sig = Signature(name=node.name, lineno=node.lineno)
        args = node.args

        for i, arg in enumerate(args.args):
            if arg.arg in ("self", "cls"):
                continue
            has_default = (len(args.defaults) > 0 and
                           i >= len(args.args) - len(args.defaults))
            sig.params.append(Param(name=arg.arg, has_default=has_default))

        if args.kwonlyargs:
            for i, arg in enumerate(args.kwonlyargs):
                default = args.kw_defaults[i] if i < len(args.kw_defaults) else None
                has_default = default is not None
                sig.params.append(Param(name=arg.arg, has_default=has_default,
                                       is_kw_only=True))

        sigs[node.name] = sig

    return sigs


def compare_signatures(old: Dict[str, Signature],
                       new: Dict[str, Signature]) -> List[Breakage]:
    """比对旧签名和新签名，找出破坏性变更。"""
    breakages: List[Breakage] = []
    all_names = set(old.keys()) | set(new.keys())

    for name in sorted(all_names):
        old_sig = old.get(name)
        new_sig = new.get(name)

        if old_sig is None:
            continue
        if new_sig is None:
            breakages.append(Breakage(name, "removed_function",
                                      f"function '{name}' removed"))
            continue

        old_req = set(old_sig.required_params)
        new_req = set(new_sig.required_params)
        old_all = {p.name for p in old_sig.params}
        new_all = {p.name for p in new_sig.params}
        new_kw = set(new_sig.kw_only_params)

        added = new_req - old_req
        removed = old_all - new_all
        old_kw = set(old_sig.kw_only_params)
        promoted = {p for p in new_kw if p in old_req and p not in old_kw}

        for p in sorted(added):
            breakages.append(Breakage(name, "added_required",
                                      f"new required param '{p}'"))
        for p in sorted(removed):
            breakages.append(Breakage(name, "removed_param",
                                      f"param '{p}' removed"))
        for p in sorted(promoted):
            breakages.append(Breakage(name, "renamed_param",
                                      f"param '{p}' became keyword-only"))

    return breakages


def scan_callers(target_dir: Path, func_names: Set[str]) -> List[Dict[str, Any]]:
    """扫描目录中所有对指定函数的调用点。

    Only scans platform/app layers — core internal callers are NOT checked.
    """
    callers: List[Dict] = []
    if not target_dir.exists():
        return callers

    for py_file in target_dir.rglob("*.py"):
        if "__pycache__" in str(py_file) or "test_" in py_file.name:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            if isinstance(node.func, ast.Name) and node.func.id in func_names:
                callers.append({
                    "file": str(py_file.relative_to(WORKSPACE)),
                    "line": node.lineno,
                    "func": node.func.id,
                    "args_count": len(node.args),
                    "keywords": [kw.arg for kw in node.keywords if kw.arg is not None],
                })
            elif isinstance(node.func, ast.Attribute) and node.func.attr in func_names:
                callers.append({
                    "file": str(py_file.relative_to(WORKSPACE)),
                    "line": node.lineno,
                    "func": node.func.attr,
                    "args_count": len(node.args),
                    "keywords": [kw.arg for kw in node.keywords if kw.arg is not None],
                })

    return callers


def check_call_sites(breakages: List[Breakage], callers: List[Dict],
                     new_sigs: Dict[str, Signature]) -> List[Dict]:
    """检查调用点是否兼容新签名，返回不兼容的调用点列表。"""
    violations: List[Dict] = []
    affected_funcs = {b.func_name for b in breakages}

    for c in callers:
        if c["func"] not in affected_funcs:
            continue
        new_sig = new_sigs.get(c["func"])
        if not new_sig:
            continue

        for req in new_sig.required_params:
            if req not in c["keywords"]:
                violations.append({
                    "file": c["file"],
                    "line": c["line"],
                    "func": c["func"],
                    "issue": f"missing required param '{req}'",
                })

        removed_params = {
            b.detail.split("'")[1] for b in breakages
            if b.func_name == c["func"] and b.change_type == "removed_param"
        }
        for kw in c["keywords"]:
            if kw in removed_params:
                violations.append({
                    "file": c["file"],
                    "line": c["line"],
                    "func": c["func"],
                    "issue": f"passing removed param '{kw}'",
                })

    return violations


def load_baseline() -> Optional[Dict]:
    if BASELINE_PATH.exists():
        with open(BASELINE_PATH) as f:
            return json.load(f)
    return None


def save_baseline(data: Dict):
    import datetime
    data["created_at"] = datetime.datetime.now().isoformat()
    data["source"] = str(FACADE_PATH.relative_to(WORKSPACE))
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BASELINE_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CoreFacade signature ripple detector")
    parser.add_argument("--check", action="store_true", help="Compare current vs baseline")
    parser.add_argument("--update", action="store_true", help="Save current signatures as baseline")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.update:
        sigs = extract_signatures(FACADE_PATH)
        save_baseline({
            "functions": {
                name: {
                    "params": [{"name": p.name, "has_default": p.has_default,
                               "is_kw_only": p.is_kw_only} for p in sig.params],
                    "lineno": sig.lineno
                } for name, sig in sigs.items()
            }
        })
        print(f"Baseline saved: {len(sigs)} signatures")
        return

    if args.check:
        baseline_data = load_baseline()
        if not baseline_data:
            print("No baseline found. Run --update first.")
            sys.exit(0)

        current_sigs = extract_signatures(FACADE_PATH)
        old_sigs: Dict[str, Signature] = {}
        for name, data in baseline_data.get("functions", {}).items():
            sig = Signature(name=name, lineno=data.get("lineno", 0))
            for p in data.get("params", []):
                sig.params.append(Param(
                    name=p["name"],
                    has_default=p.get("has_default", False),
                    is_kw_only=p.get("is_kw_only", False),
                ))
            old_sigs[name] = sig

        breakages = compare_signatures(old_sigs, current_sigs)
        if not breakages:
            if args.json:
                print(json.dumps({"violations": 0, "breakages": []}))
            else:
                print("No signature breakages detected")
            sys.exit(0)

        func_names = {b.func_name for b in breakages}
        callers = scan_callers(PLATFORM_DIR, func_names)
        callers += scan_callers(APP_DIR, func_names)

        violations = check_call_sites(breakages, callers, current_sigs)

        if args.json:
            print(json.dumps({
                "violations": len(violations),
                "breakages": [{"func": b.func_name, "type": b.change_type,
                               "detail": b.detail} for b in breakages],
                "unmatched_callers": violations,
            }))
        else:
            print(f"\u00a795: Signature ripple — {len(breakages)} breakage(s), "
                  f"{len(violations)} violation(s)")
            for v in violations:
                print(f"  {v['file']}:{v['line']}: {v['func']}() — {v['issue']}")

        sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
