# 向量存储模块

> 提供向量数据库抽象，支持多种向量后端（Milvus/FAISS/Pinecone/Chroma）

---

## 🎯 模块定位

向量存储模块负责统一管理所有向量数据存储和检索，支持：
- 向量添加、搜索、删除
- 多种向量数据库后端
- 向量索引配置
- 元数据过滤
- 近似最近邻搜索

---

## ⚙️ 配置文件结构

### 默认配置

**位置**：`config/infra/default.yaml`

```yaml
vector:
  type: milvus                    # milvus, faiss, pinecone, chroma
  host: localhost
  port: 19530
  dimension: 1536                 # text-embedding-3-small 的维度
  
  # 索引配置
  index:
    type: HNSW                    # HNSW, IVF_FLAT, IVF_SQ8
    params:
      m: 16
      ef_construction: 256
      ef_search: 100
  
  # 搜索配置
  search:
    top_k: 10
    metric_type: IP              # IP, L2, COSINE
    ef: 100
  
  # 集合配置
  collection:
    name: documents
    description: AI platform document vectors
    shards: 2
    replicas: 1
  
  # 延迟初始化
  lazy_init: true
```

---

## 📖 核心接口定义

### VectorStore 接口

**位置**：`infra/vector/base.py`

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `add` | `vectors: List[Vector]`, `metadata: List[dict]` | `List[str]` | 添加向量 |
| `search` | `query_vector: List[float]`, `top_k: int`, `filter: dict` | `List[SearchResult]` | 相似度搜索 |
| `delete` | `ids: List[str]` | `bool` | 删除向量 |
| `get` | `id: str` | `Optional[Vector]` | 获取向量 |
| `count` | 无 | `int` | 向量数量 |
| `upsert` | `vectors: List[Vector]` | `List[str]` | 插入或更新 |
| `create_index` | `index_type: str`, `params: dict` | `None` | 创建索引 |
| `close` | 无 | `None` | 关闭连接 |

### VectorIndex 接口

**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `build` | `vectors: np.ndarray` | `None` | 构建索引 |
| `search` | `query: np.ndarray`, `k: int` | `np.ndarray` | 搜索 |
| `save` | `path: str` | `None` | 保存索引 |
| `load` | `path: str` | `None` | 加载索引 |

---

## 🏭 工厂函数

### create_vector_store

**位置**：`infra/vector/factory.py`

**函数签名**：

```python
def create_vector_store(
    config: VectorConfig
) -> VectorStore:
    """
    创建向量存储客户端

    参数：
        config: 向量存储配置

    返回：
        VectorStore 实例
    """
```

**参数说明**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `config.type` | str | "milvus" | 向量数据库类型 |
| `config.host` | str | "localhost" | 服务器地址 |
| `config.port` | int | 19530 | 服务器端口 |
| `config.dimension` | int | 1536 | 向量维度 |
| `config.collection` | str | "default" | 集合名称 |
| `config.index.type` | str | "HNSW" | 索引类型 |

**使用示例**：

```python
from infra.vector import create_vector_store
from infra.vector.schemas import Vector, VectorConfig

# 创建向量存储
vector_store = create_vector_store(VectorConfig(
    type="milvus",
    host="localhost",
    dimension=1536,
    collection="documents"
))

# 添加向量
vectors = [
    Vector(values=[0.1, 0.2, ...], metadata={"source": "doc1"}),
    Vector(values=[0.3, 0.4, ...], metadata={"source": "doc2"})
]
ids = await vector_store.add(vectors)
print(f"Added {len(ids)} vectors")

# 搜索
results = await vector_store.search(
    query_vector=[0.1, 0.2, ...],
    top_k=5
)
for result in results:
    print(f"ID: {result.id}, Score: {result.score}, Meta: {result.metadata}")
```

---

## 📊 数据模型

### Vector

```python
@dataclass
class Vector:
    id: str
    values: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### SearchResult

```python
@dataclass
class SearchResult:
    id: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    distance: Optional[float] = None
```

### VectorConfig

```python
@dataclass
class VectorConfig:
    type: str = "milvus"         # milvus, faiss, pinecone, chroma
    host: str = "localhost"
    port: int = 19530
    dimension: int = 1536
    collection: str = "default"
    index: Optional[IndexConfig] = None
    search: Optional[SearchConfig] = None
    lazy_init: bool = True

@dataclass
class IndexConfig:
    type: str = "HNSW"
    params: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SearchConfig:
    top_k: int = 10
    metric_type: str = "IP"
    ef: int = 100
```

---

## 🚀 使用示例

### 基本操作

```python
from infra.vector import create_vector_store, Vector

vector_store = create_vector_store(VectorConfig(
    type="milvus",
    dimension=1536
))

# 添加向量
vector = Vector(
    id="doc_1",
    values=[0.1] * 1536,
    metadata={"source": "doc1", "page": 1}
)
ids = await vector_store.add([vector])
print(f"Added vectors: {ids}")

