#!/usr/bin/env python3
"""
verify_registry_provides_ast.py — registry provides ↔ source AST ratchet (Phase B)

Source of truth = repo checkout. For each `provides[]` entry with a `.py` module:
  - resolve module path under the monorepo
  - AST-parse top-level public names (class / def / assign)
  - assert `symbol` leaf is among them

Entries without `module`, non-.py modules, skipped types, or non-identifier
symbols are classified separately (not mixed into symbol_missing).

Usage:
  python3 scripts/verify_registry_provides_ast.py              # report, exit 0
  python3 scripts/verify_registry_provides_ast.py --ci         # new findings vs baseline → exit 1
  python3 scripts/verify_registry_provides_ast.py --write-baseline

Ratchet: scripts/baselines/registry_provides_ast_baseline.json
  Keys are stable ids: "{domain}|{symbol}|{module}|{kind}"
  --ci fails only when a finding id is absent from the baseline (new debt).
  Soft shrink: removing baseline entries after fixes is encouraged; never grow.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Set

ROOT = Path(__file__).resolve().parent.parent
REG_FILE = ROOT / "aiPlat-core" / "core" / "capability_registry.yaml"
BASELINE_PATH = ROOT / "scripts" / "baselines" / "registry_provides_ast_baseline.json"

PREFIXES = (
    "",
    "aiPlat-core/",
    "aiPlat-platform/",
    "aiPlat-management/",
    "aiPlat-infra/",
    "aiPlat-app/",
)

SKIP_TYPES = frozenset({
    "config_file",
    "react_component",
    "api_endpoint",
    "pattern",
    "doc",
    "yaml",
    "markdown",
    "endpoint",
})

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Finding(NamedTuple):
    domain: str
    symbol: str
    module: str
    kind: str  # missing_module | module_not_found | symbol_missing | non_identifier

    @property
    def id(self) -> str:
        return f"{self.domain}|{self.symbol}|{self.module}|{self.kind}"


def find_module(rel_path: str) -> Optional[Path]:
    if not rel_path or rel_path.startswith("~"):
        return None
    rel = rel_path.lstrip("./")
    candidates = [ROOT / rel]
    for pfx in PREFIXES:
        candidates.append(ROOT / f"{pfx}{rel}")
        if rel.startswith("core/") and pfx == "aiPlat-core/":
            candidates.append(ROOT / f"aiPlat-core/{rel}")
    seen: Set[str] = set()
    for c in candidates:
        key = str(c)
        if key in seen:
            continue
        seen.add(key)
        if c.is_file():
            return c
    return None


def top_level_names(path: Path) -> Set[str]:
    """Top-level defs/assigns plus Import/ImportFrom aliases (facade re-exports)."""
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
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == "*":
                    continue
                names.add(a.asname or a.name)
    return names


def _symbol_leaf(symbol: str) -> str:
    return str(symbol or "").split(".")[-1].strip().strip("\"'")


def symbol_in_module(path: Path, symbol: str) -> bool:
    """True if leaf is top-level, or Class.method exists on a top-level class."""
    raw = str(symbol or "").strip().strip("\"'")
    leaf = _symbol_leaf(raw)
    if not leaf or not IDENT_RE.match(leaf):
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, OSError):
        return False
    top = top_level_names(path)
    if leaf in top:
        return True
    parts = [p for p in raw.split(".") if p]
    if len(parts) < 2:
        return False
    cls_name, meth = parts[0], parts[-1]
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == meth:
                    return True
                if isinstance(child, ast.Assign):
                    for t in child.targets:
                        if isinstance(t, ast.Name) and t.id == meth:
                            return True
    return False


def audit_registry(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if data is None:
        import yaml

        data = yaml.safe_load(REG_FILE.read_text(encoding="utf-8"))
    domains = data.get("domains") or {}
    findings: List[Finding] = []
    counts = {
        "ok": 0,
        "skipped_type": 0,
        "non_py": 0,
        "missing_module": 0,
        "module_not_found": 0,
        "symbol_missing": 0,
        "non_identifier": 0,
        "total_provides": 0,
    }

    for domain_id, domain in domains.items():
        for prov in domain.get("provides") or []:
            if not isinstance(prov, dict):
                continue
            counts["total_provides"] += 1
            symbol = str(prov.get("symbol") or "")
            module = str(prov.get("module") or "")
            ptype = str(prov.get("type") or "")
            if ptype in SKIP_TYPES:
                counts["skipped_type"] += 1
                continue
            # Filename / path used as "symbol" under type:module — not an AST export
            if ptype == "module" or symbol.endswith(".py") or "/" in symbol:
                counts["skipped_type"] += 1
                continue
            if not module:
                findings.append(Finding(domain_id, symbol, "", "missing_module"))
                counts["missing_module"] += 1
                continue
            if not module.endswith(".py"):
                counts["non_py"] += 1
                continue
            leaf = _symbol_leaf(symbol)
            if not IDENT_RE.match(leaf):
                findings.append(Finding(domain_id, symbol, module, "non_identifier"))
                counts["non_identifier"] += 1
                continue
            fpath = find_module(module)
            if fpath is None:
                findings.append(Finding(domain_id, symbol, module, "module_not_found"))
                counts["module_not_found"] += 1
                continue
            if symbol_in_module(fpath, symbol):
                counts["ok"] += 1
            else:
                findings.append(Finding(domain_id, symbol, module, "symbol_missing"))
                counts["symbol_missing"] += 1

    finding_ids = sorted({f.id for f in findings})
    return {
        "counts": counts,
        "findings": [f._asdict() for f in findings],
        "finding_ids": finding_ids,
    }


def load_baseline(path: Path = BASELINE_PATH) -> Dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "finding_ids": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_baseline(result: Dict[str, Any], path: Path = BASELINE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "generated_by": "scripts/verify_registry_provides_ast.py --write-baseline",
        "counts": result["counts"],
        "finding_ids": result["finding_ids"],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def new_findings(result: Dict[str, Any], baseline: Dict[str, Any]) -> List[str]:
    known = set(baseline.get("finding_ids") or [])
    return sorted(set(result["finding_ids"]) - known)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    ci = "--ci" in argv
    write = "--write-baseline" in argv

    print("registry provides AST check (source of truth = repo .py modules)")
    print("-" * 60)
    result = audit_registry()
    c = result["counts"]
    print(
        f"provides={c['total_provides']} ok={c['ok']} "
        f"missing_module={c['missing_module']} module_not_found={c['module_not_found']} "
        f"symbol_missing={c['symbol_missing']} non_identifier={c['non_identifier']} "
        f"non_py={c['non_py']} skipped_type={c['skipped_type']}"
    )
    print(f"findings={len(result['finding_ids'])}")

    if write:
        write_baseline(result)
        print(f"wrote baseline {BASELINE_PATH} ({len(result['finding_ids'])} ids)")
        return 0

    baseline = load_baseline()
    novel = new_findings(result, baseline)
    if novel:
        print(f"NEW vs baseline: {len(novel)}")
        for fid in novel[:30]:
            print(f"  + {fid}")
        if len(novel) > 30:
            print(f"  ... +{len(novel) - 30} more")
    else:
        print("NEW vs baseline: 0")

    if ci and novel:
        print("CI FAIL (new provides AST debt)")
        return 1
    if ci:
        print("CI PASS (no new provides AST debt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
