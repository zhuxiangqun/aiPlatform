"""
Artifact Registry — versioned storage for pipeline execution artifacts.

Persists pipeline outputs (code, reports, evaluation results) with
versioning, tagging, and retrieval. Each artifact is stored as a
directory with metadata.json + file contents.

Storage: ~/.aiplat/artifacts/<project_id>/<artifact_name>/<version>/
"""

from __future__ import annotations
import logging

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class ArtifactRecord:
    project_id: str
    name: str
    version: str
    path: str
    created_at: str
    size_bytes: int = 0
    file_count: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_id: str = ""


class ArtifactRegistry:
    def __init__(self, base_dir: str = ""):
        self._base_dir = os.path.realpath(
            base_dir or os.path.expanduser("~/.aiplat/artifacts")
        )
        os.makedirs(self._base_dir, exist_ok=True)

    def store(
        self,
        project_id: str,
        name: str,
        files: List[Dict[str, Any]],
        *,
        version: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: str = "",
    ) -> ArtifactRecord:
        if not version:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            version = f"v_{ts}"
        art_dir = os.path.join(self._base_dir, project_id, name, version)
        os.makedirs(art_dir, exist_ok=True)

        total_size = 0
        file_count = 0
        for f in files:
            fpath = f.get("path", "")
            fcontent = f.get("content", "")
            if not fpath or not fcontent:
                continue
            full = os.path.join(art_dir, fpath.lstrip("/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            data = fcontent if isinstance(fcontent, str) else json.dumps(fcontent, ensure_ascii=False, indent=2)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(data)
            total_size += len(data.encode("utf-8"))
            file_count += 1

        record = ArtifactRecord(
            project_id=project_id,
            name=name,
            version=version,
            path=art_dir,
            created_at=datetime.now(timezone.utc).isoformat(),
            size_bytes=total_size,
            file_count=file_count,
            tags=tags or [],
            metadata=metadata or {},
            session_id=session_id,
        )

        meta_path = os.path.join(art_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "project_id": record.project_id,
                "name": record.name,
                "version": record.version,
                "created_at": record.created_at,
                "size_bytes": record.size_bytes,
                "file_count": record.file_count,
                "tags": record.tags,
                "metadata": record.metadata,
                "session_id": record.session_id,
            }, f, ensure_ascii=False, indent=2)

        return record

    def list_versions(self, project_id: str, name: str) -> List[ArtifactRecord]:
        art_root = os.path.join(self._base_dir, project_id, name)
        if not os.path.isdir(art_root):
            return []
        results = []
        for ver in sorted(os.listdir(art_root), reverse=True):
            meta_path = os.path.join(art_root, ver, "metadata.json")
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path) as f:
                        data = json.load(f)
                    results.append(ArtifactRecord(**data))
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
        return results

    def get_latest(self, project_id: str, name: str) -> Optional[ArtifactRecord]:
        versions = self.list_versions(project_id, name)
        return versions[0] if versions else None

    def get(self, project_id: str, name: str, version: str) -> Optional[ArtifactRecord]:
        meta_path = os.path.join(self._base_dir, project_id, name, version, "metadata.json")
        if not os.path.isfile(meta_path):
            return None
        try:
            with open(meta_path) as f:
                data = json.load(f)
            return ArtifactRecord(**data)
        except Exception:
            return None

    def delete(self, project_id: str, name: str, version: str) -> bool:
        art_dir = os.path.join(self._base_dir, project_id, name, version)
        if not os.path.isdir(art_dir):
            return False
        shutil.rmtree(art_dir)
        parent = os.path.join(self._base_dir, project_id, name)
        if os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
        return True

    def search_by_tag(self, project_id: str, tag: str) -> List[ArtifactRecord]:
        results = []
        proj_dir = os.path.join(self._base_dir, project_id)
        if not os.path.isdir(proj_dir):
            return results
        for art_name in os.listdir(proj_dir):
            versions = self.list_versions(project_id, art_name)
            for rec in versions:
                if tag in rec.tags:
                    results.append(rec)
        return sorted(results, key=lambda r: r.created_at, reverse=True)


_artifact_registry: Optional[ArtifactRegistry] = None


def get_artifact_registry() -> ArtifactRegistry:
    global _artifact_registry
    if _artifact_registry is None:
        _artifact_registry = ArtifactRegistry()
    return _artifact_registry


__all__ = [
    "ArtifactRegistry",
    "ArtifactRecord",
    "get_artifact_registry",
]
