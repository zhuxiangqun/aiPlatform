"""
aiPlat-app HTTP API (minimal bootstrap)

This is a lightweight FastAPI server for the app layer.
# NOTE: minimal health-only bootstrap — allowed per constitution. All business
# routes should be served through platform layer. Currently provides only a
# /health endpoint for layer health monitoring.
"""

from fastapi import FastAPI

app = FastAPI(title="aiPlat-app", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "healthy"}
