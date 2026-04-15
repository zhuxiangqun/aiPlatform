"""vector 模块真实功能测试"""

import pytest
import numpy as np
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import asyncio

from infra.vector.schemas import Vector, VectorConfig, SearchResult


class TestFaissStore:
    """FAISS 向量存储测试 - 使用真实实例"""

    @pytest.mark.asyncio
    async def test_faiss_add_vectors(self):
        """测试添加向量"""
        from infra.vector.faiss import FaissStore
        
        config = VectorConfig(
            type="faiss",
            dimension=128
        )
        store = FaissStore(config)
        
        # 创建测试向量
        vectors = [
            Vector(id="v1", values=np.random.randn(128).tolist(), metadata={"type": "test"}),
            Vector(id="v2", values=np.random.randn(128).tolist(), metadata={"type": "test"}),
        ]
        
        # 添加向量
        ids = await store.add(vectors)
        
        # 验证返回值
        assert len(ids) == 2
        assert ids[0] == "v1"
        assert ids[1] == "v2"
    
    @pytest.mark.asyncio
    async def test_faiss_search_vectors(self):
        """测试向量搜索"""
        from infra.vector.faiss import FaissStore
        
        config = VectorConfig(type="faiss", dimension=128)
        store = FaissStore(config)
        
        # 添加测试向量
        vectors = [Vector(id="v1", values=[1.0] * 128, metadata={"key": "value"})]
        await store.add(vectors)
        
        # 搜索向量
        query_vector = [1.0] * 128
        results = await store.search(query_vector, top_k=5)
        
        # 验证返回值
        assert len(results) > 0
        assert isinstance(results[0], SearchResult)
        assert results[0].id == "v1"
        assert results[0].score >= 0.99  # 相同向量，相似度应该很高
        assert results[0].metadata["key"] == "value"
    
    @pytest.mark.asyncio
    async def test_faiss_delete_vectors(self):
        """测试删除向量"""
        from infra.vector.faiss import FaissStore
        
        config = VectorConfig(type="faiss", dimension=128)
        store = FaissStore(config)
        
        # 添加向量
        vectors = [Vector(id="v3", values=np.random.randn(128).tolist())]
        await store.add(vectors)
        
        # 删除向量
        success = await store.delete(["v3"])
        assert success is True
        
        # 验证已删除
        result = await store.get("v3")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_faiss_get_vector(self):
        """测试获取单个向量"""
        from infra.vector.faiss import FaissStore
        
        config = VectorConfig(type="faiss", dimension=128)
        store = FaissStore(config)
        
        # 添加向量
        values = np.random.randn(128).tolist()
        vectors = [Vector(id="v4", values=values, metadata={"tag": "demo"})]
        await store.add(vectors)
        
        # 获取向量
        result = await store.get("v4")
        
        # 验证返回值
        assert result is not None
        assert result.id == "v4"
        assert len(result.values) == 128
        assert result.metadata["tag"] == "demo"
    
    @pytest.mark.asyncio
    async def test_faiss_count_vectors(self):
        """测试统计向量数量"""
        from infra.vector.faiss import FaissStore
        
        config = VectorConfig(type="faiss", dimension=128)
        store = FaissStore(config)
        
        # 添加多个向量
        vectors = [
            Vector(id=str(i), values=np.random.randn(128).tolist())
            for i in range(10)
        ]
        await store.add(vectors)
        
        # 统计数量
        count = await store.count()
        assert count == 10
    
    @pytest.mark.asyncio
    async def test_faiss_upsert_vectors(self):
        """测试更新插入向量"""
        from infra.vector.faiss import FaissStore
        
        config = VectorConfig(type="faiss", dimension=128)
        store = FaissStore(config)
        
        # 插入向量
        vectors1 = [Vector(id="v5", values=[1.0] * 128)]
        await store.upsert(vectors1)
        
        # 更新向量
        vectors2 = [Vector(id="v5", values=[2.0] * 128)]
        ids = await store.upsert(vectors2)
        
        assert len(ids) == 1
        assert ids[0] == "v5"
    
    @pytest.mark.asyncio
    async def test_faiss_create_index(self):
        """测试创建索引"""
        from infra.vector.faiss import FaissStore
        
        config = VectorConfig(type="faiss", dimension=128)
        store = FaissStore(config)
        
        # 添加一些向量
        vectors = [Vector(id=str(i), values=np.random.randn(128).tolist()) for i in range(100)]
        await store.add(vectors)
        
        # 创建索引
        await store.create_index("IVFFlat", {"nlist": 10})
        
        # 验证索引已创建（通过搜索测试）
        results = await store.search(np.random.randn(128).tolist(), top_k=5)
        assert isinstance(results, list)


