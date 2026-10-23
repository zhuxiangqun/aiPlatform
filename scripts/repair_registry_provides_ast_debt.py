#!/usr/bin/env python3
"""
One-shot / repeatable repair for registry provides AST soft debt.

Strategies (source = repo .py AST top-level names):
  1. empty/wrong module + symbol uniquely defined in one .py → set module
  2. non_identifier prose → split into real identifier symbols (same module) or type=doc
  3. symbol_missing with zero AST hits anywhere → drop provides entry (stale)
  4. ambiguous (multi-file) → leave for manual (reported)

Also counts ImportFrom/Import aliases as top-level exports (facade re-exports).

Usage:
  python3 scripts/repair_registry_provides_ast_debt.py --dry-run
  python3 scripts/repair_registry_provides_ast_debt.py --apply
  # then: python3 scripts/verify_registry_provides_ast.py --write-baseline
"""

from __future__ import annotations

import ast
import collections
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
REG_FILE = ROOT / "aiPlat-core" / "core" / "capability_registry.yaml"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from verify_registry_provides_ast import (  # noqa: E402
    IDENT_RE,
    SKIP_TYPES,
    _symbol_leaf,
    find_module,
)

IDENT = IDENT_RE


def top_level_names(path: Path, *, defined_only: bool = False) -> Set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, OSError):
        return set()
    names: Set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif not defined_only and isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
        elif not defined_only and isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == "*":
                    continue
                names.add(a.asname or a.name)
    return names


SKIP_PATH_PARTS = (
    ".venv",
    "node_modules",
    "__pycache__",
    "/tests/",
    "/test_",
    "tmp/",
    "dist/",
    "bench-clones",
    ".git/",
    "site-packages",
)

# Re-export hubs — never prefer these when a defining module also exists
FACADE_REEXPORTS = frozenset(
    {
        "aiPlat-core/core/api/core_facade.py",
        "aiPlat-core/core/orchestration/__init__.py",
    }
)

# domain_id → preferred path substrings (first match wins among candidates)
DOMAIN_PATH_HINTS: Dict[str, Tuple[str, ...]] = {
    "harness-execution-engine": ("core/harness/execution/", "core/harness/"),
    "skill-system": ("core/harness/skills/", "core/engine/skills/", "core/apps/skills/"),
    "agent-system": ("core/apps/agents/", "core/harness/"),
    "knowledge-engine-ontology": ("core/harness/knowledge/", "core/harness/ontology"),
    "memory-subsystem": ("core/harness/memory/",),
    "memory-runtime-filtering": ("core/harness/memory/",),
    "tool-ecosystem": ("core/apps/tools/", "core/harness/tools/"),
    "observability": ("core/api/routers/observation.py", "core/api/routers/", "core/harness/observation/"),
    "management-and-quality": ("aiPlat-platform/", "core/harness/"),
    "platform-governance": ("aiPlat-platform/",),
    "gate-system": ("core/harness/", "aiPlat-platform/"),
    "document-intelligence": ("core/harness/document/",),
    "evaluation-system": ("core/harness/evaluation/",),
    "extension-and-learning": ("core/harness/learning/", "aiPlat-app/"),
    "a2a-protocol": ("core/apps/agents/",),
    "core-api-unified-entry": ("core/api/", "core/server.py"),
    "runtime-intervention": ("core/harness/meta/", "core/harness/utils/"),
    "hermes-compression": ("core/harness/",),
}

# Hard overrides when multi-definition remains after hints
MODULE_OVERRIDES: Dict[Tuple[str, str], str] = {
    ("observability", "get_run_graph"): "aiPlat-core/core/api/routers/observation.py",
}


