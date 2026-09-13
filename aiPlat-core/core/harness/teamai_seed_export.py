"""T6': export TeamAI-compatible seed repo layout (never writes IDE dirs).

Output under ``~/.aiplat/exports/teamai-seed/`` (or custom dest).
Forbidden targets: ``.cursor``, ``.claude``, ``.codex``, IDE adapter dirs.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_FORBIDDEN_DIR_NAMES = frozenset(
    {
        ".cursor",
        ".claude",
        ".codex",
        ".codebuddy",
        "claude",
        "cursor",
    }
)

_EXPORT_RESOURCES = (
    "skills",
    "rules",
    "hooks",
    "mcp",
    "env",
    "learnings",
    "teams",
    "factory_sanitize",
    "culture.md",
)


def aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()


def default_export_dir() -> Path:
    return aiplat_home() / "exports" / "teamai-seed"


def _assert_safe_dest(dest: Path) -> Optional[str]:
    """Return error string if dest would write into IDE adapter paths."""
    resolved = dest.expanduser().resolve()
    parts = {p.lower() for p in resolved.parts}
    for bad in _FORBIDDEN_DIR_NAMES:
        if bad.lower() in parts:
            return f"refuse_ide_path:{bad}"
    # Also refuse if dest itself is named like an IDE folder
    if resolved.name.lower() in _FORBIDDEN_DIR_NAMES:
        return f"refuse_ide_path:{resolved.name}"
    return None


def export_teamai_seed(
    dest: str = "",
    *,
    include_learnings: bool = False,
    include_sources: bool = True,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """Materialize a TeamAI-shaped seed tree from ``~/.aiplat/team/`` (+ optional seeds).

    Does **not** write ``.cursor`` / ``.claude``. TeamAI CLI can consume this repo.
    """
    from core.harness.team_harness import (
        load_team_harness_schema,
        resource_relpath,
        team_dir,
    )

    target = Path(dest).expanduser() if dest else default_export_dir()
    err = _assert_safe_dest(target)
    if err:
        return {"ok": False, "error": err, "hint": "T6' never writes IDE directories; pick exports/"}

    schema = load_team_harness_schema()
    src_root = team_dir(schema)
    seed_culture = (
        Path(__file__).resolve().parents[1]
        / "workspace_seeds"
        / "team_harness"
        / "culture.md"
    )

    if target.exists() and overwrite:
        # Only clear if under exports/ or empty-ish — never home root
        if target == aiplat_home() or target == Path.home():
            return {"ok": False, "error": "refuse_home_root"}
        for child in list(target.iterdir()):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
    target.mkdir(parents=True, exist_ok=True)

    copied: List[str] = []
    for res in _EXPORT_RESOURCES:
        if res == "learnings" and not include_learnings:
            continue
        rel = resource_relpath(res.replace(".md", "") if res.endswith(".md") else res, schema)
        if res == "culture.md":
            rel = "culture.md"
        src = src_root / rel
        if not src.exists() and res == "culture.md" and seed_culture.is_file():
            src = seed_culture
        if not src.exists():
            continue
        dst = target / (Path(rel).name if res == "culture.md" else rel)
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            for f in dst.rglob("*"):
                if f.is_file():
                    copied.append(str(f.relative_to(target)).replace("\\", "/"))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(str(dst.relative_to(target)).replace("\\", "/"))

    if include_sources:
        sources = src_root / resource_relpath("sources", schema)
        if sources.is_dir():
            dst = target / "sources"
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(sources, dst)
            for f in dst.rglob("*"):
                if f.is_file():
                    copied.append(str(f.relative_to(target)).replace("\\", "/"))

    manifest = {
        "format": "teamai-seed",
        "schema_version": str(schema.get("schema_version") or "1"),
        "exported_at": time.time(),
        "source": str(src_root),
        "file_count": len(copied),
        "include_learnings": bool(include_learnings),
        "note": "Compatible seed for TeamAI CLI / Git publish. aiPlat never writes .cursor/.claude.",
    }
    (target / ".teamai-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    readme = (
        "# TeamAI-compatible seed (aiPlat T6')\n\n"
        "Generated from `~/.aiplat/team/`.\n\n"
        "- **Do not** place this under `.cursor` / `.claude` — use TeamAI CLI to distribute.\n"
        "- Publish via Git MR; aiPlat pull consumes the reviewed tree.\n"
    )
    (target / "README.md").write_text(readme, encoding="utf-8")
    copied.append("README.md")
    copied.append(".teamai-manifest.json")

    return {
        "ok": True,
        "dest": str(target),
        "copied": sorted(set(copied)),
        "count": len(set(copied)),
        "manifest": manifest,
        "ide_write": False,
    }
