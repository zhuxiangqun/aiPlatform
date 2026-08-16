#!/usr/bin/env python3
"""
Auto-register new public symbols to capability_registry.yaml.

Scans git diff for new Python/TypeScript files, extracts public symbols
(functions, classes, components, hooks), and appends them to the
correct domain section in core/capability_registry.yaml.

Usage:
  python3 scripts/auto_register_capability.py --check   # dry run, show what would be added
  python3 scripts/auto_register_capability.py --auto     # actually add + update counts
  python3 scripts/auto_register_capability.py --force    # forcibly re-register from git diff
"""
from __future__ import annotations

import os
import re
import ast
import sys
import yaml
import subprocess
from pathlib import Path
from datetime import date

WORKSPACE = Path(__file__).resolve().parent.parent
REGISTRY = WORKSPACE / "aiPlat-core" / "core" / "capability_registry.yaml"
DOMAIN_MAP_PATH = WORKSPACE / "scripts" / "registry_domain_map.yaml"


# ════════════════════════════════════════════════════════════
# Domain mapping
# ════════════════════════════════════════════════════════════

def load_domain_map() -> list[tuple[str, str]]:
    """Load path → domain mappings, sorted by specificity (longest first)."""
    if DOMAIN_MAP_PATH.exists():
        with open(DOMAIN_MAP_PATH) as f:
            data = yaml.safe_load(f)
        mapping = data.get("mapping", [])
        # Sort by pattern length descending (more specific paths first)
        mapping.sort(key=lambda x: len(x["pattern"]), reverse=True)
        return [(m["pattern"], m["domain"]) for m in mapping]
    return []


def map_file_to_domain(filepath: str) -> str:
    """Map a file path to a registry domain name."""
    # Normalize: strip workspace prefix
    for prefix in ["aiPlat-core/", "aiPlat-infra/", "aiPlat-platform/",
                    "aiPlat-management/"]:
        if filepath.startswith(prefix):
            filepath = filepath[len(prefix):]
            break

    mappings = load_domain_map()
    for pattern, domain in mappings:
        if pattern and pattern in filepath:
            return domain
    return "extension-plugins"


# ════════════════════════════════════════════════════════════
# Symbol extraction
# ════════════════════════════════════════════════════════════

class Symbol:
    def __init__(self, name: str, type_: str, signature: str, module: str):
        self.name = name
        self.type = type_
        self.signature = signature
        self.module = module


def extract_python_symbols(full_path: Path, rel_path: str) -> list[Symbol]:
    """Extract public top-level symbols from a Python file."""
    try:
        with open(full_path) as f:
            source = f.read()
    except Exception:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    symbols = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if name.startswith("_"):
                continue
            sig = _extract_signature_py(node)
            type_ = "function"
            symbols.append(Symbol(name, type_, sig, rel_path))

        elif isinstance(node, ast.ClassDef):
            name = node.name
            if name.startswith("_"):
                continue
            # Determine class type from bases/decorators
            type_ = "class"
            for base in node.bases:
                if isinstance(base, ast.Name):
                    if base.id in ("BaseModel",):
                        type_ = "pydantic_model"
                    elif base.id in ("Enum", "IntEnum", "StrEnum"):
                        type_ = "enum"

            has_dataclass = any(
                isinstance(d, ast.Name) and d.id == "dataclass"
                for d in node.decorator_list
            )
            if has_dataclass:
                type_ = "dataclass"

            sig = _extract_class_sig_py(node)
            symbols.append(Symbol(name, type_, sig, rel_path))

    return symbols


