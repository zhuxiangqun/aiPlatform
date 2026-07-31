"""
Skill Marketplace API router — list, install, and uninstall skills.

Mounted at /api/management/skills
"""
from __future__ import annotations
import logging

import os
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from auth.deps import require_auth, require_admin
from pydantic import BaseModel

router = APIRouter(prefix="/skills", tags=["skill-marketplace"])

SKILLS_HOME = os.path.expanduser("~/.aiplat/skills")
CATALOG_PATH = os.path.join(SKILLS_HOME, "catalog.yaml")


class InstallRequest(BaseModel):
    source: str  # "git+https://..." | "local+/path/to/skill" | "npm+package-name"
    skill_name: str = ""


class SkillInfo(BaseModel):
    name: str
    source: str = "installed"
    version: str = ""
    description: str = ""
    category: str = "general"


def _scan_installed() -> List[Dict[str, Any]]:
    """Scan ~/.aiplat/skills/ for installed skills."""
    skills = []
    failed_files = []
    if not os.path.isdir(SKILLS_HOME):
        return skills
    for dirname in sorted(os.listdir(SKILLS_HOME)):
        skill_dir = os.path.join(SKILLS_HOME, dirname)
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        try:
            with open(skill_md, "r") as f:
                raw = f.read()
        except Exception:
            failed_files.append(dirname)
            continue
        info = {"name": dirname, "source": "installed", "version": "", "description": "", "category": "general"}
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                try:
                    import yaml
                    fm = yaml.safe_load(parts[1]) or {}
                    info["name"] = fm.get("name", dirname)
                    info["version"] = fm.get("version", "")
                    info["description"] = fm.get("description", "")
                    info["category"] = fm.get("category", "general")
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
        skills.append(info)
    if failed_files:
        logging.getLogger(__name__).warning(
            "Failed to read SKILL.md for %d skills: %s", len(failed_files), ", ".join(failed_files))
    return skills


def _scan_catalog() -> List[Dict[str, Any]]:
    """Scan catalog.yaml for available skills."""
    available = []
    try:
        if os.path.isfile(CATALOG_PATH):
            import yaml
            with open(CATALOG_PATH, "r") as f:
                data = yaml.safe_load(f.read()) or {}
            for item in data.get("skills", []):
                available.append(dict(item))
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return available


@router.get("/marketplace", response_model=StatusResponse)
async def list_marketplace(_auth: str = Depends(require_auth)):
    """List installed and available skills."""
    installed = _scan_installed()
    available = _scan_catalog()
    installed_names = {s["name"] for s in installed}
    # Mark available skills that are already installed
    for a in available:
        a["installed"] = a.get("name", "") in installed_names
    return {
        "installed": installed,
        "available": available,
        "total_installed": len(installed),
        "total_available": len(available),
    }


@router.post("/install", response_model=StatusResponse)
async def install_skill(req: InstallRequest, _auth: str = Depends(require_admin)):
    """Install a skill from source URL or local path."""
    source = req.source.strip()
    skill_name = req.skill_name.strip()
    os.makedirs(SKILLS_HOME, exist_ok=True)

    if source.startswith("git+"):
        # Clone git repo to temp, then copy skill dir
        repo_url = source[4:]
        # Validate: only allow http/https git URLs
        if not repo_url.startswith(("https://", "http://", "git@")):
            raise HTTPException(400, f"Invalid repo URL: must be https://, http://, or git@")
        # Reject known dangerous git URL patterns
        if any(c in repo_url for c in ("--upload-pack", "--config", "-c ", ";", "|", "`")):
            raise HTTPException(400, "Repo URL contains disallowed characters")
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                subprocess.run(["git", "clone", "--depth", "1", repo_url, tmpdir], check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                raise HTTPException(400, f"Git clone failed: {e.stderr.decode()[:500]}")
            # Find SKILL.md in cloned repo
            for root, dirs, files in os.walk(tmpdir):
                if "SKILL.md" in files:
                    name = skill_name or os.path.basename(root)
                    dst = os.path.join(SKILLS_HOME, name)
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(root, dst)
                    # Trigger registry rescan
                    _notify_registry(name)
                    return {"status": "installed", "name": name, "source": source}
            raise HTTPException(400, "No SKILL.md found in cloned repository")

    elif source.startswith("local+") or os.path.isdir(source):
        # Copy local directory
        path = source[6:] if source.startswith("local+") else source
        if not os.path.isdir(path):
            raise HTTPException(400, f"Directory not found: {path}")
        name = skill_name or os.path.basename(os.path.abspath(path))
        dst = os.path.join(SKILLS_HOME, name)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(path, dst)
        _notify_registry(name)
        return {"status": "installed", "name": name, "source": source}

    else:
        raise HTTPException(400, "Unsupported source format. Use 'git+https://...' or 'local+/path/to/skill'")


@router.delete("/uninstall/{skill_name}", response_model=StatusResponse)
async def uninstall_skill(skill_name: str, _auth: str = Depends(require_admin)):
    """Remove an installed skill."""
    dst = os.path.join(SKILLS_HOME, skill_name)
    if not os.path.isdir(dst):
        raise HTTPException(404, f"Skill '{skill_name}' not found")

    shutil.rmtree(dst)
    # Try to unregister from registry
    try:
        from core.api.facades.skill_tool_facade import get_skill_registry
        reg = get_skill_registry()
        if reg and reg.get(skill_name):
            reg.unregister(skill_name)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return {"status": "uninstalled", "name": skill_name}


def _notify_registry(skill_name: str):
    """Notify the Skill registry to rescan for new skills."""
    try:
        from core.api.facades.skill_tool_facade import get_skill_registry
        reg = get_skill_registry()
        if reg and hasattr(reg, 'scan_folder'):
            reg.scan_folder(SKILLS_HOME)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
