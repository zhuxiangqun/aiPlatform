"""
Production-grade full-chain E2E smoke runner.

Runs through:
- platform identity + CRUD (tenant/user/route)
- app CRUD (channel/session)
- agent create/execute via platform (proxy core workspace agents)
- tool execute via platform gateway (proxy core gateway)
- audit logs (core + optional management proxy)

And then CLEANUP immediately (best-effort).

Secrets:
- DeepSeek key MUST come from env (DEEPSEEK_API_KEY / AIPLAT_LLM_API_KEY), never from request body.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx


def _env(name: str, default: str) -> str:
    return (os.getenv(name) or default).rstrip("/")


@dataclass
class SmokeConfig:
    platform_url: str = field(default_factory=lambda: _env("AIPLAT_PLATFORM_ENDPOINT", "http://localhost:8003"))
    app_url: str = field(default_factory=lambda: _env("AIPLAT_APP_ENDPOINT", "http://localhost:8004"))
    management_url: str = field(default_factory=lambda: _env("AIPLAT_MANAGEMENT_ENDPOINT", "http://localhost:8000"))
    timeout_s: float = 30.0


def _headers(*, actor_id: str, tenant_id: str, api_key: Optional[str] = None, request_id: Optional[str] = None) -> Dict[str, str]:
    h: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        h["X-AIPLAT-API-KEY"] = api_key
    else:
        h["X-AIPLAT-ACTOR-ID"] = actor_id
        h["X-AIPLAT-TENANT-ID"] = tenant_id
    if request_id:
        h["X-AIPLAT-REQUEST-ID"] = request_id
    return h


async def _req(client: httpx.AsyncClient, method: str, url: str, *, headers: Dict[str, str], json: Optional[dict] = None, params: Optional[dict] = None) -> Dict[str, Any]:
    resp = await client.request(method.upper(), url, headers=headers, json=json, params=params)
    resp.raise_for_status()
    if resp.headers.get("content-type", "").startswith("application/json"):
        return resp.json()
    return {"text": resp.text}


async def run_smoke_e2e(*, payload: Dict[str, Any], execution_store: Any = None) -> Dict[str, Any]:
    """
    Execute a full-chain smoke and cleanup immediately.

    payload:
      - actor_id (default: admin)
      - tenant_id (default: ops_smoke)
      - agent_model (default: deepseek-reasoner when deepseek provider, else unchanged)
      - mode: "full" | "minimal" (reserved)
    """
    cfg = SmokeConfig()
    actor_id = str(payload.get("actor_id") or "admin")
    tenant_id = str(payload.get("tenant_id") or "ops_smoke")
    agent_model = payload.get("agent_model")  # optional
    api_key = payload.get("api_key")  # optional; if omitted, use header identity

    started = time.time()
    evidence: Dict[str, Any] = {"steps": [], "created": {}}

    # Created resources (for cleanup)
    created_tenant_id: Optional[str] = None
    created_user_id: Optional[str] = None
    created_route_id: Optional[str] = None
    created_channel_id: Optional[str] = None
    created_session_id: Optional[str] = None
    created_agent_id: Optional[str] = None
    tool_run_id: Optional[str] = None

    async with httpx.AsyncClient(timeout=cfg.timeout_s) as client:
        h = _headers(actor_id=actor_id, tenant_id=tenant_id, api_key=api_key)

        try:
            # 1) whoami
            who = await _req(client, "GET", f"{cfg.platform_url}/whoami", headers=h)
            evidence["steps"].append({"name": "platform.whoami", "ok": True, "whoami": who})

            # 2) platform tenant/user/route
            t = await _req(client, "POST", f"{cfg.platform_url}/platform/tenants", headers=h, json={"id": tenant_id, "name": "ops-smoke"})
            created_tenant_id = t.get("id") or tenant_id
            evidence["created"]["tenant_id"] = created_tenant_id
            evidence["steps"].append({"name": "platform.tenants.create", "ok": True, "tenant_id": created_tenant_id})

            u = await _req(client, "POST", f"{cfg.platform_url}/platform/auth/users", headers=h, json={"username": f"ops-smoke-{int(time.time())}", "role": "admin"})
            created_user_id = u.get("id")
            evidence["created"]["user_id"] = created_user_id
            evidence["steps"].append({"name": "platform.users.create", "ok": True, "user_id": created_user_id})

            r = await _req(client, "POST", f"{cfg.platform_url}/platform/gateway/routes", headers=h, json={"name": f"ops-smoke-{int(time.time())}", "path": "/ops-smoke", "enabled": True})
            created_route_id = r.get("id")
            evidence["created"]["route_id"] = created_route_id
            evidence["steps"].append({"name": "platform.routes.create", "ok": True, "route_id": created_route_id})

            # 3) app channel/session
            ch = await _req(client, "POST", f"{cfg.app_url}/app/channels", headers=h, json={"name": "ops-smoke", "type": "webhook"})
            created_channel_id = ch.get("id")
            evidence["created"]["channel_id"] = created_channel_id
            evidence["steps"].append({"name": "app.channels.create", "ok": True, "channel_id": created_channel_id})

            sess = await _req(client, "POST", f"{cfg.app_url}/app/sessions", headers=h, json={"channel_id": created_channel_id, "user_id": str(created_user_id or "admin")})
            created_session_id = sess.get("id")
            evidence["created"]["session_id"] = created_session_id
            evidence["steps"].append({"name": "app.sessions.create", "ok": True, "session_id": created_session_id})

            # 4) agent create + execute (via platform -> core workspace agents)
            agent_body: Dict[str, Any] = {
                "name": f"ops-smoke-agent-{int(time.time())}",
                "description": "ops smoke e2e",
                "agent_type": "base",
                "config": {},
            }
            if isinstance(agent_model, str) and agent_model.strip():
                agent_body["config"] = {"model": agent_model.strip()}
            created_agent = await _req(client, "POST", f"{cfg.platform_url}/api/v1/agents", headers=h, json=agent_body)
            created_agent_id = created_agent.get("id")
            evidence["created"]["agent_id"] = created_agent_id
            evidence["steps"].append({"name": "platform.agents.create", "ok": True, "agent_id": created_agent_id})

            exec_res = await _req(
                client,
                "POST",
                f"{cfg.platform_url}/api/v1/agents/{created_agent_id}/execute",
                headers=h,
                json={"input": "hello", "session_id": created_session_id, "context": {"tenant_id": tenant_id}},
            )
            run_id = exec_res.get("run_id")
            evidence["steps"].append({"name": "platform.agents.execute", "ok": True, "run_id": run_id, "exec": exec_res})

            # We can't call core wait directly here without core endpoint; rely on platform execute result + run_id existence.
            # Ops can further inspect run via management/core runs API.
            if not run_id:
                raise RuntimeError(f"agent execute returned no run_id: {exec_res}")

            # 5) tool execute via platform gateway (should write audit)
            tool_exec = await _req(
                client,
                "POST",
                f"{cfg.platform_url}/platform/gateway/execute",
                headers=h,
                json={
                    "channel": "ops_smoke",
                    "kind": "tool",
                    "target_id": "calculator",
                    "session_id": created_session_id,
                    "payload": {"input": {"expression": "1+1"}, "context": {"tenant_id": tenant_id}},
                },
            )
            tool_run_id = tool_exec.get("run_id")
            evidence["steps"].append({"name": "platform.gateway.tool_execute", "ok": True, "run_id": tool_run_id, "exec": tool_exec})

            # 6) audit check: prefer core store if available; also attempt management proxy (best-effort)
            audit_count = None
            if execution_store is not None and tool_run_id:
                try:
                    logs = await execution_store.list_audit_logs(run_id=str(tool_run_id), action="gateway_execute", limit=5, offset=0)
                    audit_count = len(logs.get("items") or [])
                except Exception:
                    audit_count = None
            evidence["audit_count_core"] = audit_count

            try:
                if tool_run_id:
                    a = await _req(client, "GET", f"{cfg.management_url}/api/audit/logs", headers=h, params={"run_id": tool_run_id, "action": "gateway_execute", "limit": 5, "offset": 0})
                    evidence["audit_count_mgmt"] = len(a.get("items") or [])
            except Exception:
                pass

            ok = True
            return {
                "ok": ok,
                "started_at": started,
                "duration_s": time.time() - started,
                "evidence": evidence,
            }
        finally:
            # Cleanup (best-effort, do not fail the whole run due to cleanup issues)
            cleanup: Dict[str, Any] = {"attempted": [], "errors": []}
            try:
                if created_agent_id:
                    cleanup["attempted"].append("platform.agents.delete")
                    try:
                        await _req(client, "DELETE", f"{cfg.platform_url}/api/v1/agents/{created_agent_id}", headers=h)
                    except Exception as e:
                        cleanup["errors"].append({"step": "agents.delete", "error": str(e)})
                if created_session_id:
                    cleanup["attempted"].append("app.sessions.end")
                    try:
                        await _req(client, "POST", f"{cfg.app_url}/app/sessions/{created_session_id}/end", headers=h)
                    except Exception as e:
                        cleanup["errors"].append({"step": "sessions.end", "error": str(e)})
                if created_channel_id:
                    cleanup["attempted"].append("app.channels.delete")
                    try:
                        await _req(client, "DELETE", f"{cfg.app_url}/app/channels/{created_channel_id}", headers=h)
                    except Exception as e:
                        cleanup["errors"].append({"step": "channels.delete", "error": str(e)})
                if created_route_id:
                    cleanup["attempted"].append("platform.routes.delete")
                    try:
                        await _req(client, "DELETE", f"{cfg.platform_url}/platform/gateway/routes/{created_route_id}", headers=h)
                    except Exception as e:
                        cleanup["errors"].append({"step": "routes.delete", "error": str(e)})
                if created_user_id:
                    cleanup["attempted"].append("platform.users.delete")
                    try:
                        await _req(client, "DELETE", f"{cfg.platform_url}/platform/auth/users/{created_user_id}", headers=h)
                    except Exception as e:
                        cleanup["errors"].append({"step": "users.delete", "error": str(e)})
                if created_tenant_id:
                    cleanup["attempted"].append("platform.tenants.delete")
                    try:
                        await _req(client, "DELETE", f"{cfg.platform_url}/platform/tenants/{created_tenant_id}", headers=h)
                    except Exception as e:
                        cleanup["errors"].append({"step": "tenants.delete", "error": str(e)})
            finally:
                evidence["cleanup"] = cleanup

