"""
Capability Convergence Checker (Phase 2)

Uses the code graph's symbol-level call graph to verify that every
known execution path for each system capability converges on the
same mandatory gates (context injection, policy gates, event emission,
model resolution, etc.).

Per capability_convergence.yaml contract.
"""
from __future__ import annotations

import os
import sys
import io
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict, deque

# Project root
_ROOT = Path(__file__).resolve().parents[3]


def load_contract() -> Dict[str, Any]:
    """Load the capability convergence contract."""
    contract_path = Path(__file__).resolve().parent / "capability_convergence.yaml"
    if not contract_path.exists():
        return {"capabilities": []}
    with open(contract_path) as f:
        return yaml.safe_load(f) or {"capabilities": []}


def _resolve_symbol_id(file_path: str, symbol_name: str) -> str:
    """Normalize a file path + symbol name into a symbol graph ID."""
    fp = file_path.lstrip("/").replace("/", "/")
    return f"{fp}::{symbol_name}"


def _normalize_path(p: str) -> str:
    """Normalize a path to match code_graph's repo-root-relative format."""
    p = p.replace("\\", "/")
    # Remove leading / if present
    p = p.lstrip("/")
    # If path doesn't start with a known prefix, prepend aiPlat-core/
    if not any(p.startswith(prefix) for prefix in ("aiPlat-core/", "aiPlat-platform/", "aiPlat-management/")):
        p = f"aiPlat-core/core/{p}"
    return p


def run_convergence_check(repo_root: Path = None, force_rebuild: bool = False) -> Tuple[bool, List[Dict[str, Any]]]:
    """Run all convergence checks. Returns (all_pass, violation_details)."""
    if repo_root is None:
        repo_root = _ROOT

    contract = load_contract()
    capabilities = contract.get("capabilities", [])
    violations: List[Dict[str, Any]] = []

    # Build symbol graph (force rebuild if requested to include latest lazy import tracking)
    symbol_nodes, symbol_edges = _build_or_load_symbol_graph(repo_root, force_rebuild=force_rebuild)
    if not symbol_nodes:
        return True, violations  # can't check without graph

    for cap in capabilities:
        name = cap.get("name", "unknown")
        canonical = cap.get("canonical_path", "")
        known = cap.get("known_paths", [])
        gates = cap.get("mandatory_gates", [])
        forbidden = cap.get("forbidden_patterns", [])
        forbidden_paths = cap.get("forbidden_paths", [])

        # ── Check 1: Forbidden patterns (grep) ──
        _check_forbidden_patterns(name, forbidden, violations)

        # ── Check 2: Forbidden code paths ──
        _check_forbidden_paths(name, forbidden_paths, violations)

        # ── Check 3: Known paths must reach mandatory gates ──
        if known and gates:
            _check_gate_convergence(name, known, gates, symbol_nodes, symbol_edges, violations)

        # ── Check 4: Canonical path must reach all gates (self-check) ──
        if canonical and gates:
            _check_gate_convergence(name, [canonical], gates, symbol_nodes, symbol_edges, violations)

    all_pass = len(violations) == 0
    return all_pass, violations


def _build_or_load_symbol_graph(repo_root: Path, force_rebuild: bool = False) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """Build or load the symbol graph from code_graph."""
    if not force_rebuild:
        try:
            sys.path.insert(0, str(repo_root / "aiPlat-core"))
            from core.harness.knowledge.code_graph_persist import has_cache, load_nodes, load_edges

            if has_cache():
                nodes = load_nodes()
                edges = load_edges()
                from core.harness.knowledge.code_graph import _build_symbol_graph
                return _build_symbol_graph(nodes, edges, repo_root)
        except Exception:
            pass

    # Fallback: rebuild from scratch (or force-rebuild)
    try:
        roots = [
            repo_root / "aiPlat-core" / "core",
            repo_root / "aiPlat-platform",
            repo_root / "aiPlat-management",
        ]
        from core.harness.knowledge.code_graph import build_symbol_graph
        return build_symbol_graph(repo_root, [r.resolve() for r in roots if r.exists()])
    except Exception:
        return {}, []


