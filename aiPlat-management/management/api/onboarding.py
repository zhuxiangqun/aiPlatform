"""
Onboarding API (management layer)

Goals (MVP):
- Guide first-time setup via a simple wizard:
  1) Configure LLM adapter (persisted in core ExecutionStore)
  2) Check layer health (infra/core/platform/app)
  3) Trigger full-chain e2e smoke (reuses /diagnostics/e2e/smoke)
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Any, Dict, Optional, List


router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/state")
async def get_onboarding_state(request: Request) -> Dict[str, Any]:
    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")

    # Health summary
    health_checkers = request.app.state.health_checkers
    health: Dict[str, Any] = {}
    for layer, checker in health_checkers.items():
        try:
            health[layer] = await checker.get_health()
        except Exception as e:
            health[layer] = {"status": "unhealthy", "message": str(e)}

    # Current adapters
    try:
        adapters = await core_client.list_adapters(limit=100, offset=0)
    except Exception:
        adapters = {"adapters": [], "total": 0}

    # Core onboarding state (default routing, tenants, secrets)
    try:
        core_state = await core_client.get_onboarding_state()
    except Exception:
        core_state = {}

    return {"health": health, "adapters": adapters, "core_state": core_state}


@router.post("/default-llm")
async def set_default_llm(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")
    return await core_client.set_default_llm(body or {})


@router.post("/init-tenant")
async def init_tenant(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")
    return await core_client.init_tenant(body or {})


@router.post("/rotate-adapter-key")
async def rotate_adapter_key(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rotate adapter api key.
    Body:
      { "adapter_id": "...", "api_key": "..." }
    """
    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")
    adapter_id = str((body or {}).get("adapter_id") or "").strip()
    api_key = str((body or {}).get("api_key") or "").strip()
    if not adapter_id:
        raise HTTPException(status_code=400, detail="missing_adapter_id")
    if not api_key:
        raise HTTPException(status_code=400, detail="missing_api_key")
    await core_client.update_adapter(adapter_id, {"api_key": api_key})
    return {"status": "rotated", "adapter_id": adapter_id}


@router.post("/autosmoke")
async def set_autosmoke(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")
    return await core_client.set_autosmoke(body or {})


@router.get("/secrets/status")
async def get_secrets_status(request: Request) -> Dict[str, Any]:
    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")
    return await core_client.get_secrets_status()


@router.post("/secrets/migrate")
async def migrate_secrets(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")
    return await core_client.migrate_secrets(body or {})


@router.post("/strong-gate")
async def set_strong_gate(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")
    return await core_client.set_strong_gate(body or {})


@router.post("/exec-backend")
async def set_exec_backend(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="core_client not initialized")
    return await core_client.set_exec_backend(body or {})


@router.post("/trusted-skill-keys")
async def set_trusted_skill_keys(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="core_client not initialized")
    b = body or {}
    # Support Doctor ActionableFixes: keys_json (string) -> keys (list)
    if isinstance(b.get("keys_json"), str) and "keys" not in b:
        try:
            import json

            b["keys"] = json.loads(b.get("keys_json") or "[]")
        except Exception:
            b["keys"] = []
        try:
            b.pop("keys_json", None)
        except Exception:
            pass
    return await core_client.set_trusted_skill_keys(b)


@router.post("/llm-adapter")
async def configure_llm_adapter(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an adapter + add optional models + test connection.

    Body:
      {
        "name": "DeepSeek",
        "provider": "OpenAI",
        "api_key": "...",
        "api_base_url": "https://api.deepseek.com",
        "description": "",
        "models": ["deepseek-reasoner", "deepseek-chat"]
      }
    """
    core_client = getattr(request.app.state, "core_client", None)
    if not core_client:
        raise HTTPException(status_code=503, detail="Core client not initialized")

    name = str((body or {}).get("name") or "default").strip()
    provider = str((body or {}).get("provider") or "").strip()
    api_key = str((body or {}).get("api_key") or "").strip()
    api_base_url = str((body or {}).get("api_base_url") or "").strip()
    description = str((body or {}).get("description") or "").strip()
    models = (body or {}).get("models") or []

    if not provider:
        raise HTTPException(status_code=400, detail="missing_provider")
    if not api_key:
        raise HTTPException(status_code=400, detail="missing_api_key")
    if not api_base_url:
        raise HTTPException(status_code=400, detail="missing_api_base_url")

    created = await core_client.create_adapter(
        {
            "name": name,
            "provider": provider,
            "api_key": api_key,
            "api_base_url": api_base_url,
            "description": description,
        }
    )
    adapter_id = created.get("adapter_id")
    if not adapter_id:
        raise HTTPException(status_code=500, detail="create_adapter_failed")

    # Add models (best-effort)
    added: List[Dict[str, Any]] = []
    if isinstance(models, list):
        for m in models:
            mn = str(m or "").strip()
            if not mn:
                continue
            try:
                await core_client.add_adapter_model(adapter_id, {"name": mn})
                added.append({"name": mn, "status": "added"})
            except Exception as e:
                added.append({"name": mn, "status": "skipped", "reason": str(e)})

    # Test connection (best-effort)
    try:
        test = await core_client.test_adapter(adapter_id, {})
    except Exception as e:
        test = {"success": False, "error": str(e)}

    return {"status": "configured", "adapter_id": adapter_id, "models": added, "test": test}
