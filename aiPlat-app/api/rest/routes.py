"""
aiPlat-app HTTP API — serves deployed Builder/Studio applications.

Routes:
  /health                          — health check
  /app/sessions/{project_id}       — deployed app static files (SPA)
  /app/sessions/{project_id}/{path} — nested routes for SPA

# NOTE: deployed app static hosting allowed (Layer 3 serves built Web pages;
# not a business API layer — no auth/CRUD/business endpoints)
"""

import os
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from api.auth import AppTokenMiddleware

app = FastAPI(title="aiPlat-app", version="0.1.0")
app.add_middleware(AppTokenMiddleware)

APPS_HOME = Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))) / "apps"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def session_file_under_root(root: Path, relative: str) -> Optional[Path]:
    """Resolved file path inside ``root``, or None on escape / absolute path."""
    rel = relative or ""
    if not rel or rel.startswith(("/", "\\")) or "\\" in rel:
        return None
    root_r = root.resolve()
    target = (root_r / rel).resolve()
    try:
        target.relative_to(root_r)
    except ValueError:
        return None
    return target


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/app/sessions/{project_id}")
async def serve_app_index(project_id: str):
    """Serve the deployed app's index.html."""
    if not _SAFE_ID.fullmatch(project_id or ""):
        raise HTTPException(status_code=400, detail="invalid_project_id")
    app_dir = (APPS_HOME / project_id / "current").resolve()
    index = session_file_under_root(app_dir, "index.html")
    if index is not None and index.is_file():
        return FileResponse(str(index))
    if app_dir.is_dir():
        html_files = sorted(p for p in app_dir.glob("*.html") if p.is_file())
        if html_files:
            return FileResponse(str(html_files[0]))
    raise HTTPException(status_code=404, detail="app not found")


@app.get("/app/media/{app_name}/{task_id}/{path:path}")
async def serve_app_media(app_name: str, task_id: str, path: str):
    """Serve Factory media artifacts (keyframes, etc.) under ~/.aiplat/apps/{app}/media/{task}/."""
    import re as _re
    from fastapi import HTTPException

    if not _re.fullmatch(r"[A-Za-z0-9_-]+", app_name or ""):
        raise HTTPException(status_code=400, detail="invalid_app_name")
    if not _re.fullmatch(r"[A-Za-z0-9_-]+", task_id or ""):
        raise HTTPException(status_code=400, detail="invalid_task_id")
    root = (APPS_HOME / app_name / "media" / task_id).resolve()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="media_not_found")
    file_path = (root / path).resolve()
    try:
        file_path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail="path_escape")
    if file_path.is_file():
        return FileResponse(str(file_path))
    raise HTTPException(status_code=404, detail="file_not_found")


@app.get("/app/sessions/{project_id}/{path:path}")
async def serve_app_files(project_id: str, path: str):
    """Serve static files for the deployed app (JS, CSS, images, etc.)."""
    if not _SAFE_ID.fullmatch(project_id or ""):
        raise HTTPException(status_code=400, detail="invalid_project_id")
    app_dir = (APPS_HOME / project_id / "current").resolve()
    file_path = session_file_under_root(app_dir, path)
    if file_path is None:
        raise HTTPException(status_code=403, detail="path_escape")
    if file_path.is_file():
        return FileResponse(str(file_path))
    index = session_file_under_root(app_dir, "index.html")
    if index is not None and index.is_file():
        return FileResponse(str(index))
    raise HTTPException(status_code=404, detail="file not found")
