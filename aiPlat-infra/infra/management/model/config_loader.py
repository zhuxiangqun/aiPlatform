import logging
"""
Config Loader — discovers models from adapters table + YAML config.

Sources (in priority order):
1. Adapter-based models (API keys from management UI SQLite table)
2. System capability models (OCR, doc-parser, default embedder)
3. YAML model_discovery section (provider + model lists)
"""

import os
import yaml
from typing import List, Dict, Any
from datetime import datetime, timezone

from .schemas import ModelInfo, ModelType, ModelSource, ModelStatus, ModelConfig, ModelStats


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
        pass  # noqa: optional-dependency

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
        pass  # noqa: optional-dependency

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
    except Exception as e:
        logging.debug(str(e), exc_info=True)

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
        pass  # noqa: optional-dependency

    return models


def _infer_model_type(name: str, caps: list, provider: str) -> 'ModelType':
    """Infer model type from capabilities and name patterns."""
    import re
    name_lower = name.lower()
    if "embed" in name_lower or "embedding" in name_lower or "mxbai" in name_lower:
        return ModelType.EMBEDDING
    if "ocr" in name_lower or "tesseract" in name_lower:
        return ModelType("ocr")
    if "embedding" in caps or any(c for c in caps if "embed" in c):
        return ModelType.EMBEDDING
    return ModelType.CHAT


def _resolve_capabilities(model_name: str, provider: str) -> list:
    """Read capabilities from llm_profile.yaml model_capabilities, with sensible fallback.

    model_capabilities is the single source of truth for what each model can do.
    Falls back to provider-based defaults only if YAML has no entry for this model.
    """
    try:
        from pathlib import Path
        import yaml as _yaml
        cfg_path = Path(__file__).resolve().parent.parent.parent.parent / "config" / "infra" / "llm_profile.yaml"
        if not cfg_path.exists():
            cfg_path = Path(os.getenv("AIPLAT_LLM_CONFIG_PATH", str(cfg_path)))
        if cfg_path.exists():
            with open(cfg_path) as f:
                cfg = _yaml.safe_load(f) or {}
            caps_data = cfg.get("model_capabilities", {}).get(model_name, {})
            if caps_data:
                caps = []
                # Use strength_areas from YAML as capabilities
                areas = caps_data.get("strength_areas", [])
                if areas:
                    caps.extend(areas)
                # Infer type from strength_areas
                if not areas or all(a in ["chat", "fact_lookup", "long_form_summary", "multi_doc_synthesis",
                                           "instruction_following", "evaluation"] for a in areas):
                    caps.insert(0, "chat")
                if caps_data.get("reasoning_quality", 0) >= 3:
                    caps.append("reasoning")
                # Remove duplicates while preserving order
                seen = set()
                unique = []
                for c in caps:
                    if c not in seen:
                        seen.add(c)
                        unique.append(c)
                if unique:
                    return unique
    except Exception:
        pass
    # Fallback: provider-based defaults
    providers_with_reasoning = {"deepseek", "openai", "ollama"}
    caps = ["chat"]
    if provider in providers_with_reasoning:
        caps.append("reasoning")
    return caps
    """Discover models from adapters table (API keys configured via management UI)."""
    import json as _json
    import sqlite3
    models: List[ModelInfo] = []
    db_path = os.getenv("AIPLAT_EXECUTION_DB_PATH", "")
    if not db_path or not os.path.isfile(db_path):
        return models
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT adapter_id, name, provider, api_base_url, models_json "
                "FROM adapters WHERE status='active' "
                "AND ((api_key IS NOT NULL AND api_key != '') OR (api_key_enc IS NOT NULL AND api_key_enc != '')) "
                "ORDER BY updated_at DESC"
            ).fetchall()
            seen_names: set = set()
            providers_with_reasoning = {"deepseek", "openai", "ollama"}
            for row in rows:
                d = dict(row)
                provider = (d.get("provider") or "").strip().lower()
                base_url = (d.get("api_base_url") or "").strip()
                # Map OpenAI-compatible adapters to their actual provider
                if provider in ("openai", "openai_compatible"):
                    if base_url and "deepseek" in base_url.lower():
                        provider = "deepseek"
                    elif base_url and "openai" in base_url.lower():
                        provider = "openai"
                adapter_id = d.get("adapter_id") or ""
                models_json = d.get("models_json") or "[]"
                if not provider or not adapter_id:
                    continue
                try:
                    model_list = _json.loads(models_json) if isinstance(models_json, str) else models_json
                except Exception:
                    model_list = []
                if not isinstance(model_list, list) or not model_list or not any(
                    (isinstance(e, dict) and e.get("name")) or (isinstance(e, str) and e.strip())
                    for e in model_list
                ):
                    adapter_name = (d.get("name") or "").strip()
                    model_list = [{"name": adapter_name or f"{provider}-chat"}]
                for entry in model_list:
                    name = entry.get("name") if isinstance(entry, dict) else str(entry)
                    if not name or name in seen_names or "," in name:
                        continue
                    seen_names.add(name)
                    # Capabilities from model_capabilities.yaml (single source of truth)
                    caps = _resolve_capabilities(name, provider)
                    # Infer type from capabilities and model name
                    _mtype = _infer_model_type(name, caps, provider)
                    safe_id = f"adapter:{adapter_id}:{name}"
                    models.append(ModelInfo(
                        id=safe_id, name=name, provider=provider,
                        type=_mtype, source=ModelSource.EXTERNAL,
                        display_name=name, enabled=True,
                        description=f"Remote model — from adapter {adapter_id[:12]}",
                        tags=[provider] + caps[:3], capabilities=caps,
                        status=ModelStatus.AVAILABLE,
                        config=ModelConfig(adapter_id=adapter_id, base_url=base_url or None),
                        stats=ModelStats(),
                        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
                    ))
        finally:
            conn.close()
    except Exception:  # noqa: fallback-return-empty
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
        """Discover models: adapters first, then YAML model_discovery, then system capabilities."""
        models: List[ModelInfo] = []

        # 1. Adapter-based models (API keys from management UI)
        models.extend(_load_adapter_models())

        # 2. System capability models (OCR, doc-parser, default embedder)
        existing_names = {m.name for m in models}
        for cap_model in _detect_system_capability_models():
            if cap_model.name not in existing_names:
                models.append(cap_model)
                existing_names.add(cap_model.name)

        # 3. YAML model_discovery section (fallback for non-adapter providers)
        config = self._load_config()
        discovery_cfg = config.get("model_discovery", {}).get("env_models", [])
        existing_names = {m.name for m in models}
        for item in discovery_cfg:
            provider = item.get("provider", "openai_compatible")
            base_url = item.get("base_url", "")
            mtype = item.get("type", "chat")
            cap = item.get("capability", "chat")
            model_name = item.get("name", provider)
            if model_name in existing_names:
                continue
            existing_names.add(model_name)
            import re
            safe_id = f"{provider}:{re.sub(r'[^a-zA-Z0-9_-]', '-', model_name.lower())}"
            models.append(ModelInfo(
                id=safe_id, name=model_name, provider=provider,
                type=ModelType(mtype), source=ModelSource.EXTERNAL,
                tags=[provider, mtype], capabilities=[cap],
                status=ModelStatus.NOT_CONFIGURED,
                config=ModelConfig(base_url=base_url),
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

