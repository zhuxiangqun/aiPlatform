"""L3 incremental merge engine — ImpactAnalyzer + DiffMerger.

Design: plan-app-factory-l3-incremental-engine.md §3.3/§3.5.
- ImpactAnalyzer: affected-file set = user-checked files + Python first-order
  import references (v1 scope; frontend shows auto-added files, user may opt out).
- DiffMerger: new-vs-original unified diff → per-file preview (hunks/changed/
  unchanged), syntax check (py_compile), interface-preservation check (Python AST),
  and apply with deploy.prev snapshot before merge.
"""
from __future__ import annotations

import ast
import difflib
import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple

# Python module path → project-relative path map builder
_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import\s+[\w\s,*.]+|import\s+([\w.]+(?:\s*,\s*[\w.]+)*))\s*(?:#.*)?$",
    re.MULTILINE,
)


# ── ImpactAnalyzer (§3.3) ────────────────────────────────────────────────────

def _collect_py_files(import_root: str) -> List[str]:
    out = []
    for root, _dirs, files in os.walk(import_root):
        for fn in files:
            if fn.endswith(".py"):
                out.append(os.path.relpath(os.path.join(root, fn), import_root))
    return out


def _module_key(rel_path: str) -> str:
    """'src/auth/login.py' → 'src.auth.login' (and 'auth.login' for loose matching)."""
    stem = rel_path[:-3] if rel_path.endswith(".py") else rel_path
    return stem.replace("/", ".").replace("\\", ".")


def _build_module_map(py_files: List[str]) -> Dict[str, str]:
    m = {}
    for rel in py_files:
        m[_module_key(rel)] = rel
    return m


def _build_leaf_map(py_files: List[str]) -> Dict[str, List[str]]:
    """'src/models/user.py' → {'user': [...], 'models': [...], 'src': [...]}"""
    leaf: Dict[str, List[str]] = {}
    for rel in py_files:
        for seg in reversed(_module_key(rel).split(".")):
            leaf.setdefault(seg, []).append(rel)
    return leaf


def _imports_of(import_root: str, rel_path: str, module_map: Dict[str, str],
                leaf_map: Optional[Dict[str, List[str]]] = None) -> List[str]:
    """Modules imported by the given file, resolved to project-relative paths."""
    full = os.path.join(import_root, rel_path)
    if not os.path.isfile(full):
        return []
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read(200_000)
    except OSError:
        return []
    leaf_map = leaf_map or {}
    resolved = []
    for m in _IMPORT_RE.finditer(content):
        mod = (m.group(1) or "").strip() or (m.group(2) or "").strip()
        if not mod:
            continue
        # 1) try exact module key, then progressively shorter prefixes
        parts = mod.split(".")
        found = False
        for i in range(len(parts), 0, -1):
            cand = ".".join(parts[:i])
            if cand in module_map:
                resolved.append(module_map[cand])
                found = True
                break
        if found:
            continue
        # 2) leaf-module fallback (e.g. "import user" → unique src/models/user.py)
        leaves = leaf_map.get(parts[-1], [])
        if len(leaves) == 1 and leaves[0] != rel_path:
            resolved.append(leaves[0])
    return sorted(set(resolved))


def _importers_of(import_root: str, rel_path: str, py_files: List[str],
                  module_map: Dict[str, str], leaf_map: Dict[str, List[str]]) -> List[str]:
    """Files that import the given file (reverse first-order reference)."""
    target_key = _module_key(rel_path)
    out = []
    for other in py_files:
        if other == rel_path:
            continue
        deps = _imports_of(import_root, other, module_map, leaf_map)
        if target_key in [_module_key(d) for d in deps] or rel_path in deps:
            out.append(other)
    return sorted(out)


