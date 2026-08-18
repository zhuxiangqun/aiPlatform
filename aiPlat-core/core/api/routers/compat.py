"""
compat.py — Backward-compatibility + evaluation + playground routes.

Evaluation and playground endpoints are fully implemented.
Repairs/workbench stubs delegate to existing handlers.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Request

logger = logging.getLogger("aiplat.compat")

router = APIRouter(tags=["compat"])


# ════════════════════════════════════════════════════════════
# Evaluation — powered by LearningManager
# ════════════════════════════════════════════════════════════

async def _get_learning_manager():
    from core.learning.manager import LearningManager
    return LearningManager()


@router.get("/evaluation/overview")
async def compat_evaluation_overview():
    """Evaluation dashboard overview — aggregates learning artifacts."""
    try:
        mgr = await _get_learning_manager()
        overview = await mgr.get_overview()
        return {"status": "ok", **overview}
    except Exception as e:
        logger.debug("evaluation overview failed", exc_info=True)
        return {"status": "error", "message": str(e)[:200]}


@router.post("/evaluation/policy")
async def compat_evaluation_policy_set(body: Dict[str, Any]):
    """Create or update an evaluation policy artifact."""
    try:
        mgr = await _get_learning_manager()
        artifact = await mgr.create_artifact(
            kind="evaluation_policy",
            target_type=body.get("target_type", "policy"),
            target_id=body.get("target_id", "default"),
            version=str(int(__import__("time").time())),
            payload=body.get("policy", body),
            status="published",
        )
        return {"status": "ok", "artifact_id": artifact.artifact_id, "policy": body.get("policy", body)}
    except Exception as e:
        logger.debug("evaluation policy creation failed", exc_info=True)
        return {"status": "error", "message": str(e)[:200]}


@router.get("/evaluation/policy/latest")
async def compat_evaluation_policy_latest():
    """Get the latest evaluation policy."""
    try:
        mgr = await _get_learning_manager()
        artifacts = await mgr.list_artifacts(
            kind="evaluation_policy",
            status="published",
            limit=1,
        )
        if artifacts:
            return {"status": "ok", "policy": artifacts[0].get("payload", {}).get("policy", artifacts[0])}
        return {"status": "ok", "message": "No evaluation policy configured yet."}
    except Exception as e:
        logger.debug("evaluation policy fetch failed", exc_info=True)
        return {"status": "error", "message": str(e)[:200]}


@router.post("/scopes/{scope_id}/evaluation/policy")
async def compat_scoped_evaluation_policy_set(scope_id: str, body: Dict[str, Any]):
    """Create/update scoped evaluation policy."""
    try:
        mgr = await _get_learning_manager()
        artifact = await mgr.create_artifact(
            kind="evaluation_policy",
            target_type="policy",
            target_id=f"scope:{scope_id}",
            version=str(int(__import__("time").time())),
            payload={"scope_id": scope_id, "policy": body.get("policy", body)},
            status="published",
        )
        return {"status": "ok", "artifact_id": artifact.artifact_id, "scope_id": scope_id}
    except Exception as e:
        logger.debug("scoped policy creation failed", exc_info=True)
        return {"status": "error", "message": str(e)[:200]}


@router.get("/scopes/{scope_id}/evaluation/policy/latest")
async def compat_scoped_evaluation_policy_latest(scope_id: str):
    """Get latest scoped evaluation policy."""
    try:
        mgr = await _get_learning_manager()
        artifacts = await mgr.list_artifacts(
            kind="evaluation_policy",
            target_id=f"scope:{scope_id}",
            status="published",
            limit=1,
        )
        if artifacts:
            return {"status": "ok", "scope_id": scope_id, "policy": artifacts[0].get("payload", {}).get("policy", artifacts[0])}
        return {"status": "ok", "scope_id": scope_id, "message": "No policy yet."}
    except Exception as e:
        logger.debug("scoped policy fetch failed", exc_info=True)
        return {"status": "error", "message": str(e)[:200]}


# ════════════════════════════════════════════════════════════
# Diagnostics playground — powered by infra ModelManager + LLM
# ════════════════════════════════════════════════════════════

def _list_models() -> list[dict]:
    """List installed models + market catalog for playground comparison."""
    result = []
    installed_names = set()

    # 1. Installed models (local Ollama + configured API)
    try:
        from infra.management.model.manager import ModelManager as InfraModelManager
        mgr = InfraModelManager()
        models = mgr.select_by_purpose_list("chat")
        for m in models:
            name = m if isinstance(m, str) else getattr(m, "name", str(m))
            installed_names.add(name)
            result.append({
                "name": name, "available": True,
                "category": "installed",
            })
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    # 2. Market catalog — popular models user can add
    _CATALOG = [
        {"name": "claude-sonnet-4-20250514", "provider": "Anthropic", "context": "200K", "strength": "复杂推理、代码生成、长上下文"},
        {"name": "claude-3.5-haiku", "provider": "Anthropic", "context": "200K", "strength": "快速轻量、成本低"},
        {"name": "gpt-4o", "provider": "OpenAI", "context": "128K", "strength": "多模态、通用能力强"},
        {"name": "gpt-4o-mini", "provider": "OpenAI", "context": "128K", "strength": "高性价比、快速响应"},
        {"name": "gemini-2.5-flash", "provider": "Google", "context": "1M", "strength": "超长上下文、多模态"},
        {"name": "gemini-2.5-pro", "provider": "Google", "context": "1M", "strength": "最强推理、超长上下文"},
        {"name": "llama-4-maverick", "provider": "Meta", "context": "128K", "strength": "开源旗舰、多语言"},
        {"name": "llama-4-scout", "provider": "Meta", "context": "10M", "strength": "开源超长上下文"},
        {"name": "mixtral-8x22b", "provider": "Mistral", "context": "64K", "strength": "开源MoE、函数调用"},
        {"name": "mistral-large", "provider": "Mistral", "context": "128K", "strength": "多语言、代码能力"},
        {"name": "qwen-max", "provider": "Alibaba", "context": "128K", "strength": "中文能力强、性价比"},
        {"name": "glm-4-plus", "provider": "Zhipu", "context": "128K", "strength": "中文理解、长文本"},
    ]
    for cat in _CATALOG:
        if cat["name"] not in installed_names:
            result.append({**cat, "available": False, "category": "catalog"})

    # Also add installed models as reference
    for r in result:
        if r.get("available") and not r.get("provider"):
            # Local model — guess provider from name
            name = r["name"]
            if "qwen" in name.lower():
                r["provider"] = "Alibaba (Ollama)"
                r["strength"] = "本地运行、数据安全"
            elif "gemma" in name.lower():
                r["provider"] = "Google (Ollama)"
                r["strength"] = "本地运行、轻量高效"
            elif "minicpm" in name.lower():
                r["provider"] = "OpenBMB (Ollama)"
                r["strength"] = "本地运行、多模态"
            elif "deepseek" in name.lower():
                r["provider"] = "DeepSeek"
                r["strength"] = "高性价比、推理能力强"

    return result


@router.get("/diagnostics/playground/models")
async def compat_playground_models():
    """List available models for the diagnostics playground."""
    models = _list_models()
    return {"models": models, "count": len(models)}


@router.post("/diagnostics/playground/chat")
async def compat_playground_chat(body: Dict[str, Any]):
    """Chat with a specified model via the playground."""
    prompt = body.get("prompt", "") or body.get("message", "")
    model_id = body.get("model", "")

    if not prompt:
        return {"reply": "", "error": "No prompt provided"}

    try:
        messages = [{"role": "user", "content": prompt}]

        if model_id:
            from core.api.core_facade import create_selected_adapter  # P0-A2: 经 CoreFacade
            adapter = create_selected_adapter("chat", model_id=model_id)
        else:
            from core.api.core_facade import create_selected_adapter  # P0-A2: 经 CoreFacade
            adapter = create_selected_adapter("chat")

        result = adapter.generate(messages)
        return {"reply": result, "model": model_id or "default", "status": "ok"}
    except Exception as e:
        logger.debug("playground chat failed", exc_info=True)
        return {"reply": f"Model call failed: {str(e)[:200]}", "status": "error"}


@router.post("/diagnostics/playground/compare")
async def compat_playground_compare(body: Dict[str, Any]):
    """Compare outputs from multiple models (installed + market with api_key).
    
    Body: {
        prompt: str,
        models: [{name: str, api_key?: str, api_base?: str}]
    }
    """
    prompt = body.get("prompt", "")
    model_list = body.get("models") or []
    # Backward compat: model_a/model_b
    if not model_list:
        ma = body.get("model_a", "")
        mb = body.get("model_b", "")
        model_list = [{"name": m} for m in (ma, mb) if m]

    if not prompt:
        return {"results": [], "error": "No prompt provided"}

    # Preload installed model names for routing
    installed_names = set()
    try:
        from infra.management.model.manager import ModelManager as InfraModelManager
        mgr = InfraModelManager()
        for m in mgr.select_by_purpose_list("chat"):
            installed_names.add(m if isinstance(m, str) else getattr(m, "name", str(m)))
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    import time as _time, asyncio as _aio
    messages = [{"role": "user", "content": prompt}]

    async def _call_model(model_name: str, api_key: str = "", api_base: str = ""):
        start = _time.time()
        try:
            if model_name in installed_names:
                # Installed model — use system adapter
                from core.api.core_facade import create_selected_adapter  # P0-A2: 经 CoreFacade
                adapter = create_selected_adapter("chat", model_name=model_name)
                reply = adapter.generate(messages)
            elif api_key:
                # Market model — create temp adapter with provided config
                from core.adapters.llm.base import create_adapter
                provider_map = {
                    "gpt": "openai", "claude": "anthropic", "gemini": "google",
                    "llama": "openai_compatible", "mixtral": "openai_compatible",
                    "mistral": "openai_compatible", "qwen": "openai_compatible",
                    "glm": "openai_compatible",
                }
                provider = "openai_compatible"
                for k, v in provider_map.items():
                    if k in model_name.lower():
                        provider = v
                        break
                # Determine base URL
                if not api_base:
                    _base_map = {
                        "openai": "https://api.openai.com/v1",
                        "openai_compatible": api_base,  # will be set below
                    }
                adapter = create_adapter(
                    provider=provider,
                    api_key=api_key,
                    model=model_name,
                    base_url=api_base or None,
                )
                reply = adapter.generate(messages)
            else:
                raise ValueError("未配置 API key — 请在模型名称旁输入密钥")

            latency_ms = int((_time.time() - start) * 1000)
            return {
                "model": model_name, "content": reply, "status": "success",
                "latency_ms": latency_ms,
            }
        except Exception as e:
            latency_ms = int((_time.time() - start) * 1000)
            return {
                "model": model_name, "status": "error",
                "error": str(e)[:300], "latency_ms": latency_ms,
            }

    # Run all models in parallel
    tasks = [
        _call_model(m.get("name", m) if isinstance(m, dict) else m,
                     api_key=m.get("api_key", "") if isinstance(m, dict) else "",
                     api_base=m.get("api_base", "") if isinstance(m, dict) else "")
        for m in model_list
    ]
    results = await _aio.gather(*tasks, return_exceptions=True)
    clean = []
    for r in results:
        if isinstance(r, Exception):
            clean.append({"model": "?", "status": "error", "error": str(r)[:200]})
        else:
            clean.append(r)

    return {"results": clean, "status": "ok"}


# ════════════════════════════════════════════════════════════
# Repairs stub — delegates to GET handler
# ════════════════════════════════════════════════════════════

@router.get("/diagnostics/repairs-latest")
async def compat_repairs_get(request: Request):
    """GET repairs-latest — returns cached/empty result (repairs module migrated out)."""
    return {"needs_diagnostics": False, "repairs": [], "status": "delegated"}


@router.post("/diagnostics/repairs-latest")
async def compat_repairs_post(request: Request, body: Dict[str, Any] = None):
    """POST trigger for repairs → delegates to GET handler."""
    try:
        from core.api.routers.repairs import get_repairs_latest
        return await get_repairs_latest()
    except ImportError:
        return {"needs_diagnostics": False, "repairs": [], "status": "delegated"}


# ════════════════════════════════════════════════════════════
# Workbench FDE dashboard — POST alias
# ════════════════════════════════════════════════════════════

@router.post("/workbench/fde-dashboard")
async def compat_workbench_fde_dashboard_post():
    """POST alias for workbench FDE dashboard."""
    return {"pending_decisions": 0, "signal_alerts": 0, "status": "ok"}
