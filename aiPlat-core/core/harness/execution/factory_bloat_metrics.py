"""F5a: generation bloat metrics — LOC / new_deps / new_files (no abstraction_count).

Domain-agnostic: counts from ``## FILE:`` blocks in pipeline artifacts.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

_FILE_SPLIT = re.compile(r"^#{2,4}\s*FILE:\s*", re.MULTILINE)
_IMPORT_LINE = re.compile(
    r"^\s*(?:from\s+\S+\s+import\s+|import\s+|require\s*\(|from\s+['\"]|import\s+['\"])"
)
_REQ_LINE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(?:[=<>!~]=|[=~<>]|$)")
_PYPROJECT_DEP = re.compile(
    r'^\s*["\']([A-Za-z0-9_.\-]+)(?:\[.*?\])?["\']\s*,?\s*$'
)

STATE_BLOAT_KEY = "_bloat_metrics"
BASELINE_PROJECT_KEY = "bloat_baseline"


def extract_file_blocks(raw: str) -> List[Dict[str, str]]:
    """Parse ``## FILE: path`` blocks → [{path, content}, ...]."""
    text = str(raw or "")
    if not text.strip():
        return []
    parts = _FILE_SPLIT.split(text)
    out: List[Dict[str, str]] = []
    for block in parts[1:]:
        lines = block.split("\n", 1)
        if not lines:
            continue
        path = lines[0].strip().split()[0] if lines[0].strip() else ""
        body = lines[1] if len(lines) > 1 else ""
        body = re.sub(r"^```\w*\n?", "", body)
        body = re.sub(r"\n?```\s*$", "", body)
        if path:
            out.append({"path": path, "content": body})
    return out


def _count_loc(content: str) -> Tuple[int, int]:
    """Return (all_nonblank, nonblank_excluding_pure_imports)."""
    total = 0
    non_import = 0
    for line in str(content or "").splitlines():
        if not line.strip():
            continue
        total += 1
        if not _IMPORT_LINE.match(line):
            non_import += 1
    return total, non_import


