"""
sys_workflow_call — Core syscall for dynamic workflow execution.

Allows an agent in the ReAct loop to trigger a workflow by ID.
Calls the platform's workflow execution endpoint via HTTP.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx


async def sys_workflow_call(
    workflow_id: str,
    *,
    run_name: str = "",
    trace_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Trigger a workflow execution via the platform API.

    Returns:
        {
            "success": bool,
            "workflow_id": str,
            "run_id": str | None,
            "project_id": str | None,
            "error": str | None,
        }
    """
    platform_url = os.getenv("AIPLAT_PLATFORM_URL", "http://localhost:8003")
    url = f"{platform_url}/platform/workflows/{workflow_id}/execute"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json={"name": run_name or f"agent-triggered-{workflow_id}"},
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code >= 400:
                detail = ""
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    detail = resp.text or f"HTTP {resp.status_code}"
                return {
                    "success": False,
                    "workflow_id": workflow_id,
                    "run_id": None,
                    "project_id": None,
                    "error": str(detail),
                }
            data = resp.json()
            return {
                "success": True,
                "workflow_id": workflow_id,
                "run_id": data.get("run_id") or data.get("project_id"),
                "project_id": data.get("project_id"),
                "error": None,
            }
    except Exception as e:
        return {
            "success": False,
            "workflow_id": workflow_id,
            "run_id": None,
            "project_id": None,
            "error": str(e),
        }
