"""
Playbook API — export and import Industry Playbooks.

POST /playbook/export  → Package skills/ontology/pipelines into .aipb
POST /playbook/import  → Load a .aipb archive into the system
GET  /playbook/manifest → Read manifest from a .aipb without importing
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File
from core.harness.learning.playbook import (
    PlaybookManifest, pack_playbook, unpack_playbook,
)

router = APIRouter(prefix="/playbook", tags=["playbook"])


@router.post("/export", response_model=Dict[str, Any])
async def export_playbook(
    id: str = "",
    name: str = "",
    industry: str = "general",
    version: str = "1.0.0",
    skills: str = "",          # comma-separated skill IDs
    ontology: str = "",        # comma-separated domain IDs
    pipelines: str = "",       # comma-separated pipeline names
    policies: str = "",        # comma-separated policy IDs
    cleanup_rules: str = "",   # comma-separated rule names
    tags: str = "",
):
    """Export skills, ontology, pipelines as a .aipb Playbook archive."""
    if not id or not name:
        raise HTTPException(status_code=400, detail="id and name are required")

    manifest = PlaybookManifest(
        id=id,
        name=name,
        industry=industry,
        version=version,
        skills=[s.strip() for s in skills.split(",") if s.strip()] if skills else [],
        ontology=[s.strip() for s in ontology.split(",") if s.strip()] if ontology else [],
        pipelines=[s.strip() for s in pipelines.split(",") if s.strip()] if pipelines else [],
        policies=[s.strip() for s in policies.split(",") if s.strip()] if policies else [],
        cleanup_rules=[s.strip() for s in cleanup_rules.split(",") if s.strip()] if cleanup_rules else [],
        tags=[t.strip() for t in tags.split(",") if t.strip()] if tags else [],
    )

    errors = manifest.validate()
    if errors:
        raise HTTPException(status_code=400, detail=f"Invalid manifest: {errors}")

    try:
        path = await pack_playbook(manifest)
        return {"path": path, "manifest": manifest.to_dict(), "status": "exported"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import", response_model=Dict[str, Any])
async def import_playbook(
    file: UploadFile = File(...),
    on_conflict: str = "skip",
):
    """Import a .aipb Playbook archive."""
    if on_conflict not in ("skip", "overwrite", "merge"):
        raise HTTPException(status_code=400, detail="on_conflict must be: skip, overwrite, merge")

    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".aipb")
    try:
        tmp.write(await file.read())
        tmp.close()
        result = await unpack_playbook(tmp.name, on_conflict=on_conflict)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp.name)


@router.post("/manifest", response_model=Dict[str, Any])
async def read_playbook_manifest(
    file: UploadFile = File(...),
):
    """Read manifest from a .aipb archive without importing."""
    import tempfile, os, zipfile
    from pathlib import Path

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".aipb")
    try:
        tmp.write(await file.read())
        tmp.close()

        with zipfile.ZipFile(tmp.name, "r") as zf:
            if "manifest.json" not in zf.namelist():
                raise HTTPException(status_code=400, detail="Not a valid Playbook (missing manifest.json)")
            manifest_json = zf.read("manifest.json").decode("utf-8")

        manifest = PlaybookManifest.from_json(manifest_json)
        return {
            "manifest": manifest.to_dict(),
            "files": [],
            "valid": len(manifest.validate()) == 0,
        }
    finally:
        os.unlink(tmp.name)
