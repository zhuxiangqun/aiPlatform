"""Post-merge / weekly repo health scan — catch boiling-frog bloat.

Merge gates only see diffs. This module snapshots full-tree metrics
(LOC, multi-base classes, import fan-out, declared deps) into JSONL and
trends them on the duty board. Never invents green without a snapshot.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".tox",
        "coverage",
        "htmlcov",
        ".cursor",
        "tmp",
    }
)

_DEFAULT_ROOTS = (
    "aiPlat-core/core",
    "aiPlat-platform",
    "aiPlat-infra/infra",
    "aiPlat-management/frontend/src",
    "scripts",
)

_DEP_FILE_NAMES = frozenset(
    {
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
        "package.json",
        "Pipfile",
    }
)

_DEFAULT_THRESHOLDS: Dict[str, float] = {
    "repo_health_min_snapshots": 1.0,
    "repo_health_god_loc": 800.0,
    "repo_health_god_files_watch": 15.0,
    "repo_health_god_files_block": 40.0,
    "repo_health_multi_base_watch": 40.0,
    "repo_health_multi_base_block": 120.0,
    "repo_health_high_fanout_imports": 25.0,
    "repo_health_high_fanout_watch": 30.0,
    "repo_health_high_fanout_block": 80.0,
    "repo_health_dep_entries_watch": 180.0,
    "repo_health_dep_entries_block": 320.0,
    "repo_health_loc_growth_pct_watch": 8.0,  # vs previous snapshot
    "repo_health_loc_growth_pct_block": 20.0,
    "repo_health_dep_delta_watch": 8.0,
    "repo_health_dep_delta_block": 25.0,
    "repo_health_max_files": 8000.0,
}


def repo_health_dir() -> Path:
    """JSONL home — env AIPLAT_REPO_HEALTH_DIR overrides AIPLAT_HOME/org/repo_health."""
    env = (os.getenv("AIPLAT_REPO_HEALTH_DIR") or "").strip()
    if env:
        return Path(env).expanduser()
    home = Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))
    return home / "org" / "repo_health"


def repo_health_jsonl_path() -> Path:
    return repo_health_dir() / "snapshots.jsonl"


def _persist_enabled() -> bool:
    flag = (os.getenv("AIPLAT_REPO_HEALTH_PERSIST") or "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def workspace_root(explicit: Optional[str] = None) -> Path:
    env = (explicit or os.getenv("AIPLAT_WORKSPACE_ROOT") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    # Prefer repo root when this file lives under aiPlat-core/
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "aiPlat-core").is_dir() and (p / "AIPLAT_CAPABILITIES.md").is_file():
            return p
    return Path.cwd().resolve()


def default_scan_roots(root: Optional[Path] = None) -> List[Path]:
    base = root or workspace_root()
    out: List[Path] = []
    for rel in _DEFAULT_ROOTS:
        p = (base / rel).resolve()
        if p.is_dir():
            out.append(p)
    if not out and base.is_dir():
        out.append(base)
    return out


def _count_loc(text: str) -> int:
    n = 0
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        n += 1
    return n


def _import_count(tree: ast.AST) -> int:
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            n += 1
    return n


def _multi_base_classes(tree: ast.AST, allowed: Optional[set] = None) -> Tuple[int, int]:
    """Return (class_count, multi_nontrivial_base_count)."""
    allow = allowed or {"object", "Exception", "BaseException", "ABC", "Protocol", "BaseModel"}
    classes = 0
    multi = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        classes += 1
        nontrivial: List[str] = []
        for b in node.bases:
            name = ""
            if isinstance(b, ast.Name):
                name = b.id
            elif isinstance(b, ast.Attribute):
                name = b.attr
            if name and name not in allow:
                nontrivial.append(name)
        if len(nontrivial) > 1:
            multi += 1
    return classes, multi


def _parse_dep_entries(path: Path) -> int:
    name = path.name
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    if name.endswith(".txt") or name == "Pipfile":
        return sum(
            1
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("[")
        )
    if name == "package.json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return 0
        n = 0
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            block = data.get(key)
            if isinstance(block, dict):
                n += len(block)
        return n
    if name == "pyproject.toml":
        # Cheap line scan — avoid toml dependency
        n = 0
        in_deps = False
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("[") and "dependencies" in s.lower():
                in_deps = True
                continue
            if s.startswith("["):
                in_deps = False
                continue
            if in_deps and "=" in s and not s.startswith("#"):
                n += 1
        return n
    return 0


def _iter_py_files(roots: Sequence[Path], *, max_files: int) -> Iterable[Path]:
    seen = 0
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES and not d.startswith(".")]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                yield Path(dirpath) / fn
                seen += 1
                if seen >= max_files:
                    return


def _iter_dep_files(roots: Sequence[Path], workspace: Path) -> Iterable[Path]:
    candidates: List[Path] = []
    # Prefer workspace-level manifests once
    for name in _DEP_FILE_NAMES:
        p = workspace / name
        if p.is_file():
            candidates.append(p)
    for sub in ("aiPlat-core", "aiPlat-platform", "aiPlat-infra", "aiPlat-management/frontend"):
        base = workspace / sub
        if not base.is_dir():
            continue
        for name in _DEP_FILE_NAMES:
            p = base / name
            if p.is_file():
                candidates.append(p)
    # Dedup
    seen: set = set()
    for p in candidates:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        yield p


def scan_repo_health(
    *,
    roots: Optional[Sequence[Path]] = None,
    workspace: Optional[Path] = None,
    max_files: Optional[int] = None,
    god_loc: Optional[int] = None,
    high_fanout_imports: Optional[int] = None,
) -> Dict[str, Any]:
    """Full-tree metrics snapshot (deterministic; no LLM)."""
    ws = workspace or workspace_root()
    scan_roots = list(roots) if roots is not None else default_scan_roots(ws)
    mf = int(max_files if max_files is not None else _DEFAULT_THRESHOLDS["repo_health_max_files"])
    g_loc = int(god_loc if god_loc is not None else _DEFAULT_THRESHOLDS["repo_health_god_loc"])
    fan_thr = int(
        high_fanout_imports
        if high_fanout_imports is not None
        else _DEFAULT_THRESHOLDS["repo_health_high_fanout_imports"]
    )

    py_files = 0
    py_loc = 0
    classes = 0
    multi_base = 0
    god_files = 0
    high_fanout = 0
    import_sum = 0
    parse_errors = 0
    god_samples: List[str] = []
    fanout_samples: List[str] = []

    for path in _iter_py_files(scan_roots, max_files=mf):
        py_files += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            parse_errors += 1
            continue
        loc = _count_loc(text)
        py_loc += loc
        if loc >= g_loc:
            god_files += 1
            if len(god_samples) < 8:
                try:
                    rel = str(path.relative_to(ws))
                except ValueError:
                    rel = str(path)
                god_samples.append(f"{rel}:{loc}")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            parse_errors += 1
            continue
        c, m = _multi_base_classes(tree)
        classes += c
        multi_base += m
        imports = _import_count(tree)
        import_sum += imports
        if imports >= fan_thr:
            high_fanout += 1
            if len(fanout_samples) < 8:
                try:
                    rel = str(path.relative_to(ws))
                except ValueError:
                    rel = str(path)
                fanout_samples.append(f"{rel}:{imports}")

    dep_entries = 0
    dep_files: List[str] = []
    for dp in _iter_dep_files(scan_roots, ws):
        n = _parse_dep_entries(dp)
        if n <= 0:
            continue
        dep_entries += n
        try:
            dep_files.append(str(dp.relative_to(ws)))
        except ValueError:
            dep_files.append(str(dp))

    avg_imports = round(import_sum / py_files, 2) if py_files else 0.0
    return {
        "kind": "snapshot",
        "written_at": _now_iso(),
        "ts": time.time(),
        "workspace": str(ws),
        "roots": [str(r) for r in scan_roots],
        "py_files": py_files,
        "py_loc": py_loc,
        "classes": classes,
        "multi_base_classes": multi_base,
        "god_files": god_files,
        "god_loc_threshold": g_loc,
        "high_fanout_files": high_fanout,
        "high_fanout_imports": fan_thr,
        "avg_imports_per_file": avg_imports,
        "dep_entries": dep_entries,
        "dep_files": dep_files[:12],
        "parse_errors": parse_errors,
        "god_samples": god_samples,
        "fanout_samples": fanout_samples,
        "truncated": py_files >= mf,
    }


def append_health_snapshot(metrics: Mapping[str, Any]) -> Optional[str]:
    """Append one snapshot. Returns path or None on skip/failure."""
    if not _persist_enabled():
        return None
    row = {k: v for k, v in dict(metrics).items() if v is not None}
    row["kind"] = "snapshot"
    row.setdefault("written_at", _now_iso())
    row.setdefault("ts", time.time())
    try:
        out_dir = repo_health_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        path = repo_health_jsonl_path()
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return str(path)
    except Exception as e:
        logger.debug("repo_health append failed: %s", e, exc_info=True)
        return None


def list_health_snapshots(*, limit: int = 50) -> List[Dict[str, Any]]:
    path = repo_health_jsonl_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except OSError as e:
        logger.debug("repo_health read failed: %s", e)
        return []
    if limit > 0 and len(rows) > limit:
        return rows[-limit:]
    return rows


def load_repo_health_thresholds_from_duty(
    duty_thr: Optional[Mapping[str, float]] = None,
) -> Dict[str, float]:
    out = dict(_DEFAULT_THRESHOLDS)
    if isinstance(duty_thr, Mapping):
        for k in out:
            if k in duty_thr and duty_thr[k] is not None:
                try:
                    out[k] = float(duty_thr[k])
                except (TypeError, ValueError):
                    continue
    return out


def _pct_growth(prev: float, cur: float) -> Optional[float]:
    if prev <= 0:
        return None if cur <= 0 else 100.0
    return round(100.0 * (cur - prev) / prev, 2)


def assess_repo_health(
    *,
    snapshots: Optional[Sequence[Mapping[str, Any]]] = None,
    thresholds: Optional[Mapping[str, float]] = None,
    run_scan: bool = False,
    persist: bool = False,
) -> Dict[str, Any]:
    """Fold snapshots → absolute + delta severity (go|watch|block|unavailable)."""
    thr = load_repo_health_thresholds_from_duty(thresholds)
    rows = list(snapshots) if snapshots is not None else list_health_snapshots(limit=50)
    latest: Optional[Dict[str, Any]] = None
    if run_scan:
        latest = scan_repo_health(
            max_files=int(thr["repo_health_max_files"]),
            god_loc=int(thr["repo_health_god_loc"]),
            high_fanout_imports=int(thr["repo_health_high_fanout_imports"]),
        )
        if persist:
            append_health_snapshot(latest)
        rows = list(rows) + [latest]
    elif rows:
        latest = dict(rows[-1])

    min_snap = int(thr["repo_health_min_snapshots"])
    if not latest or len(rows) < min_snap:
        return {
            "status": "unavailable",
            "severity": "unavailable",
            "n_snapshots": len(rows),
            "min_snapshots": min_snap,
            "latest": latest,
            "previous": None,
            "deltas": {},
            "reasons": [
                f"repo_health_insufficient_snapshots={len(rows)}<{min_snap} — "
                "run scripts/scan_repo_health.py; never invent green"
            ],
            "thresholds": {
                k: thr[k]
                for k in thr
                if k.startswith("repo_health_")
            },
            "jsonl": str(repo_health_jsonl_path()),
        }

    prev = dict(rows[-2]) if len(rows) >= 2 else None
    god = int(latest.get("god_files") or 0)
    multi = int(latest.get("multi_base_classes") or 0)
    fan = int(latest.get("high_fanout_files") or 0)
    deps = int(latest.get("dep_entries") or 0)
    loc = int(latest.get("py_loc") or 0)

    deltas: Dict[str, Any] = {}
    if prev:
        prev_loc = int(prev.get("py_loc") or 0)
        prev_deps = int(prev.get("dep_entries") or 0)
        deltas = {
            "loc_growth_pct": _pct_growth(float(prev_loc), float(loc)),
            "dep_delta": deps - prev_deps,
            "god_delta": god - int(prev.get("god_files") or 0),
            "multi_base_delta": multi - int(prev.get("multi_base_classes") or 0),
            "high_fanout_delta": fan - int(prev.get("high_fanout_files") or 0),
            "prev_written_at": prev.get("written_at"),
        }

    reasons: List[str] = []
    severity = "go"
    status = "ok"

    def _bump(level: str, msg: str) -> None:
        nonlocal severity, status
        reasons.append(msg)
        if level == "block":
            severity = "block"
            status = "ok"
        elif level == "watch" and severity != "block":
            severity = "watch"

    if god >= thr["repo_health_god_files_block"]:
        _bump("block", f"repo_health_god_files={god}>={int(thr['repo_health_god_files_block'])}")
    elif god >= thr["repo_health_god_files_watch"]:
        _bump("watch", f"repo_health_god_files={god}>={int(thr['repo_health_god_files_watch'])}")

    if multi >= thr["repo_health_multi_base_block"]:
        _bump("block", f"repo_health_multi_base={multi}>={int(thr['repo_health_multi_base_block'])}")
    elif multi >= thr["repo_health_multi_base_watch"]:
        _bump("watch", f"repo_health_multi_base={multi}>={int(thr['repo_health_multi_base_watch'])}")

    if fan >= thr["repo_health_high_fanout_block"]:
        _bump("block", f"repo_health_high_fanout={fan}>={int(thr['repo_health_high_fanout_block'])}")
    elif fan >= thr["repo_health_high_fanout_watch"]:
        _bump("watch", f"repo_health_high_fanout={fan}>={int(thr['repo_health_high_fanout_watch'])}")

    if deps >= thr["repo_health_dep_entries_block"]:
        _bump("block", f"repo_health_dep_entries={deps}>={int(thr['repo_health_dep_entries_block'])}")
    elif deps >= thr["repo_health_dep_entries_watch"]:
        _bump("watch", f"repo_health_dep_entries={deps}>={int(thr['repo_health_dep_entries_watch'])}")

    loc_pct = deltas.get("loc_growth_pct")
    if isinstance(loc_pct, (int, float)):
        if loc_pct >= thr["repo_health_loc_growth_pct_block"]:
            _bump(
                "block",
                f"repo_health_loc_growth_pct={loc_pct}>={thr['repo_health_loc_growth_pct_block']}",
            )
        elif loc_pct >= thr["repo_health_loc_growth_pct_watch"]:
            _bump(
                "watch",
                f"repo_health_loc_growth_pct={loc_pct}>={thr['repo_health_loc_growth_pct_watch']}",
            )

    dep_delta = deltas.get("dep_delta")
    if isinstance(dep_delta, (int, float)):
        if dep_delta >= thr["repo_health_dep_delta_block"]:
            _bump(
                "block",
                f"repo_health_dep_delta={dep_delta}>={int(thr['repo_health_dep_delta_block'])}",
            )
        elif dep_delta >= thr["repo_health_dep_delta_watch"]:
            _bump(
                "watch",
                f"repo_health_dep_delta={dep_delta}>={int(thr['repo_health_dep_delta_watch'])}",
            )

    if not reasons:
        reasons.append(
            f"repo_health within band (loc={loc} god={god} multi_base={multi} "
            f"fanout={fan} deps={deps})"
        )

    return {
        "status": status,
        "severity": severity,
        "n_snapshots": len(rows),
        "min_snapshots": min_snap,
        "latest": {
            "written_at": latest.get("written_at"),
            "py_files": latest.get("py_files"),
            "py_loc": loc,
            "classes": latest.get("classes"),
            "multi_base_classes": multi,
            "god_files": god,
            "high_fanout_files": fan,
            "dep_entries": deps,
            "avg_imports_per_file": latest.get("avg_imports_per_file"),
            "god_samples": list(latest.get("god_samples") or [])[:6],
            "fanout_samples": list(latest.get("fanout_samples") or [])[:6],
            "truncated": bool(latest.get("truncated")),
        },
        "previous": (
            {
                "written_at": prev.get("written_at"),
                "py_loc": prev.get("py_loc"),
                "dep_entries": prev.get("dep_entries"),
                "god_files": prev.get("god_files"),
            }
            if prev
            else None
        ),
        "deltas": deltas,
        "reasons": reasons,
        "thresholds": {
            k: thr[k]
            for k in (
                "repo_health_god_files_watch",
                "repo_health_god_files_block",
                "repo_health_multi_base_watch",
                "repo_health_multi_base_block",
                "repo_health_high_fanout_watch",
                "repo_health_high_fanout_block",
                "repo_health_dep_entries_watch",
                "repo_health_dep_entries_block",
                "repo_health_loc_growth_pct_watch",
                "repo_health_loc_growth_pct_block",
                "repo_health_dep_delta_watch",
                "repo_health_dep_delta_block",
            )
        },
        "jsonl": str(repo_health_jsonl_path()),
    }
