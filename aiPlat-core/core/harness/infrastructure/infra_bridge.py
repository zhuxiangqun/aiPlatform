"""Bridge from core's model infrastructure to aiPlat-infra's LLM capabilities.

This is Phase A of the infra wiring plan — creates a minimal connection point
so core can optionally use infra's provider chain. Primary LLM path now flows
through core/adapters/llm/base.py::create_adapter() → InfraLLMAdapter.

Per CLAUDE.md §5.30: every module must have at least 1 production caller.
Callers: model_router.py (get_infra_model_source/list_infra_models),
         memory/semantic.py (create_infra_vector_client/get_infra_embedding).
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional
from core.harness.utils.llm_env import get_llm_api_key, get_llm_base_url

logger = logging.getLogger(__name__)

_INFRA_AVAILABLE: Optional[bool] = None


def _check_infra_available() -> bool:
    global _INFRA_AVAILABLE
    if _INFRA_AVAILABLE is not None:
        return _INFRA_AVAILABLE
    try:
        import infra  # noqa: F401
        _INFRA_AVAILABLE = True
    except ImportError:
        _INFRA_AVAILABLE = False
        logger.debug("aiplat-infra package not available; using core-only model sources")
    return _INFRA_AVAILABLE


def get_infra_model_source() -> Optional[Any]:
    """Return infra's LLMManager as a model source, or None if infra is unavailable.

    This provides an optional fallback model provider chain through the
    infra layer, which supports additional providers (local LLM, etc.)
    not natively available in core's ModelRegistry.
    """
    if not _check_infra_available():
        return None
    try:
        from infra.management.api.main import get_infra_manager
        mgr = get_infra_manager()
        llm = mgr.get("llm")
        if llm is None:
            return None
        return llm
    except Exception:
        logger.debug("Failed to load infra LLM manager", exc_info=True)
        return None


def list_infra_models() -> List[Dict[str, Any]]:
    """List models available through infra's LLMManager.

    Returns list of dicts with keys: name, provider, api_key_env, description.
    """
    if not _check_infra_available():
        return []
    try:
        from infra.management.api.main import get_infra_manager
        mgr = get_infra_manager()
        model_mgr = mgr.get("model")
        if model_mgr is None:
            return []
        return getattr(model_mgr, "list_models", lambda: [])()
    except Exception:
        return []


def create_infra_vector_client(backend: str = "chroma") -> Optional[Any]:
    """Create a vector store client backed by infra's factory.

    Args:
        backend: "chroma", "faiss", "milvus", or "pinecone"

    Returns a client object with .insert(vectors, metadata) and
    .search(query_vector, top_k) -> List[Dict] methods.

    Caller: can be used by core/harness/memory/semantic.py or
    core/apps/knowledge/ as a VectorStore backend.
    """
    if not _check_infra_available():
        return None
    try:
        from infra.vector.factory import create_vector_client
        config: Dict[str, Any] = {"backend": backend, "dimension": int(os.getenv("AIPLAT_VECTOR_DIMENSION", "1536"))}
        if backend == "chroma":
            config["collection_name"] = os.getenv("AIPLAT_CHROMA_COLLECTION", "")
        elif backend == "faiss":
            config["index_type"] = os.getenv("AIPLAT_FAISS_INDEX", "HNSW")
        elif backend == "milvus":
            config["collection_name"] = os.getenv("AIPLAT_MILVUS_COLLECTION", "")
        elif backend == "pinecone":
            config["api_key"] = os.getenv("PINECONE_API_KEY", "")
            config["environment"] = os.getenv("PINECONE_ENVIRONMENT", "")
            config["index_name"] = os.getenv("PINECONE_INDEX", "")
        client = create_vector_client(config)
        return client
    except Exception:
        logger.debug(f"Failed to create infra vector client ({backend})", exc_info=True)
        return None


_embedding_model: Optional[Any] = None


async def get_infra_embedding(text: str) -> Optional[List[float]]:
    """Generate an embedding vector via the infra LLM layer."""
    global _embedding_model
    if not _check_infra_available():
        return None
    try:
        if _embedding_model is None:
            from infra.llm.factory import create_llm_client
            config: Dict[str, Any] = {"provider": "local", "model": "embedding"}
            import os
            api_key = get_llm_api_key("openai") or get_llm_api_key("deepseek") or ""
            if api_key:
                config["api_key"] = api_key
            _embedding_model = create_llm_client(config)
        return await _embedding_model.embed(text)
    except Exception:
        logger.debug("Failed to generate embedding via infra", exc_info=True)
        return None
