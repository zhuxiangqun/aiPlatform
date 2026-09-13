"""F-T1: materialize factory seeds (teams YAML + factory_sanitize) from team/.

Prefer pulled ``~/.aiplat/team/{teams,factory_sanitize}/`` at read time; optional
apply copies into ``~/.aiplat/{teams,factory_sanitize}/`` with hash-backed rollback.
Never touches ``local/``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

_SEED_TEAMS = (
    Path(__file__).resolve().parents[1] / "workspace_seeds" / "teams"
)
_SEED_SANITIZE = (
    Path(__file__).resolve().parents[1] / "workspace_seeds" / "factory_sanitize"
)


def aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()


def team_resource_dir(name: str) -> Path:
    from core.harness.team_harness import resource_relpath, team_dir

    return team_dir() / resource_relpath(name)


def runtime_teams_dir() -> Path:
    return aiplat_home() / "teams"


def runtime_sanitize_dir() -> Path:
    return aiplat_home() / "factory_sanitize"


def seed_backups_dir() -> Path:
    return aiplat_home() / "team_seed_backups"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _tree_manifest(root: Path) -> Dict[str, str]:
    """relpath → sha256 for all files under root."""
    out: Dict[str, str] = {}
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        try:
            rel = str(p.relative_to(root)).replace("\\", "/")
            out[rel] = _file_sha256(p)
        except OSError:
            continue
    return out


def manifest_hash(manifest: Mapping[str, str]) -> str:
    payload = json.dumps(dict(sorted(manifest.items())), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def resolve_team_yaml_candidates(name: str) -> List[str]:
    """Search order: team/teams → ~/.aiplat/teams → workspace_seeds/teams."""
    n = (name or "").strip().removesuffix(".yaml")
    if not n:
        return []
    return [
        str(team_resource_dir("teams") / f"{n}.yaml"),
        str(runtime_teams_dir() / f"{n}.yaml"),
        str(_SEED_TEAMS / f"{n}.yaml"),
    ]


def resolve_factory_sanitize_dirs() -> List[Path]:
    """Prefer team/ then runtime materialize then kernel seeds."""
    return [
        team_resource_dir("factory_sanitize"),
        runtime_sanitize_dir(),
        _SEED_SANITIZE,
    ]


def resolve_factory_sanitize_file(filename: str) -> Optional[Path]:
    for root in resolve_factory_sanitize_dirs():
        path = root / filename
        if path.is_file():
            return path
    return None


def _copy_tree_files(src: Path, dst: Path) -> List[str]:
    """Copy files from src → dst (overwrite). Returns relative paths copied."""
    copied: List[str] = []
    if not src.is_dir():
        return copied
    dst.mkdir(parents=True, exist_ok=True)
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        copied.append(str(rel).replace("\\", "/"))
    return copied


def apply_team_factory_seeds(
    *,
    resources: Optional[Sequence[str]] = None,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """Copy team/{teams,factory_sanitize} → ~/.aiplat/{teams,factory_sanitize}.

    Takes a pre-apply backup (hash-addressable) for rollback. No-op when team/
    has no matching resources.
    """
    wanted = list(resources or ("teams", "factory_sanitize"))
    ensure = seed_backups_dir()
    ensure.mkdir(parents=True, exist_ok=True)

    before: Dict[str, Dict[str, str]] = {}
    targets: Dict[str, Path] = {
        "teams": runtime_teams_dir(),
        "factory_sanitize": runtime_sanitize_dir(),
    }
    sources: Dict[str, Path] = {
        "teams": team_resource_dir("teams"),
        "factory_sanitize": team_resource_dir("factory_sanitize"),
    }

    applied: Dict[str, Any] = {}
    any_source = False
    for key in wanted:
        src = sources.get(key)
        if src is None or not src.is_dir():
            applied[key] = {"skipped": True, "reason": "no_team_source"}
            continue
        files = [p for p in src.rglob("*") if p.is_file()]
        if not files:
            applied[key] = {"skipped": True, "reason": "empty_team_source"}
            continue
        any_source = True
        dst = targets[key]
        before[key] = _tree_manifest(dst)

    if not any_source:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_team_factory_seeds",
            "applied": applied,
        }

    stamp = time.strftime("%Y%m%dT%H%M%S")
    backup_root = ensure / f"{stamp}_{os.getpid()}"
    backup_root.mkdir(parents=True, exist_ok=True)
    for key, manifest in before.items():
        dst = targets[key]
        bak = backup_root / key
        if dst.is_dir():
            shutil.copytree(dst, bak)
        else:
            bak.mkdir(parents=True, exist_ok=True)
        (backup_root / f"{key}.manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    for key in wanted:
        src = sources.get(key)
        if src is None or not src.is_dir():
            continue
        dst = targets[key]
        if not overwrite and dst.is_dir() and any(dst.iterdir()):
            applied[key] = {"skipped": True, "reason": "runtime_exists"}
            continue
        copied = _copy_tree_files(src, dst)
        after = _tree_manifest(dst)
        applied[key] = {
            "copied": copied,
            "count": len(copied),
            "hash": manifest_hash(after),
            "prev_hash": manifest_hash(before.get(key) or {}),
        }

    meta = {
        "backup": str(backup_root),
        "created_at": time.time(),
        "applied": {k: v.get("hash") for k, v in applied.items() if "hash" in v},
        "prev": {k: v.get("prev_hash") for k, v in applied.items() if "prev_hash" in v},
    }
    (backup_root / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # Pointer for easy rollback
    pointer = seed_backups_dir() / "latest.json"
    pointer.write_text(
        json.dumps(
            {"backup": str(backup_root), "hash": meta.get("applied"), "at": meta["created_at"]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "ok": True,
        "skipped": False,
        "backup": str(backup_root),
        "hash": meta.get("applied"),
        "applied": applied,
    }


def rollback_team_factory_seeds(backup: str = "") -> Dict[str, Any]:
    """Restore ~/.aiplat/{teams,factory_sanitize} from an F-T1 backup dir."""
    root: Optional[Path] = None
    if backup:
        root = Path(backup)
    else:
        pointer = seed_backups_dir() / "latest.json"
        if pointer.is_file():
            try:
                data = json.loads(pointer.read_text(encoding="utf-8"))
                root = Path(str(data.get("backup") or ""))
            except Exception:
                root = None
    if root is None or not root.is_dir():
        return {"ok": False, "error": "backup_missing"}

    restored: Dict[str, str] = {}
    for key in ("teams", "factory_sanitize"):
        bak = root / key
        if not bak.is_dir():
            continue
        dst = runtime_teams_dir() if key == "teams" else runtime_sanitize_dir()
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(bak, dst)
        restored[key] = str(dst)

    if not restored:
        return {"ok": False, "error": "backup_empty", "backup": str(root)}
    return {"ok": True, "restored": restored, "backup": str(root)}
