"""
PipelineOrchestratorClient — Platform → Core HTTP client.

Encapsulates HTTP call details, retry, and timeout for pipeline
operations. BuilderProjectService depends on this interface only,
decoupled from Core's internal implementation.

Usage:
    client = PipelineOrchestratorClient()
    result = await client.trigger_run("prj_abc", config={...})
    state = await client.get_state("prj_abc")
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

_log = logging.getLogger("aiplat.pipeline.client")

_CORE_URL = os.getenv("AIPLAT_CORE_URL", "http://127.0.0.1:8002").rstrip("/")
_REQUEST_TIMEOUT = 60.0  # trigger/cancel: generous timeout (core startup is slow)
_POLL_TIMEOUT = 15.0  # state poll: slightly longer


class PipelineOrchestratorClient:
    """Platform-side client for Core pipeline API."""

    def __init__(self, base_url: str = _CORE_URL):
        self._base_url = base_url
        self._api_prefix = f"{base_url}/api/core/pipeline"

    async def trigger_run(
        self,
        project_id: str,
        config: Dict[str, Any],
        *,
        timeout: float = _REQUEST_TIMEOUT,
    ) -> Dict[str, Any]:
        """Trigger a pipeline run. Returns {status, run_id} immediately."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self._api_prefix}/run",
                    json={"project_id": project_id, "config": config},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException:
            _log.warning("trigger_run timeout for %s", project_id)
            return {"status": "timeout", "detail": "Core unavailable"}
        except httpx.HTTPStatusError as e:
            _log.warning("trigger_run HTTP %d for %s", e.response.status_code, project_id)
            return {"status": "error", "detail": f"HTTP {e.response.status_code}"}
        except Exception as e:
            _log.warning("trigger_run failed for %s: %s", project_id, str(e)[:200])
            return {"status": "error", "detail": str(e)[:200]}

    async def get_state(
        self,
        project_id: str,
        *,
        timeout: float = _POLL_TIMEOUT,
    ) -> Dict[str, Any]:
        """Read pipeline state for frontend polling."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(f"{self._api_prefix}/{project_id}/state")
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException:
            _log.debug("get_state timeout for %s", project_id)
            return {"project_id": project_id, "phase": "idle", "state": {}}
        except Exception as e:
            _log.debug("get_state failed for %s: %s", project_id, str(e)[:200])
            return {"project_id": project_id, "phase": "idle", "state": {}}

    async def cancel_run(
        self,
        project_id: str,
        *,
        timeout: float = _REQUEST_TIMEOUT,
    ) -> Dict[str, Any]:
        """Cancel a running pipeline."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{self._api_prefix}/{project_id}/cancel")
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            _log.warning("cancel_run failed for %s: %s", project_id, str(e)[:200])
            return {"status": "error", "detail": str(e)[:200]}

    async def resolve_hitl(
        self,
        project_id: str,
        action: str,
        feedback: str = "",
        *,
        timeout: float = _REQUEST_TIMEOUT,
    ) -> Dict[str, Any]:
        """Resolve a HITL pause on Core — approve or reject."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/api/core/pipeline/{project_id}/hitl-resolve",
                    json={"action": action, "feedback": feedback},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            _log.warning("resolve_hitl failed for %s: %s", project_id, str(e)[:200])
            return {"status": "error", "detail": str(e)[:200]}
