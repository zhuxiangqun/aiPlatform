from typing import Optional
from .schemas import VectorConfig
from .base import VectorStore


def create(config: Optional[VectorConfig] = None) -> VectorStore:
    """创建向量存储（便捷函数）"""
    return create_vector_store(config)


def create_vector_store(config: Optional[VectorConfig] = None) -> VectorStore:
    config = config or VectorConfig()

    if config.type == "milvus":
        try:
            from .milvus import MilvusStore

            return MilvusStore(config)
        except ImportError:
            raise ImportError(
                "pymilvus is required for Milvus support. Install with: pip install pymilvus"
            )
    elif config.type == "faiss":
        try:
            from .faiss import FaissStore

            return FaissStore(config)
        except ImportError:
            raise ImportError(
                "faiss-cpu is required for Faiss support. Install with: pip install faiss-cpu"
            )
    elif config.type == "pinecone":
        try:
            from .pinecone import PineconeStore

            return PineconeStore(config)
        except ImportError:
            raise ImportError(
                "pinecone is required for Pinecone support. Install with: pip install pinecone-client"
            )
    elif config.type == "chroma":
        try:
            from .chroma import ChromaStore

            return ChromaStore(config)
        except ImportError:
            raise ImportError(
                "chromadb is required for Chroma support. Install with: pip install chromadb"
            )
    else:
        raise ValueError(f"Unknown vector store type: {config.type}")
