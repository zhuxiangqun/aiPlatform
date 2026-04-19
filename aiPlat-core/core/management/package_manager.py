"""
Workspace Package Manager (P0 MVP).

Goal:
- Provide a "package" unit that can bundle and distribute:
  - agents (AGENT.md directories)
  - skills (SKILL.md directories)
  - mcp servers (server.yaml/policy.yaml directories)
  - hooks (python modules)

This is intentionally filesystem-backed (like agent/skill/mcp managers) to keep MVP simple:
- engine packages: <repo>/core/engine/packages/<name>/package.yaml
- workspace packages: ~/.aiplat/packages/<name>/package.yaml

Package layout (recommended):
  <pkg>/
    package.yaml
    bundle/
      agents/<id>/...
      skills/<id>/...
      mcps/<name>/...
      hooks/<hook_name>.py

If bundle/* exists, install uses bundled files; otherwise it copies from source scopes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import os
import json
import shutil
import hashlib

import yaml


def _sha256_dir(path: Path) -> str:
    h = hashlib.sha256()
    if not path.exists():
        return h.hexdigest()
    if path.is_file():
        h.update(path.read_bytes())
        return h.hexdigest()
    for p in sorted([p for p in path.rglob("*") if p.is_file()], key=lambda x: str(x)):
        h.update(str(p.relative_to(path)).encode("utf-8"))
        try:
            h.update(p.read_bytes())
        except Exception:
            pass
    return h.hexdigest()


@dataclass
class PackageResourceRef:
    kind: str  # agent|skill|mcp|hook
    id: str
    scope: str = "engine"  # engine|workspace (when copying from source)
    bundled: bool = True  # prefer bundle/<kind>s when available


@dataclass
class PackageManifest:
    name: str
    version: str = "0.1.0"
    description: str = ""
    resources: List[PackageResourceRef] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PackageInfo:
    name: str
    scope: str  # engine|workspace
    version: str
    description: str
    manifest_path: str
    package_dir: str
    resources: List[Dict[str, Any]] = field(default_factory=list)


class PackageManager:
    def __init__(self, *, scope: str = "engine", reserved_names: Optional[set] = None):
        self._scope = (scope or "engine").strip().lower()
        if self._scope not in {"engine", "workspace"}:
            self._scope = "engine"
        self._reserved_names = reserved_names or set()
        self._packages: Dict[str, PackageInfo] = {}
        self.reload()

    def _resolve_packages_paths(self) -> List[Path]:
        repo_root = Path(__file__).resolve().parents[2]  # aiPlat-core/
        engine_default = repo_root / "core" / "engine" / "packages"
        workspace_default = Path.home() / ".aiplat" / "packages"

        paths_env = os.environ.get(f"AIPLAT_{self._scope.upper()}_PACKAGES_PATHS")
        if paths_env:
            parts = [p.strip() for p in paths_env.split(os.pathsep) if p.strip()]
            return [Path(p).expanduser().resolve() for p in parts]

        single = os.environ.get(f"AIPLAT_{self._scope.upper()}_PACKAGES_PATH")
        if single:
            return [Path(single).expanduser().resolve()]

        return [engine_default.resolve()] if self._scope == "engine" else [workspace_default.resolve()]

    def _resolve_packages_base_path(self) -> Path:
        paths = self._resolve_packages_paths()
        return paths[-1] if paths else (Path(__file__).resolve().parents[2] / "packages")

    def _find_pkg_dir(self, name: str) -> Optional[Path]:
        for base in reversed(self._resolve_packages_paths()):
            p = base / name
            if p.exists() and p.is_dir():
                return p
        return None

    def reload(self) -> None:
        self._packages = {}
        for base in self._resolve_packages_paths():
            if not base.exists():
                continue
            for item in base.iterdir():
                if not item.is_dir() or item.name.startswith("."):
                    continue
                mf = item / "package.yaml"
                if not mf.exists():
                    continue
                try:
                    raw = yaml.safe_load(mf.read_text(encoding="utf-8")) or {}
                except Exception:
                    raw = {}
                if not isinstance(raw, dict):
                    raw = {}
                name = str(raw.get("name") or item.name)
                version = str(raw.get("version") or "0.1.0")
                desc = str(raw.get("description") or "")
                res = raw.get("resources") or []
                resources: List[Dict[str, Any]] = []
                if isinstance(res, list):
                    for r in res:
                        if not isinstance(r, dict):
                            continue
                        resources.append(
                            {
                                "kind": str(r.get("kind") or ""),
                                "id": str(r.get("id") or ""),
                                "scope": str(r.get("scope") or "engine"),
                                "bundled": bool(r.get("bundled", True)),
                            }
                        )
                self._packages[name] = PackageInfo(
                    name=name,
                    scope=self._scope,
                    version=version,
                    description=desc,
                    manifest_path=str(mf),
                    package_dir=str(item),
                    resources=resources,
                )

    def list_packages(self) -> List[PackageInfo]:
        return list(self._packages.values())

    def get_package(self, name: str) -> Optional[PackageInfo]:
        return self._packages.get(name)

    def upsert_package(self, *, manifest: Dict[str, Any], bundle: Optional[Dict[str, Any]] = None) -> PackageInfo:
        """
        Create/update a workspace package (writes to workspace packages base path).
        """
        if self._scope != "workspace":
            raise ValueError("can_only_upsert_in_workspace_scope")
        name = str(manifest.get("name") or "").strip()
        if not name:
            raise ValueError("missing_package_name")
        if self._reserved_names and name in self._reserved_names:
            raise ValueError(f"package '{name}' is reserved by engine scope")

        base = self._resolve_packages_base_path()
        pkg_dir = base / name
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "package.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")

        # Optional: write bundle payload (caller may provide already-copied content info).
        if isinstance(bundle, dict):
            bdir = pkg_dir / "bundle"
            bdir.mkdir(parents=True, exist_ok=True)
            # bundle is a mapping of relpath->bytes/text; keep MVP minimal and skip here.
            # (We will do bundling in API handler using copytree/copy2.)

        self.reload()
        return self._packages[name]

    def delete_package(self, name: str) -> bool:
        if self._scope != "workspace":
            return False
        pkg_dir = self._find_pkg_dir(name)
        if not pkg_dir:
            return False
        shutil.rmtree(pkg_dir, ignore_errors=True)
        self.reload()
        return True

    # ---------- install/uninstall ----------

    def _installs_dir(self) -> Path:
        return (Path.home() / ".aiplat" / "packages" / ".installs").resolve()

    def _install_record_path(self, pkg_name: str) -> Path:
        return self._installs_dir() / f"{pkg_name}.json"

    def read_install_record(self, pkg_name: str) -> Optional[Dict[str, Any]]:
        p = self._install_record_path(pkg_name)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write_install_record(self, pkg_name: str, record: Dict[str, Any]) -> None:
        d = self._installs_dir()
        d.mkdir(parents=True, exist_ok=True)
        self._install_record_path(pkg_name).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def _resolve_source_dirs(self) -> Dict[str, Path]:
        """
        Resolve source directories for copying resources when not bundled.
        """
        repo_root = Path(__file__).resolve().parents[2]
        return {
            "engine_agents": (repo_root / "core" / "engine" / "agents").resolve(),
            "engine_skills": (repo_root / "core" / "engine" / "skills").resolve(),
            "engine_mcps": (repo_root / "core" / "engine" / "mcps").resolve(),
            "workspace_agents": (Path.home() / ".aiplat" / "agents").resolve(),
            "workspace_skills": (Path.home() / ".aiplat" / "skills").resolve(),
            "workspace_mcps": (Path.home() / ".aiplat" / "mcps").resolve(),
            "workspace_hooks": (Path.home() / ".aiplat" / "hooks").resolve(),
        }

    def install(
        self,
        *,
        pkg_name: str,
        allow_overwrite: bool = False,
    ) -> Dict[str, Any]:
        """
        Install a package into workspace (~/.aiplat).
        Returns a record containing applied file paths and hashes.
        """
        pkg = self.get_package(pkg_name)
        if not pkg:
            raise ValueError("package_not_found")

        pkg_dir = Path(pkg.package_dir)
        bundle_dir = pkg_dir / "bundle"
        sources = self._resolve_source_dirs()

        applied: List[Dict[str, Any]] = []
        conflicts: List[Dict[str, Any]] = []

        def _copy_dir(src: Path, dst: Path) -> Tuple[bool, str]:
            if not src.exists():
                return False, "source_missing"
            if dst.exists():
                if not allow_overwrite:
                    # treat as conflict unless identical
                    if _sha256_dir(dst) == _sha256_dir(src):
                        return True, "already_present_same"
                    return False, "conflict_exists"
                shutil.rmtree(dst, ignore_errors=True)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst)
            return True, "copied"

        def _copy_file(src: Path, dst: Path) -> Tuple[bool, str]:
            if not src.exists():
                return False, "source_missing"
            if dst.exists() and not allow_overwrite:
                if dst.read_bytes() == src.read_bytes():
                    return True, "already_present_same"
                return False, "conflict_exists"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return True, "copied"

        for r in pkg.resources:
            kind = str(r.get("kind") or "").strip()
            rid = str(r.get("id") or "").strip()
            scope = str(r.get("scope") or "engine").strip().lower()
            bundled = bool(r.get("bundled", True))
            if not kind or not rid:
                continue

            try:
                if kind == "agent":
                    src = (bundle_dir / "agents" / rid) if bundled and (bundle_dir / "agents" / rid).exists() else (
                        (sources["engine_agents"] / rid) if scope == "engine" else (sources["workspace_agents"] / rid)
                    )
                    dst = sources["workspace_agents"] / rid
                    ok, reason = _copy_dir(src, dst)
                    if ok:
                        applied.append({"kind": kind, "id": rid, "dst": str(dst), "sha256": _sha256_dir(dst), "reason": reason})
                    else:
                        conflicts.append({"kind": kind, "id": rid, "dst": str(dst), "reason": reason})

                elif kind == "skill":
                    src = (bundle_dir / "skills" / rid) if bundled and (bundle_dir / "skills" / rid).exists() else (
                        (sources["engine_skills"] / rid) if scope == "engine" else (sources["workspace_skills"] / rid)
                    )
                    dst = sources["workspace_skills"] / rid
                    ok, reason = _copy_dir(src, dst)
                    if ok:
                        applied.append({"kind": kind, "id": rid, "dst": str(dst), "sha256": _sha256_dir(dst), "reason": reason})
                    else:
                        conflicts.append({"kind": kind, "id": rid, "dst": str(dst), "reason": reason})

                elif kind == "mcp":
                    src = (bundle_dir / "mcps" / rid) if bundled and (bundle_dir / "mcps" / rid).exists() else (
                        (sources["engine_mcps"] / rid) if scope == "engine" else (sources["workspace_mcps"] / rid)
                    )
                    dst = sources["workspace_mcps"] / rid
                    ok, reason = _copy_dir(src, dst)
                    if ok:
                        applied.append({"kind": kind, "id": rid, "dst": str(dst), "sha256": _sha256_dir(dst), "reason": reason})
                    else:
                        conflicts.append({"kind": kind, "id": rid, "dst": str(dst), "reason": reason})

                elif kind == "hook":
                    src = (bundle_dir / "hooks" / f"{rid}.py") if bundled and (bundle_dir / "hooks" / f"{rid}.py").exists() else (
                        (sources["workspace_hooks"] / f"{rid}.py")
                    )
                    dst = sources["workspace_hooks"] / f"{rid}.py"
                    ok, reason = _copy_file(src, dst)
                    if ok:
                        applied.append({"kind": kind, "id": rid, "dst": str(dst), "sha256": _sha256_dir(dst), "reason": reason})
                    else:
                        conflicts.append({"kind": kind, "id": rid, "dst": str(dst), "reason": reason})
            except Exception as e:
                conflicts.append({"kind": kind, "id": rid, "reason": f"exception:{e}"})

        record = {
            "package": {"name": pkg.name, "version": pkg.version, "scope": pkg.scope},
            "installed_at": __import__("time").time(),
            "applied": applied,
            "conflicts": conflicts,
        }
        self._write_install_record(pkg.name, record)
        return record

    def install_bundle(
        self,
        *,
        pkg_name: str,
        pkg_version: str,
        manifest: Dict[str, Any],
        bundle_dir: Path,
        allow_overwrite: bool = False,
    ) -> Dict[str, Any]:
        """
        Install using an extracted bundle directory (bundle/*).
        Used by the DB-backed package registry install flow.
        """
        sources = self._resolve_source_dirs()
        applied: List[Dict[str, Any]] = []
        conflicts: List[Dict[str, Any]] = []

        def _copy_dir(src: Path, dst: Path) -> Tuple[bool, str]:
            if not src.exists():
                return False, "source_missing"
            if dst.exists():
                if not allow_overwrite:
                    if _sha256_dir(dst) == _sha256_dir(src):
                        return True, "already_present_same"
                    return False, "conflict_exists"
                shutil.rmtree(dst, ignore_errors=True)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst)
            return True, "copied"

        def _copy_file(src: Path, dst: Path) -> Tuple[bool, str]:
            if not src.exists():
                return False, "source_missing"
            if dst.exists() and not allow_overwrite:
                if dst.read_bytes() == src.read_bytes():
                    return True, "already_present_same"
                return False, "conflict_exists"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return True, "copied"

        resources = (manifest or {}).get("resources") or []
        if not isinstance(resources, list):
            resources = []
        for r in resources:
            if not isinstance(r, dict):
                continue
            kind = str(r.get("kind") or "").strip()
            rid = str(r.get("id") or "").strip()
            if not kind or not rid:
                continue
            try:
                if kind == "agent":
                    src = bundle_dir / "agents" / rid
                    dst = sources["workspace_agents"] / rid
                    ok, reason = _copy_dir(src, dst)
                    if ok:
                        applied.append({"kind": kind, "id": rid, "dst": str(dst), "sha256": _sha256_dir(dst), "reason": reason})
                    else:
                        conflicts.append({"kind": kind, "id": rid, "dst": str(dst), "reason": reason})
                elif kind == "skill":
                    src = bundle_dir / "skills" / rid
                    dst = sources["workspace_skills"] / rid
                    ok, reason = _copy_dir(src, dst)
                    if ok:
                        applied.append({"kind": kind, "id": rid, "dst": str(dst), "sha256": _sha256_dir(dst), "reason": reason})
                    else:
                        conflicts.append({"kind": kind, "id": rid, "dst": str(dst), "reason": reason})
                elif kind == "mcp":
                    src = bundle_dir / "mcps" / rid
                    dst = sources["workspace_mcps"] / rid
                    ok, reason = _copy_dir(src, dst)
                    if ok:
                        applied.append({"kind": kind, "id": rid, "dst": str(dst), "sha256": _sha256_dir(dst), "reason": reason})
                    else:
                        conflicts.append({"kind": kind, "id": rid, "dst": str(dst), "reason": reason})
                elif kind == "hook":
                    src = bundle_dir / "hooks" / f"{rid}.py"
                    dst = sources["workspace_hooks"] / f"{rid}.py"
                    ok, reason = _copy_file(src, dst)
                    if ok:
                        applied.append({"kind": kind, "id": rid, "dst": str(dst), "sha256": _sha256_dir(dst), "reason": reason})
                    else:
                        conflicts.append({"kind": kind, "id": rid, "dst": str(dst), "reason": reason})
            except Exception as e:
                conflicts.append({"kind": kind, "id": rid, "reason": f"exception:{e}"})

        record = {
            "package": {"name": pkg_name, "version": pkg_version, "scope": "registry"},
            "installed_at": __import__("time").time(),
            "applied": applied,
            "conflicts": conflicts,
        }
        self._write_install_record(pkg_name, record)
        return record

    def uninstall(self, *, pkg_name: str, keep_modified: bool = True) -> Dict[str, Any]:
        """
        Best-effort uninstall using recorded paths.
        keep_modified=True: only delete if current hash matches install record hash.
        """
        record = self.read_install_record(pkg_name)
        if not record:
            raise ValueError("install_record_not_found")
        removed: List[Dict[str, Any]] = []
        kept: List[Dict[str, Any]] = []
        for item in record.get("applied") or []:
            dst = Path(str(item.get("dst") or ""))
            expected = str(item.get("sha256") or "")
            if not dst.exists():
                continue
            cur = _sha256_dir(dst)
            if keep_modified and expected and cur != expected:
                kept.append({"dst": str(dst), "reason": "modified"})
                continue
            try:
                if dst.is_dir():
                    shutil.rmtree(dst, ignore_errors=True)
                else:
                    dst.unlink(missing_ok=True)  # type: ignore[arg-type]
                removed.append({"dst": str(dst)})
            except Exception as e:
                kept.append({"dst": str(dst), "reason": str(e)})

        # remove record
        try:
            self._install_record_path(pkg_name).unlink(missing_ok=True)  # type: ignore[arg-type]
        except Exception:
            pass
        return {"package": record.get("package"), "removed": removed, "kept": kept}
