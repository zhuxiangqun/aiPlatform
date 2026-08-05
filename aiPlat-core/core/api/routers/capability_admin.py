"""
Core capability admin API — read/scan/manage core_guarantees in AIPLAT_CAPABILITIES.md.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import subprocess, os, json

router = APIRouter(prefix="/capabilities", tags=["capabilities"])

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "scripts")

def _run_scan() -> Dict[str, Any]:
    """Run scan_inherited_capabilities.py and return parsed JSON."""
    script = os.path.join(SCRIPTS_DIR, "scan_inherited_capabilities.py")
    try:
        result = subprocess.run(
            ["python3", script, "--json"],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.join(SCRIPTS_DIR, "..")
        )
        return json.loads(result.stdout)
    except Exception as e:
        return {"error": str(e)}


def _read_frontmatter() -> Dict[str, Any]:
    """Read core_guarantees from AIPLAT_CAPABILITIES.md frontmatter."""
    caps_path = os.path.join(SCRIPTS_DIR, "..", "AIPLAT_CAPABILITIES.md")
    with open(caps_path) as f:
        lines = f.readlines()
    
    in_fm = False
    fm_lines = []
    for line in lines:
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
                continue
            else:
                break
        if in_fm:
            fm_lines.append(line)
    
    # Simple YAML parse for core_guarantees
    auto_list = []
    cfg_list = []
    in_auto = in_cfg = False
    current = None
    for line in fm_lines:
        stripped = line.strip()
        if stripped.startswith("auto:"):
            in_auto, in_cfg = True, False
        elif stripped.startswith("configurable:"):
            in_auto, in_cfg = False, True
        elif in_auto and stripped.startswith("- id:"):
            current = {"id": stripped.split("- id:")[1].strip(), "paths": []}
            auto_list.append(current)
        elif in_cfg and stripped.startswith("- id:"):
            current = {"id": stripped.split("- id:")[1].strip()}
            cfg_list.append(current)
        elif in_auto and current and stripped.startswith("- "):
            current["paths"].append(stripped[2:])
        elif in_cfg and current and ":" in stripped:
            key, _, val = stripped.partition(":")
            current[key.strip()] = val.strip()
    
    return {"auto": auto_list, "configurable": cfg_list}


class GuaranteeUpdate(BaseModel):
    auto: Optional[List[Dict[str, Any]]] = None
    configurable: Optional[List[Dict[str, Any]]] = None


@router.get("/scan")
async def get_scan():
    """Return latest capability scan results."""
    return _run_scan()


@router.get("/guarantees")
async def get_guarantees():
    """Return current core_guarantees from frontmatter."""
    return _read_frontmatter()


@router.post("/rescan")
async def trigger_rescan():
    """Re-run scan and merge into AIPLAT_CAPABILITIES.md."""
    script = os.path.join(SCRIPTS_DIR, "scan_inherited_capabilities.py")
    try:
        result = subprocess.run(
            ["python3", script, "--merge"],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.join(SCRIPTS_DIR, "..")
        )
        return {"status": "ok", "output": result.stdout, "error": result.stderr}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
