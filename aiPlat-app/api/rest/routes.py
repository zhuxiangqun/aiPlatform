"""
aiPlat-app HTTP API (minimal bootstrap)

This is a lightweight FastAPI server for the app layer.
Currently provides only a /health endpoint for layer health monitoring.
API endpoints are added as the app layer matures.
"""

from fastapi import FastAPI

app = FastAPI(title="aiPlat-app", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "healthy"}
