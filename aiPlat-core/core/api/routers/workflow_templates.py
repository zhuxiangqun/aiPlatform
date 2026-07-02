"""
Workflow Templates API — save / load / list workflow configurations.
Storage: ~/.aiplat/workflow_templates/{name}.json
"""

from __future__ import annotations
import logging

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import os
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
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


@router.get("/workflow/templates", response_model=Dict[str, Any])
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
    return {"templates": templates, "total": len(templates)}


@router.post("/workflow/templates", response_model=Dict[str, Any])
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
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


@router.get("/workflow/templates/{name}", response_model=Dict[str, Any])
async def load_template(name: str):
    """Load a workflow template by name."""
    name = _sanitize(name)
    d = _templates_dir()
    fp = d / f"{name}.json"
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    return json.loads(fp.read_text(encoding="utf-8"))


@router.delete("/workflow/templates/{name}", response_model=Dict[str, Any])
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

@router.post("/workflows/installer/plan", response_model=Dict[str, Any])
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


@router.post("/workflows/installer/install", response_model=Dict[str, Any])
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


@router.post("/workflows/installer/upload-plan", response_model=Dict[str, Any])
async def workflow_installer_upload_plan(
    file: UploadFile = File(...),
    subdir: str = Form(""),
    auto_detect_subdir: str = Form("true"),
):
    from core.management.asset_installer import WorkflowInstaller
    inst = WorkflowInstaller(target_base_dir=_templates_dir())
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        plan = inst.plan_from_zip(zip_path=tmp_path,
            subdir=subdir or None,
            auto_detect_subdir=auto_detect_subdir.lower() in ("true", "1", "yes"))
        return {"status": "ok", "source": plan.source,
                "workflows": plan.assets, "warnings": plan.warnings}
    except ValueError as e:
        return {"workflows": [], "warnings": [str(e)]}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/workflows/installer/upload-install", response_model=Dict[str, Any])
async def workflow_installer_upload_install(
    file: UploadFile = File(...),
    subdir: str = Form(""),
    auto_detect_subdir: str = Form("true"),
    allow_overwrite: str = Form("false"),
):
    from core.management.asset_installer import WorkflowInstaller
    inst = WorkflowInstaller(target_base_dir=_templates_dir())
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        res = inst.install_from_zip(zip_path=tmp_path,
            subdir=subdir or None,
            auto_detect_subdir=auto_detect_subdir.lower() in ("true", "1", "yes"),
            allow_overwrite=allow_overwrite.lower() in ("true", "1", "yes"))
        return {"status": "ok", "installed": res.installed, "skipped": res.skipped}
    except ValueError as e:
        return {"installed": [], "skipped": [{"reason": str(e)}]}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/workflow/templates/{template_name}/submit-for-review", response_model=Dict[str, Any])
async def submit_workflow_for_review(template_name: str):
    """提交 Workflow 进入审批流水线。"""
    import time as _time

    d = _templates_dir()
    safe = _sanitize(template_name)
    json_path = d / f"{safe}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"Template {template_name} not found")

    lint_errors = 0
    lint_warnings = 0
    lint_messages = []

    try:
        from core.management.workflow_config_validator import validate_workflow_template
        issues = validate_workflow_template(json_path)
        for iss in issues:
            lint_messages.append(f"{'ERROR' if iss.severity == 'error' else 'WARN'}: {iss.message}")
            if iss.severity == "error":
                lint_errors += 1
            else:
                lint_warnings += 1
    except Exception as e:
        lint_messages.append(f"Validate failed: {e}")
        lint_errors += 1

    lint_result = {
        "risk_level": "high" if lint_errors > 0 else "low",
        "blocked": lint_errors > 0,
        "error_count": lint_errors,
        "warning_count": lint_warnings,
        "messages": lint_messages,
    }

    if lint_errors > 0:
        # Write governance failed
        try:
            raw = _json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
            raw["_governance"] = {"status": "failed", "lint_result": lint_result, "submitted_at": _time.time()}
            json_path.write_text(_json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        raise HTTPException(status_code=422, detail={"message": f"配置校验未通过：{lint_errors} 个错误", "lint": lint_result})

    try:
        raw = _json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
        raw["status"] = "ready"
        raw["_governance"] = {"status": "pending", "lint_result": lint_result, "submitted_at": _time.time()}
        json_path.write_text(_json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update workflow: {e}")

    return {
        "status": "ok",
        "template_name": template_name,
        "new_status": "ready",
        "governance": "pending",
        "lint": {"risk_level": lint_result["risk_level"], "error_count": lint_errors, "warning_count": lint_warnings},
    }
