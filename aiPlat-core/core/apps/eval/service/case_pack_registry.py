"""Minimal Eval Case Pack registry: scope + ACL + atomic write (P0 nail 5).

global = builtin/platform (read-mostly under AIPLAT_HOME/eval_packs/global)
workspace = private under AIPLAT_HOME/workspaces/{id}/eval_packs
Cross-scope / cross-workspace references are rejected.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.case_pack_legacy import assert_claim_eligible_allowed
from core.utils.paths import get_aiplat_home

_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()

VALID_SCOPES = frozenset({"global", "workspace", "tenant"})


class PackRegistryError(ValueError):
    """Pack registry / ACL / atomic-write failure."""


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        if key not in _LOCKS:
            _LOCKS[key] = threading.Lock()
        return _LOCKS[key]


def _scope_root(scope: str, *, workspace_id: str = "", tenant_id: str = "") -> Path:
    home = Path(get_aiplat_home())
    sc = str(scope or "").strip().lower()
    if sc not in VALID_SCOPES:
        raise PackRegistryError(f"invalid scope={scope!r}")
    if sc == "global":
        return home / "eval_packs" / "global"
    if sc == "workspace":
        wid = str(workspace_id or "").strip()
        if not wid:
            raise PackRegistryError("workspace scope requires workspace_id")
        return home / "workspaces" / wid / "eval_packs"
    tid = str(tenant_id or "").strip()
    if not tid:
        raise PackRegistryError("tenant scope requires tenant_id")
    return home / "tenants" / tid / "eval_packs"


def assert_pack_acl(
    *,
    scope: str,
    workspace_id: str = "",
    tenant_id: str = "",
    caller_workspace_id: str = "",
    caller_tenant_id: str = "",
    write: bool = False,
) -> None:
    """Fail closed on cross-scope / cross-workspace / cross-tenant access."""
    sc = str(scope or "").strip().lower()
    if sc not in VALID_SCOPES:
        raise PackRegistryError(f"invalid scope={scope!r}")
    if sc == "global":
        if write:
            # Platform publish role not modeled yet — refuse writes in P0.
            raise PackRegistryError("global packs are read-only in P0")
        return
    if sc == "workspace":
        wid = str(workspace_id or "").strip()
        caller = str(caller_workspace_id or "").strip()
        if not wid or not caller or wid != caller:
            raise PackRegistryError(
                f"workspace ACL deny: pack workspace={wid!r} caller={caller!r}"
            )
        return
    tid = str(tenant_id or "").strip()
    caller_t = str(caller_tenant_id or "").strip()
    if not tid or not caller_t or tid != caller_t:
        raise PackRegistryError(
            f"tenant ACL deny: pack tenant={tid!r} caller={caller_t!r}"
        )


def _registry_path(root: Path) -> Path:
    return root / "registry.json"


def _pack_payload_path(
    *,
    scope: str,
    pack_id: str,
    version: str,
    workspace_id: str = "",
    tenant_id: str = "",
) -> Path:
    root = _scope_root(scope, workspace_id=workspace_id, tenant_id=tenant_id)
    safe_pid = str(pack_id).strip().replace("/", "_")
    safe_ver = str(version).strip().replace("/", "_")
    return root / "packs" / safe_pid / safe_ver / "pack.json"


def write_pack_payload(
    *,
    pack_id: str,
    version: str,
    scope: str,
    cases: Sequence[Mapping[str, Any]],
    meta: Mapping[str, Any],
    workspace_id: str = "",
    tenant_id: str = "",
    caller_workspace_id: str = "",
    caller_tenant_id: str = "",
    allow_overwrite_frozen: bool = False,
) -> Path:
    """Persist cases+meta for a pack version (needed so freeze can rehash kind)."""
    assert_pack_acl(
        scope=scope,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
        caller_tenant_id=caller_tenant_id or tenant_id,
        write=True,
    )
    path = _pack_payload_path(
        scope=scope,
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
    )
    if path.is_file() and not allow_overwrite_frozen:
        existing_kind = ""
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            existing_kind = str((existing.get("meta") or {}).get("kind") or "").lower()
        except (OSError, json.JSONDecodeError):
            existing_kind = ""  # unreadable ≠ frozen; allow rewrite
        if existing_kind == "frozen":
            raise PackRegistryError(
                f"refuse overwrite frozen pack payload {pack_id}@{version}"
            )
    payload = {
        "schema": "eval.pack_payload.v1",
        "pack_id": str(pack_id).strip(),
        "version": str(version).strip(),
        "scope": scope,
        "cases": [dict(c) for c in cases],
        "meta": dict(meta),
    }
    _atomic_write_json(path, payload)
    return path


def load_pack_payload(
    *,
    pack_id: str,
    version: str,
    scope: str,
    workspace_id: str = "",
    tenant_id: str = "",
    caller_workspace_id: str = "",
    caller_tenant_id: str = "",
) -> Dict[str, Any]:
    assert_pack_acl(
        scope=scope,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
        caller_tenant_id=caller_tenant_id or tenant_id,
        write=False,
    )
    path = _pack_payload_path(
        scope=scope,
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
    )
    if not path.is_file():
        raise PackRegistryError(f"pack payload missing: {pack_id}@{version}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise PackRegistryError(f"pack payload corrupt: {e}") from e
    if not isinstance(raw, dict):
        raise PackRegistryError("pack payload root must be object")
    return raw


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".registry.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:  # noqa: cleanup-best-effort
                pass


def load_registry(
    *,
    scope: str,
    workspace_id: str = "",
    tenant_id: str = "",
) -> Dict[str, Any]:
    root = _scope_root(scope, workspace_id=workspace_id, tenant_id=tenant_id)
    path = _registry_path(root)
    if not path.is_file():
        return {"schema": "eval.pack_registry.v1", "scope": scope, "packs": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise PackRegistryError(f"registry corrupt: {e}") from e
    if not isinstance(raw, dict):
        raise PackRegistryError("registry root must be object")
    packs = raw.get("packs")
    if packs is None:
        raw["packs"] = {}
    elif not isinstance(packs, dict):
        raise PackRegistryError("registry.packs must be object")
    raw.setdefault("schema", "eval.pack_registry.v1")
    raw["scope"] = scope
    return raw


def register_pack_version(
    *,
    pack_id: str,
    version: str,
    kind: str,
    claim_eligible: bool,
    scope: str,
    pack_hash: str,
    object_types: Optional[List[str]] = None,
    workspace_id: str = "",
    tenant_id: str = "",
    caller_workspace_id: str = "",
    caller_tenant_id: str = "",
    status: str = "active",
) -> Dict[str, Any]:
    """Atomically register ``(pack_id, version)``. Duplicate → fail (no clobber)."""
    assert_claim_eligible_allowed(kind=kind, claim_eligible=claim_eligible)
    assert_pack_acl(
        scope=scope,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
        caller_tenant_id=caller_tenant_id or tenant_id,
        write=True,
    )
    pid = str(pack_id or "").strip()
    ver = str(version or "").strip()
    if not pid or not ver:
        raise PackRegistryError("pack_id and version required")
    ph = str(pack_hash or "").strip()
    if not ph.startswith("sha256:"):
        raise PackRegistryError("pack_hash must be sha256:…")

    root = _scope_root(scope, workspace_id=workspace_id, tenant_id=tenant_id)
    path = _registry_path(root)
    lock = _lock_for(path)
    with lock:
        reg = load_registry(
            scope=scope, workspace_id=workspace_id, tenant_id=tenant_id
        )
        packs = reg.setdefault("packs", {})
        entry = packs.get(pid)
        if not isinstance(entry, dict):
            entry = {"versions": {}}
            packs[pid] = entry
        versions = entry.setdefault("versions", {})
        if ver in versions:
            raise PackRegistryError(
                f"pack {pid}@{ver} already registered — refuse overwrite"
            )
        versions[ver] = {
            "kind": str(kind),
            "claim_eligible": bool(claim_eligible),
            "hash": ph,
            "object_types": sorted(str(x) for x in (object_types or [])),
            "status": str(status or "active"),
            "scope": scope,
            "workspace_id": workspace_id or None,
            "tenant_id": tenant_id or None,
        }
        entry["latest"] = ver
        _atomic_write_json(path, reg)
        return dict(versions[ver])


def get_pack_version(
    *,
    pack_id: str,
    version: str,
    scope: str,
    workspace_id: str = "",
    tenant_id: str = "",
    caller_workspace_id: str = "",
    caller_tenant_id: str = "",
) -> Dict[str, Any]:
    assert_pack_acl(
        scope=scope,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
        caller_tenant_id=caller_tenant_id or tenant_id,
        write=False,
    )
    reg = load_registry(scope=scope, workspace_id=workspace_id, tenant_id=tenant_id)
    packs = reg.get("packs") or {}
    entry = packs.get(str(pack_id or "").strip())
    if not isinstance(entry, dict):
        raise PackRegistryError(f"pack not found: {pack_id}")
    ver = (entry.get("versions") or {}).get(str(version or "").strip())
    if not isinstance(ver, dict):
        raise PackRegistryError(f"pack version not found: {pack_id}@{version}")
    return dict(ver)


def update_pack_version_meta(
    *,
    pack_id: str,
    version: str,
    scope: str,
    workspace_id: str = "",
    tenant_id: str = "",
    caller_workspace_id: str = "",
    caller_tenant_id: str = "",
    status: Optional[str] = None,
    review: Optional[Mapping[str, Any]] = None,
    allow_claim_eligible: bool = False,
) -> Dict[str, Any]:
    """Update status/review metadata only. Never flips claim_eligible unless explicit.

    Refuse kind→frozen and refuse setting claim_eligible=true here (P1.1).
    """
    if allow_claim_eligible:
        raise PackRegistryError(
            "update_pack_version_meta refuses claim_eligible flips — freeze path later"
        )
    assert_pack_acl(
        scope=scope,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
        caller_tenant_id=caller_tenant_id or tenant_id,
        write=True,
    )
    pid = str(pack_id or "").strip()
    ver = str(version or "").strip()
    if not pid or not ver:
        raise PackRegistryError("pack_id and version required")

    root = _scope_root(scope, workspace_id=workspace_id, tenant_id=tenant_id)
    path = _registry_path(root)
    lock = _lock_for(path)
    with lock:
        reg = load_registry(
            scope=scope, workspace_id=workspace_id, tenant_id=tenant_id
        )
        packs = reg.setdefault("packs", {})
        entry = packs.get(pid)
        if not isinstance(entry, dict):
            raise PackRegistryError(f"pack not found: {pid}")
        versions = entry.setdefault("versions", {})
        cur = versions.get(ver)
        if not isinstance(cur, dict):
            raise PackRegistryError(f"pack version not found: {pid}@{ver}")
        if str(cur.get("kind") or "").lower() == "frozen" and status not in (
            None,
            str(cur.get("status") or ""),
        ):
            # allow no-op status; refuse mutating frozen packs in P1.1
            if status is not None and str(status) != str(cur.get("status") or ""):
                raise PackRegistryError("cannot mutate frozen pack status in P1.1")
        updated = dict(cur)
        if status is not None:
            st = str(status).strip().lower()
            if st == "frozen":
                raise PackRegistryError(
                    "status=frozen is not a registry status — use freeze path later"
                )
            updated["status"] = st
        if review is not None:
            if not isinstance(review, Mapping):
                raise PackRegistryError("review must be object")
            prev = dict(updated.get("review") or {}) if isinstance(updated.get("review"), dict) else {}
            prev.update({k: review[k] for k in review})
            updated["review"] = prev
        # honesty lock
        updated["claim_eligible"] = False
        versions[ver] = updated
        _atomic_write_json(path, reg)
        return dict(updated)


def freeze_pack_version(
    *,
    pack_id: str,
    version: str,
    scope: str,
    pack_hash: str,
    workspace_id: str = "",
    tenant_id: str = "",
    caller_workspace_id: str = "",
    caller_tenant_id: str = "",
    frozen_by: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    """Mark reviewed pack as kind=frozen. claim_eligible stays false (P1.2)."""
    from datetime import datetime, timezone

    assert_claim_eligible_allowed(kind="frozen", claim_eligible=False)
    assert_pack_acl(
        scope=scope,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
        caller_tenant_id=caller_tenant_id or tenant_id,
        write=True,
    )
    pid = str(pack_id or "").strip()
    ver = str(version or "").strip()
    ph = str(pack_hash or "").strip()
    if not pid or not ver:
        raise PackRegistryError("pack_id and version required")
    if not ph.startswith("sha256:"):
        raise PackRegistryError("pack_hash must be sha256:…")

    root = _scope_root(scope, workspace_id=workspace_id, tenant_id=tenant_id)
    path = _registry_path(root)
    lock = _lock_for(path)
    with lock:
        reg = load_registry(
            scope=scope, workspace_id=workspace_id, tenant_id=tenant_id
        )
        packs = reg.setdefault("packs", {})
        entry = packs.get(pid)
        if not isinstance(entry, dict):
            raise PackRegistryError(f"pack not found: {pid}")
        versions = entry.setdefault("versions", {})
        cur = versions.get(ver)
        if not isinstance(cur, dict):
            raise PackRegistryError(f"pack version not found: {pid}@{ver}")
        st = str(cur.get("status") or "").lower()
        kind = str(cur.get("kind") or "").lower()
        if kind == "frozen":
            # idempotent: require same hash
            if str(cur.get("hash") or "") != ph:
                raise PackRegistryError(
                    "already frozen with different hash — refuse clobber"
                )
            return dict(cur)
        if st != "reviewed":
            raise PackRegistryError(
                f"freeze requires status=reviewed, got {st!r}"
            )
        if kind in ("generated", "trace", "exploratory"):
            raise PackRegistryError(
                f"kind={kind!r} cannot freeze into L1 claim candidate path"
            )
        updated = dict(cur)
        updated["kind"] = "frozen"
        updated["status"] = "active"
        updated["claim_eligible"] = False
        updated["hash"] = ph
        review = dict(updated.get("review") or {}) if isinstance(updated.get("review"), dict) else {}
        review.update(
            {
                "status": "frozen",
                "frozen_at": datetime.now(timezone.utc).isoformat(),
                "frozen_by": str(frozen_by or ""),
                "notes": str(notes or review.get("notes") or ""),
            }
        )
        updated["review"] = review
        versions[ver] = updated
        _atomic_write_json(path, reg)
        return dict(updated)
