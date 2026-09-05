"""Load declarative PRD gate packs from YAML (domain rules outside harness code).

Merge order (later wins):
  1. Package builtins ``prd_gate_packs/`` — kernel-only (``_common.yaml``)
  2. ``workspace_seeds/prd_gates/`` — vertical domain seeds (e.g. media)
  3. ``~/.aiplat/prd_gates`` or ``$AIPLAT_PRD_GATES_DIR`` — user overrides

Vertical packs MUST NOT live under ``prd_gate_packs/`` (kernel-agnostic).
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PACK_CACHE: Optional[List[Dict[str, Any]]] = None


def _builtin_packs_dir() -> Path:
    return Path(__file__).resolve().parent / "prd_gate_packs"


def _workspace_seed_packs_dir() -> Path:
    # core/harness/execution → core/workspace_seeds/prd_gates
    return Path(__file__).resolve().parents[2] / "workspace_seeds" / "prd_gates"


def _user_packs_dir() -> Path:
    override = os.getenv("AIPLAT_PRD_GATES_DIR", "").strip()
    if override:
        return Path(os.path.expanduser(override))
    return Path(os.path.expanduser("~/.aiplat/prd_gates"))


def materialize_prd_gate_seeds(*, overwrite: bool = False) -> Path:
    """Copy kernel ``_common`` + vertical seeds to ~/.aiplat/prd_gates when missing.

    Does not overwrite by default so local edits are preserved. Kernel ``_common``
    ships under ``prd_gate_packs/``; domain packs (media, …) live in
    ``workspace_seeds/prd_gates/``. Stale user ``_common.yaml`` still wins on load.
    """
    dst = _user_packs_dir()
    dst.mkdir(parents=True, exist_ok=True)
    seen: set = set()
    for src in (_builtin_packs_dir(), _workspace_seed_packs_dir()):
        if not src.is_dir():
            continue
        key = src.resolve()
        if key in seen:
            continue
        seen.add(key)
        for path in src.glob("*.yaml"):
            target = dst / path.name
            if target.exists() and not overwrite:
                continue
            try:
                shutil.copy2(path, target)
            except OSError as e:
                logger.debug("prd gate seed copy failed: %s", e)
    return dst


def _load_yaml_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        import yaml  # type: ignore
    except ImportError:
        logger.warning("PyYAML not available; cannot load PRD gate pack %s", path)
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("failed to load PRD gate pack %s: %s", path, e)
        return None
    if not isinstance(data, dict):
        return None
    data.setdefault("domain_id", path.stem)
    data.setdefault("always", False)
    data.setdefault("triggers", [])
    data.setdefault("checks", [])
    data.setdefault("repairs", [])
    return data


def _load_dir(directory: Path, *, prefer: Dict[str, Dict[str, Any]]) -> None:
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.yaml")):
        pack = _load_yaml_file(path)
        if not pack:
            continue
        did = str(pack.get("domain_id") or path.stem)
        # Later dirs override earlier (user overrides builtin)
        prefer[did] = pack


def load_prd_gate_packs(*, force_reload: bool = False) -> List[Dict[str, Any]]:
    """Return all gate packs (common + domains). Cached until force_reload.

    Merge order (later wins):
      1. Package builtins — kernel-only ``_common``
      2. Workspace seeds — vertical domains (media, …)
      3. ~/.aiplat/prd_gates or AIPLAT_PRD_GATES_DIR — user overrides
    """
    global _PACK_CACHE
    if _PACK_CACHE is not None and not force_reload:
        return _PACK_CACHE

    by_id: Dict[str, Dict[str, Any]] = {}
    _load_dir(_builtin_packs_dir(), prefer=by_id)
    seed = _workspace_seed_packs_dir()
    if seed.resolve() != _builtin_packs_dir().resolve():
        _load_dir(seed, prefer=by_id)
    try:
        materialize_prd_gate_seeds(overwrite=False)
    except Exception:
        logger.debug("prd gate seed materialize skipped", exc_info=True)
    _load_dir(_user_packs_dir(), prefer=by_id)

    packs = list(by_id.values())
    # stable: _common first, then others by domain_id
    packs.sort(key=lambda p: (0 if p.get("domain_id") == "_common" else 1, str(p.get("domain_id"))))
    _PACK_CACHE = packs
    return packs


def clear_prd_gate_pack_cache() -> None:
    global _PACK_CACHE
    _PACK_CACHE = None
