"""Bridge from core's model infrastructure to aiPlat-infra's LLM capabilities.

This is Phase A of the infra wiring plan — creates a minimal connection point
so core can optionally use infra's provider chain. Primary LLM path now flows
through core/adapters/llm/base.py::create_adapter() → InfraLLMAdapter.

## Wiring Status (Per CLAUDE.md §5.30, every module must have ≥1 caller)

✅ WIRED:
  create_infra_database_client() → aiPlat-platform/storage/sqlite.py, aiPlat-platform/kb/db.py
  create_infra_vector_client()   → core memory/semantic.py
  get_infra_model_source()       → model_router.py (list_infra_models)
  list_infra_models()            → model_router.py

⚠ NOT YET WIRED:
  get_infra_embedding()          → embedding flows through memory/embedding.py::EmbeddingProvider
                                   (wire when infra-based embedding preferred over local sentence-transformers)

⚠ FULL INFRA CAPABILITIES NOT IN PRODUCTION PATH:
  aiPlat-infra has 18 capability modules (LLM/Cache/Vector/Database/Messaging/Storage/
  Compute/Memory/HTTP/Logging/Config/DI/Network/Monitoring/MCP/Observability/Utils/Management).
  Only 4 are bridged here. Core maintains parallel infrastructure in core/harness/infrastructure/.
  See aiPlat-infra/CLAUDE.md §5.6 for full wiring plan.
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
        fn = getattr(model_mgr, "list_models", None)
        if fn is None:
            return []
        import inspect as _inspect
        result = fn()
        if _inspect.iscoroutine(result):
            import asyncio as _asyncio
            try:
                loop = _asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                import concurrent.futures as _futures
                with _futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(_asyncio.run, result)
                    return future.result(timeout=5)
            else:
                return _asyncio.run(result)
        return result
    except Exception:
        return []


def create_infra_vector_client(backend: str = "faiss") -> Optional[Any]:
    """Create a vector store client backed by infra's factory.

    Args:
        backend: "faiss", "milvus", "chroma", or "pinecone"

    Returns a VectorStore with .add(vectors, metadata) and
    .search(query_vector, top_k) methods, or None on failure.
    """
    if not _check_infra_available():
        return None
    try:
        from infra.vector.schemas import VectorConfig, CollectionConfig, IndexConfig
        from infra.vector.factory import create_vector_store
        dim = int(os.getenv("AIPLAT_VECTOR_DIMENSION", "1536"))
        config = VectorConfig(
            type=backend,
            dimension=dim,
            collection=CollectionConfig(name=os.getenv("AIPLAT_VECTOR_COLLECTION", "aiplat_knowledge")),
            index=IndexConfig(type=os.getenv("AIPLAT_FAISS_INDEX", "IndexHNSW")),
        )
        client = create_vector_store(config)
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


def create_infra_database_client(db_path: str) -> Any:
    """创建数据库连接，通过 Infra Bridge 模式返回。

    Platform 层不应直接 import sqlite3，而应通过此函数获取
    数据库连接。连接已配置 WAL 模式、normal synchronous、
    并设置 row_factory 为 sqlite3.Row。

    Args:
        db_path: 数据库文件路径（如 "data/aiplat_platform.sqlite3"）

    Returns:
        sqlite3.Connection（符合 DatabasePort Protocol），
        已配置 row_factory=sqlite3.Row、PRAGMA journal_mode=WAL。

    callers: aiPlat-platform/storage/sqlite.py, aiPlat-platform/kb/db.py
    """
    import sqlite3

    path = db_path
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)

    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn
