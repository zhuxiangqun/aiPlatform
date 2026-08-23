"""L4 cross-module impact analyzer (plan-app-factory-l4 §3.3/§3.5).

Builds a module dependency graph from three contract kinds (v1 static analysis):
- API contract:   module A declares @router/@app route "/x", module B calls it
                  (fetch("/api/...") / httpx / requests / url string)
- Data contract:  module B imports module A's entity (from a.models import X)
- Event contract: module A publishes topic, module B subscribes (publish/subscribe)
Returns dependency graph + evidence lines for frontend display.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Set

_API_DECL_RE = re.compile(
    r'@(?:router|app|bp)\.(?:get|post|put|delete|patch)\s*\(\s*["\'](/[^"\']*)["\']',
    re.MULTILINE,
)
_API_CALL_RE = re.compile(
    r'(?:fetch|axios|httpx|requests|\.post|\.get|\.put|\.delete)\s*\(\s*["\']([^"\']*/[^"\']*)["\']',
    re.MULTILINE,
)
_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import\s+[\w\s,*]+|import\s+[\w.]+)\s*(?:#.*)?$",
    re.MULTILINE,
)
_PUBLISH_RE = re.compile(r"(?:publish|emit|broadcast)\s*\(\s*[\"']([\w.\-]+)[\"']", re.MULTILINE)
_SUBSCRIBE_RE = re.compile(r"(?:subscribe|on_event|listen)\s*\(\s*[\"']([\w.\-]+)[\"']", re.MULTILINE)

_CODE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx")


def _read_module_files(root: str) -> Dict[str, str]:
    """module root → {rel_path: content} (code files only, capped)."""
    out: Dict[str, str] = {}
    if not root or not os.path.isdir(root):
        return out
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.endswith(_CODE_EXTS):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            full = os.path.join(dirpath, fn)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    out[rel] = fh.read(200_000)
            except OSError:
                continue
    return out


def _module_key(module_id: str) -> str:
    return module_id.replace("-", "_").replace("/", "_")


def scan_module_contracts(root: str) -> Dict[str, Any]:
    """Extract declared contracts of one module: apis / events / entity modules."""
    apis: List[str] = []
    events: List[str] = []
    entity_mods: Set[str] = set()
    for rel, content in _read_module_files(root).items():
        apis.extend(_API_DECL_RE.findall(content))
        events.extend(_PUBLISH_RE.findall(content))
        for m in _IMPORT_RE.finditer(content):
            mod = (m.group(1) or "").strip()
            if mod and ("models" in mod or "entity" in mod or "schema" in mod):
                entity_mods.add(mod)
    return {
        "apis": sorted(set(apis)),
        "events": sorted(set(events)),
        "entity_modules": sorted(entity_mods),
    }


def _module_calls_target(module_files: Dict[str, str], target: Dict[str, Any],
                         target_contracts: Dict[str, Any]) -> Dict[str, Any]:
    """Does the given module reference the target's contracts? Returns evidence."""
    evidence: Dict[str, Any] = {"apis": [], "events": [], "entities": []}
    target_apis = set(target_contracts.get("apis") or [])
    target_events = set(target_contracts.get("events") or [])
    for rel, content in module_files.items():
        # API calls → match against target's declared routes (suffix match)
        for call in _API_CALL_RE.findall(content):
            for ta in target_apis:
                if call.endswith(ta) or ta in call:
                    evidence["apis"].append({"line_file": rel, "call": call, "route": ta})
                    break
        # Event subscription → match target's published topics
        for ev in _SUBSCRIBE_RE.findall(content):
            if ev in target_events:
                evidence["events"].append({"line_file": rel, "topic": ev})
        # Entity import → match target module id in import path
        target_key = _module_key(target.get("module_id", ""))
        for m in _IMPORT_RE.finditer(content):
            mod = (m.group(1) or "").strip()
            if target_key in mod.replace(".", "_") and ("models" in mod or "entity" in mod):
                evidence["entities"].append({"line_file": rel, "import": mod})
    return evidence


def analyze_cross_module(modules: List[Dict[str, Any]], workspace_root: str) -> Dict[str, Any]:
    """Module dependency graph: {module_id: {depends_on, depended_by, evidence}}.

    modules: [{module_id, root (abs path)}]; workspace_root: base for relative roots.
    """
    # 1) scan each module's declared contracts
    contracts: Dict[str, Dict[str, Any]] = {}
    files_by_mod: Dict[str, Dict[str, str]] = {}
    for mod in modules:
        mid = mod.get("module_id", "")
        root = mod.get("root", "")
        if not mid or not root:
            continue
        if not os.path.isabs(root):
            root = os.path.join(workspace_root, root)
        files_by_mod[mid] = _read_module_files(root)
        contracts[mid] = scan_module_contracts(root)

    # 2) pairwise dependency detection
    graph: Dict[str, Dict[str, Any]] = {}
    for mid in files_by_mod:
        graph[mid] = {"depends_on": [], "depended_by": [], "evidence": {}}
    for mid, files in files_by_mod.items():
        deps: List[str] = []
        evidence: Dict[str, Any] = {}
        for tid in files_by_mod:
            if tid == mid:
                continue
            ev = _module_calls_target(files, {"module_id": tid}, contracts[tid])
            if ev["apis"] or ev["events"] or ev["entities"]:
                deps.append(tid)
                evidence[tid] = ev
        graph[mid]["depends_on"] = deps
        graph[mid]["evidence"] = evidence
    # reverse: depended_by
    for mid in graph:
        for dep in graph[mid]["depends_on"]:
            if mid not in graph[dep]["depended_by"]:
                graph[dep]["depended_by"].append(mid)

    return {"graph": graph, "contracts": contracts}


def impact_closure(module_id: str, graph: Dict[str, Any]) -> List[str]:
    """Affected set = module + everything that depends on it (direct + transitive)."""
    affected: List[str] = []
    seen: Set[str] = set()

    def walk(mid: str) -> None:
        if mid in seen:
            return
        seen.add(mid)
        affected.append(mid)
        for dep in graph.get(mid, {}).get("depended_by", []):
            walk(dep)

    walk(module_id)
    return affected


def topological_order(module_ids: List[str], graph: Dict[str, Any]) -> List[str]:
    """Order changed modules so dependencies come first (Kahn's algorithm)."""
    ordered: List[str] = []
    remaining = set(module_ids)
    while remaining:
        progress = False
        for mid in sorted(remaining):
            deps = set(graph.get(mid, {}).get("depends_on", [])) & remaining
            if not deps:
                ordered.append(mid)
                remaining.discard(mid)
                progress = True
                break
        if not progress:
            # cycle guard: append remaining in id order
            ordered.extend(sorted(remaining))
            break
    return ordered
