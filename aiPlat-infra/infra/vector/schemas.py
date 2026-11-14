"""schemas：模块接口。"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any


@dataclass
class IndexConfig:
    """IndexConfig。"""
    type: str = "HNSW"
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchConfig:
    """SearchConfig。"""
    top_k: int = 10
    metric_type: str = "IP"
    ef: int = 100


@dataclass
class CollectionConfig:
    """CollectionConfig。"""
    name: str = "documents"
    description: str = ""
    shards: int = 2
    replicas: int = 1


@dataclass
class VectorConfig:
    """VectorConfig。"""
    type: str = "milvus"
    host: str = "localhost"
    port: int = 19530
    dimension: int = 1536
    index: Optional[IndexConfig] = None
    search: Optional[SearchConfig] = None
    collection: Optional[CollectionConfig] = None
    lazy_init: bool = True


@dataclass
class Vector:
    """Vector。"""
    id: Optional[str] = None
    values: List[float] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """SearchResult。"""
    id: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
