"""
Config Loader — discovers models from environment variables + YAML config.

Sources (in priority order):
1. Environment variables: AIPLAT_LLM_MODEL, AIPLAT_AGENT_MODEL, etc.
2. YAML model_discovery section: provider + model lists
3. Local_embedding fallback models
"""

import os
import yaml
from typing import List, Dict, Any
from datetime import datetime, timezone

from .schemas import ModelInfo, ModelType, ModelSource, ModelStatus, ModelConfig, ModelStats


_ENV_MODEL_TEMPLATES = {
    "DEEPSEEK_API_KEY": (
        "openai_compatible", "chat", "https://api.deepseek.com", "chat", ["deepseek", "chat", "reasoning"],
        ["AIPLAT_LLM_MODEL", "AIPLAT_AGENT_MODEL", "AIPLAT_DOC_LLM_MODEL"],
    ),
    "OPENAI_API_KEY": (
        "openai_compatible", "chat", "https://api.openai.com/v1", "chat", ["openai", "chat", "function_call"],
        ["OPENAI_MODEL", "OPENAI_AGENT_MODEL", "AIPLAT_LLM_MODEL"],
    ),
    "ANTHROPIC_API_KEY": (
        "anthropic", "chat", "https://api.anthropic.com", "chat", ["anthropic", "chat"],
        ["ANTHROPIC_MODEL", "AIPLAT_LLM_MODEL"],
    ),
}

# Models that don't need an API key — detected from env vars or system capabilities
_NON_API_MODEL_ENVS = {
    "AIPLAT_EMBEDDING_MODEL": ("local-embedding", "embedding", "embedding", ["local", "embedding", "huggingface"]),
    "AIPLAT_RERANK_MODEL": ("reranker", "reranker", "reranker", ["reranker", "search"]),
    "AIPLAT_VIDEO_WHISPER_MODEL": ("whisper", "audio", "audio", ["whisper", "stt", "speech"]),
}


def _models_from_env(api_key_env: str, provider: str, model_type: str,
                     base_url: str, capability: str, tags: List[str],
                     model_envs: List[str]) -> List[ModelInfo]:
    """Build ModelInfo list from environment variables. api_key_env gates availability;
       model_envs provide the actual model names."""
    import re
    api_key = os.getenv(api_key_env, "").strip()
    if not api_key:
        return []

    seen = set()
    for env_name in model_envs:
        val = os.getenv(env_name, "").strip()
        if not val:
            continue
        for name in val.split(","):
            name = name.strip()
            if not name or name in seen:
                continue
            seen.add(name)
    # Also check AIPLAT_LLM_MODEL as fallback
    if not seen:
        for env_name in ["AIPLAT_LLM_MODEL", "AIPLAT_DOC_LLM_MODEL", "AIPLAT_CODE_GEN_MODEL", "AIPLAT_AGENT_MODEL"]:
            val = os.getenv(env_name, "").strip()
            if val and val not in seen:
                seen.add(val)
    if not seen:
        return []

    models = []
    for name in seen:
        safe_id = f"{provider}:{re.sub(r'[^a-zA-Z0-9_-]', '-', name.lower())}"
        models.append(ModelInfo(
            id=safe_id, name=name, provider=provider,
            type=ModelType(model_type), source=ModelSource.CONFIG,
            display_name=name, enabled=True,
            description=f"Remote model ({provider}) — from env",
            tags=tags[:], capabilities=[capability],
            status=ModelStatus.AVAILABLE,
            config=ModelConfig(api_key_env=api_key_env, base_url=base_url),
            stats=ModelStats(), created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        ))
    return models


def _load_env_models() -> List[ModelInfo]:
    """Discover all remote models from environment variables."""
    all_models: List[ModelInfo] = []
    for env_key, (provider, mtype, url, cap, tags, model_envs) in _ENV_MODEL_TEMPLATES.items():
        all_models.extend(_models_from_env(env_key, provider, mtype, url, cap, tags, model_envs))
    return all_models


def _load_non_api_models() -> List[ModelInfo]:
    """Discover models that don't need an API key (embedding, reranker, whisper, etc.)
    — detected solely from their environment variables."""
    import re
    models: List[ModelInfo] = []
    for env_name, (provider, mtype, capability, tags) in _NON_API_MODEL_ENVS.items():
        val = os.getenv(env_name, "").strip()
        if not val:
            continue
        for name in val.split(","):
            name = name.strip()
            if not name:
                continue
            safe_id = f"{provider}:{re.sub(r'[^a-zA-Z0-9_-]', '-', name.lower())}"
            models.append(ModelInfo(
                id=safe_id, name=name, provider=provider,
                type=ModelType(mtype), source=ModelSource.CONFIG,
                display_name=name, enabled=True,
                description=f"Model from env {env_name}",
                tags=list(tags), capabilities=[capability],
                status=ModelStatus.AVAILABLE,
                config=ModelConfig(),
                stats=ModelStats(), created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
            ))
    # AIPLAT_DOC_LLM_MODEL is a CHAT purpose variant, skip if already in chat models
    return models


def _detect_system_capability_models() -> List[ModelInfo]:
    """Detect models from system capabilities (OCR engines, document parsers, etc.)
    that don't have dedicated environment variables."""
    import re
    models: List[ModelInfo] = []

    # PaddleOCR
    try:
        import paddleocr  # noqa: F401
        models.append(ModelInfo(
            id="paddleocr:default",
            name="PaddleOCR", provider="paddleocr",
            type=ModelType("ocr"), source=ModelSource.CONFIG,
            display_name="PaddleOCR", enabled=True,
            description="Chinese OCR engine (PaddlePaddle-based)",
            tags=["ocr", "chinese", "document"], capabilities=["ocr"],
            status=ModelStatus.AVAILABLE,
            config=ModelConfig(), stats=ModelStats(),
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        ))
    except ImportError:
        pass

    # Tesseract (pytesseract + tesseract binary)
    try:
        import pytesseract  # noqa: F401
        import shutil
        tesseract_ok = shutil.which("tesseract") is not None
        models.append(ModelInfo(
            id="tesseract:default",
            name="Tesseract OCR", provider="tesseract",
            type=ModelType("ocr"), source=ModelSource.CONFIG,
            display_name="Tesseract OCR", enabled=True,
            description="Open-source OCR engine (chi_sim+eng)",
            tags=["ocr", "tesseract", "document"], capabilities=["ocr"],
            status=ModelStatus.AVAILABLE if tesseract_ok else ModelStatus.NOT_CONFIGURED,
            config=ModelConfig(), stats=ModelStats(),
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        ))
    except ImportError:
        pass

    # MinerU
    import subprocess as _sp
    try:
        result = _sp.run(["mineru", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0 or "mineru" in (result.stdout + result.stderr).lower():
            models.append(ModelInfo(
                id="mineru:default",
                name="MinerU", provider="mineru",
                type=ModelType("chat"), source=ModelSource.CONFIG,
                display_name="MinerU", enabled=True,
                description="Structure-driven PDF parser (table extraction, content list)",
                tags=["document", "pdf", "parser"], capabilities=["doc-parser"],
                status=ModelStatus.AVAILABLE,
                config=ModelConfig(), stats=ModelStats(),
                created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
            ))
    except Exception:
        pass

    # Default sentence-transformers model (always available if installed)
    try:
        import sentence_transformers  # noqa: F401
        default_embed = os.getenv("AIPLAT_EMBEDDING_MODEL", "")
        if "all-MiniLM" not in default_embed.lower() and "all-minilm" not in default_embed.lower():
            safe_id = f"local-embedding:all-minilm-l6-v2"
            models.append(ModelInfo(
                id=safe_id, name="all-MiniLM-L6-v2", provider="local-embedding",
                type=ModelType.EMBEDDING, source=ModelSource.CONFIG,
                display_name="all-MiniLM-L6-v2", enabled=True,
                description="Default sentence-transformers embedding model (384-dim)",
                tags=["local", "embedding", "sentence-transformers"], capabilities=["embedding"],
                status=ModelStatus.AVAILABLE,
                config=ModelConfig(base_url="sentence-transformers/all-MiniLM-L6-v2"),
                stats=ModelStats(), created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
            ))
    except ImportError:
        pass

    return models


class ConfigLoader:
    """Model discovery loader — env vars + YAML config."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = self._find_config_file()
        self.config_path = config_path
        self._config_cache = None

    def _find_config_file(self) -> str:
        base_dir = os.path.dirname(__file__)
        search_paths = [
            os.path.join(base_dir, "..", "..", "..", "config", "infra", "default.yaml"),
            os.path.join(base_dir, "..", "..", "..", "config", "infra", "development.yaml"),
            os.getenv("AIPLAT_INFRA_CONFIG", ""),
        ]
        for path in search_paths:
            if os.path.exists(path):
                return path
        return ""

    def _load_config(self) -> Dict[str, Any]:
        if self._config_cache is not None:
            return self._config_cache
        if not self.config_path or not os.path.exists(self.config_path):
            self._config_cache = {}
            return self._config_cache
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config_cache = yaml.safe_load(f) or {}
                return self._config_cache
        except Exception:
            self._config_cache = {}
            return self._config_cache

    def load(self) -> List[ModelInfo]:
        """Discover models: env vars first, then YAML model_discovery, then local_embedding."""
        models: List[ModelInfo] = []

        # 1. Remote chat models from environment variables (primary source)
        models.extend(_load_env_models())

        # 2. Non-API models from env vars (embedding, reranker, whisper)
        models.extend(_load_non_api_models())

        # 3. System capability models (OCR, doc-parser, default embedder)
        existing_names = {m.name for m in models}
        for cap_model in _detect_system_capability_models():
            if cap_model.name not in existing_names:
                models.append(cap_model)
                existing_names.add(cap_model.name)

        # 2. YAML model_discovery section (fallback if env not set)
        config = self._load_config()
        discovery_cfg = config.get("model_discovery", {}).get("env_models", [])
        existing_names = {m.name for m in models}
        for item in discovery_cfg:
            env_key = item.get("env", "")
            api_key = os.getenv(env_key, "").strip()
            if not api_key or env_key in {"DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}:
                continue  # already handled above
            provider = item.get("provider", "openai_compatible")
            base_url = item.get("base_url", "")
            mtype = item.get("type", "chat")
            cap = item.get("capability", "chat")
            model_name = provider
            if model_name in existing_names:
                continue
            existing_names.add(model_name)
            import re
            safe_id = f"{provider}:{re.sub(r'[^a-zA-Z0-9_-]', '-', model_name.lower())}"
            models.append(ModelInfo(
                id=safe_id, name=model_name, provider=provider,
                type=ModelType(mtype), source=ModelSource.CONFIG,
                display_name=model_name.title(), enabled=True,
                description=f"Remote model ({provider})",
                tags=[provider, mtype], capabilities=[cap],
                status=ModelStatus.AVAILABLE,
                config=ModelConfig(api_key_env=env_key, base_url=base_url),
                stats=ModelStats(), created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
            ))

        # 3. Local embedding models
        local_emb = config.get("local_embedding", {})
        if local_emb.get("enabled", False):
            for emb in local_emb.get("models", []):
                model = self._parse_local_embedding_config(emb)
                if model:
                    models.append(model)

        return models

    def _parse_local_embedding_config(self, config: Dict[str, Any]) -> ModelInfo:
        import re
        name = config.get("name", "")
        safe_id = f"local-embedding:{re.sub(r'[^a-zA-Z0-9_-]', '-', name.lower())}"
        return ModelInfo(
            id=safe_id, name=name, provider="local-embedding",
            type=ModelType.EMBEDDING, source=ModelSource.CONFIG,
            display_name=config.get("display_name", name),
            enabled=config.get("enabled", True),
            description=config.get("description", f"Local embedding model: {name}"),
            tags=config.get("tags", ["local", "embedding", "huggingface"]),
            capabilities=config.get("capabilities", ["embedding"]),
            status=ModelStatus.AVAILABLE,
            config=ModelConfig(base_url=f"sentence-transformers/{config.get('path', '')}"),
            stats=ModelStats(), created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )

    def get_local_scan_endpoints(self) -> List[str]:
        """Get list of local model endpoints to scan."""
        config = self._load_config()
        local_scan = config.get("model_discovery", {}).get("local_scan", {})
        endpoints = local_scan.get("endpoints", ["http://localhost:11434"])
        auto = local_scan.get("auto_scan", True)
        if not auto:
            return []
        # Allow override via env var
        env_endpoints = os.getenv("AIPLAT_LOCAL_MODEL_ENDPOINTS", "")
        if env_endpoints:
            return [e.strip() for e in env_endpoints.split(",") if e.strip()]
        return endpoints

    def get_ollama_config(self) -> dict:
        """Legacy Ollama config accessor."""
        cfg = self._load_config()
        scan = cfg.get("model_discovery", {}).get("local_scan", {})
        endpoints = scan.get("endpoints", ["http://localhost:11434"])
        return {"endpoint": endpoints[0] if endpoints else "http://localhost:11434",
                "auto_scan": scan.get("auto_scan", True)}