def _deps_from_requirements(content: str) -> List[str]:
    deps: List[str] = []
    for line in str(content or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("-"):
            continue
        m = _REQ_LINE.match(s)
        if m:
            name = m.group(1).strip()
            if name and name.lower() not in ("python", "python_version"):
                deps.append(name.lower())
    return deps


def _deps_from_package_json(content: str) -> List[str]:
    try:
        data = json.loads(content)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    names: List[str] = []
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        block = data.get(key)
        if isinstance(block, dict):
            names.extend(str(k).lower() for k in block.keys())
    return names


def _deps_from_pyproject(content: str) -> List[str]:
    deps: List[str] = []
    in_deps = False
    for line in str(content or "").splitlines():
        if re.match(r"^\s*\[project\.optional-dependencies", line) or re.match(
            r"^\s*\[tool\.poetry\.group", line
        ):
            in_deps = True
            continue
        if re.match(r"^\s*dependencies\s*=\s*\[", line):
            in_deps = True
            continue
        if re.match(r"^\s*\[", line):
            in_deps = False
            continue
        if not in_deps:
            continue
        m = _PYPROJECT_DEP.match(line.strip().rstrip(","))
        if m:
            deps.append(m.group(1).lower())
        elif line.strip() == "]":
            in_deps = False
    for m in re.finditer(
        r'^\s*([A-Za-z0-9_.\-]+)\s*=\s*["\']', content, re.MULTILINE
    ):
        name = m.group(1).lower()
        if name not in ("python", "name", "version", "description"):
            deps.append(name)
    return deps


def deps_declared_in_file(path: str, content: str) -> List[str]:
    p = str(path or "").replace("\\", "/").lower()
    base = p.rsplit("/", 1)[-1]
    if base in ("requirements.txt", "requirements-dev.txt", "requirements.in"):
        return _deps_from_requirements(content)
    if base == "package.json":
        return _deps_from_package_json(content)
    if base in ("pyproject.toml", "pipfile"):
        return _deps_from_pyproject(content)
    return []


def compute_bloat_from_files(files: Sequence[Mapping[str, str]]) -> Dict[str, Any]:
    """Aggregate LOC / new_files / new_deps from file dicts."""
    loc = 0
    loc_code = 0
    deps: List[str] = []
    paths: List[str] = []
    for f in files:
        if not isinstance(f, Mapping):
            continue
        path = str(f.get("path") or "").strip()
        content = str(f.get("content") or "")
        if not path:
            continue
        paths.append(path)
        t, ni = _count_loc(content)
        loc += t
        loc_code += ni
        for d in deps_declared_in_file(path, content):
            if d not in deps:
                deps.append(d)
    return {
        "loc": loc,
        "loc_non_import": loc_code,
        "new_files": len(paths),
        "new_deps": len(deps),
        "files": paths[:200],
        "deps": deps[:100],
    }


def collect_files_from_artifact(artifact: Any) -> List[Dict[str, str]]:
    if artifact is None:
        return []
    if isinstance(artifact, str):
        return extract_file_blocks(artifact)
    if not isinstance(artifact, Mapping):
        return []
    raw = artifact.get("raw_output")
    if isinstance(raw, str) and "## FILE:" in raw:
        return extract_file_blocks(raw)
    files = artifact.get("files")
    if isinstance(files, list):
        out: List[Dict[str, str]] = []
        for item in files:
            if isinstance(item, Mapping) and item.get("path"):
                out.append(
                    {
                        "path": str(item.get("path")),
                        "content": str(item.get("content") or item.get("body") or ""),
                    }
                )
            elif isinstance(item, str):
                out.append({"path": item, "content": ""})
        return out
    return []


def compute_bloat_from_state(
    state: Mapping[str, Any],
    *,
    artifact_keys: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Scan pipeline state artifacts for ## FILE blocks and aggregate metrics."""
    keys: List[str] = []
    if artifact_keys:
        keys.extend(str(k) for k in artifact_keys if k)
    else:
        for preferred in ("code", "agent_app", "frontend_pages", "frontend", "generated_code"):
            if preferred in state:
                keys.append(preferred)
        for k, v in state.items():
            if str(k).startswith("_"):
                continue
            if k in keys:
                continue
            if isinstance(v, Mapping):
                raw = v.get("raw_output")
                if isinstance(raw, str) and "## FILE:" in raw:
                    keys.append(str(k))
            elif isinstance(v, str) and "## FILE:" in v:
                keys.append(str(k))

    seen_paths: set[str] = set()
    merged: List[Dict[str, str]] = []
    sources: List[str] = []
    for key in keys:
        files = collect_files_from_artifact(state.get(key))
        if not files:
            continue
        sources.append(key)
        for f in files:
            p = f["path"]
            if p in seen_paths:
                continue
            seen_paths.add(p)
            merged.append(f)

    metrics = compute_bloat_from_files(merged)
    metrics["sources"] = sources
    metrics["schema_version"] = "f5a.1"
    return metrics


def compare_bloat(
    current: Optional[Mapping[str, Any]],
    baseline: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Delta vs previous build baseline (missing baseline → empty delta)."""
    cur = current if isinstance(current, Mapping) else {}
    base = baseline if isinstance(baseline, Mapping) else {}
    if not base:
        return {"has_baseline": False}
    out: Dict[str, Any] = {"has_baseline": True}
    for key in ("loc", "loc_non_import", "new_files", "new_deps"):
        c = int(cur.get(key) or 0)
        b = int(base.get(key) or 0)
        out[f"delta_{key}"] = c - b
        out[key] = c
        out[f"baseline_{key}"] = b
    return out


def write_bloat_metrics(
    state: MutableMapping[str, Any],
    *,
    baseline: Optional[Mapping[str, Any]] = None,
    artifact_keys: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Compute, attach to state[_bloat_metrics], optionally compare baseline."""
    metrics = compute_bloat_from_state(state, artifact_keys=artifact_keys)
    if baseline:
        metrics["vs_baseline"] = compare_bloat(metrics, baseline)
    state[STATE_BLOAT_KEY] = metrics
    return metrics