def analyze_impact(import_root: str, modify_files: List[Dict], manifest: List[Dict]) -> Dict[str, Any]:
    """Affected-file set: user-checked files + first-order import references.

    v1 scope: Python only. Result is advisory — frontend shows auto-added files
    and the user may uncheck them (design §3.3/§3.6).
    """
    affected = [str(m.get("path") or "").strip() for m in modify_files if m and m.get("path")]
    affected = [p for p in affected if p]
    manifest_paths = {str(m.get("path") or "") for m in manifest}
    py_files = _collect_py_files(import_root)
    module_map = _build_module_map(py_files)
    leaf_map = _build_leaf_map(py_files)

    refs: Dict[str, List[str]] = {}
    auto_added: List[str] = []
    for af in affected:
        deps = _imports_of(import_root, af, module_map, leaf_map)
        importers = _importers_of(import_root, af, py_files, module_map, leaf_map)
        related = [p for p in set(deps) | set(importers) if p in manifest_paths]
        refs[af] = related
        for p in related:
            if p not in affected and p not in auto_added:
                auto_added.append(p)

    return {
        "affected": sorted(set(affected) | set(auto_added)),
        "auto_added": sorted(auto_added),
        "analysis": refs,
        "note": "v1: Python 一阶 import 引用分析，仅供参考，用户可取消自动加入的文件",
    }


# ── DiffMerger (§3.5) ────────────────────────────────────────────────────────

def _group_hunks(diff_lines: List[str]) -> List[Dict[str, Any]]:
    hunks: List[Dict[str, Any]] = []
    current: List[str] = []
    for line in diff_lines:
        if line.startswith("@@"):
            if current:
                hunks.append({"header": current[0], "lines": current[1:]})
            current = [line]
        elif current:
            current.append(line)
    if current:
        hunks.append({"header": current[0], "lines": current[1:]})
    return hunks


def _categorize_hunk(hunk_lines: List[str]) -> str:
    """L3-P1-04: classify a hunk as 'formatting' vs 'logic'.

    A hunk is formatting when the set of added lines equals the set of removed
    lines after stripping all whitespace — i.e. only spacing/blank lines changed.
    Any non-whitespace content difference → 'logic'."""
    added = [re.sub(r"\s+", "", l[1:]) for l in hunk_lines
             if l.startswith("+") and not l.startswith("+++") and l[1:].strip()]
    removed = [re.sub(r"\s+", "", l[1:]) for l in hunk_lines
               if l.startswith("-") and not l.startswith("---") and l[1:].strip()]
    has_change = any(l.startswith(("+", "-")) and not l.startswith(("+++", "---"))
                     for l in hunk_lines)
    if has_change and added == removed:
        return "formatting"
    return "logic"


def build_merge_preview(original: str, new: str, path: str) -> Dict[str, Any]:
    """New-vs-original unified diff → preview (three-way: base=imported original)."""
    diff_lines = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""))
    changed = sum(1 for l in diff_lines
                  if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))
    unchanged = max(len(original.splitlines()) - changed, 0)
    hunks = _group_hunks(diff_lines)
    for h in hunks:
        h["category"] = _categorize_hunk(h.get("lines") or [])
    logic_changes = sum(1 for h in hunks if h.get("category") == "logic")
    return {
        "path": path,
        "changed_lines": changed,
        "unchanged_lines": unchanged,
        "logic_changes": logic_changes,
        "hunks": hunks,
        "diff_text": "".join(diff_lines),
        "has_changes": changed > 0,
    }


def syntax_check(content: str, path: str) -> Dict[str, Any]:
    """Python: compile() check. Other languages: skipped (text-only)."""
    if path.endswith(".py"):
        try:
            compile(content, path, "exec")
            return {"ok": True}
        except SyntaxError as e:
            return {"ok": False, "error": f"{e.msg} (line {e.lineno})"}
    return {"ok": True, "note": "non-python, syntax check skipped"}


def _extract_signatures(content: str) -> List[str]:
    """Python AST: function names + class names + module-level route decorator paths."""
    sigs = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return sigs
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sigs.append(f"def {node.name}")
        elif isinstance(node, ast.ClassDef):
            sigs.append(f"class {node.name}")
    # route decorators: @router.get("/login") / @app.post(...)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.decorator_list:
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    for arg in dec.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            sigs.append(f"route {arg.value}")
    return sorted(set(sigs))


