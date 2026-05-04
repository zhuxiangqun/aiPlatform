from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request

from core.harness.kernel.runtime import get_kernel_runtime

router = APIRouter()


@dataclass
class _ScanResult:
    created_at: float
    roots_key: str
    stats: Dict[str, Any]
    nodes: Dict[str, Dict[str, Any]]  # path -> node
    edges: List[Dict[str, str]]  # {from,to}
    issues: List[Dict[str, Any]]
    health: Dict[str, Any]


_CACHE: Optional[_ScanResult] = None
_CACHE_TTL_SEC = 120.0


def _repo_root() -> Path:
    """
    Try to locate monorepo root so we can scan:
      - aiPlat-core
      - aiPlat-management/frontend
    """
    here = Path(__file__).resolve()
    p = here
    for _ in range(12):
        if (p / "aiPlat-core").exists() and (p / "aiPlat-management").exists():
            return p
        p = p.parent
    # fallback: parent of aiPlat-core if present
    for _ in range(12):
        if p.name == "aiPlat-core":
            return p.parent
        p = p.parent
    return Path.cwd()


def _default_roots() -> List[str]:
    return ["aiPlat-core", "aiPlat-management/frontend"]


_PY_IMPORT_RE = re.compile(r"^\s*(from\s+([a-zA-Z0-9_\.]+)\s+import|import\s+([a-zA-Z0-9_\.]+))", re.M)
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+[^;]*?\s+from\s+['"]([^'"]+)['"]|import\s*\(\s*['"]([^'"]+)['"]\s*\)|require\s*\(\s*['"]([^'"]+)['"]\s*\))"""
)

def _strip_py_type_checking(text: str) -> str:
    """
    Remove imports under `if TYPE_CHECKING:` blocks to avoid false edges.
    This makes metrics reflect runtime coupling rather than type-only imports.
    """
    if "TYPE_CHECKING" not in text:
        return text
    lines = text.splitlines()
    out: List[str] = []
    skip = False
    skip_indent: Optional[int] = None
    for line in lines:
        # start skipping
        if re.match(r"^\s*if\s+TYPE_CHECKING\s*:\s*$", line):
            skip = True
            skip_indent = None
            continue
        if skip:
            # determine indent baseline
            if skip_indent is None:
                if line.strip() == "":
                    continue
                skip_indent = len(line) - len(line.lstrip(" "))
            # stop on dedent (or new top-level)
            cur_indent = len(line) - len(line.lstrip(" "))
            if line.strip() != "" and skip_indent is not None and cur_indent < skip_indent:
                skip = False
                skip_indent = None
            else:
                continue
        if not skip:
            out.append(line)
    return "\n".join(out)


def _is_code_file(p: Path) -> bool:
    if not p.is_file():
        return False
    if p.name.startswith("."):
        return False
    ext = p.suffix.lower()
    return ext in {".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".java", ".go", ".rs", ".rb", ".php"}


def _should_skip(p: Path) -> bool:
    parts = set(p.parts)
    if any(
        x in parts
        for x in {
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "node_modules",
            "dist",
            "build",
            # Exclude tests from architecture graph (product-oriented signal).
            "tests",
            "__tests__",
        }
    ):
        return True
    if p.name.endswith((".min.js", ".map")):
        return True
    return False


def _read_text(p: Path, max_bytes: int = 800_000) -> str:
    try:
        if p.stat().st_size > max_bytes:
            return ""
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _resolve_js_relative(from_file: Path, spec: str) -> Optional[Path]:
    base = (from_file.parent / spec).resolve()
    candidates = []
    if base.suffix:
        candidates.append(base)
    else:
        for ext in [".ts", ".tsx", ".js", ".jsx"]:
            candidates.append(Path(str(base) + ext))
        for ext in [".ts", ".tsx", ".js", ".jsx"]:
            candidates.append(base / ("index" + ext))
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def _resolve_py_module(repo_root: Path, from_file: Path, mod: str) -> Optional[Path]:
    # very lightweight resolver: map a.b.c to repo_root/**/a/b/c.py or a/b/c/__init__.py
    # We first try relative to repo root.
    rel = Path(*mod.split("."))
    cand1 = repo_root / rel.with_suffix(".py")
    cand2 = repo_root / rel / "__init__.py"
    if cand1.exists():
        return cand1
    if cand2.exists():
        return cand2
    # fallback: try relative to current package folder (walk up until found "core" etc.)
    pkg_root = from_file.parent
    for _ in range(6):
        cand = pkg_root / rel.with_suffix(".py")
        if cand.exists():
            return cand
        cand = pkg_root / rel / "__init__.py"
        if cand.exists():
            return cand
        pkg_root = pkg_root.parent
    return None


def _detect_issues(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not text:
        return out
    # Secrets (heuristics)
    if re.search(r"AKIA[0-9A-Z]{16}", text):
        out.append({"type": "secret", "severity": "high", "rule": "aws_access_key_id"})
    if re.search(r"-----BEGIN (?:RSA|EC|OPENSSH) PRIVATE KEY-----", text):
        out.append({"type": "secret", "severity": "high", "rule": "private_key_block"})
    if re.search(r"(api[_-]?key|secret|token)\s*=\s*['\"][^'\"]{12,}['\"]", text, re.I):
        out.append({"type": "secret", "severity": "medium", "rule": "hardcoded_token_like"})
    # Dangerous eval
    if re.search(r"\beval\s*\(", text):
        out.append({"type": "security", "severity": "medium", "rule": "eval_usage"})
    if re.search(r"\bexec\s*\(", text):
        out.append({"type": "security", "severity": "medium", "rule": "exec_usage"})
    return out


def _build_graph(repo_root: Path, roots: List[Path]) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, str]], List[Dict[str, Any]]]:
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, str]] = []
    issues: List[Dict[str, Any]] = []

    # Collect files
    files: List[Path] = []
    for r in roots:
        if not r.exists():
            continue
        for p in r.rglob("*"):
            if _should_skip(p):
                continue
            if _is_code_file(p):
                files.append(p)

    # Index by path for quick lookup
    for f in files:
        rel = str(f.relative_to(repo_root))
        nodes[rel] = {"id": rel, "path": rel, "ext": f.suffix.lower(), "out": [], "in": 0, "issue_count": 0}

    # Parse imports
    for f in files:
        rel_from = str(f.relative_to(repo_root))
        text = _read_text(f)
        file_issues = _detect_issues(text)
        if file_issues:
            for it in file_issues:
                issues.append({**it, "file": rel_from})
            nodes[rel_from]["issue_count"] = len(file_issues)

        deps: Set[str] = set()
        if f.suffix.lower() == ".py":
            text = _strip_py_type_checking(text)
            for m in _PY_IMPORT_RE.finditer(text):
                mod = m.group(2) or m.group(3)
                if not mod:
                    continue
                tgt = _resolve_py_module(repo_root, f, mod)
                if tgt and tgt.exists():
                    rel_to = str(tgt.relative_to(repo_root))
                    if rel_to in nodes and rel_to != rel_from:
                        deps.add(rel_to)
        else:
            for m in _JS_IMPORT_RE.finditer(text):
                spec = m.group(1) or m.group(2) or m.group(3)
                if not spec:
                    continue
                if spec.startswith("."):
                    tgt = _resolve_js_relative(f, spec)
                    if tgt and tgt.exists():
                        rel_to = str(tgt.relative_to(repo_root))
                        if rel_to in nodes and rel_to != rel_from:
                            deps.add(rel_to)

        for rel_to in sorted(deps):
            edges.append({"from": rel_from, "to": rel_to})
            nodes[rel_from]["out"].append(rel_to)
            nodes[rel_to]["in"] += 1

    return nodes, edges, issues


def _count_cycles(nodes: Dict[str, Dict[str, Any]]) -> int:
    # Simple cycle detection count (number of back-edges found in DFS).
    visiting: Set[str] = set()
    visited: Set[str] = set()
    back_edges = 0

    def dfs(u: str):
        nonlocal back_edges
        visiting.add(u)
        for v in nodes[u].get("out") or []:
            if v not in nodes:
                continue
            if v in visiting:
                back_edges += 1
            elif v not in visited:
                dfs(v)
        visiting.remove(u)
        visited.add(u)

    for u in list(nodes.keys()):
        if u not in visited:
            dfs(u)
    return back_edges


def _health_score(*, nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]], issues: List[Dict[str, Any]], cycles_back_edges: int) -> Dict[str, Any]:
    """
    Heuristic score (0..100) for "architecture health".
    This is intentionally lightweight and explainable; it's a signal, not a formal SAST.
    """
    files = max(1, len(nodes))
    e = len(edges)
    issue_count = len(issues)
    degs = []
    max_deg = 0
    for n in nodes.values():
        d = int((len(n.get("out") or [])) + int(n.get("in") or 0))
        degs.append(d)
        max_deg = max(max_deg, d)
    avg_deg = (sum(degs) / len(degs)) if degs else 0.0
    issue_density = issue_count / files

    # Penalties (tuned for repo-scale; keep stable, monotonic)
    score = 100.0
    score -= min(40.0, cycles_back_edges * 1.5)
    score -= min(25.0, issue_density * 80.0)
    score -= min(20.0, max(0.0, avg_deg - 3.0) * 2.0)
    score -= min(15.0, max(0.0, (e / files) - 1.2) * 6.0)
    score = max(0.0, min(100.0, score))

    grade = "A"
    if score < 90:
        grade = "B"
    if score < 75:
        grade = "C"
    if score < 60:
        grade = "D"
    if score < 45:
        grade = "F"

    return {
        "score": round(score, 1),
        "grade": grade,
        "signals": {
            "files": files,
            "edges": e,
            "cycles_back_edges": cycles_back_edges,
            "issues": issue_count,
            "avg_degree": round(avg_deg, 2),
            "max_degree": int(max_deg),
            "issue_density": round(issue_density, 4),
        },
    }


def _is_aggregator_file(path: str) -> Tuple[bool, str]:
    """
    Heuristic: files that act as "wiring"/"barrel"/"router include" hubs.
    These tend to have extremely high degree and can distort health metrics.
    """
    p = str(path).replace("\\", "/")
    name = p.split("/")[-1]
    if name in {"server.py"}:
        return True, "server_entry"
    # Kernel runtime is a global registry / facade used across the codebase.
    if path.replace("\\", "/").endswith("core/harness/kernel/runtime.py"):
        return True, "kernel_runtime_registry"
    # Harness integration is a unified entry point (facade) that intentionally wires many pieces.
    if path.replace("\\", "/").endswith("core/harness/integration.py"):
        return True, "harness_integration_facade"
    if name in {"__init__.py"}:
        return True, "python_package_init"
    if name in {"index.ts", "index.tsx", "index.js", "index.jsx"}:
        return True, "frontend_barrel_index"
    if p.endswith("aiPlat-management/frontend/src/App.tsx") or p.endswith("aiPlat-management/frontend/src/main.tsx"):
        return True, "frontend_app_entry"
    if "/core/api/routers/" in p:
        return True, "api_router_module"
    if p.endswith("/api/rest/routes.py") or p.endswith("/api/rest/routes.ts"):
        return True, "routes_entry"
    if p.endswith("/gateway/router.py") or p.endswith("/gateway/router.ts"):
        return True, "gateway_router"
    return False, ""


def _effective_health(
    *,
    nodes: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, str]],
    issues: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute health metrics excluding aggregator files (wiring / routers / barrel exports).
    This gives a more actionable signal for architecture refactors.
    """
    excluded: Set[str] = set()
    for p in nodes.keys():
        ok, _ = _is_aggregator_file(p)
        if ok:
            excluded.add(p)
    if not excluded:
        cyc = _count_cycles(nodes)
        return _health_score(nodes=nodes, edges=edges, issues=issues, cycles_back_edges=cyc)

    filt_nodes = {k: v for k, v in nodes.items() if k not in excluded}
    filt_edges = [e for e in edges if (e.get("from") not in excluded) and (e.get("to") not in excluded)]
    filt_issues = [it for it in issues if str(it.get("file") or "") not in excluded]
    cyc = _count_cycles(filt_nodes) if filt_nodes else 0
    base = _health_score(nodes=filt_nodes or {"_": {"out": [], "in": 0}}, edges=filt_edges, issues=filt_issues, cycles_back_edges=cyc)
    base["excluded_aggregators"] = len(excluded)
    return base