def _extract_signature_py(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Extract signature from function docstring or args."""
    # Try docstring first line
    if (isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)):
        doc = ast.literal_eval(node.body[0].value) if isinstance(node.body[0].value, ast.Constant) else node.body[0].value.s
        first_line = doc.strip().split("\n")[0].strip()
        if first_line:
            return first_line[:80]

    # Fallback: list arg names
    args = [a.arg for a in node.args.args if a.arg != "self"]
    return f"{node.name}({', '.join(args[:4])})"


def _extract_class_sig_py(node: ast.ClassDef) -> str:
    """Extract class signature from docstring."""
    if (isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)):
        doc = ast.literal_eval(node.body[0].value) if isinstance(node.body[0].value, ast.Constant) else node.body[0].value.s
        first_line = doc.strip().split("\n")[0].strip()
        if first_line:
            return first_line[:80]

    # Fallback: count public methods
    methods = [m.name for m in node.body
               if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
               and not m.name.startswith("_")]
    return ", ".join(methods[:4]) if methods else node.name


def extract_ts_symbols(full_path: Path, rel_path: str) -> list[Symbol]:
    """Extract exported symbols from a TypeScript/TSX file."""
    try:
        with open(full_path) as f:
            source = f.read()
    except Exception:
        return []

    symbols = []
    basename = full_path.stem

    # export default function ComponentName
    for m in re.finditer(r'export\s+default\s+function\s+(\w+)', source):
        name = m.group(1)
        if name.startswith("_"): continue
        sig = _find_ts_description(source, name)
        symbols.append(Symbol(name, "component", sig, rel_path))

    # export default function (anonymous) → use filename
    if re.search(r'export\s+default\s+function\s*\(', source):
        name = _pascal_case(basename)
        if not name.startswith("_"):
            sig = _find_ts_description(source, basename)
            symbols.append(Symbol(name, "component", sig, rel_path))

    # export function / export async function
    for m in re.finditer(r'export\s+(?:async\s+)?function\s+(\w+)', source):
        name = m.group(1)
        if name.startswith("_"): continue
        type_ = "hook" if name.startswith("use") else "function"
        sig = _find_ts_description(source, name)
        symbols.append(Symbol(name, type_, sig, rel_path))

    # export const Xyz: React.FC = / export const Xyz = () =>
    for m in re.finditer(r'export\s+const\s+(\w+)(?:\s*:\s*React\.FC)?\s*=\s*(?:\(|\()', source):
        name = m.group(1)
        if name.startswith("_"): continue
        type_ = "hook" if name.startswith("use") else "component"
        sig = _find_ts_description(source, name)
        symbols.append(Symbol(name, type_, sig, rel_path))

    return symbols


def _find_ts_description(source: str, name: str) -> str:
    """Try to find a comment description near the symbol."""
    # Look for JSDoc or inline comment
    patterns = [
        rf'\/\*\*?\s*\n?\s*\*?\s*(.+?)\s*\*\/\s*(?:export\s+)?.*?{name}',
        rf'\/\/\s*(.+?)\n\s*(?:export\s+)?.*?{name}',
    ]
    for pat in patterns:
        m = re.search(pat, source, re.DOTALL)
        if m:
            return m.group(1).strip()[:80]
    return name


def _pascal_case(s: str) -> str:
    """kebab-case or snake_case → PascalCase."""
    return "".join(w.capitalize() for w in re.split(r'[-_]', s))


# ════════════════════════════════════════════════════════════
# Registry I/O (text-based — preserves formatting, comments)
# ════════════════════════════════════════════════════════════

def read_registry_lines() -> list[str]:
    with open(REGISTRY) as f:
        return f.readlines()


def write_registry_lines(lines: list[str]) -> None:
    with open(REGISTRY, "w") as f:
        f.writelines(lines)


def is_already_registered(lines: list[str], symbol: str, module: str) -> bool:
    """Check if symbol+module combo appears anywhere."""
    text = "".join(lines)
    # Look for "symbol: {name}" followed by "module: {module}" nearby
    sym_re = re.compile(r'-\s+symbol:\s+' + re.escape(symbol) + r'\s*$', re.MULTILINE)
    mod_re = re.compile(r'module:\s+' + re.escape(module) + r'\s*$')
    for m in sym_re.finditer(text):
        # Check if module appears within next 5 lines
        nearby = text[m.end():m.end() + 300]
        if mod_re.search(nearby):
            return True
    return False


def find_domain_insertion_point(lines: list[str], domain_key: str) -> int | None:
    """Find line index to insert new provides entries in a domain.
    Returns index right after the last provides entry.
    """
    in_domain = False
    in_provides = False
    last_provide_line = -1

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == f"{domain_key}:":
            in_domain = True
        elif in_domain and stripped == "provides:":
            in_provides = True
        elif in_provides:
            if stripped.startswith("- symbol:"):
                last_provide_line = i
            elif not stripped.startswith("-") and ":" in stripped and not stripped.startswith("#"):
                # Exit provides section
                if last_provide_line >= 0:
                    return last_provide_line + 1
                # No provides entries yet — insert after "provides:" line
                return i - 1  # insert before next section
            elif stripped == "breaks:" or stripped == "consumers_expected:":
                return last_provide_line + 1 if last_provide_line >= 0 else i

    return None


def add_symbol_text(lines: list[str], sym: Symbol, domain_key: str) -> bool:
    """Insert symbol entry into registry lines. Returns True if added."""
    idx = find_domain_insertion_point(lines, domain_key)
    if idx is None:
        return False

    # Build entry
    module = sym.module
    indent = "      "
    entry_lines = [
        f"{indent}- symbol: {sym.name}\n",
        f"{indent}  type: {sym.type}\n",
        f"{indent}  signature: '{sym.signature[:80]}'\n",
        f"{indent}  module: {module}\n",
    ]

    # Insert after the last provides entry
    for i, line in enumerate(entry_lines):
        lines.insert(idx + i, line)
    return True


def update_registry_counts(lines: list[str], added: int) -> None:
    """Update caps_count and total_capabilities."""
    text = "".join(lines)

    # Update total_capabilities
    if added > 0:
        m = re.search(r'total_capabilities:\s*(\d+)', text)
        if m:
            new_total = int(m.group(1)) + added
            text = re.sub(r'total_capabilities:\s*\d+', f'total_capabilities: {new_total}', text)
        text = re.sub(
            r'generated_at:\s*\'\d{4}-\d{2}-\d{2}\'',
            f"generated_at: '{date.today().strftime('%Y-%m-%d')}'",
            text
        )

    lines[:] = text.splitlines(True)


# ════════════════════════════════════════════════════════════
# File discovery
# ════════════════════════════════════════════════════════════

def get_new_files() -> list[str]:
    """Get new files from git diff (staged + unstaged)."""
    files = set()

    # Staged new files
    try:
        out = subprocess.check_output(
            ["git", "-C", str(WORKSPACE), "diff", "--cached", "--name-only",
             "--diff-filter=A"],
            text=True, timeout=5
        )
        files.update(f.strip() for f in out.split("\n") if f.strip())
    except Exception:
        pass

    # Unstaged new files (git ls-files --others)
    try:
        out = subprocess.check_output(
            ["git", "-C", str(WORKSPACE), "ls-files", "--others",
             "--exclude-standard"],
            text=True, timeout=5
        )
        files.update(f.strip() for f in out.split("\n") if f.strip())
    except Exception:
        pass

    return sorted(f for f in files
                  if (f.endswith(".py") and "test" not in f.lower()
                      and "__init__" not in f)
                  or f.endswith((".tsx", ".ts")))


# ════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"

    if not REGISTRY.exists():
        print("❌ capability_registry.yaml not found")
        sys.exit(1)

    lines = read_registry_lines()
    new_files = get_new_files()
    added = 0
    skipped = 0

    for f in new_files:
        full = WORKSPACE / f
        if not full.exists():
            continue

        if f.endswith(".py"):
            symbols = extract_python_symbols(full, f)
        else:
            symbols = extract_ts_symbols(full, f)

        for sym in symbols:
            if is_already_registered(lines, sym.name, sym.module):
                skipped += 1
                continue

            domain = map_file_to_domain(f)
            if mode == "--check":
                print(f"  ➕ {sym.name:30s} | {sym.type:15s} | {domain:25s} | {f}")
            else:
                if add_symbol_text(lines, sym, domain):
                    print(f"  ✅ {sym.name:30s} | {sym.type:15s} | {domain:25s} | {f}")
                    added += 1

    if mode == "--check":
        print(f"\n  Found {len(new_files)} new files with symbols (--auto to register)")
        return

    if added > 0:
        update_registry_counts(lines, added)
        write_registry_lines(lines)
        print(f"\n✅ Added {added} symbols, skipped {skipped} existing")
    else:
        print(f"\n✅ No new symbols to register (skipped {skipped} existing)")


if __name__ == "__main__":
    main()