def build_symbol_index() -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Return (all_exports_index, defined_only_index)."""
    all_idx: Dict[str, List[str]] = collections.defaultdict(list)
    def_idx: Dict[str, List[str]] = collections.defaultdict(list)
    for p in ROOT.rglob("*.py"):
        rel = str(p.relative_to(ROOT))
        if any(x in rel for x in SKIP_PATH_PARTS):
            continue
        for n in top_level_names(p, defined_only=False):
            all_idx[n].append(rel)
        for n in top_level_names(p, defined_only=True):
            def_idx[n].append(rel)
    return all_idx, def_idx


def repo_module(rel: str) -> str:
    """Prefer aiPlat-core/… paths when under core/."""
    if rel.startswith("aiPlat-"):
        return rel
    return rel


def pick_module(
    domain_id: str,
    hits: List[str],
    claimed: str = "",
    defined_hits: Optional[List[str]] = None,
) -> Optional[str]:
    """Choose defining module among index hits; None if still ambiguous."""
    # Prefer sites that actually define the symbol (not ImportFrom re-export)
    if defined_hits:
        picked = pick_module(domain_id, defined_hits, claimed=claimed, defined_hits=None)
        if picked:
            return picked
    if not hits:
        return None
    hits = [h for h in hits if not any(x in h for x in SKIP_PATH_PARTS)]
    if not hits:
        return None
    if claimed:
        for h in hits:
            c = claimed.lstrip("./")
            if h == c or h.endswith("/" + c) or h.endswith(c) or c.endswith(h):
                return h
    non_facade = [h for h in hits if h not in FACADE_REEXPORTS]
    pool = non_facade if non_facade else hits
    if len(pool) == 1:
        return pool[0]
    hints = DOMAIN_PATH_HINTS.get(domain_id) or ()
    for hint in hints:
        matched = [h for h in pool if hint in h]
        if len(matched) == 1:
            return matched[0]
        if matched:
            pool = matched
    core = [h for h in pool if h.startswith("aiPlat-core/")]
    if len(core) == 1:
        return core[0]
    if len(pool) == 1:
        return pool[0]
    return None


def extract_idents(text: str) -> List[str]:
    parts = re.split(r"[\s/,|]+", text or "")
    out: List[str] = []
    for p in parts:
        p = p.strip().strip("\"'")
        if IDENT.match(p):
            out.append(p)
    return out


def load_yaml() -> Dict[str, Any]:
    import yaml

    return yaml.safe_load(REG_FILE.read_text(encoding="utf-8"))


def _format_provide(prov: Dict[str, Any]) -> List[str]:
    """Render one provides list item (2-space domain / 4-space provides / 6-space fields)."""
    lines = [f'      - symbol: "{prov.get("symbol")}"']
    for key in ("module", "type", "signature", "notes"):
        if key not in prov or prov[key] is None or prov[key] == "":
            continue
        val = prov[key]
        if key == "module":
            lines.append(f"        module: {val}")
        elif key == "type":
            lines.append(f"        type: {val}")
        elif key == "signature":
            s = str(val).replace('"', '\\"')
            lines.append(f'        signature: "{s}"')
        elif key == "notes":
            s = str(val).replace('"', '\\"')
            lines.append(f'        notes: "{s}"')
    return lines


def apply_provides_preserving_comments(
    data: Dict[str, Any], only_domains: Optional[Set[str]] = None
) -> None:
    """Replace selected domains' provides list + caps_count; keep section comments."""
    text = REG_FILE.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    domains = data.get("domains") or {}
    total = sum(len(b.get("provides") or []) for b in domains.values())
    touch = only_domains if only_domains is not None else set(domains.keys())
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("total_capabilities:"):
            out.append(f"total_capabilities: {total}\n")
            i += 1
            continue
        m = re.match(r"^  ([a-z0-9][a-z0-9_-]*):\s*$", line)
        if m and m.group(1) in touch:
            domain_id = m.group(1)
            body = domains[domain_id]
            out.append(line)
            i += 1
            while i < len(lines):
                cur = lines[i]
                if re.match(r"^  #", cur) or (
                    re.match(r"^  [a-z0-9]", cur) and not cur.startswith("    ")
                ):
                    break
                if re.match(r"^    caps_count:\s*", cur):
                    out.append(f"    caps_count: {len(body.get('provides') or [])}\n")
                    i += 1
                    continue
                if re.match(r"^    provides:\s*$", cur):
                    out.append(cur)
                    i += 1
                    while i < len(lines):
                        nxt = lines[i]
                        if nxt.startswith("      "):
                            i += 1
                            continue
                        if nxt.strip() == "" and i + 1 < len(lines) and lines[i + 1].startswith(
                            "      "
                        ):
                            i += 1
                            continue
                        break
                    for prov in body.get("provides") or []:
                        if isinstance(prov, dict):
                            for pl in _format_provide(prov):
                                out.append(pl + "\n")
                    continue
                out.append(cur)
                i += 1
            continue
        out.append(line)
        i += 1

    REG_FILE.write_text("".join(out), encoding="utf-8")


def sync_caps_counts(data: Dict[str, Any]) -> None:
    domains = data.get("domains") or {}
    total = 0
    for _did, body in domains.items():
        n = len(body.get("provides") or [])
        body["caps_count"] = n
        total += n
    if "total_capabilities" in data:
        data["total_capabilities"] = total
    if "domains_count" in data:
        data["domains_count"] = len(domains)


