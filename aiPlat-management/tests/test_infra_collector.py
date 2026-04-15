"""
Tests for InfraMetricsCollector
"""

import pytest
from management.monitoring import InfraMetricsCollector, Metric


class TestInfraMetricsCollector:
    """Test InfraMetricsCollector"""
    
    @pytest.fixture
    def collector(self):
        """Create InfraMetricsCollector instance"""
        return InfraMetricsCollector(endpoint="http://localhost:8001")
    
    @pytest.mark.asyncio
    async def test_collect(self, collector):
        """Test collect method"""
        metrics = await collector.collect()
        
        assert isinstance(metrics, list)
        assert len(metrics) > 0
        assert all(isinstance(m, Metric) for m in metrics)
    
    @pytest.mark.asyncio
    async def test_collect_database_metrics(self, collector):
        """Test database metrics collection"""
        metrics = await collector._collect_database_metrics()
        
        assert isinstance(metrics, list)
        assert len(metrics) > 0
        
        # Check connection metrics
        connection_metrics = [m for m in metrics if "connection" in m.name]
        assert len(connection_metrics) > 0
        
        # Check query metrics
        query_metrics = [m for m in metrics if "query" in m.name]
        assert len(query_metrics) > 0
    
    @pytest.mark.asyncio
    async def test_collect_cache_metrics(self, collector):
        """Test cache metrics collection"""
        metrics = await collector._collect_cache_metrics()
        
        assert isinstance(metrics, list)
        assert len(metrics) > 0
        
        # Check hit rate metrics
        hit_rate_metrics = [m for m in metrics if "hit_rate" in m.name]
        assert len(hit_rate_metrics) > 0
        
        # Check memory metrics
        memory_metrics = [m for m in metrics if "memory" in m.name]
        assert len(memory_metrics) > 0
    
    @pytest.mark.asyncio
    async def test_collect_vector_metrics(self, collector):
        """Test vector metrics collection"""
        metrics = await collector._collect_vector_metrics()
        
        assert isinstance(metrics, list)
        assert len(metrics) > 0
        
        # Check collection metrics
        collection_metrics = [m for m in metrics if "collection" in m.name]
        assert len(collection_metrics) > 0
        
        # Check query metrics
        query_metrics = [m for m in metrics if "query" in m.name]
        assert len(query_metrics) > 0
    
    @pytest.mark.asyncio
    async def test_collect_llm_metrics(self, collector):
        """Test LLM metrics collection"""
        metrics = await collector._collect_llm_metrics()
        
        assert isinstance(metrics, list)
        assert len(metrics) > 0
        
        # Check request metrics
        request_metrics = [m for m in metrics if "request" in m.name]
        assert len(request_metrics) > 0
        
        # Check token metrics
        token_metrics = [m for m in metrics if "token" in m.name]
        assert len(token_metrics) > 0
        
        # Check latency metrics
        latency_metrics = [m for m in metrics if "latency" in m.name]
        assert len(latency_metrics) > 0
    
    @pytest.mark.asyncio
    async def test_collect_messaging_metrics(self, collector):
        """Test messaging metrics collection"""
        metrics = await collector._collect_messaging_metrics()
        
        assert isinstance(metrics, list)
        assert len(metrics) > 0
        
        # Check queue metrics
        queue_metrics = [m for m in metrics if "queue" in m.name]
        assert len(queue_metrics) > 0
        
        # Check throughput metrics
        throughput_metrics = [m for m in metrics if "throughput" in m.name]
        assert len(throughput_metrics) > 0
    
    @pytest.mark.asyncio
    async def test_collect_storage_metrics(self, collector):
        """Test storage metrics collection"""
        metrics = await collector._collect_storage_metrics()
        
        assert isinstance(metrics, list)
        assert len(metrics) > 0
        
        # Check space metrics
        space_metrics = [m for m in metrics if "space" in m.name]
        assert len(space_metrics) > 0
        
        # Check file metrics
        file_metrics = [m for m in metrics if "file" in m.name]
        assert len(file_metrics) > 0
    
    @pytest.mark.asyncio
    async def test_collect_network_metrics(self, collector):
        """Test network metrics collection"""
        metrics = await collector._collect_network_metrics()
        
        assert isinstance(metrics, list)
        assert len(metrics) > 0
        
        # Check connection metrics
        connection_metrics = [m for m in metrics if "connection" in m.name]
        assert len(connection_metrics) > 0
        
        # Check latency metrics
        latency_metrics = [m for m in metrics if "latency" in m.name]
        assert len(latency_metrics) > 0
    
    @pytest.mark.asyncio
    async def test_collect_memory_metrics(self, collector):
        """Test memory metrics collection"""
        metrics = await collector._collect_memory_metrics()
        
        assert isinstance(metrics, list)
        assert len(metrics) > 0
        
        # Check system memory metrics
        system_metrics = [m for m in metrics if "system" in m.name]
        assert len(system_metrics) > 0
        
        # Check process memory metrics
        process_metrics = [m for m in metrics if "process" in m.name]
        assert len(process_metrics) > 0
    
    @pytest.mark.asyncio
    async def test_metric_labels(self, collector):
        """Test metric labels"""
        metrics = await collector.collect()
        
        for metric in metrics:
            assert metric.name is not None
            assert metric.value is not None
            assert metric.unit is not None
    
    @pytest.mark.asyncio
    async def test_get_all_metrics(self, collector):
        """Test get_all_metrics method"""
        all_metrics = await collector.get_all_metrics()
        
        assert "layer" in all_metrics
        assert all_metrics["layer"] == "infra"
        assert "timestamp" in all_metrics
        assert "metrics" in all_metrics
        assert isinstance(all_metrics["metrics"], list)