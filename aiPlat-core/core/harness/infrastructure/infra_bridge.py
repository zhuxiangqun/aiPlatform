"""Bridge from core's model infrastructure to aiPlat-infra's LLM capabilities.

This is Phase A of the infra wiring plan — creates a minimal connection point
so core can optionally use infra's provider chain. Primary LLM path now flows
through core/adapters/llm/base.py::create_adapter() → InfraLLMAdapter.

## Wiring Status (Per CLAUDE.md §5.30, every module must have ≥1 caller)

✅ WIRED:
  create_infra_database_client() → aiPlat-platform/storage/sqlite.py, aiPlat-platform/kb/db.py
  create_infra_vector_client()   → core memory/semantic.py
  get_infra_model_source()       → model_injection.py (list_infra_models)
  list_infra_models()            → model_injection.py
  NOTE: Full model migration is COMPLETE. model_router.py was deleted.
  model_injection.py is the canonical path, using infra ModelManager.select().

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


def deploy_app_service(name: str, namespace: str, image: str,
                       config: Optional[Dict[str, Any]] = None) -> bool:
    """L5 v2: register a service deployment via infra's ServiceManager.

    Platform must NOT import infra directly (single-direction platform → core →
    infra). This bridge is the sanctioned path. Standalone mode or unavailable
    infra → returns False (no-op), never raises.

    callers: aiPlat-platform/builder/builder_project_service.py (via CoreFacade)
    """
    if not _check_infra_available():
        logger.info("infra not available — L5 deploy skipped: %s/%s", namespace, name)
        return False
    try:
        from infra.management.service.manager import ServiceManager  # noqa: infra 桥接（本文件为唯一入口）
        mgr = ServiceManager(standalone_mode=False)
        _svc = mgr.deploy_service({
            "name": name,
            "namespace": namespace,
            "type": "aiplat-app",
            "image": image,
            "replicas": 1,
            "config": config or {},
        })
        return _svc is not None
    except Exception as e:  # noqa: BLE001 — bridge must degrade gracefully
        logger.warning("L5 infra deploy skipped: %s", str(e)[:200])
        return False