def verify_interface_preserved(original: str, new: str, path: str) -> Dict[str, Any]:
    """Python: function/class/route signatures must survive the merge."""
    if not path.endswith(".py"):
        return {"ok": True, "note": "non-python, interface check skipped"}
    old_sigs = _extract_signatures(original)
    if not old_sigs:
        return {"ok": True, "note": "no detectable signatures in original"}
    new_sigs = _extract_signatures(new)
    missing = [s for s in old_sigs if s not in new_sigs]
    return {
        "ok": not missing,
        "missing": missing,
        "preserved": len(old_sigs) - len(missing),
        "total": len(old_sigs),
    }


def snapshot_affected_files(import_root: str, paths: List[str]) -> Dict[str, str]:
    """L3-P0-02: sha256 snapshot of affected imported files before generation."""
    snap: Dict[str, str] = {}
    for rel in paths:
        full = os.path.join(import_root, rel)
        if os.path.isfile(full):
            try:
                with open(full, "rb") as fh:
                    snap[rel] = _sha256(fh.read())
            except OSError:
                continue
    return snap


def verify_snapshot(import_root: str, snapshot: Dict[str, str]) -> Tuple[bool, List[str]]:
    """L3-P0-02: verify imported files still match the pre-generation snapshot."""
    changed = []
    for rel, old_hash in (snapshot or {}).items():
        full = os.path.join(import_root, rel)
        if not os.path.isfile(full):
            changed.append(rel)
            continue
        try:
            with open(full, "rb") as fh:
                new_hash = _sha256(fh.read())
            if new_hash != old_hash:
                changed.append(rel)
        except OSError:
            changed.append(rel)
    return (not changed, changed)


def _sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def apply_merge(project_id: str, import_root: str, deploy_dir: str,
                previews: List[Dict], decisions: Dict[str, str]) -> Dict[str, Any]:
    """Apply approved previews: write new versions to deploy_dir, copy the rest
    of the imported originals as baseline, snapshot deploy_dir to deploy.prev first.

    L3-P0-01: atomic approval — every preview path MUST be "approved", otherwise
    the merge is refused (rejected = regenerate, never partial apply).

    decisions: {path: "approved"} only; any missing/rejected path → ValueError.
    """
    os.makedirs(deploy_dir, exist_ok=True)

    # ── P0-01 atomic gate: all previews must be approved ──
    preview_paths = [p.get("path", "") for p in previews if isinstance(p, dict) and p.get("path")]
    if not preview_paths:
        raise ValueError("没有合并预览，无法应用。请先运行 merge-preview。")
    missing_approval = [p for p in preview_paths if (decisions or {}).get(p) != "approved"]
    if missing_approval:
        raise ValueError(
            "必须审批全部文件（原子化）：未通过的文件："
            + "、".join(missing_approval[:10])
            + "。请驳回并重新生成，或修改为通过后再应用。")

    # 1) Snapshot current deploy dir before merge (design §3.7)
    prev = os.path.join(os.path.dirname(deploy_dir), "deploy.prev")
    if os.path.isdir(deploy_dir) and any(os.scandir(deploy_dir)):
        if os.path.isdir(prev):
            shutil.rmtree(prev)
        shutil.copytree(deploy_dir, prev)

    # 2) Baseline: copy whole imported/ into deploy_dir (untouched files stay intact)
    if os.path.isdir(import_root):
        for root, _dirs, files in os.walk(import_root):
            for fn in files:
                src = os.path.join(root, fn)
                rel = os.path.relpath(src, import_root)
                dst = os.path.join(deploy_dir, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

    # 3) Apply approved new versions (all are approved by the gate above)
    applied: List[str] = []
    failed: List[Dict[str, Any]] = []
    for pv in previews:
        path = pv.get("path", "")
        new_content = pv.get("new_content", "")
        dst = os.path.join(deploy_dir, path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            with open(dst, "w", encoding="utf-8") as fh:
                fh.write(new_content)
            applied.append(path)
        except OSError as e:
            failed.append({"path": path, "error": str(e)})

    return {
        "status": "ok",
        "project_id": project_id,
        "applied": applied,
        "rejected": [],
        "failed": failed,
        "merged_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "warnings": [
            f"Merged {len(applied)} files (incremental_merge) — please review diff manually."
        ] if applied else [],
    }