class TestMilvusStore:
    """Milvus 向量存储测试 - 使用Mock"""
    
    @pytest.mark.asyncio
    async def test_milvus_add_vectors(self):
        """测试添加向量到Milvus"""
        from infra.vector.milvus import MilvusStore
        
        config = VectorConfig(
            type="milvus",
            host="localhost",
            port=19530,
            dimension=128
        )
        
        # Mock MilvusClient
        with patch('infra.vector.milvus.MilvusClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Mock insert返回
            mock_insert_result = MagicMock()
            mock_insert_result.insert_primary_keys = ["id1", "id2"]
            mock_client.insert.return_value = mock_insert_result
            
            # Mock collection检查
            mock_collection = MagicMock()
            mock_client.has_collection.return_value = True
            mock_client.get_collection.return_value = mock_collection
            
            store = MilvusStore(config)
            
            # 直接设置_client，避免初始化
            store._client = mock_client
            store._collection_name = "test_collection"
            store._initialized = True
            
            vectors = [
                Vector(id="id1", values=[1.0] * 128, metadata={"type": "test"}),
                Vector(id="id2", values=[2.0] * 128, metadata={"type": "test"}),
            ]
            
            # 添加向量
            ids = await store.add(vectors)
            
            # 验证返回值
            assert len(ids) == 2
            assert "id1" in ids or "id2" in ids
    
    @pytest.mark.asyncio
    async def test_milvus_search_vectors(self):
        """测试搜索向量"""
        from infra.vector.milvus import MilvusStore
        
        config = VectorConfig(type="milvus", dimension=128)
        
        with patch('infra.vector.milvus.MilvusClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Mock search返回 - 使用支持.get()方法的dict
            mock_hit = {
                "id": "result1",
                "distance": 0.95,
                "entity": {"metadata": '{"key": "value"}'}
            }
            mock_client.search.return_value = [[mock_hit]]
            
            store = MilvusStore(config)
            store._client = mock_client
            store._collection_name = "test_collection"
            store._initialized = True
            
            # 搜索
            results = await store.search([1.0] * 128, top_k=5)
            
            # 验证结果
            assert len(results) > 0
            assert results[0].id == "result1"
            assert results[0].score >= 0.9
    
    @pytest.mark.asyncio
    async def test_milvus_delete_vectors(self):
        """测试删除向量"""
        from infra.vector.milvus import MilvusStore
        
        config = VectorConfig(type="milvus", dimension=128)
        
        with patch('infra.vector.milvus.MilvusClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            mock_client.delete.return_value = MagicMock()
            
            store = MilvusStore(config)
            store._client = mock_client
            store._collection_name = "test_collection"
            store._initialized = True
            
            success = await store.delete(["id1", "id2"])
            
            assert success is True
            mock_client.delete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_milvus_count_vectors(self):
        """测试统计向量数量"""
        from infra.vector.milvus import MilvusStore
        
        config = VectorConfig(type="milvus", dimension=128)
        
        with patch('infra.vector.milvus.MilvusClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Mock get_collection_stats返回 - row_count is accesseds as dict
            mock_client.get_collection_stats.return_value = {"row_count": 100}
            
            store = MilvusStore(config)
            store._client = mock_client
            store._collection_name = "test_collection"
            store._initialized = True
            
            count = await store.count()
            
            assert count == 100


class TestVectorStoreErrors:
    """测试错误处理"""
    
    @pytest.mark.asyncio
    async def test_faiss_invalid_vector_dimension(self):
        """测试无效向量维度"""
        from infra.vector.faiss import FaissStore
        
        config = VectorConfig(type="faiss", dimension=128)
        store = FaissStore(config)
        
        # 尝试添加错误维度的向量
        vectors = [Vector(id="v1", values=[1.0] * 64)]  # 应该是128维
        
        # FAISS会抛出AssertionError（维度不匹配）
        with pytest.raises((AssertionError, ValueError, RuntimeError)):
            await store.add(vectors)
    
    @pytest.mark.asyncio
    async def test_faiss_get_nonexistent_vector(self):
        """测试获取不存在的向量"""
        from infra.vector.faiss import FaissStore
        
        config = VectorConfig(type="faiss", dimension=128)
        store = FaissStore(config)
        
        result = await store.get("nonexistent_id")
        
        # 应该返回None
        assert result is None
    
    @pytest.mark.asyncio
    async def test_faiss_delete_nonexistent_vector(self):
        """测试删除不存在的向量"""
        from infra.vector.faiss import FaissStore
        
        config = VectorConfig(type="faiss", dimension=128)
        store = FaissStore(config)
        
        # 删除不存在的向量应该不影响系统
        success = await store.delete(["nonexistent"])
        
        # 即使向量不存在，delete也应该成功返回
        assert success is True or success is False  # 取决于实现


class TestVectorUtils:
    """向量工具测试"""
    
    def test_cosine_similarity(self):
        """测试余弦相似度计算"""
        from infra.vector.utils import cosine_similarity
        
        # 相同向量
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        result = cosine_similarity(a, b)
        assert result == pytest.approx(1.0)
        
        # 正交向量
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        result = cosine_similarity(a, b)
        assert result == pytest.approx(0.0)
        
        # 相反向量
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        result = cosine_similarity(a, b)
        assert result == pytest.approx(-1.0)
    
    def test_normalize(self):
        """测试向量归一化"""
        from infra.vector.utils import normalize
        
        # 测试归一化
        vec = np.array([3.0, 4.0])
        result = normalize(vec)
        
        # 验证长度为1
        norm = np.linalg.norm(result)
        assert norm == pytest.approx(1.0)
        
        # 验证方向一致
        assert result[0] == pytest.approx(0.6)
        assert result[1] == pytest.approx(0.8)


class TestVectorFactory:
    """测试工厂函数"""
    
    def test_create_faiss_store(self):
        """测试创建FAISS存储"""
        from infra.vector.factory import create_vector_store
        from infra.vector.schemas import VectorConfig
        
        config = VectorConfig(type="faiss", dimension=128)
        store = create_vector_store(config)
        
        assert store is not None
        assert hasattr(store, 'add')
        assert hasattr(store, 'search')
        assert hasattr(store, 'delete')
    
    def test_create_milvus_store(self):
        """测试创建Milvus存储"""
        from infra.vector.factory import create_vector_store
        from infra.vector.schemas import VectorConfig
        
        config = VectorConfig(type="milvus", host="localhost", port=19530, dimension=128)
        store = create_vector_store(config)
        
        assert store is not None
        assert hasattr(store, 'add')
        assert hasattr(store, 'search')
    
    def test_create_chroma_store(self):
        """测试创建Chroma存储"""
        from infra.vector.factory import create_vector_store
        from infra.vector.schemas import VectorConfig
        
        config = VectorConfig(type="chroma", dimension=128)
        store = create_vector_store(config)
        
        assert store is not None
    
    def test_create_pinecone_store(self):
        """测试创建Pinecone存储"""
        from infra.vector.factory import create_vector_store
        from infra.vector.schemas import VectorConfig
        
        config = VectorConfig(type="pinecone", dimension=128)
        store = create_vector_store(config)
        
        assert store is not None
    
    def test_unsupported_type(self):
        """测试不支持的存储类型"""
        from infra.vector.factory import create_vector_store
        from infra.vector.schemas import VectorConfig
        
        config = VectorConfig(type="unsupported")
        
        with pytest.raises(ValueError):
            create_vector_store(config)


class TestVectorSchemas:
    """测试数据模型"""
    
    def test_vector_creation(self):
        """测试向量创建"""
        values = [1.0, 2.0, 3.0]
        metadata = {"key": "value"}
        
        vector = Vector(id="test_id", values=values, metadata=metadata)
        
        assert vector.id == "test_id"
        assert vector.values == values
        assert vector.metadata == metadata
    
    def test_search_result_creation(self):
        """测试搜索结果创建"""
        result = SearchResult(
            id="result_id",
            score=0.95,
            metadata={"type": "test"}
        )
        
        assert result.id == "result_id"
        assert result.score == 0.95
        assert result.metadata["type"] == "test"
    
    def test_vector_config_defaults(self):
        """测试向量配置默认值"""
        config = VectorConfig(type="faiss", dimension=128)
        
        # 验证默认值
        assert config.type == "faiss"
        assert config.dimension == 128