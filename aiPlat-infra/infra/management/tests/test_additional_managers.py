"""
Additional Manager Tests

Tests for MonitoringManager, CostManager, VectorManager, and MessagingManager.
"""

import pytest
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from infra.management.monitoring.manager import MonitoringManager
from infra.management.cost.manager import CostManager
from infra.management.vector.manager import VectorManager
from infra.management.messaging.manager import MessagingManager
from infra.management.base import Status
from infra.management.schemas import AlertRule


class TestMonitoringManager:
    """Test MonitoringManager"""
    
    @pytest.mark.asyncio
    async def test_add_alert_rule(self):
        """Test adding alert rules"""
        manager = MonitoringManager({})
        
        rule = AlertRule(
            name="high_cpu",
            metric="cpu_usage",
            threshold=0.9,
            duration=300,
            severity="critical",
            enabled=True
        )
        
        success = await manager.add_alert_rule(rule)
        assert success is True
        
        rules = await manager.get_alert_rules()
        assert len(rules) == 1
        assert rules[0].name == "high_cpu"
    
    @pytest.mark.asyncio
    async def test_trigger_and_resolve_alert(self):
        """Test triggering and resolving alerts"""
        manager = MonitoringManager({})
        
        rule = AlertRule(
            name="high_memory",
            metric="memory_usage",
            threshold=0.85,
            duration=60,
            severity="warning",
            enabled=True
        )
        
        await manager.add_alert_rule(rule)
        
        alert = await manager.trigger_alert("high_memory", "Memory usage at 92%")
        assert alert is not None
        assert alert.status == "active"
        
        resolved = await manager.resolve_alert(alert.alert_id)
        assert resolved is True
        
        alerts = await manager.get_alerts(status="resolved")
        assert len(alerts) == 1
    
    @pytest.mark.asyncio
    async def test_threshold_management(self):
        """Test threshold management"""
        manager = MonitoringManager({})
        
        await manager.set_threshold("cpu_usage", 0.85)
        threshold = await manager.get_threshold("cpu_usage")
        
        assert threshold == 0.85
    
    @pytest.mark.asyncio
    async def test_check_thresholds(self):
        """Test threshold violation checking"""
        manager = MonitoringManager({})
        
        await manager.set_threshold("cpu_usage", 0.8)
        await manager.set_threshold("memory_usage", 0.9)
        
        metrics = {
            "cpu_usage": 0.85,
            "memory_usage": 0.75,
            "disk_usage": 0.95
        }
        
        violations = await manager.check_thresholds(metrics)
        
        assert len(violations) == 1
        assert violations[0]["metric"] == "cpu_usage"
    
    @pytest.mark.asyncio
    async def test_enable_disable_rules(self):
        """Test enabling and disabling alert rules"""
        manager = MonitoringManager({})
        
        rule = AlertRule(
            name="test_rule",
            metric="test_metric",
            threshold=1.0,
            duration=60,
            severity="info",
            enabled=True
        )
        
        await manager.add_alert_rule(rule)
        
        disabled = await manager.disable_rule("test_rule")
        assert disabled is True
        
        rules = await manager.get_alert_rules()
        assert rules[0].enabled is False
        
        enabled = await manager.enable_rule("test_rule")
        assert enabled is True
        
        rules = await manager.get_alert_rules()
        assert rules[0].enabled is True


