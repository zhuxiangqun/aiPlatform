"""
E2E test fixtures — shared infrastructure for end-to-end smoke tests.

Provides:
  - live_server: skip test if core service is unreachable
  - audit_log_reader: query execution_store for recent audit events
  - agent_executor: submit task → poll until complete → return result
"""

import os
import time
import pytest
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

CORE_URL = os.getenv("AIPLAT_CORE_URL", "http://localhost:8001")


def _is_live() -> bool:
    try:
        r = urllib.request.urlopen(f"{CORE_URL}/health", timeout=5)
        return r.status == 200
    except Exception:
        return False


@pytest.fixture(scope="session")
def live_server_url() -> Optional[str]:
    """Return the live server URL, or skip all tests if unreachable."""
    if not _is_live():
        pytest.skip(f"Core server not reachable at {CORE_URL}")
    return CORE_URL


@pytest.fixture(scope="function")
async def audit_log_reader(live_server_url):
    """Read recent audit log entries from the execution store.
    
    Returns an async function audit_log_read(keyword, limit=50) → List[dict].
    Requires the server to be running with execution_store initialized.
    """
    import httpx
    
    async def read(keyword: str = "", limit: int = 50) -> list:
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(
                    f"{live_server_url}/api/core/diagnostics/audit",
                    params={"keyword": keyword, "limit": str(limit)}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("entries", data.get("items", []))
            except Exception:
                pass
        return []
    
    return read


@pytest.fixture(scope="function")
async def agent_executor(live_server_url):
    """Execute an agent task and return the result.
    
    Returns a coroutine execute(agent_id, prompt, **kwargs) → dict with
    {success, output, run_id, error}.
    """
    import httpx
    
    async def execute(agent_id: str = "conversational_agent",
                      prompt: str = "Hello",
                      **kwargs) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=120) as client:
            body = {
                "input": {"text": prompt},
                "context": {"tenant_id": "default"},
                "user_id": "e2e-test",
                "session_id": f"e2e-{int(time.time())}",
                "config": {"model": kwargs.get("model", "")},
                **kwargs,
            }
            
            # Submit task
            resp = await client.post(
                f"{live_server_url}/api/core/workspace/agents/{agent_id}/execute",
                json=body
            )
            if resp.status_code != 200:
                return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
            
            data = resp.json()
            run_id = data.get("run_id", "")
            
            # Poll until complete (max 60 seconds)
            for _ in range(30):
                await __import__('asyncio').sleep(2)
                poll = await client.get(
                    f"{live_server_url}/api/core/runs/{run_id}"
                )
                if poll.status_code == 200:
                    result = poll.json()
                    status = result.get("status", "")
                    if status in ("completed", "failed", "error"):
                        return {
                            "success": status == "completed",
                            "output": result.get("output", {}),
                            "run_id": run_id,
                            "status": status,
                            "error": result.get("error", ""),
                        }
            
            return {"success": False, "run_id": run_id, "error": "timeout — task did not complete in 60s"}
    
    return execute


@pytest.fixture(scope="function")
def mock_failing_tool(live_server_url):
    """Marker fixture — indicates a test needs a mock failing tool.
    
    Actual mock tool registration requires server-side setup.
    Tests using this fixture should be skipped if mock registration API is not available.
    """
    import httpx
    
    async def check_registration_api() -> bool:
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                resp = await client.get(f"{live_server_url}/api/core/tools")
                return resp.status_code == 200
            except Exception:
                return False
    
    return check_registration_api
