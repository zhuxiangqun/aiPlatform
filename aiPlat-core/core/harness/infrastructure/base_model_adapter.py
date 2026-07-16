"""
BaseModelAdapter — shared model resolution, caching, and factory for all
core→infra model adapters.

All concrete adapters (Embedding, Reranker, Audio, OCR) MUST inherit from this
base. They only override the business-specific interface (embed/rerank/transcribe/ocr).
Zero-copy rule: if a new adapter copies > 20% of code from an existing adapter,
extract the common logic here first.

Design rule: see aiPlat-core/CLAUDE.md §5.31 (Core Adapter 设计规则)
"""

from __future__ import annotations
import logging

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, Optional, TypeVar

# ── Model resolution ─────────────────────────────────────────

_MODEL_ENV_MAP: Dict[str, str] = {
    "embedding": "AIPLAT_EMBEDDING_MODEL",
    "reranker": "AIPLAT_RERANK_MODEL",
    "audio": "AIPLAT_VIDEO_WHISPER_MODEL",
    "ocr": "AIPLAT_VIDEO_OCR_MODEL",
}

_MODEL_DEFAULTS: Dict[str, str] = {
    "embedding": "paraphrase-multilingual-MiniLM-L12-v2",
    "reranker": "jinaai/jina-reranker-v2-base-multilingual",
    "audio": "base",
    "ocr": "eng+chi_sim",
}

_MODEL_TYPE_MAP: Dict[str, str] = {
    "embedding": "embedding",
    "reranker": "reranker",
    "audio": "audio",
    "ocr": "ocr",
}


def resolve_model_name(capability: str) -> str:
    """Resolve model name for a given capability.
    
    Resolution chain: env var → infra ModelManager → capability default.
    Env var has highest priority so users can override ModelManager at runtime.
    """
    # Hash backend bypass: no model needed for embedding
    if capability == "embedding" and os.getenv("AIPLAT_EMBED_BACKEND", "") == "hash":
        return "hash_embed"

    # Check env var first (user override takes priority)
    env_var = _MODEL_ENV_MAP.get(capability, "")
    if env_var:
        model = os.getenv(env_var, "").strip()
        if model:
            return model

    # Try infra ModelManager (single source of truth for model selection)
    try:
        from infra.management.model.manager import ModelManager
        mgr = ModelManager()
        target_type = _MODEL_TYPE_MAP.get(capability, capability)
        for m in mgr._models.values():
            if m.type.value == target_type and m.enabled:
                return m.name
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    return _MODEL_DEFAULTS.get(capability, capability)


# ── Model cache ───────────────────────────────────────────────

_model_cache: Dict[str, Any] = {}
_model_cache_name: Dict[str, Optional[str]] = {}


def get_cached_model(capability: str, loader_fn, *, model_name: str = "") -> Any:
    """Get or load a model with singleton caching per capability.
    
    Args:
        capability: "embedding", "reranker", "audio", "ocr"
        loader_fn: fn(name) → model instance
        model_name: optional override
    """
    name = model_name or resolve_model_name(capability)
    cached = _model_cache.get(capability)
    if cached is not None and _model_cache_name.get(capability) == name:
        return cached
    model = loader_fn(name)
    if model is not None:
        _model_cache[capability] = model
        _model_cache_name[capability] = name
    return model


# ── Base adapter class ────────────────────────────────────────

T = TypeVar("T")


class BaseModelAdapter(ABC):
    """Shared base for all core→infra model adapters.
    
    Subclass and override:
      - capability: str class attr (e.g. "embedding")
      - _load_model(name) → model instance
      - Business methods (embed/rerank/transcribe/ocr)
    """

    capability: str = ""

    def __init__(self, *, model_name: str = ""):
        self._model_name = model_name or resolve_model_name(self.capability)

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_model(self) -> Any:
        """Get or load the backing model (cached)."""
        return get_cached_model(
            self.capability,
            self._load_model,  # noqa: boundary — framework callback wiring
            model_name=self._model_name,
        )

    def _load_model(self, name: str) -> Any:
        """Override in subclass to load the specific model type."""
        raise NotImplementedError(f"{self.capability} adapter must implement _load_model")  # noqa: boundary — abstract base class


# ── Factory ───────────────────────────────────────────────────

_CAPABILITY_ADAPTERS: Dict[str, Any] = {}


def create_adapter(capability: str, **kwargs) -> BaseModelAdapter:
    """Unified factory: create the right adapter for a capability.
    
    Usage:
        adapter = create_adapter("embedding", model_name="jina-embeddings")
        vec = adapter.embed("hello")
    """
    # Lazy registration (avoids circular imports)
    if not _CAPABILITY_ADAPTERS:
        _CAPABILITY_ADAPTERS["embedding"] = _lazy_import(
            "core.harness.infrastructure.infra_embedding_adapter", "create_infra_embedding_adapter"
        )
        _CAPABILITY_ADAPTERS["reranker"] = _lazy_import(
            "core.harness.infrastructure.infra_reranker_adapter", "create_infra_reranker_adapter"
        )
        _CAPABILITY_ADAPTERS["audio"] = _lazy_import(
            "core.harness.infrastructure.infra_audio_adapter", "create_infra_audio_adapter"
        )
        _CAPABILITY_ADAPTERS["ocr"] = _lazy_import(
            "core.harness.infrastructure.infra_ocr_adapter", "create_infra_ocr_adapter"
        )

    factory = _CAPABILITY_ADAPTERS.get(capability)
    if factory:
        return factory(**kwargs)
    raise ValueError(f"Unknown model capability: {capability}")


def _lazy_import(module: str, factory: str):
    def _fn(**kwargs):
        import importlib
        mod = importlib.import_module(module)
        fn = getattr(mod, factory)
        return fn(**kwargs)
    return _fn


__all__ = [
    "BaseModelAdapter",
    "resolve_model_name",
    "get_cached_model",
    "create_adapter",
]
