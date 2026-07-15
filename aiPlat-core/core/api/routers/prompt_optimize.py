"""Prompt Optimize API — template-aware LLM optimization."""
from __future__ import annotations
from typing import Dict, Any
import json as _json
import re as _re
import logging

from fastapi import APIRouter, HTTPException
from core.schemas_prompt_app import PromptOptimizeRequest
from core.harness.syscalls.llm import sys_llm_generate

router = APIRouter()
_log = logging.getLogger("aiplat.prompt_optimize")


@router.post("/prompts/optimize", response_model=Dict[str, Any])
async def optimize_prompt(req: PromptOptimizeRequest):
    """Optimize a prompt template with context-aware analysis."""
    if not req.prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    # Load template context if available
    context_text = ""
    if req.template_id:
        from core.harness.kernel.runtime import get_kernel_runtime
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        if store:
            try:
                tpl = await store.get_prompt_app_template(template_id=req.template_id)
                if tpl:
                    cat = tpl.get("category", "")
                    name = tpl.get("name", "")
                    vars_text = tpl.get("variables", "[]")
                    context_text = f"\n模板名称: {name}\n行业分类: {cat}\n变量定义: {vars_text[:500]}"
            except Exception as e:
                logging.warning(str(e), exc_info=True)

    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        model_name = req.model or best_model_for_purpose("query_translation")
        if not model_name:
            return {"error": "无可用模型", "original": req.prompt[:500], "optimized": "", "changes": [], "analysis": ""}
        try:
            model = create_selected_adapter(model_name=model_name)
        except RuntimeError as re:
            return {"error": f"模型不可用: {str(re)[:200]}", "original": req.prompt[:500],
                    "optimized": "", "changes": [], "analysis": "",
                    "hint": "请配置 AIPLAT_LLM_API_KEY 或启动 Ollama/LM Studio 本地模型"}

        from core.harness.utils.prompt_loader import _async_prompt_resolve
        optimize_prompt = await _async_prompt_resolve("prompt-optimize",
            context=context_text,
            prompt=req.prompt[:3000],
        )

        resp = await sys_llm_generate(model, [
            {"role": "system", "content": await _async_prompt_resolve("prompt-optimize-system-role")},
            {"role": "user", "content": optimize_prompt},
        ])

        content = resp.content if hasattr(resp, 'content') else str(resp)
        match = _re.search(r'\{[\s\S]*\}', content.strip())
        result = {}
        if match:
            try:
                result = _json.loads(match.group(0))
            except Exception:
                result = {}

        return {
            "original": req.prompt[:2000],
            "optimized": result.get("optimized", "")[:2000],
            "changes": result.get("changes", [])[:8],
            "suggested_vars": result.get("suggested_vars", [])[:5],
            "analysis": result.get("analysis", "")[:500],
            "score_before": result.get("score_before", 7),
            "score_after": result.get("score_after", 9),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Optimize failed: {str(e)[:200]}")
