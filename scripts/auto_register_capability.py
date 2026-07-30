#!/usr/bin/env python3
"""
auto_register_capability.py — Phase 43: auto-register new capabilities.

Modes:
  --check-only:  Scan git diff for unregistered symbols, generate draft templates.
                 Exit 0 if all registered, exit 1 if unregistered found (blocks commit).
  --auto:        Read draft templates, open $EDITOR, validate, append to registry.

Design:
  - Automatable: symbol name, type, module path (from AST)
  - Must be human: section_name, reason (from template TODO fields)
  - Gate: template with any "TODO" → block commit
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "aiPlat-core" / "core" / "capability_registry.yaml"
DRAFT_DIR = Path.home() / ".aiplat" / "registry_drafts"

# Patterns to skip
SKIP_PREFIXES = ("_", "__", "test_")
SKIP_DIRS = ("tests", "__pycache__", ".git", "node_modules", "download", "archive")
SKIP_SUFFIXES = (".pyc",)


def get_staged_files() -> List[str]:
    """Get staged (cached) files from git diff."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True, text=True, cwd=ROOT,
        )
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except Exception:
        return []


def get_staged_diff_lines(filepath: str) -> List[str]:
    """Get added lines from staged diff for a file."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "-U0", filepath],
            capture_output=True, text=True, cwd=ROOT,
        )
        lines = []
        for line in result.stdout.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                lines.append(line[1:])  # strip leading +
        return lines
    except Exception:
        return []


def extract_python_symbols(filepath: str) -> List[Tuple[str, str, int]]:
    """Extract public class/function definitions from a .py file.
    Returns list of (symbol_name, symbol_type, line_number).
    """
    full_path = filepath
    for pfx in ("", str(ROOT) + "/", str(ROOT) + "/aiPlat-core/",
                str(ROOT) + "/aiPlat-platform/", str(ROOT) + "/aiPlat-management/"):
        candidate = Path(pfx + filepath) if pfx.endswith("/") else Path(pfx) / filepath
        if candidate.exists():
            full_path = str(candidate)
            break
    if not os.path.exists(full_path):
        return []

    symbols = []
    try:
        with open(full_path) as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                return []
        for node in ast.walk(tree):
            # Class definitions
            if isinstance(node, ast.ClassDef):
                if not any(node.name.startswith(p) for p in SKIP_PREFIXES):
                    # Skip private classes and dunder-only classes
                    if not node.name.startswith("_") or (
                        node.name.startswith("__") and node.name.endswith("__")
                    ):
                        continue
                    symbols.append((node.name, "class", node.lineno))
            # Function definitions (top-level only)
            elif isinstance(node, ast.FunctionDef):
                if not any(node.name.startswith(p) for p in SKIP_PREFIXES):
                    if not node.name.startswith("_"):
                        symbols.append((node.name, "function", node.lineno))
            # Async function definitions
            elif isinstance(node, ast.AsyncFunctionDef):
                if not any(node.name.startswith(p) for p in SKIP_PREFIXES):
                    if not node.name.startswith("_"):
                        symbols.append((node.name, "async_function", node.lineno))
    except Exception:
        pass
    return symbols


def extract_tsx_symbols(filepath: str) -> List[Tuple[str, str, int]]:
    """Extract exported symbols from .tsx/.ts files."""
    full_path = filepath
    for pfx in ("", str(ROOT) + "/"):
        candidate = Path(pfx) / filepath if pfx else Path(filepath)
        if candidate.exists():
            full_path = str(candidate)
            break
    if not os.path.exists(full_path):
        return []

    symbols = []
    try:
        with open(full_path) as f:
            content = f.read()
        # export const Xxx
        for m in re.finditer(r'export\s+(?:const|function|class)\s+(\w+)', content):
            name = m.group(1)
            if not any(name.startswith(p) for p in SKIP_PREFIXES):
                stype = "react_component" if name[0].isupper() else "function"
                symbols.append((name, stype, 0))
        # export default function/class Xxx
        for m in re.finditer(r'export\s+default\s+(?:function|class)\s+(\w+)', content):
            name = m.group(1)
            if not any(name.startswith(p) for p in SKIP_PREFIXES):
                symbols.append((name, "react_component", 0))
    except Exception:
        pass
    return symbols


def load_registry() -> dict:
    """Load capability registry."""
    import yaml as _yaml
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH) as f:
            return _yaml.safe_load(f) or {"domains": {}}
    return {"domains": {}}


def is_registered(symbol: str, registry: dict) -> bool:
    """Check if a symbol is already in the registry."""
    for domain_id, domain in registry.get("domains", {}).items():
        for prov in domain.get("provides", []):
            reg_sym = prov.get("symbol", "")
            if symbol in reg_sym or reg_sym.endswith("." + symbol):
                return True
    return False


def infer_domain(filepath: str) -> Tuple[str, str]:
    """Infer which domain a file belongs to by grepping CAPABILITIES.md."""
    caps_path = ROOT / "AIPLAT_CAPABILITIES.md"
    if not caps_path.exists():
        return "unclassified", "三十三(待分类)"

    # Extract the module hint from the filepath
    hints = filepath.split("/")
    hints = [h for h in hints if h not in ("core", "aiPlat-core", "aiPlat-platform", "aiPlat-management")]
    best_count = 0
    best_domain = "unclassified"
    best_section = "三十三(待分类)"

    try:
        with open(caps_path) as f:
            content = f.read()
        import re as _re
        for hint in hints[:3]:
            # Find sections that mention this path component
            pattern = _re.escape(hint)
            matches = _re.findall(pattern, content, _re.IGNORECASE)
            if len(matches) > best_count:
                best_count = len(matches)
                # Find which section this belongs to
                section_match = _re.search(
                    r'^## (.*' + _re.escape(hint) + r'.*)$',
                    content, _re.MULTILINE | _re.IGNORECASE,
                )
                if section_match:
                    best_domain = hint.replace(".py", "").replace("_", "-")
                    best_section = section_match.group(1)
    except Exception:
        pass

    return best_domain, best_section


def generate_draft(
    symbols: List[Tuple[str, str, int]],
    filepath: str,
) -> str:
    """Generate YAML draft template for unregistered symbols."""
    domain_id, section_name = infer_domain(filepath)
    lines = [f"# Auto-generated draft from: {filepath}"]
    lines.append(f"# Fill in the 2 TODO fields:")
    lines.append(f"#   1. section_name (what is this capability?)")
    lines.append(f"#   2. reason (why does each consumer need this?)")
    lines.append("")
    lines.append(f"domain_id: {domain_id}")
    lines.append(f"section_name: \"{section_name}\"  # TODO: describe this capability")
    lines.append(f"caps_count: {len(symbols)}")
    lines.append("provides:")
    for name, stype, lineno in symbols:
        lines.append(f"  - symbol: \"{name}\"")
        lines.append(f"    type: \"{stype}\"")
        lines.append(f"    signature: \"TODO: describe signature\"")
        lines.append(f"    module: \"{filepath}\"")
    lines.append("breaks: []")
    lines.append("consumers_expected:")
    lines.append("  - module: \"TODO\"  # TODO: which module uses this?")
    lines.append("    reason: \"TODO: why does this module use {symbols[0][0] if symbols else ''}?\"")
    return "\n".join(lines)


def has_todos(yaml_content: str) -> bool:
    """Check if YAML content still has TODO placeholders."""
    return "TODO" in yaml_content or "todo" in yaml_content


def append_to_registry(yaml_content: str) -> None:
    """Parse draft YAML and append to capability_registry.yaml."""
    import yaml as _yaml
    draft = _yaml.safe_load(yaml_content)
    domain_id = draft.get("domain_id", "unclassified")

    # Load current registry
    registry = load_registry()

    # Check if domain already exists
    if domain_id in registry["domains"]:
        # Append provides
        existing = registry["domains"][domain_id].get("provides", [])
        existing_symbols = {p["symbol"] for p in existing}
        for prov in draft.get("provides", []):
            if prov["symbol"] not in existing_symbols:
                existing.append(prov)
        registry["domains"][domain_id]["caps_count"] = len(existing)
        # Append consumers_expected
        existing_cons = registry["domains"][domain_id].get("consumers_expected", [])
        existing_cons.extend(draft.get("consumers_expected", []))
    else:
        registry["domains"][domain_id] = {
            "section": "三十三",
            "section_name": draft.get("section_name", "待分类"),
            "caps_count": draft.get("caps_count", len(draft.get("provides", []))),
            "provides": draft.get("provides", []),
            "breaks": draft.get("breaks", []),
            "consumers_expected": draft.get("consumers_expected", []),
        }

    # Update header
    registry["total_capability_domains"] = len(registry["domains"])
    registry["total_capabilities"] = sum(
        v.get("caps_count", 0) for v in registry["domains"].values()
    )

    # Write back
    with open(REGISTRY_PATH, "w") as f:
        _yaml.dump(registry, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"✅ Registry updated: {REGISTRY_PATH}")
    print(f"   {registry['total_capability_domains']} domains, {registry['total_capabilities']} capabilities")


def check_only() -> bool:
    """Return True if clean (all registered), False if violations found."""
    staged = get_staged_files()
    py_files = [f for f in staged if f.endswith(".py") and not any(
        d in f for d in SKIP_DIRS) and not any(f.endswith(s) for s in SKIP_SUFFIXES)]
    tsx_files = [f for f in staged if (f.endswith(".tsx") or f.endswith(".ts")) and not any(
        d in f for d in SKIP_DIRS)]

    registry = load_registry()
    unregistered = []

    for f in py_files:
        if not f.startswith("aiPlat-core") and not f.startswith("aiPlat-platform"):
            continue
        symbols = extract_python_symbols(f)
        for name, stype, lineno in symbols:
            if not is_registered(name, registry):
                unregistered.append((f, name, stype, lineno))

    for f in tsx_files:
        symbols = extract_tsx_symbols(f)
        for name, stype, lineno in symbols:
            if not is_registered(name, registry):
                unregistered.append((f, name, stype, lineno))

    if not unregistered:
        print("✅ All new symbols are registered.")
        return True

    # Group by file for clean output
    by_file: Dict[str, list] = {}
    for f, name, stype, lineno in unregistered:
        by_file.setdefault(f, []).append((name, stype, lineno))

    print(f"\n❌ {len(unregistered)} unregistered capabilities detected:\n")
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)

    for f, symbols in by_file.items():
        print(f"  {f}:")
        draft_path = DRAFT_DIR / f"{Path(f).stem.replace('.', '_')}_draft.yaml"
        draft_content = generate_draft(symbols, f)
        with open(draft_path, "w") as df:
            df.write(draft_content)
        for name, stype, lineno in symbols:
            print(f"    {lineno}: {stype} {name}")
        print(f"    → Draft: {draft_path}")
        print()

    print("Run: cap auto-register")
    print("Or fill drafts manually and run: cap register <draft.yaml>")
    return False


def auto_mode() -> None:
    """Read drafts, open editor, validate, append to registry."""
    if not DRAFT_DIR.exists() or not list(DRAFT_DIR.glob("*.yaml")):
        print("No draft files found in", DRAFT_DIR)
        print("Run 'cap check' first to generate drafts.")
        sys.exit(1)

    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "vim"))
    count = 0

    for draft_path in sorted(DRAFT_DIR.glob("*_draft.yaml")):
        if not draft_path.name.endswith("_draft.yaml"):
            continue

        # Open editor
        subprocess.run([editor, str(draft_path)])

        # Validate: no TODOs
        with open(draft_path) as f:
            content = f.read()
        if has_todos(content):
            print(f"\n⚠️  {draft_path.name} still contains TODO placeholders.")
            print("   Please complete all TODO fields and run again.")
            print("   Skipping this draft for now.")
            continue

        # Append to registry (skip comment lines)
        clean_content = "\n".join(
            line for line in content.split("\n")
            if not line.strip().startswith("#")
        )
        append_to_registry(clean_content)
        count += 1
        print(f"  ✅ Registered from {draft_path.name}")

    if count > 0:
        # Stage the registry update
        subprocess.run(["git", "add", str(REGISTRY_PATH)], cwd=ROOT)
        print(f"\n✅ {count} capability drafts registered.")
        print("   capability_registry.yaml updated and staged.")
    else:
        print("   Fix TODOs in drafts and run 'cap auto-register' again.")
        sys.exit(1)


def main():
    if "--check-only" in sys.argv:
        ok = check_only()
        sys.exit(0 if ok else 1)
    elif "--auto" in sys.argv:
        auto_mode()
    else:
        print("Usage: auto_register_capability.py --check-only | --auto")
        sys.exit(1)


if __name__ == "__main__":
    main()