def _aggregate_by_folder(
    *,
    nodes: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, str]],
    depth: int = 2,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """
    Reduce node count by folding file paths into folder buckets:
      depth=1 => "aiPlat-core"
      depth=2 => "aiPlat-core/core"
    """
    depth = max(1, min(6, int(depth)))

    def bucket(path: str) -> str:
        parts = [p for p in str(path).split("/") if p]
        return "/".join(parts[:depth]) if parts else str(path)

    agg: Dict[str, Dict[str, Any]] = {}
    for p, n in nodes.items():
        b = bucket(p)
        if b not in agg:
            agg[b] = {"id": b, "path": b, "kind": "folder", "file_count": 0, "issue_count": 0, "in": 0, "out_count": 0}
        agg[b]["file_count"] += 1
        agg[b]["issue_count"] += int(n.get("issue_count") or 0)

    # edges between buckets
    out_sets: Dict[str, Set[str]] = {k: set() for k in agg.keys()}
    in_counts: Dict[str, int] = {k: 0 for k in agg.keys()}
    edge_set: Set[Tuple[str, str]] = set()
    for e in edges:
        a = bucket(e.get("from") or "")
        b = bucket(e.get("to") or "")
        if not a or not b or a == b:
            continue
        if a not in agg or b not in agg:
            continue
        if (a, b) not in edge_set:
            edge_set.add((a, b))
            out_sets[a].add(b)
            in_counts[b] += 1

    out_edges = [{"from": a, "to": b} for (a, b) in sorted(edge_set)]
    for k, v in out_sets.items():
        agg[k]["out_count"] = len(v)
        agg[k]["in"] = int(in_counts.get(k) or 0)

    return list(agg.values()), out_edges


