"""
Workflow Manager — directory-based workflow definitions.

Stores workflows as:
  ~/.aiplat/workflows/<id>/
    workflow.json          ← nodes, edges, name, description
    WORKFLOW.manifest.json ← provenance, signature, publisher

Supports the same governance pipeline as Skills/Agents:
  provenance + integrity enrichment, Ed25519 signature verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import json
import logging
import os
import time

from core.utils.ids import new_prefixed_id

_logger = logging.getLogger(__name__)


@dataclass
class WorkflowInfo:
    id: str
    name: str
    description: str = ""
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "ready"  # draft | ready | published | listed | deprecated
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "1.0.0"


def _notify_resource_mutated(resource_type: str, action: str, resource_id: str) -> None:
    """Fire-and-forget publish to EventBus so graph caches know to invalidate."""
    try:
        from core.harness.observability.events import EventBus, EventType
        EventBus.get_instance().emit(
            event_type=EventType.RESOURCE_MUTATED,
            source="WorkflowManager",
            data={"resource_type": resource_type, "action": action, "resource_id": resource_id},
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)


class WorkflowManager:
    """Directory-based workflow manager with provenance/integrity enrichment."""

    def __init__(self, *, scope: str = "workspace"):
        self._scope = (scope or "workspace").strip().lower()
        self._workflows: Dict[str, WorkflowInfo] = {}
        self.reload()

    def _resolve_paths(self) -> List[Path]:
        repo_root = Path(__file__).resolve().parents[2]
        engine_default = repo_root / "core" / "engine" / "workflows"
        workspace_default = Path.home() / ".aiplat" / "workflows"

        if self._scope == "engine":
            env_path = os.environ.get("AIPLAT_ENGINE_WORKFLOWS_PATH")
            return [engine_default.resolve()] if not env_path else [Path(env_path).expanduser().resolve()]
        env_path = os.environ.get("AIPLAT_WORKSPACE_WORKFLOWS_PATH")
        return [workspace_default.resolve()] if not env_path else [Path(env_path).expanduser().resolve()]

    def _resolve_base_path(self) -> Path:
        paths = self._resolve_paths()
        return paths[-1] if paths else (Path.home() / ".aiplat" / "workflows")

    # ==================== Load & Save ====================

    def reload(self) -> None:
        """Reload all workflows from filesystem, migrating from SQLite if needed."""
        self._workflows = {}
        now = datetime.now(timezone.utc)

        for base_dir in reversed(self._resolve_paths()):
            if not base_dir.exists():
                continue
            for item in base_dir.iterdir():
                if not item.is_dir() or item.name.startswith("."):
                    continue
                wf_json = item / "workflow.json"
                if not wf_json.exists():
                    continue
                try:
                    data = json.loads(wf_json.read_text(encoding="utf-8")) or {}
                except Exception:
                    data = {}
                if not isinstance(data, dict):
                    continue

                wf_id = str(data.get("id") or item.name)
                wf = WorkflowInfo(
                    id=wf_id,
                    name=str(data.get("name") or wf_id),
                    description=str(data.get("description") or ""),
                    nodes=data.get("nodes") if isinstance(data.get("nodes"), list) else [],
                    edges=data.get("edges") if isinstance(data.get("edges"), list) else [],
                    status=str(data.get("status") or "ready"),
                    enabled=bool(data.get("enabled", True)),
                    metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
                    created_at=now,
                    updated_at=now,
                    version=str(data.get("version") or "1.0.0"),
                )
                wf.metadata.setdefault("filesystem", {})
                wf.metadata["filesystem"]["server_dir"] = str(item)
                wf.metadata["filesystem"]["workflow_json"] = str(wf_json)
                wf.metadata["filesystem"]["source"] = str(base_dir)

                self._enrich_workflow_provenance_and_integrity(wf.metadata, workflow_dir=item)
                self._workflows[wf_id] = wf

        # Migration: if empty after scanning, try to import from SQLite
        if not self._workflows and self._scope == "workspace":
            self._migrate_from_sqlite()

        _logger.info(f"Loaded {len(self._workflows)} workflows from scope={self._scope}")

    def _migrate_from_sqlite(self) -> None:
        """One-time migration: import workflow definitions from platform SQLite into directories."""
        try:
            from importlib import import_module
            pkg = import_module("storage.sqlite")
            list_workflows = pkg.list_workflows
            get_workflow = pkg.get_workflow
        except Exception:
            return

        wfs = list_workflows()
        if not wfs:
            return

        base = self._resolve_base_path()
        base.mkdir(parents=True, exist_ok=True)
        migrated = 0
        for w in wfs:
            try:
                wf_id = str(w.get("id") or "")
                if not wf_id or wf_id in self._workflows:
                    continue
                wf_dir = base / wf_id
                wf_dir.mkdir(parents=True, exist_ok=True)
                wf_json = wf_dir / "workflow.json"
                if wf_json.exists():
                    continue  # already migrated
                payload = {
                    "id": wf_id,
                    "name": str(w.get("name") or wf_id),
                    "description": str(w.get("description") or ""),
                    "nodes": w.get("nodes_json") or w.get("nodes") or [],
                    "edges": w.get("edges_json") or w.get("edges") or [],
                    "status": "draft",
                    "enabled": bool(w.get("enabled", True)),
                    "version": "1.0.0",
                    "migrated_from_sqlite": True,
                }
                wf_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                migrated += 1
                _logger.info(f"Migrated workflow from SQLite: {wf_id}")
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        if migrated:
            _logger.info(f"Migrated {migrated} workflows from SQLite to directories")
            self.reload()

    def _write_workflow_json(self, wf: WorkflowInfo) -> None:
        """Persist workflow to its directory."""
        wf_dir = Path(wf.metadata.get("filesystem", {}).get("server_dir") or "")
        if not wf_dir or not wf_dir.exists():
            base = self._resolve_base_path()
            wf_dir = base / wf.id
            wf_dir.mkdir(parents=True, exist_ok=True)
            wf.metadata.setdefault("filesystem", {})
            wf.metadata["filesystem"]["server_dir"] = str(wf_dir)
            wf.metadata["filesystem"]["workflow_json"] = str(wf_dir / "workflow.json")
        payload = {
            "id": wf.id,
            "name": wf.name,
            "description": wf.description,
            "nodes": wf.nodes,
            "edges": wf.edges,
            "status": wf.status,
            "enabled": wf.enabled,
            "version": wf.version,
            "metadata": {k: v for k, v in wf.metadata.items() if k != "filesystem"},
        }
        (wf_dir / "workflow.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # ==================== Provenance & Integrity ====================

    def _sha256_file(self, p: Path) -> str:
        h = hashlib.sha256()
        with p.open("rb") as f:
            while True:
                b = f.read(1024 * 1024)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()

    def _read_workflow_manifest_json(self, workflow_dir: Path) -> Dict[str, Any]:
        p = workflow_dir / "WORKFLOW.manifest.json"
        if not p.exists():
            return {}
        try:
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _compute_workflow_bundle_integrity(self, workflow_dir: Path) -> Dict[str, Any]:
        entries: List[str] = []
        total_bytes = 0
        file_count = 0
        files_sample: List[str] = []
        try:
            for p in sorted(workflow_dir.rglob("*")):
                try:
                    if p.is_dir():
                        continue
                    rel = str(p.relative_to(workflow_dir))
                    if rel.startswith("__pycache__/") or rel.endswith(".pyc"):
                        continue
                    if rel.startswith(".revisions/"):
                        continue
                    if rel.startswith(".git/"):
                        continue
                    size = int(p.stat().st_size)
                    sha = self._sha256_file(p)
                    entries.append(f"{rel}\t{size}\t{sha}")
                    total_bytes += size
                    file_count += 1
                    if len(files_sample) < 20:
                        files_sample.append(rel)
                except Exception:
                    continue
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        bundle_sha256 = hashlib.sha256(("\n".join(entries)).encode("utf-8")).hexdigest()
        return {
            "bundle_sha256": bundle_sha256,
            "file_count": int(file_count),
            "total_bytes": int(total_bytes),
            "files_sample": files_sample,
        }

    def _enrich_workflow_provenance_and_integrity(self, metadata: Dict[str, Any], *, workflow_dir: Path) -> None:
        if not isinstance(metadata, dict):
            return
        prov = metadata.get("provenance") if isinstance(metadata.get("provenance"), dict) else {}
        prov.setdefault("source_type", "filesystem")
        prov.setdefault("scope", self._scope)
        prov.setdefault("workflow_dir", str(workflow_dir))

        manifest = self._read_workflow_manifest_json(workflow_dir)
        if not manifest and (self._scope or "").strip().lower() != "engine":
            manifest = {"version": "1.0.0"}
            try:
                (workflow_dir / "WORKFLOW.manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        if manifest:
            prov.setdefault("publisher", manifest.get("publisher"))
            prov.setdefault("source", manifest.get("source"))
            prov.setdefault("version", manifest.get("version"))
            if manifest.get("signature") is not None:
                prov.setdefault("signature", manifest.get("signature"))
            try:
                mpath = workflow_dir / "WORKFLOW.manifest.json"
                if mpath.exists():
                    prov.setdefault("manifest_sha256", self._sha256_file(mpath))
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        metadata["provenance"] = prov

        integ = metadata.get("integrity") if isinstance(metadata.get("integrity"), dict) else {}
        try:
            integ.update(self._compute_workflow_bundle_integrity(workflow_dir))
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        metadata["integrity"] = integ

    def compute_workflow_signature_verification(self, wf: WorkflowInfo, trusted_keys: Dict[str, str]) -> Dict[str, Any]:
        if not isinstance(getattr(wf, "metadata", None), dict):
            return {}
        prov = dict(wf.metadata.get("provenance") or {}) if isinstance(wf.metadata.get("provenance"), dict) else {}
        integ = wf.metadata.get("integrity") if isinstance(wf.metadata, dict) else {}
        sig = prov.get("signature")
        bundle_sha = integ.get("bundle_sha256") if isinstance(integ, dict) else None
        if not sig or not bundle_sha:
            return prov
        prov = dict(prov)
        prov["signature_verified"] = False
        prov["signature_verified_reason"] = ""
        prov["signature_verified_key_id"] = ""
        try:
            from core.harness.infrastructure.crypto.signature import verify_skill_signature
            r = verify_skill_signature(
                skill_id=str(getattr(wf, "id", "")),
                version=str(getattr(wf, "version", "0.1.0") or "0.1.0"),
                bundle_sha256=str(bundle_sha),
                signature=str(sig),
                trusted_keys=trusted_keys,
            )
            prov["signature_verified"] = bool(r.get("verified"))
            prov["signature_verified_key_id"] = r.get("key_id") or ""
            prov["signature_verified_reason"] = (r.get("error") or "") if not r.get("verified") else ""
        except Exception as e:
            prov["signature_verified_reason"] = str(e)
        return prov

    # ==================== CRUD ====================

    def list_workflows(self) -> List[WorkflowInfo]:
        return list(self._workflows.values())

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowInfo]:
        return self._workflows.get(workflow_id)

    def create_workflow(self, name: str, description: str = "", nodes: List[Any] = None, edges: List[Any] = None) -> WorkflowInfo:
        if not name.strip():
            raise ValueError("name is required")
        wf_id = new_prefixed_id("wf")
        now = datetime.now(timezone.utc)
        base = self._resolve_base_path()
        wf_dir = base / wf_id
        wf_dir.mkdir(parents=True, exist_ok=True)
        wf = WorkflowInfo(
            id=wf_id, name=name.strip(), description=description.strip(),
            nodes=nodes or [], edges=edges or [],
            created_at=now, updated_at=now,
        )
        self._workflows[wf_id] = wf
        self._write_workflow_json(wf)
        self._enrich_workflow_provenance_and_integrity(wf.metadata, workflow_dir=wf_dir)
        _notify_resource_mutated("workflow", "created", wf_id)
        return wf

    def update_workflow(self, workflow_id: str, **kwargs: Any) -> Optional[WorkflowInfo]:
        wf = self._workflows.get(workflow_id)
        if not wf:
            return None
        if "name" in kwargs:
            wf.name = str(kwargs["name"])
        if "description" in kwargs:
            wf.description = str(kwargs["description"])
        if "nodes" in kwargs:
            wf.nodes = kwargs["nodes"]
        if "edges" in kwargs:
            wf.edges = kwargs["edges"]
        if "status" in kwargs:
            wf.status = str(kwargs["status"])
        if "enabled" in kwargs:
            wf.enabled = bool(kwargs["enabled"])
        wf.updated_at = datetime.now(timezone.utc)
        self._write_workflow_json(wf)
        wf_dir = Path(wf.metadata.get("filesystem", {}).get("server_dir") or "")
        if wf_dir.exists():
            self._enrich_workflow_provenance_and_integrity(wf.metadata, workflow_dir=wf_dir)
        _notify_resource_mutated("workflow", "updated", workflow_id)
        return wf

    def delete_workflow(self, workflow_id: str) -> bool:
        wf = self._workflows.pop(workflow_id, None)
        if not wf:
            return False
        wf_dir = Path(wf.metadata.get("filesystem", {}).get("server_dir") or "")
        if wf_dir.exists():
            import shutil
            shutil.rmtree(wf_dir, ignore_errors=True)
        _notify_resource_mutated("workflow", "deleted", workflow_id)
        return True

    def toggle_enabled(self, workflow_id: str) -> Optional[bool]:
        wf = self._workflows.get(workflow_id)
        if not wf:
            return None
        wf.enabled = not wf.enabled
        wf.updated_at = datetime.now(timezone.utc)
        self._write_workflow_json(wf)
        return wf.enabled

    def publish(self, workflow_id: str) -> Dict[str, Any]:
        wf = self._workflows.get(workflow_id)
        if not wf:
            raise ValueError(f"workflow not found: {workflow_id}")
        wf.status = "published"
        wf.updated_at = datetime.now(timezone.utc)
        self._write_workflow_json(wf)
        return {"workflow_id": workflow_id, "status": "published", "name": wf.name}

    # ==================== Migration Helpers ====================

    def get_workflow_dict(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Return a dict compatible with the old SQLite-based API."""
        wf = self._workflows.get(workflow_id)
        if not wf:
            return None
        return {
            "id": wf.id, "name": wf.name, "description": wf.description,
            "nodes": wf.nodes, "edges": wf.edges,
            "nodes_json": json.dumps(wf.nodes), "edges_json": json.dumps(wf.edges),
            "data_json": "{}",
            "status": wf.status, "enabled": wf.enabled,
            "created_at": wf.created_at.timestamp(),
            "updated_at": wf.updated_at.timestamp(),
        }

    def list_workflow_dicts(self) -> List[Dict[str, Any]]:
        """Return dicts compatible with the old SQLite-based API."""
        return [self.get_workflow_dict(wf.id) for wf in self._workflows.values() if self.get_workflow_dict(wf.id)]
