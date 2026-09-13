"""T3b: multi-source team harness subscription (namespaced merge).

Secondary sources live under ``~/.aiplat/team/sources/{namespace}/``.
Locked primary resources (skills/rules/…) are never overwritten by a source merge.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

_SEED_SOURCES = (
    Path(__file__).resolve().parents[1]
    / "workspace_seeds"
    / "team_harness"
    / "sources.yaml"
)


def aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.debug("sources yaml load failed: %s", path, exc_info=True)
        return {}


def load_sources_config() -> Dict[str, Any]:
    """team/sources.yaml → home override → seed."""
    for path in (
        aiplat_home() / "team" / "sources.yaml",
        aiplat_home() / "sources.yaml",
        _SEED_SOURCES,
    ):
        data = _read_yaml(path)
        if data:
            return data
    return {"schema_version": "1", "sources": []}


def sources_root() -> Path:
    from core.harness.team_harness import resource_relpath, team_dir

    return team_dir() / resource_relpath("sources")


def list_source_namespaces() -> List[str]:
    root = sources_root()
    if not root.is_dir():
        return []
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")
    )


def _safe_ns(name: str) -> str:
    raw = str(name or "").strip().lower()
    out = "".join(c if c.isalnum() or c in "-_" else "-" for c in raw).strip("-_")
    return out or "source"


def merge_source_tree(
    src: Path,
    *,
    namespace: str,
    resources: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Copy secondary source into team/sources/{ns}/ — never into locked primary paths.

    Locked primary bodies under team/{skills,rules,…} are untouched.
    """
    from core.harness.team_harness import is_resource_locked, load_team_harness_schema, resource_relpath

    ns = _safe_ns(namespace)
    if not src.is_dir():
        return {"ok": False, "error": f"source_missing:{src}"}

    schema = load_team_harness_schema()
    wanted = list(resources) if resources else None
    dest_root = sources_root() / ns
    dest_root.mkdir(parents=True, exist_ok=True)

    copied: List[str] = []
    skipped_locked: List[str] = []

    # Walk top-level resource dirs/files from src
    for child in sorted(src.iterdir()):
        if child.name.startswith(".") or child.name == "sources.yaml":
            continue
        # Map child name to resource key when possible
        res_key = child.name
        if child.name.endswith(".md"):
            res_key = child.stem  # culture.md → culture
        if wanted is not None and res_key not in wanted and child.name not in (wanted or []):
            # also allow path match
            if child.name not in [resource_relpath(r, schema) for r in (wanted or [])]:
                continue

        # Never write into primary locked locations — only under sources/{ns}/
        if is_resource_locked(res_key, schema):
            # Still allow namespaced copy (secondary), not primary overwrite
            pass

        target = dest_root / child.name
        if child.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(child, target)
            for f in target.rglob("*"):
                if f.is_file():
                    copied.append(str(f.relative_to(dest_root)).replace("\\", "/"))
        else:
            shutil.copy2(child, target)
            copied.append(child.name)

    meta = {
        "namespace": ns,
        "merged_at": time.time(),
        "source": str(src),
        "copied": len(copied),
    }
    (dest_root / ".source_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "ok": True,
        "namespace": ns,
        "dest": str(dest_root),
        "copied": copied,
        "skipped_locked_primary": skipped_locked,
        "primary_untouched": True,
    }


def configure_sources(sources: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Persist sources list to ~/.aiplat/sources.yaml (and team/ copy when present)."""
    payload = {
        "schema_version": "1",
        "sources": [dict(s) for s in sources],
        "updated_at": time.time(),
    }
    home = aiplat_home()
    home.mkdir(parents=True, exist_ok=True)
    path = home / "sources.yaml"
    try:
        import yaml  # type: ignore

        path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    except Exception:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "path": str(path), "count": len(payload["sources"])}


def apply_configured_sources(*, dry_run: bool = False) -> Dict[str, Any]:
    """Materialize each configured local path source under team/sources/{ns}/."""
    cfg = load_sources_config()
    rows = cfg.get("sources") if isinstance(cfg.get("sources"), list) else []
    results: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        ns = str(row.get("id") or row.get("namespace") or "").strip()
        path = str(row.get("path") or "").strip()
        if not ns or not path:
            results.append({"ok": False, "error": "missing_id_or_path", "row": dict(row)})
            continue
        src = Path(path).expanduser()
        if not src.is_absolute():
            src = aiplat_home() / path
        if dry_run:
            results.append(
                {
                    "ok": True,
                    "dry_run": True,
                    "namespace": _safe_ns(ns),
                    "would_merge": str(src),
                    "exists": src.is_dir(),
                }
            )
            continue
        results.append(merge_source_tree(src, namespace=ns))
    return {
        "ok": all(r.get("ok") for r in results) if results else True,
        "skipped": not results,
        "results": results,
    }


def namespaced_skill_candidates(skill_name: str) -> List[str]:
    """Resolve skill name across primary + sources/{ns}/skills/{name}.

    Returns filesystem candidates (paths as strings). Does not overwrite primary.
    """
    from core.harness.team_harness import resource_relpath, team_dir

    name = str(skill_name or "").strip()
    if not name:
        return []
    # Explicit ns/name
    if "/" in name:
        ns, _, rest = name.partition("/")
        p = sources_root() / _safe_ns(ns) / "skills" / rest
        return [str(p)] if rest else []

    out: List[str] = []
    primary = team_dir() / resource_relpath("skills") / name
    out.append(str(primary))
    for ns in list_source_namespaces():
        out.append(str(sources_root() / ns / "skills" / name))
    return out