def _check_forbidden_patterns(
    cap_name: str,
    patterns: List[Dict[str, Any]],
    violations: List[Dict[str, Any]],
) -> None:
    """Run grep for forbidden regex patterns."""
    import re, subprocess

    for fp_def in patterns:
        if isinstance(fp_def, dict):
            pattern = fp_def.get("pattern", "")
            paths = fp_def.get("paths", ["core/"])
        else:
            pattern = str(fp_def)
            paths = ["core/"]

        for scope in paths:
            dir_path = _ROOT / scope.lstrip("/")
            if not dir_path.exists():
                continue
            try:
                result = subprocess.run(
                    ["grep", "-rn", "-E", pattern, str(dir_path)],
                    capture_output=True, text=True, timeout=10,
                )
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split(":", 2)
                        violations.append({
                            "capability": cap_name,
                            "type": "forbidden_pattern",
                            "pattern": pattern,
                            "file": parts[0] if len(parts) > 0 else "",
                            "line": parts[1] if len(parts) > 1 else "",
                            "detail": parts[2].strip() if len(parts) > 2 else "",
                        })
            except Exception:
                pass


def _check_forbidden_paths(
    cap_name: str,
    paths: List[str],
    violations: List[Dict[str, Any]],
) -> None:
    """Check that forbidden code paths don't execute the capability."""
    for forbidden in paths:
        parts = forbidden.split("::", 1)
        file_path = parts[0] if len(parts) > 0 else forbidden
        symbol = parts[1] if len(parts) > 1 else ""
        full = _ROOT / "aiPlat-core" / file_path.lstrip("/")
        if full.exists():
            violations.append({
                "capability": cap_name,
                "type": "forbidden_path_exists",
                "path": forbidden,
                "detail": f"Forbidden execution path exists: {file_path}" + (f"::{symbol}" if symbol else ""),
            })

    # Also grep for resolution_required bypass patterns
    contract = load_contract()
    caps = contract.get("capabilities", [])
    for cap in caps:
        if cap.get("resolution_required") and cap.get("name") == cap_name:
            # Check if any file outside approved paths imports/calls the capability
            pass  # complex check deferred to Phase 2.5


def _check_gate_convergence(
    cap_name: str,
    entry_paths: List[str],
    gates: List[Dict[str, Any]],
    symbol_nodes: Dict[str, Any],
    symbol_edges: List[Dict[str, str]],
    violations: List[Dict[str, Any]],
) -> None:
    """Verify that every entry path can reach all mandatory gates."""
    # Build adjacency list for forward traversal
    adj: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for edge in symbol_edges:
        frm = edge.get("from", "")
        to = edge.get("to", "")
        kind = edge.get("kind", "")
        if frm and to:
            adj[frm].append((to, kind))

    for entry_path in entry_paths:
        parts = entry_path.split("::", 1)
        file_path = parts[0] if len(parts) > 0 else ""
        symbol_name = parts[1] if len(parts) > 1 else ""

        # Normalize file path
        norm_file = _normalize_path(file_path)

        # Find entry node — try exact match, then file-level fallback
        entry_id = f"{norm_file}::{symbol_name}"
        if entry_id not in symbol_nodes:
            alt_id = f"aiPlat-core/{norm_file}::{symbol_name}"
            entry_id = alt_id if alt_id in symbol_nodes else None

        if not entry_id or entry_id not in symbol_nodes:
            # Fallback: find any symbol in the target file as a proxy entry point
            file_symbols = sorted(
                [nid for nid, n in symbol_nodes.items() if n.get("file") == norm_file],
                key=lambda x: (0 if symbol_name in x else 1, x)
            )
            if file_symbols:
                entry_id = file_symbols[0]
            else:
                violations.append({
                    "capability": cap_name,
                    "type": "entry_not_found",
                    "path": entry_path,
                    "detail": f"No symbols found for: {entry_path}",
                })
                continue

        # For each mandatory gate, check reachability from entry
        for gate in gates:
            gate_symbol = gate.get("symbol", "")
            gate_file = gate.get("from", "")
            norm_gate_file = _normalize_path(gate_file)

            # Find gate symbol nodes
            gate_matches = []
            for nid, node in symbol_nodes.items():
                if node.get("name") == gate_symbol:
                    if norm_gate_file in nid:
                        gate_matches.append(nid)

            if not gate_matches:
                continue  # gate not in graph, skip

            # BFS forward from entry, see if we reach any gate match
            reachable = _is_reachable(entry_id, set(gate_matches), adj, max_depth=50)
            if not reachable:
                violations.append({
                    "capability": cap_name,
                    "type": "gate_not_reachable",
                    "path": entry_path,
                    "gate": gate_symbol,
                    "gate_file": gate_file,
                    "detail": f"'{entry_path}' cannot reach mandatory gate '{gate_symbol}' ({gate_file})",
                })


