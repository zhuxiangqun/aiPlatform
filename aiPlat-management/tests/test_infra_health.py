"""
Tests for InfraHealthChecker
"""

import pytest
from management.diagnostics import InfraHealthChecker, HealthStatus


class TestInfraHealthChecker:
    """Test InfraHealthChecker"""
    
    @pytest.fixture
    def checker(self):
        """Create InfraHealthChecker instance"""
        return InfraHealthChecker(endpoint="http://localhost:8001")
    
    @pytest.mark.asyncio
    async def test_check(self, checker):
        """Test check method"""
        results = await checker.check()
        
        assert isinstance(results, list)
        assert len(results) > 0
        
        # Should have checks for all components
        component_names = [r.component for r in results]
        assert "database_connection_pool" in component_names
        assert "cache_connection" in component_names
        assert "vector_connection" in component_names
        assert "llm_api_availability" in component_names
        assert "messaging_connection" in component_names
        assert "storage_space" in component_names
        assert "network_connectivity" in component_names
        assert "memory_system" in component_names
    
    @pytest.mark.asyncio
    async def test_check_database(self, checker):
        """Test database health checks"""
        results = await checker._check_database()
        
        assert isinstance(results, list)
        assert len(results) >= 3  #connection pool, query performance, availability
        
        # Check connection pool result
        pool_result = next(r for r in results if r.component == "database_connection_pool")
        assert pool_result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        assert "active_connections" in pool_result.details
        assert "max_connections" in pool_result.details
    
    @pytest.mark.asyncio
    async def test_check_cache(self, checker):
        """Test cache health checks"""
        results = await checker._check_cache()
        
        assert isinstance(results, list)
        assert len(results) >= 3  # connection, memory, hit rate
        
        # Check cache connection result
        connection_result = next(r for r in results if r.component == "cache_connection")
        assert connection_result.status == HealthStatus.HEALTHY
        assert "type" in connection_result.details
        assert "host" in connection_result.details
        
        # Check hit rate result
        hit_rate_result = next(r for r in results if r.component == "cache_hit_rate")
        assert "hit_rate" in hit_rate_result.details
    
    @pytest.mark.asyncio
    async def test_check_vector(self, checker):
        """Test vector storage health checks"""
        results = await checker._check_vector()
        
        assert isinstance(results, list)
        assert len(results) >= 3  # connection, index, collections
        
        # Check connection result
        connection_result = next(r for r in results if r.component == "vector_connection")
        assert connection_result.status == HealthStatus.HEALTHY
        
        # Check index result
        index_result = next(r for r in results if r.component == "vector_index")
        assert "query_latency_avg_ms" in index_result.details
    
    @pytest.mark.asyncio
    async def test_check_llm(self, checker):
        """Test LLM health checks"""
        results = await checker._check_llm()
        
        assert isinstance(results, list)
        assert len(results) >= 4  # api availability, model availability, latency, queue
        
        # Check API availability result
        api_result = next(r for r in results if r.component == "llm_api_availability")
        assert api_result.status == HealthStatus.HEALTHY
        assert "provider" in api_result.details
        
        # Check latency result
        latency_result = next(r for r in results if r.component == "llm_latency")
        assert "avg_latency_seconds" in latency_result.details
    
    @pytest.mark.asyncio
    async def test_check_messaging(self, checker):
        """Test messaging health checks"""
        results = await checker._check_messaging()
        
        assert isinstance(results, list)
        assert len(results) >= 3  # connection, queue status, consumers
        
        # Check connection result
        connection_result = next(r for r in results if r.component == "messaging_connection")
        assert connection_result.status == HealthStatus.HEALTHY
        
        # Check queue status result
        queue_result = next(r for r in results if r.component == "messaging_queue_status")
        assert "total_messages" in queue_result.details
    
    @pytest.mark.asyncio
    async def test_check_storage(self, checker):
        """Test storage health checks"""
        results = await checker._check_storage()
        
        assert isinstance(results, list)
        assert len(results) >= 2  # space, filesystem
        
        # Check space result
        space_result = next(r for r in results if r.component == "storage_space")
        assert "total_bytes" in space_result.details
        assert "used_bytes" in space_result.details
        assert "available_bytes" in space_result.details
    
    @pytest.mark.asyncio
    async def test_check_network(self, checker):
        """Test network health checks"""
        results = await checker._check_network()
        
        assert isinstance(results, list)
        assert len(results) >= 3  # connectivity, latency, traffic
        
        # Check connectivity result
        connectivity_result = next(r for r in results if r.component == "network_connectivity")
        assert connectivity_result.status == HealthStatus.HEALTHY
        
        # Check latency result
        latency_result = next(r for r in results if r.component == "network_latency")
        assert "avg_latency_ms" in latency_result.details
    
    @pytest.mark.asyncio
    async def test_check_memory(self, checker):
        """Test memory health checks"""
        results = await checker._check_memory()
        
        assert isinstance(results, list)
        assert len(results) >= 3  # system, processes, gpu
        
        # Check system memory result
        system_result = next(r for r in results if r.component == "memory_system")
        assert "total_bytes" in system_result.details
        assert "used_bytes" in system_result.details
    
    @pytest.mark.asyncio
    async def test_get_health(self, checker):
        """Test get_health method"""
        health = await checker.get_health()
        
        assert "layer" in health
        assert health["layer"] == "infra"
        assert "status" in health
        assert health["status"] in ["healthy", "degraded", "unhealthy"]
        assert "timestamp" in health
        assert "checks" in health
        assert isinstance(health["checks"], list)
    
    @pytest.mark.asyncio
    async def test_thresholds(self, checker):
        """Test health check thresholds"""
        assert "database_connection_usage" in checker.thresholds
        assert "cache_memory_usage" in checker.thresholds
        assert "cache_hit_rate_warning" in checker.thresholds
        assert "cache_hit_rate_critical" in checker.thresholds
        assert "storage_usage" in checker.thresholds
        assert "memory_usage" in checker.thresholds
    
    @pytest.mark.asyncio
    async def test_health_status_calculation(self, checker):
        """Test overall health status calculation"""
        health = await checker.get_health()
        
        # If all checks are healthy, overall should be healthy
        all_checks_healthy = all(
            check["status"] in ["healthy", "degraded"]
            for check in health["checks"]
        )
        if all_checks_healthy:
            assert health["status"] in ["healthy", "degraded"]