"""
Local model scanner — discovers models from local inference servers.

Supported endpoints:
- Ollama: GET /api/tags
- OpenAI-compatible (LM Studio/oMLX/vLLM/llama.cpp): GET /v1/models
"""

import asyncio
import json
import os
from typing import Dict, List, Optional
from urllib.parse import urljoin

import aiohttp

from .schemas import ModelInfo, ModelType, ModelSource, ModelStatus, ModelConfig, ModelStats
from datetime import datetime, timezone

# Ollama model families known to support native tool/function calling
_OLLAMA_TOOL_CALLING = {
    "llama3.1", "llama3.2", "llama3.3", "llama3",
    "mistral", "mistral-nemo", "mixtral",
    "qwen2.5", "qwen3",
    "command-r", "command-r-plus",
    "phi4", "phi3.5",
    "nemotron", "nemotron-mini",
    "granite3.2", "granite3.1",
}


def _ollama_supports_tool_calling(model_name: str) -> bool:
    """Fuzzy-match Ollama model name against known tool-calling families."""
    base = model_name.split(":")[0].lower().strip()
    import re
    base = re.sub(r"[-_.]\d*[bBkKqQ]$", "", base)
    return base in _OLLAMA_TOOL_CALLING


async def _scan_openai_compatible(endpoint: str, provider_label: str, source: ModelSource) -> List[ModelInfo]:
    """Scan an OpenAI-compatible endpoint for available models."""
    import re
    models: List[ModelInfo] = []
    try:
        url = urljoin(endpoint.rstrip("/") + "/", "v1/models")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("data", []):
                        name = item.get("id", "")
                        safe_id = f"{provider_label}:{re.sub(r'[^a-zA-Z0-9_-]', '-', name.lower())}"
                        models.append(ModelInfo(
                            id=safe_id, name=name, provider=provider_label,
                            type=ModelType.CHAT, source=source,
                            display_name=name, enabled=True,
                            description=f"Local model via {endpoint}",
                            tags=[provider_label, "local"],
                            capabilities=["chat"],
                            status=ModelStatus.AVAILABLE,
                            config=ModelConfig(base_url=endpoint),
                            stats=ModelStats(), created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
                        ))
    except Exception:
        pass
    return models


async def _scan_ollama(endpoint: str) -> List[ModelInfo]:
    """Scan Ollama for available models using /api/tags."""
    import re
    models: List[ModelInfo] = []
    try:
        url = urljoin(endpoint.rstrip("/") + "/", "api/tags")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("models", []):
                        name = item.get("name", "")
                        details = item.get("details", {})
                        safe_id = f"ollama:{re.sub(r'[^a-zA-Z0-9_-]', '-', name.lower())}"
                        caps = ["chat"]
                        if details.get("embedding"):
                            caps.append("embedding")
                        if _ollama_supports_tool_calling(name):
                            caps.append("function_call")
                            caps.append("json_mode")
                        models.append(ModelInfo(
                            id=safe_id, name=name, provider="ollama",
                            type=ModelType.CHAT, source=ModelSource.LOCAL,
                            display_name=name, enabled=True,
                            description=f"Ollama local model",
                            tags=["ollama", "local"] + ([details.get("family", "")] if details.get("family") else []),
                            capabilities=caps,
                            status=ModelStatus.AVAILABLE,
                            config=ModelConfig(base_url=endpoint),
                            stats=ModelStats(), created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
                        ))
    except Exception:
        pass
    return models


async def scan_local_models(endpoints: List[str]) -> List[ModelInfo]:
    """Scan all configured local endpoints for available models."""
    all_models: List[ModelInfo] = []
    for ep in endpoints:
        ep = ep.strip()
        if not ep:
            continue
        # Try Ollama first (has better metadata)
        ollama_models = await _scan_ollama(ep)
        if ollama_models:
            all_models.extend(ollama_models)
        else:
            # Fallback to OpenAI-compatible scan
            label = next((n for n in ["lm-studio", "omlx", "vllm"] if n in ep.lower()), "local-api")
            local_models = await _scan_openai_compatible(ep, label, ModelSource.LOCAL)
            all_models.extend(local_models)
    return all_models


__all__ = ["scan_local_models"]