def _layer_bucket(path: str) -> str:
    """
    Productized "architecture layer" bucketing for this monorepo.
    Goal: stable, readable groups (not pure depth-based).
    """
    p = str(path).replace("\\", "/")

    # aiPlat-core layers
    if p.startswith("aiPlat-core/core/"):
        rest = p[len("aiPlat-core/core/") :]
        if rest.startswith("api/"):
            return "aiPlat-core:api"
        if rest.startswith("harness/"):
            return "aiPlat-core:harness"
        if rest.startswith("apps/"):
            return "aiPlat-core:apps"
        if rest.startswith("services/"):
            return "aiPlat-core:services"
        if rest.startswith("governance/"):
            return "aiPlat-core:governance"
        if rest.startswith("security/"):
            return "aiPlat-core:security"
        if rest.startswith("learning/"):
            return "aiPlat-core:learning"
        if rest.startswith("management/"):
            return "aiPlat-core:management"
        if rest.startswith("mcp/"):
            return "aiPlat-core:mcp"
        if rest.startswith("observability/"):
            return "aiPlat-core:observability"
        if rest.startswith("orchestration/"):
            return "aiPlat-core:orchestration"
        return "aiPlat-core:core-other"
    if p.startswith("aiPlat-core/agents/"):
        return "aiPlat-core:agents"
    if p.startswith("aiPlat-core/scripts/"):
        return "aiPlat-core:scripts"

    # Frontend layers (management frontend)
    if p.startswith("aiPlat-management/frontend/"):
        rest = p[len("aiPlat-management/frontend/") :]
        if rest.startswith("src/pages/"):
            return "frontend:pages"
        if rest.startswith("src/services/"):
            return "frontend:services"
        if rest.startswith("src/components/"):
            return "frontend:components"
        if rest.startswith("src/utils/"):
            return "frontend:utils"
        if rest.startswith("src/hooks/"):
            return "frontend:hooks"
        if rest.startswith("src/store/"):
            return "frontend:store"
        if rest.startswith("src/"):
            return "frontend:src-other"
        return "frontend:other"

    # Fallback
    if p.startswith("aiPlat-core/"):
        return "aiPlat-core:other"
    if p.startswith("aiPlat-management/"):
        return "aiPlat-management:other"
    return "other"


