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
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI(title="aiPlat-app", version="0.1.0")

APPS_HOME = Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))) / "apps"


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/app/sessions/{project_id}")
async def serve_app_index(project_id: str):
    """Serve the deployed app's index.html."""
    app_dir = APPS_HOME / project_id / "current"
    index = app_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    # Fallback: serve any HTML file in the directory
    html_files = sorted(app_dir.glob("*.html"))
    if html_files:
        return FileResponse(str(html_files[0]))
    return {"error": "app not found", "project_id": project_id}, 404


@app.get("/app/sessions/{project_id}/{path:path}")
async def serve_app_files(project_id: str, path: str):
    """Serve static files for the deployed app (JS, CSS, images, etc.)."""
    app_dir = APPS_HOME / project_id / "current"
    file_path = app_dir / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    # SPA fallback: serve index.html for client-side routing
    index = app_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"error": "file not found"}, 404
