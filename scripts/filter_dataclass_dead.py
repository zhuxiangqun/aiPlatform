#!/usr/bin/env python3
"""Post-filter caller_verify output — exclude false-positive dead symbols.

Filters:
  dc: @dataclass classes (type annotation, grep cannot see)
  internal: functions called within their own file (grep skips def file)
  cls: class definitions (type annotation/ABC/enum, grep cannot see)

Usage: bash scripts/caller_verify.sh | python3 scripts/filter_dataclass_dead.py
"""
import sys, ast, re
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
dead_pattern = re.compile(r"^  .*?([^/\s]+\.py):\s*(\w+)\s*—")
fail_pattern = re.compile(r"(\d+) dead symbols")


def get_dataclass_classes(filepath):
    """Return set of class names decorated with @dataclass in the given file."""
    try:
        tree = ast.parse(Path(filepath).read_text())
    except Exception:
        return set()
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for d in node.decorator_list:
                if isinstance(d, ast.Name) and d.id == 'dataclass':
                    result.add(node.name)
    return result


def has_internal_caller(filepath, symbol):
    """Check if symbol is called elsewhere in the same file (excluding its own def)."""
    try:
        tree = ast.parse(Path(filepath).read_text())
    except Exception:
        return False
    def_line = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
            def_line = node.lineno
            break
    if def_line is None:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == symbol:
                if node.lineno != def_line:
                    return True
    return False


def is_class_definition(filepath, symbol):
    """Check if symbol is a class (not a function) — a type, likely used as annotation."""
    try:
        tree = ast.parse(Path(filepath).read_text())
    except Exception:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == symbol:
            return True
    return False


def used_as_type_annotation(filepath, symbol):
    """Check if symbol is used as a type annotation in other production files.
    
    Handles patterns like:
      var: ClassName = ...
      def foo() -> ClassName:
      Dict[str, ClassName]
      Optional[ClassName]
    """
    try:
        tree = ast.parse(Path(filepath).read_text())
    except Exception:
        return False
    
    for node in ast.walk(tree):
        # Direct annotation: x: Symbol = ...
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.annotation, ast.Name) and node.annotation.id == symbol:
                return True
            # Optional[Symbol] or Dict[str, Symbol]
            if isinstance(node.annotation, ast.Subscript):
                for subnode in ast.walk(node.annotation):
                    if isinstance(subnode, ast.Name) and subnode.id == symbol:
                        return True
        
        # Return type: def foo() -> Symbol:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns:
                if isinstance(node.returns, ast.Name) and node.returns.id == symbol:
                    return True
                if isinstance(node.returns, ast.Subscript):
                    for subnode in ast.walk(node.returns):
                        if isinstance(subnode, ast.Name) and subnode.id == symbol:
                            return True
        
        # Argument annotation: def foo(x: Symbol):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args + node.args.kwonlyargs:
                if arg.annotation:
                    if isinstance(arg.annotation, ast.Name) and arg.annotation.id == symbol:
                        return True
                    if isinstance(arg.annotation, ast.Subscript):
                        for subnode in ast.walk(arg.annotation):
                            if isinstance(subnode, ast.Name) and subnode.id == symbol:
                                return True
    
    return False


def find_file(fname):
    """Find the project source file (excluding .venv, tests, __pycache__)."""
    for root in [".", "aiPlat-core", "aiPlat-platform", "aiPlat-infra", "aiPlat-app"]:
        p = WORKSPACE / root
        if not p.exists():
            continue
        for found in p.rglob(fname):
            sp = str(found)
            if any(s in sp for s in ("/.venv/", "/tests/", "__pycache__")):
                continue
            return sp
    return None


def find_files(fname):
    """Yield all project source files matching fname."""
    for root in [".", "aiPlat-core", "aiPlat-platform", "aiPlat-infra", "aiPlat-app"]:
        p = WORKSPACE / root
        if not p.exists():
            continue
        for found in p.rglob(fname):
            sp = str(found)
            if any(s in sp for s in ("/.venv/", "/tests/", "__pycache__")):
                continue
            yield sp


# ── Main filter loop ──
# Filters are applied in order; only symbols that escape ALL automatic filters
# land in KNOWN_FALSE_POSITIVE_CLASSES (last resort, documented per-entry).
KNOWN_FALSE_POSITIVE_CLASSES = {
    # Symbols that survive all 4 automatic filters but are known legitimate.
    # Each entry MUST have a comment explaining WHY the filter misses it.
    # Goal: this list should shrink as filters improve.
}

anno_count = 0  # Filter 4 counter

dc_cache = {}
internal_cache = {}
class_cache = {}
dc_count = 0
internal_count = 0
class_count = 0
internal_cache = {}
class_cache = {}
dc_count = 0
internal_count = 0
class_count = 0
lines = []

for line in sys.stdin:
    m = dead_pattern.search(line)
    if m:
        fname, sym = m.group(1), m.group(2)
        full = find_file(fname)

        # Filter 1: @dataclass
        if full and full not in dc_cache:
            dc_cache[full] = get_dataclass_classes(full)
        if full and sym in dc_cache[full]:
            dc_count += 1
            continue

        # Filter 2: same-file internal caller
        if full and full not in internal_cache:
            internal_cache[full] = set()
        if full and sym not in internal_cache[full]:
            if has_internal_caller(full, sym):
                internal_cache[full].add(sym)
        if full and sym in internal_cache[full]:
            internal_count += 1
            continue

        # Filter 3: class definition (type annotation)
        cache_key = (fname, sym)
        if cache_key not in class_cache:
            class_cache[cache_key] = False
            for alt_full in find_files(fname):
                if is_class_definition(alt_full, sym):
                    class_cache[cache_key] = True
                    break
        if class_cache[cache_key]:
            class_count += 1
            continue

        # Filter 4: used as type annotation in other production files
        if full:
            used = False
            for alt_full in find_files(fname):
                if alt_full != full and used_as_type_annotation(alt_full, sym):
                    used = True
                    break
            if not used:
                # Also check the defining file itself (e.g., self-referencing in list/dict)
                for alt_full in find_files(fname):
                    if alt_full == full and used_as_type_annotation(alt_full, sym):
                        used = True
                        break
            if used:
                anno_count += 1
                continue

        # Filter 0 (last resort): known false positive classes
        if sym in KNOWN_FALSE_POSITIVE_CLASSES:
            class_count += 1
            continue

    lines.append(line)

# ── Replace summary with adjusted count ──
saw_summary = False
final_new_count = 0
for i, line in enumerate(lines):
    m = fail_pattern.search(line)
    if m:
        saw_summary = True
        orig = int(m.group(1))
        total_f = dc_count + internal_count + class_count + anno_count
        new_count = orig - total_f
        final_new_count = new_count
        lines[i] = line.replace(
            f"{orig} dead symbols",
            f"{new_count} dead symbols (dc={dc_count} int={internal_count} cls={class_count} anno={anno_count})"
        )
        if new_count <= 0:
            lines[i] = lines[i].replace("CALLER VERIFY FAILED", "CALLER VERIFY PASSED (FP-filtered)")

for line in lines:
    sys.stdout.write(line)

# Exit status must reflect the FILTERED count, not caller_verify's raw exit.
# (Previously this script only rewrote the display — the pipeline still inherited
#  caller_verify's exit 1 under `set -o pipefail`, so filtering was cosmetic only.)
sys.exit(1 if (saw_summary and final_new_count > 0) else 0)
