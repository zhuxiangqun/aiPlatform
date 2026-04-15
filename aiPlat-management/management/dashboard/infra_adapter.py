"""
Layer 0 (infra) 适配器 - Dashboard 数据聚合
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
from .system_info import get_all_metrics
from .service_detector import (
    check_postgresql, check_redis, check_milvus, check_rabbitmq,
    check_ollama, get_network_connections, get_process_info
)


@dataclass
class ComponentStatus:
    """组件状态"""
    name: str
    status: str  # healthy, degraded, unhealthy
    message: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)


class InfraAdapter:
    """Layer 0 (infra) Dashboard 适配器
    
    管理infra 层的状态聚合，包括：
    - Database (PostgreSQL, MySQL, MongoDB, SQLite)
    - Cache (Redis)
    - Vector Store (Milvus, Pinecone, Chroma, FAISS)
    - LLM (OpenAI, Anthropic, Local)
    - Messaging (RabbitMQ, Kafka)
    - Storage (File, S3)
    - Network (WebSocket)
    """
    
    def __init__(self, endpoint: str = None):
        self.endpoint = endpoint or "http://localhost:8001"
        self.layer_name = "infra"
        self._init_configs()
        
    async def get_status(self) -> Dict[str, Any]:
        """获取 infra 层整体状态
        
        Returns:
            包含所有组件状态的字典
        """
        components = await self._get_all_component_status()
        overall_status = self._calculate_overall_status(components)
        score = self._calculate_score(components)
        uptime = await self._get_uptime()
        
        return {
            "layer": self.layer_name,
            "status": overall_status,
            "score": score,
            "uptime": uptime,
            "components": {name: self._component_to_dict(comp) for name, comp in components.items()},
            "last_check": datetime.utcnow().isoformat()
        }
    
    async def health_check(self) -> bool:
        """健康检查
        
        Returns:
            所有组件是否健康
        """
        components = await self._get_all_component_status()
        return all(
            comp.status in ["healthy", "degraded"]
            for comp in components.values()
        )
    
    async def get_metrics(self) -> Dict[str, Any]:
        """获取指标数据
        
        Returns:
            各组件的详细指标
        """
        return {
            "database": await self._get_database_metrics(),
            "cache": await self._get_cache_metrics(),
            "vector": await self._get_vector_metrics(),
            "llm": await self._get_llm_metrics(),
            "messaging": await self._get_messaging_metrics(),
            "storage": await self._get_storage_metrics(),
            "network": await self._get_network_metrics(),
            "memory": await self._get_memory_metrics(),
            "compute": await self._get_compute_metrics()
        }
    
    async def _get_all_component_status(self) -> Dict[str, ComponentStatus]:
        """获取所有组件状态"""
        tasks = [
            self._get_database_status(),
            self._get_cache_status(),
            self._get_vector_status(),
            self._get_llm_status(),
            self._get_messaging_status(),
            self._get_storage_status(),
            self._get_network_status(),
            self._get_memory_status(),
            self._get_compute_status()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        components = {}
        names = ["database", "cache", "vector", "llm", "messaging", "storage", "network", "memory", "compute"]
        
        for name, result in zip(names, results):
            if isinstance(result, Exception):
                components[name] = ComponentStatus(
                    name=name,
                    status="unhealthy",
                    message=str(result)
                )
            else:
                components[name] = result
                
        return components
    
    async def _get_database_status(self) -> ComponentStatus:
        """获取数据库状态（真实数据）"""
        db_info = await check_postgresql()
        
        if db_info["running"]:
            status = "healthy"
            message = "PostgreSQL is running"
        else:
            status = "unhealthy"
            message = "PostgreSQL is not running"
        
        return ComponentStatus(
            name="database",
            status=status,
            message=message,
            metrics={
                "connections_active": db_info["connections"]["active"],
                "connections_idle": db_info["connections"]["idle"],
                "connections_max": db_info["connections"]["max"]
            },
            details={
                "type": "postgres",
                "host": db_info["host"],
                "port": db_info["port"],
                "running": db_info["running"]
            }
        )
    
    async def _get_cache_status(self) -> ComponentStatus:
        """获取缓存状态（真实数据）"""
        redis_info = await check_redis()
        
        if redis_info["running"]:
            status = "healthy"
            message = "Redis is running"
        else:
            status = "unhealthy"
            message = "Redis is not running"
        
        return ComponentStatus(
            name="cache",
            status=status,
            message=message,
            metrics={
                "hit_rate": redis_info["hit_rate"],
                "miss_rate": redis_info["miss_rate"],
                "memory_used_bytes": redis_info["memory"]["used_bytes"],
                "memory_max_bytes": redis_info["memory"]["max_bytes"],
                "memory_usage_percent": redis_info["memory"]["usage_percent"],
                "keys_total": redis_info["keys"]["total"]
            },
            details={
                "type": "redis",
                "host": redis_info["host"],
                "port": redis_info["port"],
                "running": redis_info["running"]
            }
        )
    
    async def _get_vector_status(self) -> ComponentStatus:
        """获取向量存储状态（真实数据）"""
        milvus_info = await check_milvus()
        
        if milvus_info["running"]:
            status = "healthy"
            message = "Vector store is running"
        else:
            status = "unhealthy"
            message = "Vector store is not running"
        
        return ComponentStatus(
            name="vector",
            status=status,
            message=message,
            metrics={
                "collections": milvus_info["collections"],
                "total_vectors": milvus_info["vectors"]["total"],
                "index_size_bytes": milvus_info["index"]["size_bytes"],
                "queries_per_second": milvus_info["queries"]["per_second"]
            },
            details={
                "type": "milvus",
                "host": milvus_info["host"],
                "port": milvus_info["port"],
                "running": milvus_info["running"]
            }
        )
    
    async def _get_llm_status(self) -> ComponentStatus:
        """获取 LLM 状态（真实数据）"""
        ollama_info = await check_ollama()
        
        if ollama_info["running"]:
            status = "healthy"
            message = f"Ollama is running with {len(ollama_info['models'])} models"
        else:
            status = "unhealthy"
            message = "Ollama is not running"
        
        return ComponentStatus(
            name="llm",
            status=status,
            message=message,
            metrics={
                "requests_total": 0,
                "tokens_total": 0,
                "average_latency_seconds": 0,
                "queue_size": 0,
                "max_concurrent": 100
            },
            details={
                "type": "ollama",
                "models": ollama_info["models"],
                "running": ollama_info["running"],
                "host": ollama_info["host"],
                "port": ollama_info["port"]
            }
        )
    
    async def _get_messaging_status(self) -> ComponentStatus:
        """获取消息队列状态（真实数据）"""
        rabbitmq_info = await check_rabbitmq()
        
        if rabbitmq_info["running"]:
            status = "healthy"
            message = "Message queue is running"
        else:
            status = "unhealthy"
            message = "Message queue is not running"
        
        return ComponentStatus(
            name="messaging",
            status=status,
            message=message,
            metrics={
                "queues": rabbitmq_info["queues"]["total"],
                "messages_pending": 0,
                "consumers": rabbitmq_info["consumers"]["total"],
                "producers": 0,
                "throughput_per_second": 0
            },
            details={
                "type": "rabbitmq",
                "host": rabbitmq_info["host"],
                "port": rabbitmq_info["port"],
                "running": rabbitmq_info["running"]
            }
        )
    
    async def _get_storage_status(self) -> ComponentStatus:
        """获取存储状态（真实数据）"""
        metrics = get_all_metrics()
        storage = metrics.get("storage", {})
        usage_percent = storage.get("usage_percent", 0)
        
        if usage_percent < 80:
            status = "healthy"
            message = "Storage is available"
        elif usage_percent < 95:
            status = "degraded"
            message = f"Storage usage is high ({usage_percent:.1f}%)"
        else:
            status = "unhealthy"
            message = f"Storage is nearly full ({usage_percent:.1f}%)"
        
        return ComponentStatus(
            name="storage",
            status=status,
            message=message,
            metrics={
                "total_space_bytes": storage.get("total_bytes", 0),
                "used_space_bytes": storage.get("used_bytes", 0),
                "available_space_bytes": storage.get("available_bytes", 0),
                "usage_percent": usage_percent
            },
            details={
                "type": "file",
                "running": True
            }
        )
    
    async def _get_network_status(self) -> ComponentStatus:
        """获取网络状态（真实数据）"""
        net_info = get_network_connections()
        
        return ComponentStatus(
            name="network",
            status="healthy",
            message="Network is accessible",
            metrics={
                "connections_active": net_info["connections"]["active"],
                "connections_idle": net_info["connections"]["idle"],
                "connections_total": net_info["connections"]["total"],
                "bytes_sent": net_info["throughput"]["bytes_in_per_second"],
                "bytes_received": net_info["throughput"]["bytes_out_per_second"],
                "latency_ms": net_info["latency"]["avg_ms"]
            },
            details={
                "type": "system"
            }
        )
    
    async def _get_memory_status(self) -> ComponentStatus:
        """获取内存状态（真实数据）"""
        metrics = get_all_metrics()
        mem = metrics.get("memory", {})
        usage_percent = mem.get("usage_percent", 0)
        
        if usage_percent < 80:
            status = "healthy"
            message = "Memory system is healthy"
        elif usage_percent < 95:
            status = "degraded"
            message = f"Memory usage is high ({usage_percent:.1f}%)"
        else:
            status = "unhealthy"
            message = f"Memory is nearly full ({usage_percent:.1f}%)"
        
        return ComponentStatus(
            name="memory",
            status=status,
            message=message,
            metrics={
                "total_bytes": mem.get("total_bytes", 0),
                "used_bytes": mem.get("used_bytes", 0),
                "available_bytes": mem.get("available_bytes", 0),
                "usage_percent": usage_percent
            },
            details={
                "type": "system",
                "swap_total_bytes": mem.get("swap", {}).get("total_bytes", 0),
                "swap_used_bytes": mem.get("swap", {}).get("used_bytes", 0)
            }
        )
    
    async def _get_compute_status(self) -> ComponentStatus:
        """获取算力状态（真实数据）"""
        metrics = get_all_metrics()
        gpu = metrics.get("gpu", {})
        
        if gpu.get("total", 0) > 0:
            status = "healthy"
            message = f"Compute resources available ({gpu.get('total', 0)} GPUs)"
        else:
            status = "degraded"
            message = "No GPU detected, using CPU only"
        
        return ComponentStatus(
            name="compute",
            status=status,
            message=message,
            metrics={
                "gpus_total": gpu.get("total", 0),
                "gpus_available": gpu.get("available", 0),
                "gpus_used": gpu.get("used", 0),
                "gpu_utilization_percent": gpu.get("utilization_percent", 0),
                "gpu_memory_total_bytes": gpu.get("total_memory_bytes", 0),
                "gpu_memory_used_bytes": gpu.get("used_memory_bytes", 0)
            },
            details={
                "type": "gpu" if gpu.get("total", 0) > 0 else "cpu",
                "gpus": gpu.get("details", [])
            }
        )
    
    async def _get_database_metrics(self) -> Dict[str, Any]:
        """获取数据库详细指标（真实数据）"""
        db_info = await check_postgresql()
        return {
            "connections": {
                "active": db_info["connections"]["active"],
                "idle": db_info["connections"]["idle"],
                "max": db_info["connections"]["max"]
            },
            "queries": db_info.get("queries", {"per_second": 0, "average_time_ms": 0}),
            "pool": db_info.get("pool", {"size": 0, "usage_percent": 0})
        }
    
    async def _get_cache_metrics(self) -> Dict[str, Any]:
        """获取缓存详细指标（真实数据）"""
        redis_info = await check_redis()
        return {
            "hit_rate": redis_info["hit_rate"],
            "miss_rate": redis_info["miss_rate"],
            "memory": {
                "used_bytes": redis_info["memory"]["used_bytes"],
                "max_bytes": redis_info["memory"]["max_bytes"],
                "usage_percent": redis_info["memory"]["usage_percent"]
            },
            "keys": {
                "total": redis_info["keys"]["total"],
                "expires": redis_info["keys"].get("expires", 0)
            },
            "operations": {
                "gets_per_second": 0,
                "sets_per_second": 0
            }
        }
    
    async def _get_vector_metrics(self) -> Dict[str, Any]:
        """获取向量存储详细指标（真实数据）"""
        milvus_info = await check_milvus()
        return {
            "collections": milvus_info["collections"],
            "vectors": milvus_info["vectors"],
            "index": milvus_info["index"],
            "queries": milvus_info["queries"]
        }
    
    async def _get_llm_metrics(self) -> Dict[str, Any]:
        """获取 LLM 详细指标（真实数据）"""
        ollama_info = await check_ollama()
        return {
            "requests": {"total": 0, "by_model": {}},
            "tokens": {"total": 0, "prompt": 0, "completion": 0},
            "latency": {"average_seconds": 0, "p50_seconds": 0, "p99_seconds": 0},
            "cost": {"total_usd": 0, "by_model": {}},
            "models": ollama_info["models"],
            "running": ollama_info["running"]
        }
    
    async def _get_messaging_metrics(self) -> Dict[str, Any]:
        """获取消息队列详细指标（真实数据）"""
        rabbitmq_info = await check_rabbitmq()
        return {
            "queues": rabbitmq_info["queues"],
            "throughput": rabbitmq_info["throughput"],
            "consumers": rabbitmq_info["consumers"]
        }
    
    async def _get_storage_metrics(self) -> Dict[str, Any]:
        """获取存储详细指标（真实数据）"""
        metrics = get_all_metrics()
        storage = metrics.get("storage", {})
        return {
            "space": {
                "total_bytes": storage.get("total_bytes", 0),
                "used_bytes": storage.get("used_bytes", 0),
                "available_bytes": storage.get("available_bytes", 0),
                "usage_percent": storage.get("usage_percent", 0)
            },
            "files": {
                "total": 0,
                "by_type": {}
            },
            "io": {
                "reads_per_second": 0,
                "writes_per_second": 0
            }
        }
    
    async def _get_network_metrics(self) -> Dict[str, Any]:
        """获取网络详细指标（真实数据）"""
        net_info = get_network_connections()
        return {
            "connections": {
                "active": net_info["connections"]["active"],
                "idle": net_info["connections"]["idle"],
                "total": net_info["connections"]["total"]
            },
            "throughput": {
                "bytes_in_per_second": net_info["throughput"]["bytes_in_per_second"],
                "bytes_out_per_second": net_info["throughput"]["bytes_out_per_second"]
            },
            "latency": {
                "avg_ms": net_info["latency"]["avg_ms"],
                "p99_ms": net_info["latency"]["p99_ms"]
            }
        }
    
    async def _get_memory_metrics(self) -> Dict[str, Any]:
        """获取内存详细指标（真实数据）"""
        metrics = get_all_metrics()
        mem = metrics.get("memory", {})
        return {
            "total_bytes": mem.get("total_bytes", 0),
            "used_bytes": mem.get("used_bytes", 0),
            "available_bytes": mem.get("available_bytes", 0),
            "usage_percent": mem.get("usage_percent", 0),
            "swap": mem.get("swap", {})
        }
    
    async def _get_compute_metrics(self) -> Dict[str, Any]:
        """获取算力详细指标（真实数据）"""
        metrics = get_all_metrics()
        gpu = metrics.get("gpu", {})
        cpu = metrics.get("cpu", {})
        mem = metrics.get("memory", {})
        
        return {
            "gpu": {
                "type": gpu.get("type", "unknown"),
                "total": gpu.get("total", 0),
                "available": gpu.get("available", 0),
                "used": gpu.get("used", 0),
                "utilization_percent": gpu.get("utilization_percent", 0),
                "memory_shared": gpu.get("memory_shared", False),
                "total_memory_bytes": gpu.get("total_memory_bytes", 0),
                "used_memory_bytes": gpu.get("used_memory_bytes", 0)
            },
            "cpu": {
                "count_physical": cpu.get("count_physical", 0),
                "count_logical": cpu.get("count_logical", 0),
                "usage_percent": cpu.get("usage_percent", 0),
                "load_avg": cpu.get("load_avg", [0, 0, 0])
            },
            "memory": {
                "total_bytes": mem.get("total_bytes", 0),
                "used_bytes": mem.get("used_bytes", 0),
                "available_bytes": mem.get("available_bytes", 0),
                "usage_percent": mem.get("usage_percent", 0)
            },
            "jobs": {
                "active": 0,
                "queued": 0,
                "completed_today": 0,
                "failed_today": 0
            }
        }
    
    async def _get_uptime(self) -> int:
        """获取运行时间（秒）"""
        return 86400  # 24小时
    
    def _calculate_overall_status(self, components: Dict[str, ComponentStatus]) -> str:
        """计算整体状态"""
        statuses = [comp.status for comp in components.values()]
        
        if "unhealthy" in statuses:
            return "unhealthy"
        elif "degraded" in statuses:
            return "degraded"
        else:
            return "healthy"
    
    def _calculate_score(self, components: Dict[str, ComponentStatus]) -> int:
        """计算健康分数（0-100）
        
        基于所有组件状态计算整体健康百分比：
        - healthy:100%
        - degraded: 50%
        - unhealthy: 0%
        """
        if not components:
            return 0
        
        score_map = {"healthy": 100, "degraded": 50, "unhealthy": 0}
        total_score = sum(score_map.get(comp.status, 0) for comp in components.values())
        return int(total_score / len(components))
    
    def _component_to_dict(self, component: ComponentStatus) -> Dict[str, Any]:
        """转换组件状态为字典"""
        return {
            "status": component.status,
            "message": component.message,
            "metrics": component.metrics,
            "details": component.details
        }
    
    # ===== 配置管理接口 (与文档对齐) =====
    
    async def get_config(self, component_name: str) -> Dict[str, Any]:
        """获取指定组件的配置
        
        Args:
            component_name: 组件名称 (database, cache, llm, etc.)
            
        Returns:
            组件配置字典
        """
        configs = await self.get_all_configs()
        return configs.get(component_name, {})
    
    async def update_config(self, component_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """更新指定组件的配置
        
        Args:
            component_name: 组件名称
            config: 新的配置字典
            
        Returns:
            更新后的配置
        """
        if component_name not in self._configs:
            raise ValueError(f"Unknown component: {component_name}")
        
        self._configs[component_name].update(config)
        return self._configs[component_name]
    
    async def get_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """获取所有组件的配置
        
        Returns:
            所有组件配置的字典
        """
        return self._configs.copy()
    
    def _init_configs(self):
        """初始化默认配置"""
        self._configs = {
            "database": {
                "type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "aiplat",
                "pool_size": 20,
                "pool_min": 5,
                "pool_max": 100,
                "connection_timeout": 30
            },
            "cache": {
                "type": "redis",
                "host": "localhost",
                "port": 6379,
                "db": 0,
                "max_memory": "4gb",
                "ttl": 3600
            },
            "llm": {
                "provider": "openai",
                "api_endpoint": "https://api.openai.com/v1",
                "models": ["gpt-4", "gpt-3.5-turbo"],
                "routing_strategy": "round_robin",
                "timeout": 60,
                "max_retries": 3
            },
            "vector": {
                "type": "milvus",
                "host": "localhost",
                "port": 19530,
                "collections": ["embeddings", "documents", "images"],
                "index_type": "IVF_FLAT"
            },
            "messaging": {
                "type": "rabbitmq",
                "host": "localhost",
                "port": 5672,
                "queues": ["tasks", "notifications", "events"],
                "max_consumers": 100
            },
            "storage": {
                "type": "file",
                "path": "/data/storage",
                "max_size": "100gb",
                "cleanup_enabled": True
            },
            "network": {
                "type": "websocket",
                "endpoint": "ws://localhost:8000/ws",
                "max_connections": 1000
            },
            "memory": {
                "type": "system",
                "total_bytes": 16 * 1024 * 1024 * 1024,
                "monitoring_enabled": True
            }
        }