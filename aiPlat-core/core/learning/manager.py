"""
Phase 6: LearningManager (placeholder).

Responsibilities (future):
- Run evaluation benchmarks and generate LearningArtifacts
- Aggregate feedback from online runs
- Produce evolution proposals and (optionally) publish/rollback them

Current implementation:
- Persistence helpers that store artifacts in ExecutionStore (schema v11+).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from core.harness.kernel.runtime import get_kernel_runtime

from .types import LearningArtifact, LearningArtifactKind, LearningArtifactStatus


class LearningManager:
    def __init__(self, execution_store: Optional[Any] = None) -> None:
        self._store = execution_store

    def _get_store(self) -> Optional[Any]:
        if self._store is not None:
            return self._store
        rt = get_kernel_runtime()
        return getattr(rt, "execution_store", None) if rt else None

    async def create_artifact(
        self,
        *,
        kind: LearningArtifactKind,
        target_type: str,
        target_id: str,
        version: str,
        status: str = LearningArtifactStatus.DRAFT,
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> LearningArtifact:
        artifact = LearningArtifact(
            artifact_id=str(uuid.uuid4()),
            kind=kind,
            target_type=target_type,
            target_id=target_id,
            version=version,
            status=LearningArtifactStatus.DRAFT,
            trace_id=trace_id,
            run_id=run_id,
            payload=payload or {},
            metadata=metadata or {},
        )
        # Allow custom status beyond the enum (e.g. pending/verified/failed) for governance.
        try:
            if isinstance(status, str) and status:
                artifact.status = status  # type: ignore[assignment]
        except Exception:
            pass
        store = self._get_store()
        if store is not None and hasattr(store, "upsert_learning_artifact"):
            try:
                await store.upsert_learning_artifact(artifact.to_record())
            except Exception:
                pass
        return artifact

    async def set_artifact_status(
        self,
        *,
        artifact_id: str,
        status: str,
        metadata_update: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Update an artifact status (best-effort).
        This is used by offline publish/rollback workflows.
        """
        store = self._get_store()
        if store is None or not hasattr(store, "get_learning_artifact") or not hasattr(store, "upsert_learning_artifact"):
            return False
        try:
            rec = await store.get_learning_artifact(artifact_id)
            if not rec:
                return False
            meta = rec.get("metadata") or {}
            if metadata_update:
                meta.update(metadata_update)
            rec["status"] = status
            rec["metadata"] = meta
            # upsert expects payload/metadata keys
            await store.upsert_learning_artifact(
                {
                    "artifact_id": rec["artifact_id"],
                    "kind": rec["kind"],
                    "target_type": rec["target_type"],
                    "target_id": rec["target_id"],
                    "version": rec["version"],
                    "status": rec["status"],
                    "trace_id": rec.get("trace_id"),
                    "run_id": rec.get("run_id"),
                    "payload": rec.get("payload") or {},
                    "metadata": rec.get("metadata") or {},
                    "created_at": rec.get("created_at"),
                }
            )
            return True
        except Exception:
            return False
