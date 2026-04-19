"""
E2E Smoke Test Script (aiPlat core/platform/app/management)

Usage (assumes services are running):
  python3 e2e_smoke.py

Environment:
  AIPLAT_CORE_ENDPOINT=http://localhost:8002
  AIPLAT_PLATFORM_ENDPOINT=http://localhost:8003
  AIPLAT_APP_ENDPOINT=http://localhost:8004
  AIPLAT_MANAGEMENT_ENDPOINT=http://localhost:8000
  AIPLAT_API_KEY=apl_xxx   (optional)
  AIPLAT_TENANT_ID=t_demo  (optional)
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, Optional

import requests


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).rstrip("/")


CORE = _env("AIPLAT_CORE_ENDPOINT", "http://localhost:8002")
PLATFORM = _env("AIPLAT_PLATFORM_ENDPOINT", "http://localhost:8003")
APP = _env("AIPLAT_APP_ENDPOINT", "http://localhost:8004")
MGMT = _env("AIPLAT_MANAGEMENT_ENDPOINT", "http://localhost:8000")

API_KEY = os.getenv("AIPLAT_API_KEY", "").strip()
TENANT_ID = os.getenv("AIPLAT_TENANT_ID", "").strip()
ACTOR_ID = os.getenv("AIPLAT_ACTOR_ID", "").strip()
LLM_PROVIDER = os.getenv("AIPLAT_LLM_PROVIDER", "").strip().lower()
AGENT_MODEL = os.getenv("AIPLAT_AGENT_MODEL", "").strip()
AGENT_REASONER = os.getenv("AIPLAT_AGENT_REASONER", "").strip()


def _headers() -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["X-AIPLAT-API-KEY"] = API_KEY
    # For local dev, allow explicit header identity so permissions work out-of-the-box.
    # If you have a real API key / JWT, set AIPLAT_API_KEY instead.
    if not API_KEY:
        h["X-AIPLAT-ACTOR-ID"] = ACTOR_ID or "admin"
        h["X-AIPLAT-TENANT-ID"] = TENANT_ID or "default"
    else:
        if TENANT_ID:
            h["X-AIPLAT-TENANT-ID"] = TENANT_ID
    return h


def _req(method: str, url: str, *, json_body: Optional[dict] = None, params: Optional[dict] = None) -> Dict[str, Any]:
    r = requests.request(method.upper(), url, headers=_headers(), json=json_body, params=params, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {url} failed: {r.status_code} {r.text}")
    return r.json()


def main() -> int:
    started = time.time()
    print("=== aiPlat E2E smoke ===")
    print(f"core={CORE} platform={PLATFORM} app={APP} mgmt={MGMT}")

    # 1) identity
    who = _req("GET", f"{PLATFORM}/whoami")
    print(f"[whoami] tenant={who.get('tenant_id')} actor={who.get('actor_id')} auth={who.get('auth_type')} request_id={who.get('request_id')}")

    tenant_id = TENANT_ID or who.get("tenant_id") or "default"

    # 2) platform CRUD (sqlite)
    t = _req("POST", f"{PLATFORM}/platform/tenants", json_body={"id": tenant_id, "name": "smoke-tenant"})
    print(f"[platform] tenant created id={t.get('id')}")

    u = _req("POST", f"{PLATFORM}/platform/auth/users", json_body={"username": "smoke-user", "role": "admin"})
    print(f"[platform] user created id={u.get('id')}")

    route = _req("POST", f"{PLATFORM}/platform/gateway/routes", json_body={"name": "smoke-route", "path": "/smoke", "enabled": True})
    print(f"[platform] route created id={route.get('id')}")

    # 3) app CRUD (sqlite)
    ch = _req("POST", f"{APP}/app/channels", json_body={"name": "smoke-channel", "type": "webhook"})
    print(f"[app] channel created id={ch.get('id')}")

    sess = _req("POST", f"{APP}/app/sessions", json_body={"channel_id": ch.get("id"), "user_id": str(u.get('id'))})
    print(f"[app] session created id={sess.get('id')}")

    # 4) agents CRUD via platform -> core workspace agents
    created = _req(
        "POST",
        f"{PLATFORM}/api/v1/agents",
        json_body={
            "name": f"smoke-agent-{int(time.time())}",
            "description": "e2e smoke",
            "agent_type": "base",
            # If you want real LLM runs in smoke, set:
            #   AIPLAT_LLM_PROVIDER=deepseek
            #   AIPLAT_LLM_API_KEY=...
            # Optionally override model name via AIPLAT_AGENT_MODEL / AIPLAT_LLM_MODEL.
            "config": {
                "model": (
                    AGENT_MODEL
                    or AGENT_REASONER
                    or ("deepseek-reasoner" if LLM_PROVIDER == "deepseek" else None)
                )
            }
            if (AGENT_MODEL or AGENT_REASONER or LLM_PROVIDER == "deepseek")
            else {},
        },
    )
    agent_id = created.get("id")
    if not agent_id:
        raise RuntimeError(f"agent create returned no id: {created}")
    print(f"[agent] created id={agent_id}")

    agents = _req("GET", f"{PLATFORM}/api/v1/agents", params={"limit": 50})
    if not any(a.get("id") == agent_id for a in (agents.get("agents") or [])):
        raise RuntimeError("agent not found in list")
    print(f"[agent] list ok total={agents.get('total')}")

    # 5) execute agent (platform -> core gateway_execute)
    exec_res = _req(
        "POST",
        f"{PLATFORM}/api/v1/agents/{agent_id}/execute",
        json_body={"input": "hello", "session_id": sess.get("id"), "context": {"tenant_id": tenant_id}},
    )
    run_id = exec_res.get("run_id")
    if not run_id:
        raise RuntimeError(f"execute returned no run_id: {exec_res}")
    print(f"[execute] run_id={run_id} status={exec_res.get('status')} ok={exec_res.get('ok')}")

    # 6) wait run (core)
    waited = _req("POST", f"{CORE}/api/core/runs/{run_id}/wait", json_body={"timeout_ms": 60000, "after_seq": 0})
    run = waited.get("run") or {}
    print(f"[run] status={run.get('status')} done={waited.get('done')}")
    if str(run.get("status")) != "completed":
        raise RuntimeError(f"agent run not completed: {run}")

    # 7) observe (core events + audit via management proxy)
    events = _req("GET", f"{CORE}/api/core/runs/{run_id}/events", params={"after_seq": 0, "limit": 50})
    print(f"[events] count={len(events.get('items') or [])}")

    # 8) tool run via platform gateway (guaranteed non-LLM path) to validate run+audit pipeline
    tool_exec = _req(
        "POST",
        f"{PLATFORM}/platform/gateway/execute",
        json_body={
            "channel": "e2e",
            "kind": "tool",
            "target_id": "calculator",
            "session_id": sess.get("id"),
            "payload": {"input": {"expression": "1+1"}, "context": {"tenant_id": tenant_id}},
        },
    )
    tool_run_id = tool_exec.get("run_id")
    if not tool_run_id:
        raise RuntimeError(f"tool execute returned no run_id: {tool_exec}")
    print(f"[tool] run_id={tool_run_id} status={tool_exec.get('status')} ok={tool_exec.get('ok')}")

    tool_waited = _req("POST", f"{CORE}/api/core/runs/{tool_run_id}/wait", json_body={"timeout_ms": 60000, "after_seq": 0})
    tool_run = tool_waited.get("run") or {}
    if str(tool_run.get("status")) not in ("completed",):
        raise RuntimeError(f"tool run not completed: {tool_run}")
    print(f"[tool-run] status={tool_run.get('status')} done={tool_waited.get('done')}")

    audit = _req("GET", f"{MGMT}/api/audit/logs", params={"run_id": tool_run_id, "action": "gateway_execute", "limit": 20, "offset": 0})
    print(f"[audit] count={len(audit.get('items') or [])}")
    if len(audit.get("items") or []) < 1:
        raise RuntimeError("expected at least 1 audit log for gateway_execute")

    print(f"✓ PASS in {time.time() - started:.2f}s")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"✗ FAIL: {e}")
        sys.exit(1)