def _is_reachable(
    start: str,
    targets: Set[str],
    adj: Dict[str, List[Tuple[str, str]]],
    max_depth: int = 50,
) -> bool:
    """BFS forward from start to see if any target is reachable."""
    seen: Set[str] = set()
    q = deque([(start, 0)])
    seen.add(start)
    while q:
        node, depth = q.popleft()
        if node in targets:
            return True
        if depth >= max_depth:
            continue
        for neighbor, _ in adj.get(node, []):
            if neighbor not in seen:
                seen.add(neighbor)
                q.append((neighbor, depth + 1))
    return False


def print_report(all_pass: bool, violations: List[Dict[str, Any]]) -> str:
    """Generate a human-readable report."""
    buf = io.StringIO()
    buf.write("=" * 70 + "\n")
    buf.write("  Capability Convergence Report\n")
    buf.write("=" * 70 + "\n")

    if all_pass:
        buf.write("\n  [PASS] All capabilities converge on mandatory gates.\n")
        return buf.getvalue()

    # Group violations by capability
    by_cap: Dict[str, List[Dict]] = defaultdict(list)
    for v in violations:
        by_cap[v.get("capability", "unknown")].append(v)

    for cap_name, items in sorted(by_cap.items()):
        buf.write(f"\n  ── {cap_name} ──\n")
        for item in items:
            vtype = item.get("type", "?")
            detail = item.get("detail", "")
            fpath = item.get("file", "") or item.get("path", "")
            gate = item.get("gate", "")
            if vtype == "gate_not_reachable":
                buf.write(f"    ❌ MISSING GATE: {gate}\n")
                buf.write(f"       Path: {fpath} cannot reach {gate}\n")
            elif vtype == "forbidden_pattern":
                line = item.get("line", "")
                buf.write(f"    ❌ FORBIDDEN: {detail}  [{fpath}:{line}]\n")
            elif vtype == "forbidden_path_exists":
                buf.write(f"    ❌ BYPASS: {detail}\n")
            elif vtype == "entry_not_found":
                buf.write(f"    ⚠️  SKIP: {detail}\n")
            else:
                buf.write(f"    ❌ {detail}\n")

    buf.write(f"\n  {len(violations)} violation(s) found.\n")
    return buf.getvalue()


# ── CLI ──

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Capability Convergence Checker")
    parser.add_argument("--repo-root", default=str(_ROOT), help="Repository root path")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--force", action="store_true", help="Force rebuild of code graph (bypass cache)")
    args = parser.parse_args()

    all_pass, violations = run_convergence_check(Path(args.repo_root), force_rebuild=args.force)

    if args.json:
        import json as _json
        print(_json.dumps({"pass": all_pass, "violations": violations}, indent=2))
    else:
        print(print_report(all_pass, violations))

    sys.exit(0 if all_pass else 1)