class TestCostManager:
    """Test CostManager"""
    
    @pytest.mark.asyncio
    async def test_set_budget(self):
        """Test setting budgets"""
        manager = CostManager({})
        
        await manager.set_budget("daily", 100)
        await manager.set_budget("monthly", 3000)
        
        daily = await manager.get_budget("daily")
        monthly = await manager.get_budget("monthly")
        
        assert daily == 100
        assert monthly == 3000
    
    @pytest.mark.asyncio
    async def test_record_cost(self):
        """Test recording costs"""
        manager = CostManager({})
        
        await manager.record_cost("openai", 15.50, {"model": "gpt-4"})
        await manager.record_cost("aws", 23.45, {"service": "s3"})
        
        breakdown = await manager.get_cost_breakdown()
        
        assert breakdown.total > 0
        assert "openai" in breakdown.by_model
        assert "aws" in breakdown.by_model
    
    @pytest.mark.asyncio
    async def test_budget_status(self):
        """Test getting budget status"""
        manager = CostManager({"budget": {"daily": 100, "monthly": 3000}})
        
        await manager.record_cost("service1", 50)
        await manager.record_cost("service2", 100)
        
        status = await manager.get_budget_status()
        
        assert status.daily_limit == 100
        assert status.monthly_limit == 3000
        assert status.daily_used > 0
        assert status.monthly_used > 0
    
    @pytest.mark.asyncio
    async def test_top_costs(self):
        """Test getting top cost services"""
        manager = CostManager({})
        
        await manager.record_cost("service-a", 100)
        await manager.record_cost("service-b", 50)
        await manager.record_cost("service-c", 75)
        
        top_costs = await manager.get_top_costs(limit=2)
        
        assert len(top_costs) == 2
        assert top_costs[0]["service"] == "service-a"
    
    @pytest.mark.asyncio
    async def test_cost_optimization(self):
        """Test cost optimization recommendations"""
        manager = CostManager({})
        
        # Record high-cost service
        for i in range(20):
            await manager.record_cost("expensive-service", 15)
        
        recommendations = await manager.optimize_costs()
        
        assert len(recommendations) > 0
        assert recommendations[0]["type"] == "high_cost"


class TestVectorManager:
    """Test VectorManager"""
    
    @pytest.mark.asyncio
    async def test_create_collection(self):
        """Test creating vector collections"""
        manager = VectorManager({})
        
        created = await manager.create_collection("test-collection", {"dimension": 1536})
        assert created is True
        
        collections = await manager.list_collections()
        assert "test-collection" in collections
    
    @pytest.mark.asyncio
    async def test_insert_vectors(self):
        """Test inserting vectors"""
        manager = VectorManager({})
        
        await manager.create_collection("embeddings", {"dimension": 768})
        
        vectors = [
            {"vector": [0.1] * 768, "metadata": {"id": "1"}},
            {"vector": [0.2] * 768, "metadata": {"id": "2"}}
        ]
        
        ids = await manager.insert_vectors("embeddings", vectors)
        
        assert len(ids) == 2
        
        count = await manager.get_vector_count("embeddings")
        assert count == 2
    
    @pytest.mark.asyncio
    async def test_search_vectors(self):
        """Test vector search"""
        manager = VectorManager({})
        
        await manager.create_collection("search-test", {"dimension": 512})
        
        vectors = [
            {"vector": [0.5] * 512, "metadata": {"category": "A"}},
            {"vector": [0.3] * 512, "metadata": {"category": "B"}}
        ]
        
        await manager.insert_vectors("search-test", vectors)
        
        results = await manager.search_vectors(
            "search-test",
            [0.4] * 512,
            top_k=2
        )
        
        assert len(results) == 2
    
    @pytest.mark.asyncio
    async def test_delete_vectors(self):
        """Test deleting vectors"""
        manager = VectorManager({})
        
        await manager.create_collection("delete-test", {"dimension": 256})
        
        vectors = [
            {"vector": [0.1] * 256, "metadata": {"id": "1"}},
            {"vector": [0.2] * 256, "metadata": {"id": "2"}}
        ]
        
        ids = await manager.insert_vectors("delete-test", vectors)
        
        deleted = await manager.delete_vectors("delete-test", [ids[0]])
        
        assert deleted == 1
        
        count = await manager.get_vector_count("delete-test")
        assert count == 1
    
    @pytest.mark.asyncio
    async def test_collection_stats(self):
        """Test getting collection statistics"""
        manager = VectorManager({})
        
        await manager.create_collection("stats-test", {"dimension": 128})
        
        stats = await manager.get_collection_stats("stats-test")
        
        assert stats["name"] == "stats-test"
        assert stats["status"] == "healthy"
        assert stats["dimension"] == 128