# 批量添加
vectors = [
    Vector(values=[0.1] * 1536, metadata={"id": f"doc_{i}"})
    for i in range(100)
]
ids = await vector_store.add(vectors)

# 搜索
query = [0.15] * 1536
results = await vector_store.search(query, top_k=5)
print(f"Found {len(results)} results")
for r in results:
    print(f"  ID: {r.id}, Score: {r.score:.4f}")

# 获取向量
vector = await vector_store.get("doc_1")
print(f"Vector: {vector.values[:10]}...")

# 删除向量
await vector_store.delete(["doc_1", "doc_2"])

# 计数
count = await vector_store.count()
print(f"Total vectors: {count}")
```

### 元数据过滤

```python
# 过滤搜索
results = await vector_store.search(
    query_vector=query,
    top_k=10,
    filter={
        "source": "doc1",
        "page": {"$gte": 1, "$lte": 10}
    }
)

# 复杂过滤
results = await vector_store.search(
    query_vector=query,
    top_k=10,
    filter={
        "$and": [
            {"source": {"$in": ["doc1", "doc2"]}},
            {"page": {"$gt": 0}},
            {"status": "active"}
        ]
    }
)
```

### 索引管理

```python
# 创建索引
await vector_store.create_index(
    index_type="HNSW",
    params={
        "m": 16,
        "ef_construction": 256
    }
)

# 查看索引信息
info = await vector_store.get_index_info()
print(f"Index type: {info.index_type}")
print(f"Index params: {info.params}")
```

### 向量计算

```python
# 计算向量相似度
from infra.vector.utils import cosine_similarity, euclidean_distance

v1 = [1.0, 0.0, 0.0]
v2 = [0.707, 0.707, 0.0]

cos_sim = cosine_similarity(v1, v2)
print(f"Cosine similarity: {cos_sim:.4f}")  # 0.7071

dist = euclidean_distance(v1, v2)
print(f"Euclidean distance: {dist:.4f}")  # 0.5858
```

---

## 🔧 扩展指南

### 添加新的向量后端

**文件**：`infra/vector/weaviate.py`

```python
from infra.vector.base import VectorStore
from infra.vector.schemas import Vector, SearchResult

class WeaviateStore(VectorStore):
    """Weaviate 向量存储"""
    
    def __init__(self, config: VectorConfig):
        import weaviate
        self.client = weaviate.Client(url=f"http://{config.host}:{config.port}")
        self.collection = config.collection
    
    async def add(self, vectors: List[Vector], metadata: List[dict]) -> List[str]:
        """添加向量"""
        objects = [
            {
                "vector": v.values,
                "metadata": m
            }
            for v, m in zip(vectors, metadata)
        ]
        
        self.client.batch.add_objects(
            class_name=self.collection,
            objects=objects
        )
        
        return [v.id for v in vectors]
    
    async def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filter: dict = None
    ) -> List[SearchResult]:
        """搜索"""
        query = self.client.query.get(
            self.collection,
            ["id", "metadata"]
        ).with_near_vector({"vector": query_vector})
        
        if filter:
            query = query.with_where(filter)
        
        results = query.with_limit(top_k).do()
        
        return [
            SearchResult(
                id=r["id"],
                score=r["_additional"]["certainty"],
                metadata=r["metadata"]
            )
            for r in results["data"]["Get"][self.collection]
        ]
    
    async def delete(self, ids: List[str]) -> bool:
        """删除"""
        for id in ids:
            self.client.data_object.delete(id, class_name=self.collection)
        return True
```

### 注册到工厂

```python
def create_vector_store(config: VectorConfig) -> VectorStore:
    if config.type == "milvus":
        return MilvusStore(config)
    elif config.type == "faiss":
        return FaissStore(config)
    elif config.type == "pinecone":
        return PineconeStore(config)
    elif config.type == "chroma":
        return ChromaStore(config)
    elif config.type == "weaviate":
        return WeaviateStore(config)
    else:
        raise ValueError(f"Unknown vector store type: {config.type}")
```

---

## ✅ 配置校验

| 配置项 | 校验规则 | 错误信息 |
|--------|----------|----------|
| `vector.type` | milvus/faiss/pinecone/chroma | invalid type |
| `vector.dimension` | > 0 | must be > 0 |
| `vector.index.type` | HNSW/IVF_FLAT/IVF_SQ8 | invalid index type |
| `vector.search.top_k` | > 0 | must be > 0 |

---

## 📁 文件结构

```
infra/vector/
├── __init__.py               # 模块导出
├── base.py                   # VectorStore 接口
├── factory.py                # create_vector_store()
├── schemas.py                # 数据模型
├── utils.py                 # 向量计算工具
├── milvus.py                # Milvus 实现
├── faiss.py                 # FAISS 实现
├── pinecone.py               # Pinecone 实现
└── chroma.py               # Chroma 实现
```

---

*最后更新: 2026-04-11*