def _aggregate_by_layer(
    *,
    nodes: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, str]],
    bucket_fn=_layer_bucket,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Aggregate file graph into "architecture layers" based on repo-aware rules.
    - nodes: layers with file_count/issue_count
    - edges: unique directed edges between layers, with weight (# underlying edges)
    """
    agg: Dict[str, Dict[str, Any]] = {}
    file_to_layer: Dict[str, str] = {}

    for p, n in nodes.items():
        b = str(bucket_fn(p))
        file_to_layer[p] = b
        if b not in agg:
            agg[b] = {
                "id": b,
                "path": b,
                "kind": "layer",
                "file_count": 0,
                "issue_count": 0,
                "in": 0,
                "out_count": 0,
                "out": [],
            }
        agg[b]["file_count"] += 1
        agg[b]["issue_count"] += int(n.get("issue_count") or 0)

    # edge weights between layers
    weights: Dict[Tuple[str, str], int] = {}
    out_sets: Dict[str, Set[str]] = {k: set() for k in agg.keys()}
    in_counts: Dict[str, int] = {k: 0 for k in agg.keys()}

    for e in edges:
        src = str(e.get("from") or "")
        dst = str(e.get("to") or "")
        a = file_to_layer.get(src) or bucket_fn(src)
        b = file_to_layer.get(dst) or bucket_fn(dst)
        if not a or not b or a == b:
            continue
        if a not in agg or b not in agg:
            continue
        weights[(a, b)] = weights.get((a, b), 0) + 1
        out_sets[a].add(b)

    # finalize in/out counts
    for (a, b), w in weights.items():
        in_counts[b] = in_counts.get(b, 0) + 1
    for k, v in out_sets.items():
        agg[k]["out"] = sorted(v)
        agg[k]["out_count"] = len(v)
    for k in agg.keys():
        agg[k]["in"] = int(in_counts.get(k) or 0)

    out_edges = [{"from": a, "to": b, "weight": w} for (a, b), w in sorted(weights.items(), key=lambda x: (-x[1], x[0][0], x[0][1]))]
    return list(agg.values()), out_edges


def _top_insights(
    *,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, str]],
    max_items: int = 15,
    compute_blast_for_top: int = 10,
) -> Dict[str, Any]:
    """
    Product-ish insights for UI: top degree / top issues / top blast.
    Bounded-cost: blast is computed only for the top-N degree candidates.
    """
    deg: Dict[str, int] = {}
    out_map: Dict[str, List[str]] = {}
    node_by_id: Dict[str, Dict[str, Any]] = {}

    for n in nodes:
        pid = str(n.get("path") or n.get("id") or "")
        if not pid:
            continue
        node_by_id[pid] = n
        out = n.get("out") if isinstance(n.get("out"), list) else None
        out_count = len(out) if isinstance(out, list) else int(n.get("out_count") or 0)
        inn = int(n.get("in") or 0)
        deg[pid] = out_count + inn
        out_map[pid] = [str(x) for x in out] if isinstance(out, list) else []

    top_degree = sorted(
        [{"path": k, "degree": int(v), "issue_count": int((node_by_id.get(k) or {}).get("issue_count") or 0)} for k, v in deg.items()],
        key=lambda x: (x.get("degree", 0), x.get("issue_count", 0)),
        reverse=True,
    )[: max_items]

    top_issues = sorted(
        [
            {
                "path": str(n.get("path") or n.get("id") or ""),
                "issue_count": int(n.get("issue_count") or 0),
                "degree": int(deg.get(str(n.get("path") or n.get("id") or ""), 0)),
            }
            for n in nodes
            if str(n.get("path") or n.get("id") or "")
        ],
        key=lambda x: (x.get("issue_count", 0), x.get("degree", 0)),
        reverse=True,
    )[: max_items]

    # Blast for top candidates (best-effort; bounded)
    blast_rank: List[Dict[str, Any]] = []
    nodes_dict: Dict[str, Dict[str, Any]] = {k: {"out": out_map.get(k) or []} for k in out_map.keys()}
    for it in top_degree[: max(1, int(compute_blast_for_top))]:
        p = str(it.get("path") or "")
        if p and p in nodes_dict:
            blast_rank.append(
                {
                    "path": p,
                    "blast_count": len(_blast(nodes_dict, p)),
                    "degree": int(it.get("degree") or 0),
                    "issue_count": int(it.get("issue_count") or 0),
                }
            )
    blast_rank.sort(key=lambda x: (x.get("blast_count", 0), x.get("degree", 0)), reverse=True)
    blast_rank = blast_rank[: max_items]

    recs: List[str] = []
    if top_degree and int(top_degree[0].get("degree") or 0) >= 25:
        recs.append("存在高耦合节点：建议优先拆分/抽象边界（从 Top Degree 开始）")
    if top_issues and int(top_issues[0].get("issue_count") or 0) >= 3:
        recs.append("存在多风险文件：建议把硬编码密钥/危险用法纳入 CI 或在 Gate 中升级为阻断")
    if blast_rank and int(blast_rank[0].get("blast_count") or 0) >= 40:
        recs.append("存在大影响面节点：建议对相关变更强制走更严格的 GatePolicy（autosmoke+approval）")

    return {"top_degree": top_degree, "top_issues": top_issues, "top_blast": blast_rank, "recommendations": recs}


def _top_hubs(
    *,
    nodes: Dict[str, Dict[str, Any]],
    issues: List[Dict[str, Any]],
    limit: int = 20,
    compute_blast_for_top: int = 10,
) -> List[Dict[str, Any]]:
    issue_count_by_file: Dict[str, int] = {}
    for it in issues:
        f = str(it.get("file") or "")
        if f:
            issue_count_by_file[f] = issue_count_by_file.get(f, 0) + 1

    deg_list: List[Tuple[str, int, int, int]] = []  # (path, degree, in, out)
    for p, n in nodes.items():
        out = n.get("out") or []
        outc = len(out) if isinstance(out, list) else 0
        inc = int(n.get("in") or 0)
        deg_list.append((p, outc + inc, inc, outc))
    deg_list.sort(key=lambda x: x[1], reverse=True)

    # blast on a bounded subset (best-effort)
    blast_counts: Dict[str, int] = {}
    tiny_nodes = {k: {"out": (v.get("out") or [])} for k, v in nodes.items()}
    for p, _, _, _ in deg_list[: max(1, int(compute_blast_for_top))]:
        try:
            blast_counts[p] = len(_blast(tiny_nodes, p))
        except Exception:
            blast_counts[p] = 0

    out: List[Dict[str, Any]] = []
    for p, d, inc, outc in deg_list[: int(limit)]:
        is_ag, reason = _is_aggregator_file(p)
        out.append(
            {
                "path": p,
                "degree": int(d),
                "in": int(inc),
                "out": int(outc),
                "issue_count": int(issue_count_by_file.get(p) or int(nodes.get(p, {}).get("issue_count") or 0)),
                "blast_count": int(blast_counts.get(p) or 0),
                "is_aggregator": bool(is_ag),
                "aggregator_reason": reason or None,
            }
        )
    return out


def _tarjan_scc(graph: Dict[str, List[str]]) -> List[List[str]]:
    """
    Tarjan SCC algorithm.
    graph: node -> outgoing list
    """
    index = 0
    stack: List[str] = []
    on_stack: Set[str] = set()
    idx: Dict[str, int] = {}
    low: Dict[str, int] = {}
    out: List[List[str]] = []

    def strongconnect(v: str):
        nonlocal index
        idx[v] = index
        low[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)

        for w in graph.get(v, []) or []:
            if w not in idx:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], idx[w])

        if low[v] == idx[v]:
            comp: List[str] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                comp.append(w)
                if w == v:
                    break
            out.append(comp)

    for v in list(graph.keys()):
        if v not in idx:
            strongconnect(v)
    return out


def _top_cycles(
    *,
    nodes: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, str]],
    limit: int = 20,
) -> List[Dict[str, Any]]:
    graph: Dict[str, List[str]] = {k: list(v.get("out") or []) for k, v in nodes.items()}
    comps = _tarjan_scc(graph)
    # keep SCCs with size >= 2
    sccs = [c for c in comps if len(c) >= 2]
    # score by size + internal edges
    edge_set = {(str(e.get("from") or ""), str(e.get("to") or "")) for e in edges}
    scored: List[Tuple[int, int, List[str]]] = []
    for comp in sccs:
        s = set(comp)
        internal = 0
        for a in comp:
            for b in graph.get(a, []) or []:
                if b in s and (a, b) in edge_set:
                    internal += 1
        scored.append((len(comp), internal, sorted(comp)))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    out: List[Dict[str, Any]] = []
    for size, internal, comp in scored[: int(limit)]:
        out.append({"size": int(size), "internal_edges": int(internal), "nodes": comp[:200]})
    return out


def _health_by_root(*, roots: List[str], nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]], issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for r in roots:
        prefix = str(r).rstrip("/") + "/"
        sub_nodes = {k: v for k, v in nodes.items() if str(k).startswith(prefix) or str(k) == str(r)}
        if not sub_nodes:
            continue
        sub_edges = [e for e in edges if str(e.get("from") or "").startswith(prefix) and str(e.get("to") or "").startswith(prefix)]
        sub_issues = [it for it in issues if str(it.get("file") or "").startswith(prefix)]
        cyc = _count_cycles(sub_nodes)
        out[r] = _health_score(nodes=sub_nodes, edges=sub_edges, issues=sub_issues, cycles_back_edges=cyc)
    return out


def _blast(nodes: Dict[str, Dict[str, Any]], start: str) -> List[str]:
    # forward reachability
    if start not in nodes:
        return []
    q = [start]
    seen = {start}
    out: List[str] = []
    while q:
        u = q.pop(0)
        for v in nodes[u].get("out") or []:
            if v in nodes and v not in seen:
                seen.add(v)
                q.append(v)
                out.append(v)
    return out


async def _get_scan(rt, roots: List[str]) -> _ScanResult:
    global _CACHE
    roots_key = ",".join(roots)
    now = time.time()
    if _CACHE and _CACHE.roots_key == roots_key and (now - _CACHE.created_at) < _CACHE_TTL_SEC:
        return _CACHE

    repo_root = _repo_root()
    abs_roots = [(repo_root / r).resolve() for r in roots]
    nodes, edges, issues = _build_graph(repo_root, abs_roots)
    cycles = _count_cycles(nodes)
    health = _health_score(nodes=nodes, edges=edges, issues=issues, cycles_back_edges=cycles)
    stats = {
        "repo_root": str(repo_root),
        "roots": [str(r) for r in roots],
        "files": len(nodes),
        "edges": len(edges),
        "cycles_back_edges": cycles,
        "issues": len(issues),
    }
    _CACHE = _ScanResult(created_at=now, roots_key=roots_key, stats=stats, nodes=nodes, edges=edges, issues=issues, health=health)
    return _CACHE


@router.get("/diagnostics/code-intel/scan")
async def scan_code_intel(
    request: Request,
    roots: Optional[str] = None,
    mode: str = "file",
    depth: int = 2,
    limit: int = 0,
    rt=Depends(get_kernel_runtime),
):
    """
    Code intelligence scan (CodeFlow-inspired, server-side).
    Defaults to scanning: aiPlat-core + aiPlat-management/frontend
    """
    store = getattr(rt, "execution_store", None) if rt else None
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    root_list = [x.strip() for x in (roots.split(",") if roots else _default_roots()) if x.strip()]
    res = await _get_scan(rt, root_list)
    mode = str(mode or "file").strip().lower()
    if mode not in {"file", "folder", "layer"}:
        mode = "file"

    nodes_out: List[Dict[str, Any]]
    edges_out: List[Dict[str, str]]
    issues_out: List[Dict[str, Any]] = res.issues
    stats_out = dict(res.stats)

    if mode == "folder":
        nodes_out, edges_out = _aggregate_by_folder(nodes=res.nodes, edges=res.edges, depth=int(depth or 2))
        # in folder mode, issues list is still file-based; keep it but front-end may ignore
        stats_out["mode"] = "folder"
        stats_out["depth"] = int(depth or 2)
        stats_out["folders"] = len(nodes_out)
        stats_out["edges"] = len(edges_out)
    elif mode == "layer":
        nodes_out, edges_out = _aggregate_by_layer(nodes=res.nodes, edges=res.edges)
        stats_out["mode"] = "layer"
        stats_out["layers"] = len(nodes_out)
        stats_out["edges"] = len(edges_out)
    else:
        nodes_out = list(res.nodes.values())
        edges_out = res.edges
        stats_out["mode"] = "file"
        if int(limit or 0) > 0 and len(nodes_out) > int(limit):
            # keep most informative nodes: by (issue_count, degree)
            def _rank(n: Dict[str, Any]) -> Tuple[int, int]:
                return (int(n.get("issue_count") or 0), int((len(n.get("out") or [])) + int(n.get("in") or 0)))

            nodes_out.sort(key=_rank, reverse=True)
            keep_ids = set(str(n.get("id") or n.get("path") or "") for n in nodes_out[: int(limit)])
            nodes_out = [n for n in nodes_out if str(n.get("id") or n.get("path") or "") in keep_ids]
            edges_out = [e for e in edges_out if str(e.get("from") or "") in keep_ids and str(e.get("to") or "") in keep_ids]
            issues_out = [it for it in issues_out if str(it.get("file") or "") in keep_ids]
            stats_out["limited_to"] = int(limit)
            stats_out["files"] = len(nodes_out)
            stats_out["edges"] = len(edges_out)
            stats_out["issues"] = len(issues_out)

    health = dict(res.health)
    try:
        health["by_root"] = _health_by_root(roots=root_list, nodes=res.nodes, edges=res.edges, issues=res.issues)
    except Exception:
        health["by_root"] = {}
    # effective metrics (excluding aggregator/wiring files)
    try:
        health["effective"] = _effective_health(nodes=res.nodes, edges=res.edges, issues=res.issues)
    except Exception:
        health["effective"] = None
    insights = _top_insights(nodes=nodes_out, edges=edges_out, max_items=15, compute_blast_for_top=10)
    governance = {
        "top_hubs": _top_hubs(nodes=res.nodes, issues=res.issues, limit=20, compute_blast_for_top=10),
        "top_cycles": _top_cycles(nodes=res.nodes, edges=res.edges, limit=20),
    }

    return {
        "status": "ok",
        "stats": stats_out,
        "health": health,
        "insights": insights,
        "governance": governance,
        "nodes": nodes_out,
        "edges": edges_out,
        "issues": issues_out,
    }


@router.get("/diagnostics/code-intel/hubs")
async def code_intel_hubs(roots: Optional[str] = None, limit: int = 30, rt=Depends(get_kernel_runtime)):
    root_list = [x.strip() for x in (roots.split(",") if roots else _default_roots()) if x.strip()]
    res = await _get_scan(rt, root_list)
    return {"status": "ok", "roots": root_list, "hubs": _top_hubs(nodes=res.nodes, issues=res.issues, limit=int(limit or 30), compute_blast_for_top=15)}


@router.get("/diagnostics/code-intel/cycles")
async def code_intel_cycles(roots: Optional[str] = None, limit: int = 30, rt=Depends(get_kernel_runtime)):
    root_list = [x.strip() for x in (roots.split(",") if roots else _default_roots()) if x.strip()]
    res = await _get_scan(rt, root_list)
    return {"status": "ok", "roots": root_list, "cycles": _top_cycles(nodes=res.nodes, edges=res.edges, limit=int(limit or 30))}


@router.get("/diagnostics/code-intel/blast")
async def blast_radius(
    file: str,
    roots: Optional[str] = None,
    rt=Depends(get_kernel_runtime),
):
    root_list = [x.strip() for x in (roots.split(",") if roots else _default_roots()) if x.strip()]
    res = await _get_scan(rt, root_list)
    start = str(file).strip()
    out = _blast(res.nodes, start)
    return {"status": "ok", "file": start, "affected": out, "count": len(out)}