class TestMessagingManager:
    """Test MessagingManager"""
    
    @pytest.mark.asyncio
    async def test_create_queue(self):
        """Test creating message queues"""
        manager = MessagingManager({})
        
        created = await manager.create_queue("test-queue")
        assert created is True
        
        queues = await manager.list_queues()
        assert "test-queue" in queues
    
    @pytest.mark.asyncio
    async def test_publish_and_consume(self):
        """Test publishing and consuming messages"""
        manager = MessagingManager({})
        
        await manager.create_queue("work-queue")
        await manager.register_consumer("work-queue", "consumer-1")
        
        published = await manager.publish("work-queue", {"task": "process_data"})
        assert published is True
        
        message = await manager.consume("work-queue", "consumer-1")
        
        assert message is not None
        assert message["data"]["task"] == "process_data"
        assert message["status"] == "processing"
    
    @pytest.mark.asyncio
    async def test_ack_message(self):
        """Test acknowledging messages"""
        manager = MessagingManager({})
        
        await manager.create_queue("ack-queue")
        await manager.register_consumer("ack-queue", "consumer-1")
        
        await manager.publish("ack-queue", {"job": "test"})
        message = await manager.consume("ack-queue", "consumer-1")
        
        acked = await manager.ack("ack-queue", message["id"])
        assert acked is True
    
    @pytest.mark.asyncio
    async def test_nack_message(self):
        """Test negative acknowledging messages"""
        manager = MessagingManager({})
        
        await manager.create_queue("nack-queue")
        await manager.register_consumer("nack-queue", "consumer-1")
        
        await manager.publish("nack-queue", {"job": "test"})
        message = await manager.consume("nack-queue", "consumer-1")
        
        nacked = await manager.nack("nack-queue", message["id"])
        assert nacked is True
    
    @pytest.mark.asyncio
    async def test_queue_depth(self):
        """Test getting queue depth"""
        manager = MessagingManager({})
        
        await manager.create_queue("depth-queue")
        
        await manager.publish("depth-queue", {"msg": "1"})
        await manager.publish("depth-queue", {"msg": "2"})
        await manager.publish("depth-queue", {"msg": "3"})
        
        depth = await manager.get_queue_depth("depth-queue")
        assert depth == 3
    
    @pytest.mark.asyncio
    async def test_queue_stats(self):
        """Test getting queue statistics"""
        manager = MessagingManager({})
        
        await manager.create_queue("stats-queue")
        await manager.register_consumer("stats-queue", "consumer-1")
        
        await manager.publish("stats-queue", {"test": "data"})
        
        stats = await manager.get_queue_stats("stats-queue")
        
        assert stats["name"] == "stats-queue"
        assert stats["total_messages"] == 1
        assert stats["consumers"] == 1
    
    @pytest.mark.asyncio
    async def test_purge_queue(self):
        """Test purging queue"""
        manager = MessagingManager({})
        
        await manager.create_queue("purge-queue")
        
        await manager.publish("purge-queue", {"msg": "1"})
        await manager.publish("purge-queue", {"msg": "2"})
        
        purged = await manager.purge_queue("purge-queue")
        assert purged == 2
        
        depth = await manager.get_queue_depth("purge-queue")
        assert depth == 0
    
    @pytest.mark.asyncio
    async def test_consumer_management(self):
        """Test consumer registration"""
        manager = MessagingManager({})
        
        await manager.create_queue("consumer-queue")
        
        registered = await manager.register_consumer("consumer-queue", "consumer-1")
        assert registered is True
        
        registered = await manager.register_consumer("consumer-queue", "consumer-2")
        assert registered is True
        
        unregistered = await manager.unregister_consumer("consumer-queue", "consumer-1")
        assert unregistered is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])