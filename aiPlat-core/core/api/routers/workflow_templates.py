"""
Workflow Templates API — save / load / list workflow configurations.
Storage: ~/.aiplat/workflow_templates/{name}.json
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class TemplateSave(BaseModel):
    name: str
    description: str = ""
    stages: List[Dict[str, Any]] = []


def _templates_dir() -> Path:
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    return Path(home) / "workflow_templates"


def _sanitize(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "_-").strip("_-")[:50]


@router.get("/workflow/templates")
async def list_templates():
    """List all saved workflow templates."""
    d = _templates_dir()
    d.mkdir(parents=True, exist_ok=True)
    templates = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            templates.append({
                "name": f.stem,
                "label": data.get("name", f.stem),
                "description": data.get("description", ""),
                "stage_count": len(data.get("stages", [])),
                "updated_at": data.get("updated_at", ""),
                "version": data.get("version", "1"),
            })
        except Exception:
            pass
    return {"templates": templates, "total": len(templates)}


@router.post("/workflow/templates")
async def save_template(body: TemplateSave):
    """Save workflow as a named template."""
    name = _sanitize(body.name)
    if not name:
        raise HTTPException(status_code=400, detail="Invalid template name")
    d = _templates_dir()
    d.mkdir(parents=True, exist_ok=True)
    fp = d / f"{name}.json"
    existing = None
    if fp.exists():
        try:
            existing = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            pass
    version = str(int(existing.get("version", "1") if existing else "1") + 1 if existing else "1")
    data = {
        "name": body.name,
        "description": body.description,
        "stages": body.stages,
        "version": version,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "saved", "name": name, "version": version}


@router.get("/workflow/templates/{name}")
async def load_template(name: str):
    """Load a workflow template by name."""
    name = _sanitize(name)
    d = _templates_dir()
    fp = d / f"{name}.json"
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    return json.loads(fp.read_text(encoding="utf-8"))


@router.delete("/workflow/templates/{name}")
async def delete_template(name: str):
    """Delete a workflow template."""
    name = _sanitize(name)
    d = _templates_dir()
    fp = d / f"{name}.json"
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    fp.unlink()
    return {"status": "deleted"}


# ── Workflow Installer endpoints ──────────────────────────────────

@router.post("/workflows/installer/plan")
async def workflow_installer_plan(request: dict):
    try:
        from core.management.asset_installer import WorkflowInstaller
        inst = WorkflowInstaller(target_base_dir=_templates_dir())
        st = str(request.get("source_type", "")).strip().lower()
        if st == "git":
            plan = inst.plan_from_git(url=str(request.get("url", "")), ref=str(request.get("ref", "")),
                subdir=request.get("subdir"), auto_detect_subdir=bool(request.get("auto_detect_subdir", True)))
        elif st == "path":
            plan = inst.plan_from_path(path=str(request.get("path", "")),
                subdir=request.get("subdir"), auto_detect_subdir=bool(request.get("auto_detect_subdir", True)))
        elif st == "zip":
            plan = inst.plan_from_zip(zip_path=str(request.get("path", "")),
                subdir=request.get("subdir"), auto_detect_subdir=bool(request.get("auto_detect_subdir", True)))
        else:
            return {"workflows": [], "warnings": ["invalid_source_type"]}
        return {"source": plan.source, "detected_subdir": plan.detected_subdir,
                "workflows": plan.assets, "warnings": plan.warnings}
    except ValueError as e:
        return {"workflows": [], "warnings": [str(e)]}


@router.post("/workflows/installer/install")
async def workflow_installer_install(request: dict):
    try:
        from core.management.asset_installer import WorkflowInstaller
        inst = WorkflowInstaller(target_base_dir=_templates_dir())
        st = str(request.get("source_type", "")).strip().lower()
        if st == "git":
            res = inst.install_from_git(url=str(request.get("url", "")), ref=str(request.get("ref", "")),
                subdir=request.get("subdir"), auto_detect_subdir=bool(request.get("auto_detect_subdir", True)),
                allow_overwrite=bool(request.get("allow_overwrite", False)))
        elif st == "path":
            res = inst.install_from_path(path=str(request.get("path", "")),
                subdir=request.get("subdir"), auto_detect_subdir=bool(request.get("auto_detect_subdir", True)),
                allow_overwrite=bool(request.get("allow_overwrite", False)))
        elif st == "zip":
            res = inst.install_from_zip(zip_path=str(request.get("path", "")),
                subdir=request.get("subdir"), auto_detect_subdir=bool(request.get("auto_detect_subdir", True)),
                allow_overwrite=bool(request.get("allow_overwrite", False)))
        else:
            return {"installed": [], "skipped": [{"reason": "invalid_source_type"}]}
        return {"installed": res.installed, "skipped": res.skipped}
    except ValueError as e:
        return {"installed": [], "skipped": [{"reason": str(e)}]}
