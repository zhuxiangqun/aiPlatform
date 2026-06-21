"""
DatasetManager — 数据集 CRUD + 血缘追踪 + 快照 + streaming 校验。
"""

from __future__ import annotations

import json as _json
import os as _os
import time as _time
import uuid as _uuid
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional

from core.schemas_finetune import (
    DatasetStatus, DatasetSourceType, DatasetFormat,
    DatasetCreateRequest, DatasetResponse, DatasetListResponse, DatasetPreviewResponse,
)


class DatasetManager:
    """Manage fine-tuning datasets stored in SQLite + JSONL files."""

    def __init__(self, base_dir: str = ""):
        self._base = _Path(base_dir or _os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "finetune_data"
        self._base.mkdir(parents=True, exist_ok=True)
        self._meta_path = self._base / "datasets_meta.json"

    # ── Meta storage ──────────────────────────────────────────────────

    def _read_meta(self) -> Dict[str, dict]:
        if not self._meta_path.exists():
            return {}
        try:
            return _json.loads(self._meta_path.read_text())
        except Exception:
            return {}

    def _write_meta(self, meta: Dict[str, dict]) -> None:
        self._meta_path.write_text(_json.dumps(meta, ensure_ascii=False, indent=2))

    # ── CRUD ──────────────────────────────────────────────────────────

    def create(self, req: DatasetCreateRequest) -> DatasetResponse:
        meta = self._read_meta()
        did = _uuid.uuid4().hex[:12]
        now = _time.time()
        entry = {
            "id": did,
            "name": req.name.strip(),
            "description": req.description or "",
            "source_type": req.source_type.value,
            "source_id": req.source_id or "",
            "source_filter": req.source_filter,
            "format": req.format.value,
            "sample_count": 0,
            "file_size_bytes": 0,
            "status": DatasetStatus.READY.value,
            "error": "",
            "created_at": now,
            "updated_at": now,
        }
        meta[did] = entry
        self._write_meta(meta)
        return DatasetResponse(**entry)

    def get(self, dataset_id: str) -> Optional[DatasetResponse]:
        meta = self._read_meta()
        entry = meta.get(dataset_id)
        if not entry:
            return None
        return DatasetResponse(**entry)

    def list_all(self, limit: int = 100, offset: int = 0) -> DatasetListResponse:
        meta = self._read_meta()
        entries = sorted(meta.values(), key=lambda e: -e.get("created_at", 0))
        total = len(entries)
        return DatasetListResponse(
            datasets=[DatasetResponse(**e) for e in entries[offset:offset+limit]],
            total=total,
        )

    def update(self, dataset_id: str, updates: dict) -> Optional[DatasetResponse]:
        meta = self._read_meta()
        entry = meta.get(dataset_id)
        if not entry:
            return None
        entry.update(updates)
        entry["updated_at"] = _time.time()
        meta[dataset_id] = entry
        self._write_meta(meta)
        return DatasetResponse(**entry)

    def delete(self, dataset_id: str) -> bool:
        meta = self._read_meta()
        if dataset_id not in meta:
            return False
        del meta[dataset_id]
        self._write_meta(meta)
        # Clean up data file
        data_file = self._base / f"{dataset_id}.jsonl"
        data_file.unlink(missing_ok=True)
        return True

    # ── Import JSONL ──────────────────────────────────────────────────

    def import_jsonl(self, dataset_id: str, content: str) -> DatasetResponse:
        meta = self._read_meta()
        entry = meta.get(dataset_id)
        if not entry:
            raise ValueError(f"Dataset {dataset_id} not found")

        # Save data file
        data_file = self._base / f"{dataset_id}.jsonl"
        data_file.write_text(content, encoding="utf-8")

        # Validate format (streaming, no full load into memory)
        sample_count = 0
        errors = []
        line_count = 0
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            line_count += 1
            try:
                parsed = _json.loads(line)
                msgs = parsed.get("messages", [])
                if not isinstance(msgs, list) or len(msgs) < 2:
                    errors.append(f"Line {line_count}: messages array must contain at least 2 messages")
                    continue
                roles = {m.get("role") for m in msgs if isinstance(m, dict)}
                if "user" not in roles:
                    errors.append(f"Line {line_count}: must contain at least one user message")
                    continue
                if "assistant" not in roles:
                    errors.append(f"Line {line_count}: must contain at least one assistant message")
                    continue
                sample_count += 1
            except _json.JSONDecodeError:
                errors.append(f"Line {line_count}: invalid JSON")

        if sample_count < 10:
            errors.append(f"Insufficient samples: {sample_count} (minimum 10 required)")

        file_size = data_file.stat().st_size if data_file.exists() else 0
        entry.update({
            "sample_count": sample_count,
            "file_size_bytes": file_size,
            "status": DatasetStatus.READY.value if not errors else DatasetStatus.ERROR.value,
            "error": "; ".join(errors[:10]) if errors else "",
            "updated_at": _time.time(),
        })
        meta[dataset_id] = entry
        self._write_meta(meta)
        return DatasetResponse(**entry)

    # ── Preview ───────────────────────────────────────────────────────

    def preview(self, dataset_id: str, limit: int = 100) -> DatasetPreviewResponse:
        meta = self._read_meta()
        entry = meta.get(dataset_id)
        if not entry:
            raise ValueError(f"Dataset {dataset_id} not found")

        data_file = self._base / f"{dataset_id}.jsonl"
        if not data_file.exists():
            return DatasetPreviewResponse(dataset_id=dataset_id, samples=[], total_count=0)

        samples = []
        total = 0
        with open(data_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total += 1
                if len(samples) < limit:
                    try:
                        samples.append(_json.loads(line))
                    except _json.JSONDecodeError:
                        samples.append({"error": "invalid JSON", "line": total})
        return DatasetPreviewResponse(
            dataset_id=dataset_id,
            samples=samples[:limit],
            total_count=total,
            stats={"sample_count": total, "file_size_bytes": data_file.stat().st_size},
        )

    # ── Snapshot for job ──────────────────────────────────────────────

    def snapshot(self, dataset_id: str, job_id: str) -> _Path:
        """Copy dataset to job snapshot for reproducibility."""
        data_file = self._base / f"{dataset_id}.jsonl"
        if not data_file.exists():
            raise ValueError(f"Dataset {dataset_id} has no data file")
        snapshot_dir = self._base / "snapshots" / job_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / "data.jsonl"
        snapshot_path.write_text(data_file.read_text(), encoding="utf-8")
        return snapshot_path
