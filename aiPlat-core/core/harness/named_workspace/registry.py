"""Named workspace registry — atomic write, fail-closed load."""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.utils.paths import get_aiplat_home

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
_DEFAULT_ENTRY: Dict[str, Any] = {
    "id": "default",
    "label": "Default",
    "kind": "local",
    "root": "",  # empty → legacy AIPLAT_HOME/agents + eval_results
    "allowed_tenants": ["*"],
}


def registry_path() -> Path:
    return Path(get_aiplat_home()) / "workspaces" / "registry.yaml"


def _lock_path() -> Path:
    return registry_path().with_suffix(".yaml.lock")


def validate_workspace_id(workspace_id: str) -> str:
    wid = (workspace_id or "").strip()
    if not wid or not _ID_RE.match(wid):
        raise ValueError(f"invalid workspace_id: {workspace_id!r}")
    if wid in {".", ".."} or "/" in wid or "\\" in wid:
        raise ValueError(f"invalid workspace_id: {workspace_id!r}")
    return wid


def _default_registry_doc() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "workspaces": [dict(_DEFAULT_ENTRY)],
    }


def ensure_registry() -> Dict[str, Any]:
    """Create default-only registry if missing; return loaded doc."""
    path = registry_path()
    if not path.exists():
        _atomic_write_yaml(path, _default_registry_doc())
    return load_registry()


def load_registry() -> Dict[str, Any]:
    """Load registry; fail closed on unsupported/corrupt schema."""
    path = registry_path()
    if not path.exists():
        return ensure_registry()
    try:
        import yaml  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"yaml unavailable for workspace registry: {e}") from e
    try:
        raw = path.read_text(encoding="utf-8")
        doc = yaml.safe_load(raw) or {}
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"workspace registry corrupt: {e}") from e
    if not isinstance(doc, dict):
        raise RuntimeError("workspace registry corrupt: not a mapping")
    ver = int(doc.get("schema_version") or 0)
    if ver != SCHEMA_VERSION:
        raise RuntimeError(f"workspace registry unsupported schema_version={ver}")
    items = doc.get("workspaces")
    if not isinstance(items, list) or not items:
        raise RuntimeError("workspace registry corrupt: empty workspaces")
    # Ensure default exists
    ids = {str(x.get("id") or "") for x in items if isinstance(x, dict)}
    if "default" not in ids:
        raise RuntimeError("workspace registry corrupt: missing default")
    return doc


def list_registry_entries() -> List[Dict[str, Any]]:
    doc = load_registry()
    out: List[Dict[str, Any]] = []
    for row in doc.get("workspaces") or []:
        if not isinstance(row, dict):
            continue
        wid = str(row.get("id") or "").strip()
        if not wid:
            continue
        routes = row.get("allowed_routes")
        if not isinstance(routes, list):
            routes = []
        out.append(
            {
                "id": wid,
                "label": str(row.get("label") or wid),
                "kind": str(row.get("kind") or "local"),
                "root": str(row.get("root") or ""),
                "allowed_tenants": list(row.get("allowed_tenants") or ["*"]),
                "base_url": str(row.get("base_url") or "") or None,
                "auth_secret_env": str(row.get("auth_secret_env") or "") or None,
                "allowed_routes": [str(x) for x in routes if str(x).strip()],
            }
        )
    return out


def get_registry_entry(workspace_id: str) -> Optional[Dict[str, Any]]:
    wid = validate_workspace_id(workspace_id)
    for row in list_registry_entries():
        if row["id"] == wid:
            return row
    return None


def _append_registry_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    doc = load_registry()
    workspaces = list(doc.get("workspaces") or [])
    workspaces.append(entry)
    doc["workspaces"] = workspaces
    _atomic_write_yaml(registry_path(), doc)
    return entry


def create_local_workspace(
    workspace_id: str,
    *,
    label: str = "",
    allowed_tenants: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Idempotent create of a local empty workspace entry + dirs."""
    wid = validate_workspace_id(workspace_id)
    if wid == "default":
        ensure_registry()
        return get_registry_entry("default") or dict(_DEFAULT_ENTRY)

    ensure_registry()
    existing = get_registry_entry(wid)
    if existing:
        if str(existing.get("kind") or "local") != "local":
            raise ValueError(f"workspace {wid} exists with kind={existing.get('kind')}")
        _ensure_local_dirs(wid)
        return existing

    entry = {
        "id": wid,
        "label": (label or wid).strip() or wid,
        "kind": "local",
        "root": f"workspaces/{wid}",
        "allowed_tenants": list(allowed_tenants) if allowed_tenants else ["*"],
    }
    _append_registry_entry(entry)
    _ensure_local_dirs(wid)
    return entry


def create_remote_workspace(
    workspace_id: str,
    *,
    label: str = "",
    base_url: str = "",
    auth_secret_env: str = "",
    allowed_routes: Optional[List[str]] = None,
    allowed_tenants: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Idempotent create of a remote Core profile (no local disk partition)."""
    from core.harness.named_workspace.remote_proxy import normalize_remote_base_url

    wid = validate_workspace_id(workspace_id)
    if wid == "default":
        raise ValueError("default workspace cannot be remote")
    base = normalize_remote_base_url(base_url)

    ensure_registry()
    existing = get_registry_entry(wid)
    if existing:
        if str(existing.get("kind") or "") != "remote":
            raise ValueError(f"workspace {wid} exists with kind={existing.get('kind')}")
        # Idempotent: same id remote — refresh display fields if provided
        return existing

    entry = {
        "id": wid,
        "label": (label or wid).strip() or wid,
        "kind": "remote",
        "root": "",
        "base_url": base,
        "auth_secret_env": (auth_secret_env or "").strip(),
        "allowed_routes": list(allowed_routes or []),
        "allowed_tenants": list(allowed_tenants) if allowed_tenants else ["*"],
    }
    return _append_registry_entry(entry)


def _ensure_local_dirs(workspace_id: str) -> None:
    home = Path(get_aiplat_home())
    if workspace_id == "default":
        agents = home / "agents"
        evals = home / "eval_results"
    else:
        root = home / "workspaces" / workspace_id
        agents = root / "agents"
        evals = root / "eval_results"
    for d in (agents, evals):
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            logger.debug("chmod workspace dir failed path=%s", d, exc_info=True)


def _atomic_write_yaml(path: Path, doc: Dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"yaml unavailable: {e}") from e

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass  # noqa: cleanup-best-effort

    lock = _lock_path()
    lock_fd = None
    try:
        lock_fd = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            import fcntl  # type: ignore

            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        except Exception:
            logger.debug("fcntl flock unavailable; proceeding without", exc_info=True)

        data = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".registry.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, str(path))
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass  # noqa: cleanup-best-effort
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass  # noqa: cleanup-best-effort
    finally:
        if lock_fd is not None:
            try:
                import fcntl  # type: ignore

                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except Exception:
                pass  # noqa: optional-dependency
            try:
                os.close(lock_fd)
            except OSError:
                pass  # noqa: cleanup-best-effort
