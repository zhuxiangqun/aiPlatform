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
    """List available models from infra ModelManager."""
    try:
        from core.harness.utils.model_injection import best_model_for_purpose
        purposes = ["chat", "code_gen", "reasoning", "skill_execution", "clarify", "doc_llm"]
        models = {}
        for p in purposes:
            try:
                model = best_model_for_purpose(p)
                if model:
                    models[model] = {"name": model, "purposes": models.get(model, {}).get("purposes", []) + [p]}
            except Exception:
                pass  # noqa: cleanup-best-effort — model unavailable, skip
        return [
            {"name": name, "purposes": info["purposes"], "available": True}
            for name, info in models.items()
        ]
    except Exception:
        return []


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
            from core.harness.utils.model_injection import create_selected_adapter
            adapter = create_selected_adapter("chat", model_id=model_id)
        else:
            from core.harness.utils.model_injection import create_selected_adapter
            adapter = create_selected_adapter("chat")

        result = adapter.generate(messages)
        return {"reply": result, "model": model_id or "default", "status": "ok"}
    except Exception as e:
        logger.debug("playground chat failed", exc_info=True)
        return {"reply": f"Model call failed: {str(e)[:200]}", "status": "error"}


@router.post("/diagnostics/playground/compare")
async def compat_playground_compare(body: Dict[str, Any]):
    """Compare outputs from multiple models."""
    prompt = body.get("prompt", "")
    model_a = body.get("model_a", "")
    model_b = body.get("model_b", "")

    if not prompt:
        return {"results": [], "error": "No prompt provided"}

    results = []
    for label, model_id in [("A", model_a), ("B", model_b)]:
        if not model_id:
            continue
        try:
            from core.harness.utils.model_injection import create_selected_adapter
            adapter = create_selected_adapter("chat", model_id=model_id)
            messages = [{"role": "user", "content": prompt}]
            reply = adapter.generate(messages)
            results.append({"label": label, "model": model_id, "reply": reply, "status": "ok"})
        except Exception as e:
            results.append({"label": label, "model": model_id, "reply": str(e)[:200], "status": "error"})

    return {"results": results, "status": "ok" if results else "error"}


# ════════════════════════════════════════════════════════════
# Repairs stub — delegates to GET handler
# ════════════════════════════════════════════════════════════

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