def repair(dry_run: bool = True) -> Dict[str, Any]:
    index, def_index = build_symbol_index()
    data = load_yaml()
    stats = collections.Counter()
    notes: List[str] = []

    changed_domains: Set[str] = set()
    for domain_id, body in (data.get("domains") or {}).items():
        provides = body.get("provides") or []
        new_provides: List[Dict[str, Any]] = []
        domain_dirty = False
        for prov in provides:
            if not isinstance(prov, dict):
                new_provides.append(prov)
                continue
            ptype = str(prov.get("type") or "")
            if ptype in SKIP_TYPES:
                new_provides.append(prov)
                stats["skipped_type"] += 1
                continue

            symbol = str(prov.get("symbol") or "")
            module = str(prov.get("module") or "").strip()
            leaf = _symbol_leaf(symbol)

            # Prose / non-identifier
            if not IDENT.match(leaf):
                idents = extract_idents(symbol)
                real = []
                for ident in idents:
                    hits = index.get(ident) or []
                    dh = def_index.get(ident) or []
                    if module:
                        fpath = find_module(module)
                        if fpath and ident in top_level_names(fpath):
                            real.append((ident, module))
                            continue
                    picked = pick_module(domain_id, hits, defined_hits=dh)
                    if picked:
                        real.append((ident, picked))
                if real:
                    for ident, mod in real:
                        entry = dict(prov)
                        entry["symbol"] = ident
                        entry["module"] = repo_module(mod)
                        if not entry.get("type"):
                            entry["type"] = "function"
                        new_provides.append(entry)
                        stats["prose_split"] += 1
                        notes.append(f"split {domain_id}|{symbol} → {ident}@{mod}")
                    domain_dirty = True
                else:
                    entry = dict(prov)
                    entry["type"] = "doc"
                    entry.setdefault("notes", "conceptual; not an AST export")
                    new_provides.append(entry)
                    stats["prose_to_doc"] += 1
                    notes.append(f"doc {domain_id}|{symbol}")
                    domain_dirty = True
                continue

            # Resolve module path
            hits = index.get(leaf) or []
            dh = def_index.get(leaf) or []
            override = MODULE_OVERRIDES.get((domain_id, leaf))
            if override and module != override:
                entry = dict(prov)
                entry["module"] = override
                if not entry.get("type"):
                    entry["type"] = "function"
                new_provides.append(entry)
                stats["override"] += 1
                notes.append(f"override {domain_id}|{leaf} → {override}")
                domain_dirty = True
                continue
            if not module:
                picked = pick_module(domain_id, hits, defined_hits=dh)
                if picked:
                    entry = dict(prov)
                    entry["module"] = repo_module(picked)
                    if not entry.get("type"):
                        entry["type"] = "function"
                    new_provides.append(entry)
                    stats["fill_module"] += 1
                    notes.append(f"fill {domain_id}|{leaf} → {picked}")
                    domain_dirty = True
                elif hits:
                    new_provides.append(prov)
                    stats["ambiguous"] += 1
                    notes.append(f"AMBIG empty {domain_id}|{leaf} hits={hits[:4]}")
                else:
                    stats["drop_gone"] += 1
                    notes.append(f"DROP empty-gone {domain_id}|{leaf}")
                    domain_dirty = True
                continue

            if not module.endswith(".py"):
                new_provides.append(prov)
                stats["non_py"] += 1
                continue

            from verify_registry_provides_ast import symbol_in_module

            fpath = find_module(module)
            if fpath is not None and symbol_in_module(fpath, symbol):
                new_provides.append(prov)
                stats["ok"] += 1
                continue

            # type:module or filename-as-symbol → keep, AST checker skips
            if ptype == "module" or symbol.endswith(".py") or "/" in symbol:
                new_provides.append(prov)
                stats["ok_module"] += 1
                continue

            # Wrong path or missing symbol — try reloc / demote to doc
            picked = pick_module(domain_id, hits, claimed=module, defined_hits=dh)
            if picked:
                entry = dict(prov)
                entry["module"] = repo_module(picked)
                new_provides.append(entry)
                stats["reloc_module"] += 1
                notes.append(f"reloc {domain_id}|{leaf} {module} → {picked}")
                domain_dirty = True
                continue
            if hits:
                new_provides.append(prov)
                stats["ambiguous"] += 1
                notes.append(f"AMBIG {domain_id}|{leaf}@{module} hits={hits[:4]}")
                continue

            # Module file exists but symbol is conceptual / renamed → keep as doc
            if fpath is not None:
                entry = dict(prov)
                entry["type"] = "doc"
                entry.setdefault("notes", "conceptual or non-export; retained for domain map")
                new_provides.append(entry)
                stats["missing_to_doc"] += 1
                notes.append(f"doc-keep {domain_id}|{symbol}@{module}")
                domain_dirty = True
                continue

            # Zero hits and no file → drop
            stats["drop_gone"] += 1
            notes.append(f"DROP gone {domain_id}|{leaf}@{module}")
            domain_dirty = True

        body["provides"] = new_provides
        if domain_dirty:
            changed_domains.add(domain_id)

    sync_caps_counts(data)
    if not dry_run:
        apply_provides_preserving_comments(data, only_domains=changed_domains)

    return {
        "stats": dict(stats),
        "notes": notes,
        "dry_run": dry_run,
        "changed_domains": sorted(changed_domains),
    }


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    dry = "--apply" not in argv
    result = repair(dry_run=dry)
    print(f"repair_registry_provides_ast_debt dry_run={result['dry_run']}")
    print("stats:", result["stats"])
    for n in result["notes"][:40]:
        print(" ", n)
    if len(result["notes"]) > 40:
        print(f"  … +{len(result['notes']) - 40} more")
    if dry:
        print("Re-run with --apply to write capability_registry.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
