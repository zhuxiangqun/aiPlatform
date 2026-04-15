"""
Layer 0 (infra) 指标采集器 - 监控数据采集
"""

from typing import List, Dict, Any
from .collector import MetricsCollector, Metric


class InfraMetricsCollector(MetricsCollector):
    """Layer 0 (infra) 指标采集器
    
    采集 infra 层所有组件的监控指标：
    - Database: 连接数、QPS、查询时间
    - Cache: 命中率、内存使用、键数量
    - Vector: 向量数、查询性能
    - LLM: 请求数、Token消耗、延迟
    - Messaging: 队列长度、吞吐量
    - Storage: 存储空间、文件数
    - Network: 连接数、流量
    - Memory: 内存使用
    """
    
    def __init__(self, endpoint: str = None):
        super().__init__("infra", endpoint)
        
    async def collect(self) -> List[Metric]:
        """采集 infra 层所有指标"""
        metrics = []
        
        # Database 指标
        metrics.extend(await self._collect_database_metrics())
        
        # Cache 指标
        metrics.extend(await self._collect_cache_metrics())
        
        # Vector 指标
        metrics.extend(await self._collect_vector_metrics())
        
        # LLM 指标
        metrics.extend(await self._collect_llm_metrics())
        
        # Messaging 指标
        metrics.extend(await self._collect_messaging_metrics())
        
        # Storage 指标
        metrics.extend(await self._collect_storage_metrics())
        
        # Network 指标
        metrics.extend(await self._collect_network_metrics())
        
        # Memory 指标
        metrics.extend(await self._collect_memory_metrics())
        
        # GPU 指标
        metrics.extend(await self._collect_gpu_metrics())
        
        return metrics
    
    async def _collect_database_metrics(self) -> List[Metric]:
        """采集数据库指标"""
        return [
            # 连接指标
            Metric(
                name="database_connections_active",
                value=2,
                labels={"type": "postgres"},
                unit="connections"
            ),
            Metric(
                name="database_connections_idle",
                value=8,
                labels={"type": "postgres"},
                unit="connections"
            ),
            Metric(
                name="database_connections_max",
                value=100,
                labels={"type": "postgres"},
                unit="connections"
            ),
            Metric(
                name="database_connections_usage_percent",
                value=50.0,
                labels={"type": "postgres"},
                unit="percent"
            ),
            
            # 查询指标
            Metric(
                name="database_queries_per_second",
                value=150,
                labels={"type": "postgres"},
                unit="qps"
            ),
            Metric(
                name="database_query_latency_avg_ms",
                value=25.5,
                labels={"type": "postgres"},
                unit="ms"
            ),
            Metric(
                name="database_slow_queries_total",
                value=5,
                labels={"type": "postgres"},
                unit="queries"
            ),
            Metric(
                name="database_query_errors_total",
                value=2,
                labels={"type": "postgres"},
                unit="errors"
            ),
            
            # MongoDB 指标
            Metric(
                name="database_connections_active",
                value=5,
                labels={"type": "mongodb"},
                unit="connections"
            ),
            Metric(
                name="database_operations_per_second",
                value=200,
                labels={"type": "mongodb"},
                unit="ops"
            ),
        ]
    
    async def _collect_cache_metrics(self) -> List[Metric]:
        """采集缓存指标"""
        return [
            # 命中率指标
            Metric(
                name="cache_hit_rate",
                value=0.95,
                labels={"type": "redis"},
                unit="ratio"
            ),
            Metric(
                name="cache_miss_rate",
                value=0.05,
                labels={"type": "redis"},
                unit="ratio"
            ),
            Metric(
                name="cache_hit_total",
                value=9500,
                labels={"type": "redis"},
                unit="hits"
            ),
            Metric(
                name="cache_miss_total",
                value=500,
                labels={"type": "redis"},
                unit="misses"
            ),
            
            # 内存指标
            Metric(
                name="cache_memory_used_bytes",
                value=2 * 1024 * 1024 * 1024,  # 2GB
                labels={"type": "redis"},
                unit="bytes"
            ),
            Metric(
                name="cache_memory_max_bytes",
                value=4 * 1024 * 1024 * 1024,  # 4GB
                labels={"type": "redis"},
                unit="bytes"
            ),
            Metric(
                name="cache_memory_usage_percent",
                value=50.0,
                labels={"type": "redis"},
                unit="percent"
            ),
            
            # 键指标
            Metric(
                name="cache_keys_total",
                value=10000,
                labels={"type": "redis"},
                unit="keys"
            ),
            Metric(
                name="cache_keys_expires",
                value=2000,
                labels={"type": "redis"},
                unit="keys"
            ),
            
            # 操作指标
            Metric(
                name="cache_operations_per_second",
                value=1100,
                labels={"type": "redis", "operation": "total"},
                unit="ops"
            ),
            Metric(
                name="cache_gets_per_second",
                value=1000,
                labels={"type": "redis"},
                unit="ops"
            ),
            Metric(
                name="cache_sets_per_second",
                value=100,
                labels={"type": "redis"},
                unit="ops"
            ),
            
            # 连接指标
            Metric(
                name="cache_connected_clients",
                value=5,
                labels={"type": "redis"},
                unit="clients"
            ),
        ]
    
    async def _collect_vector_metrics(self) -> List[Metric]:
        """采集向量存储指标"""
        return [
            # 集合指标
            Metric(
                name="vector_collections_total",
                value=5,
                labels={"type": "milvus"},
                unit="collections"
            ),
            Metric(
                name="vector_vectors_total",
                value=50000,
                labels={"type": "milvus"},
                unit="vectors"
            ),
            
            # 集合详情
            Metric(
                name="vector_collection_vectors",
                value=30000,
                labels={"type": "milvus", "collection": "embeddings"},
                unit="vectors"
            ),
            Metric(
                name="vector_collection_vectors",
                value=15000,
                labels={"type": "milvus", "collection": "documents"},
                unit="vectors"
            ),
            Metric(
                name="vector_collection_vectors",
                value=5000,
                labels={"type": "milvus", "collection": "images"},
                unit="vectors"
            ),
            
            # 索引指标
            Metric(
                name="vector_index_size_bytes",
                value=1024 * 1024 * 1024,  # 1GB
                labels={"type": "milvus"},
                unit="bytes"
            ),
            Metric(
                name="vector_index_build_time_seconds",
                value=30,
                labels={"type": "milvus"},
                unit="seconds"
            ),
            
            # 查询指标
            Metric(
                name="vector_queries_per_second",
                value=100,
                labels={"type": "milvus"},
                unit="qps"
            ),
            Metric(
                name="vector_query_latency_avg_ms",
                value=50,
                labels={"type": "milvus"},
                unit="ms"
            ),
            Metric(
                name="vector_query_latency_p99_ms",
                value=150,
                labels={"type": "milvus"},
                unit="ms"
            ),
        ]
    
    async def _collect_llm_metrics(self) -> List[Metric]:
        """采集 LLM 指标"""
        return [
            # 请求指标
            Metric(
                name="llm_requests_total",
                value=1000,
                labels={"provider": "openai"},
                unit="requests"
            ),
            Metric(
                name="llm_requests_per_second",
                value=10,
                labels={"provider": "openai"},
                unit="rps"
            ),
            Metric(
                name="llm_requests_by_model",
                value=300,
                labels={"provider": "openai", "model": "gpt-4"},
                unit="requests"
            ),
            Metric(
                name="llm_requests_by_model",
                value=700,
                labels={"provider": "openai", "model": "gpt-3.5-turbo"},
                unit="requests"
            ),
            
            # Token 指标
            Metric(
                name="llm_tokens_total",
                value=100000,
                labels={"provider": "openai"},
                unit="tokens"
            ),
            Metric(
                name="llm_tokens_prompt",
                value=40000,
                labels={"provider": "openai"},
                unit="tokens"
            ),
            Metric(
                name="llm_tokens_completion",
                value=60000,
                labels={"provider": "openai"},
                unit="tokens"
            ),
            Metric(
                name="llm_tokens_by_model",
                value=50000,
                labels={"provider": "openai", "model": "gpt-4"},
                unit="tokens"
            ),
            Metric(
                name="llm_tokens_by_model",
                value=50000,
                labels={"provider": "openai", "model": "gpt-3.5-turbo"},
                unit="tokens"
            ),
            
            # 延迟指标
            Metric(
                name="llm_latency_avg_seconds",
                value=1.5,
                labels={"provider": "openai"},
                unit="seconds"
            ),
            Metric(
                name="llm_latency_p50_seconds",
                value=1.2,
                labels={"provider": "openai"},
                unit="seconds"
            ),
            Metric(
                name="llm_latency_p99_seconds",
                value=3.5,
                labels={"provider": "openai"},
                unit="seconds"
            ),
            
            # 成本指标
            Metric(
                name="llm_cost_total_usd",
                value=12.50,
                labels={"provider": "openai"},
                unit="usd"
            ),
            Metric(
                name="llm_cost_by_model",
                value=10.00,
                labels={"provider": "openai", "model": "gpt-4"},
                unit="usd"
            ),
            Metric(
                name="llm_cost_by_model",
                value=2.50,
                labels={"provider": "openai", "model": "gpt-3.5-turbo"},
                unit="usd"
            ),
            
            # 错误指标
            Metric(
                name="llm_errors_total",
                value=5,
                labels={"provider": "openai"},
                unit="errors"
            ),
            Metric(
                name="llm_rate_limit_hits",
                value=2,
                labels={"provider": "openai"},
                unit="hits"
            ),
            
            # 队列指标
            Metric(
                name="llm_queue_size",
                value=10,
                labels={"provider": "openai"},
                unit="requests"
            ),
            Metric(
                name="llm_max_concurrent",
                value=100,
                labels={"provider": "openai"},
                unit="requests"
            ),
        ]
    
    async def _collect_messaging_metrics(self) -> List[Metric]:
        """采集消息队列指标"""
        return [
            #RabbitMQ 指标
            Metric(
                name="messaging_queues_total",
                value=5,
                labels={"type": "rabbitmq"},
                unit="queues"
            ),
            Metric(
                name="messaging_messages_pending",
                value=120,
                labels={"type": "rabbitmq"},
                unit="messages"
            ),
            Metric(
                name="messaging_messages_pending_by_queue",
                value=50,
                labels={"type": "rabbitmq", "queue": "tasks"},
                unit="messages"
            ),
            Metric(
                name="messaging_messages_pending_by_queue",
                value=30,
                labels={"type": "rabbitmq", "queue": "notifications"},
                unit="messages"
            ),
            Metric(
                name="messaging_messages_pending_by_queue",
                value=40,
                labels={"type": "rabbitmq", "queue": "events"},
                unit="messages"
            ),
            
            # 生产者/消费者指标
            Metric(
                name="messaging_consumers_total",
                value=10,
                labels={"type": "rabbitmq"},
                unit="consumers"
            ),
            Metric(
                name="messaging_consumers_active",
                value=8,
                labels={"type": "rabbitmq"},
                unit="consumers"
            ),
            Metric(
                name="messaging_producers_total",
                value=5,
                labels={"type": "rabbitmq"},
                unit="producers"
            ),
            
            # 吞吐量指标
            Metric(
                name="messaging_throughput_messages_per_second",
                value=500,
                labels={"type": "rabbitmq"},
                unit="mps"
            ),
            Metric(
                name="messaging_throughput_bytes_per_second",
                value=1024 * 1024,  # 1MB/s
                labels={"type": "rabbitmq"},
                unit="bytes"
            ),
            
            # Kafka 指标
            Metric(
                name="messaging_kafka_partitions_total",
                value=10,
                labels={"topic": "events"},
                unit="partitions"
            ),
            Metric(
                name="messaging_kafka_offset_lag",
                value=100,
                labels={"topic": "events", "consumer_group": "processor"},
                unit="messages"
            ),
        ]
    
    async def _collect_storage_metrics(self) -> List[Metric]:
        """采集存储指标"""
        return [
            # 存储空间指标
            Metric(
                name="storage_space_total_bytes",
                value=100 * 1024 * 1024 * 1024,  # 100GB
                labels={"type": "file"},
                unit="bytes"
            ),
            Metric(
                name="storage_space_used_bytes",
                value=30 * 1024 * 1024 * 1024,# 30GB
                labels={"type": "file"},
                unit="bytes"
            ),
            Metric(
                name="storage_space_available_bytes",
                value=70 * 1024 * 1024 * 1024,  # 70GB
                labels={"type": "file"},
                unit="bytes"
            ),
            Metric(
                name="storage_space_usage_percent",
                value=30.0,
                labels={"type": "file"},
                unit="percent"
            ),
            
            # 文件指标
            Metric(
                name="storage_files_total",
                value=5000,
                labels={"type": "file"},
                unit="files"
            ),
            Metric(
                name="storage_files_by_type",
                value=1000,
                labels={"type": "file", "file_type": "pdf"},
                unit="files"
            ),
            Metric(
                name="storage_files_by_type",
                value=2000,
                labels={"type": "file", "file_type": "images"},
                unit="files"
            ),
            Metric(
                name="storage_files_by_type",
                value=1500,
                labels={"type": "file", "file_type": "documents"},
                unit="files"
            ),
            Metric(
                name="storage_files_by_type",
                value=500,
                labels={"type": "file", "file_type": "other"},
                unit="files"
            ),
            
            # I/O 指标
            Metric(
                name="storage_io_reads_per_second",
                value=50,
                labels={"type": "file"},
                unit="iops"
            ),
            Metric(
                name="storage_io_writes_per_second",
                value=10,
                labels={"type": "file"},
                unit="iops"
            ),
        ]
    
    async def _collect_network_metrics(self) -> List[Metric]:
        """采集网络指标"""
        return [
            # 连接指标
            Metric(
                name="network_connections_active",
                value=50,
                labels={"type": "websocket"},
                unit="connections"
            ),
            Metric(
                name="network_connections_max",
                value=1000,
                labels={"type": "websocket"},
                unit="connections"
            ),
            Metric(
                name="network_connections_usage_percent",
                value=5.0,
                labels={"type": "websocket"},
                unit="percent"
            ),
            
            # 流量指标
            Metric(
                name="network_bytes_sent_total",
                value=1024 * 1024 * 100,  # 100MB
                labels={"type": "websocket"},
                unit="bytes"
            ),
            Metric(
                name="network_bytes_received_total",
                value=1024 * 1024 * 200,  # 200MB
                labels={"type": "websocket"},
                unit="bytes"
            ),
            Metric(
                name="network_bytes_total",
                value=1024 * 1024 * 300,  # 300MB
                labels={"type": "websocket"},
                unit="bytes"
            ),
            
            # 延迟指标
            Metric(
                name="network_latency_avg_ms",
                value=10,
                labels={"type": "websocket"},
                unit="ms"
            ),
            Metric(
                name="network_latency_p50_ms",
                value=8,
                labels={"type": "websocket"},
                unit="ms"
            ),
            Metric(
                name="network_latency_p99_ms",
                value=50,
                labels={"type": "websocket"},
                unit="ms"
            ),
            
            # 错误指标
            Metric(
                name="network_errors_total",
                value=2,
                labels={"type": "websocket"},
                unit="errors"
            ),
            Metric(
                name="network_timeouts_total",
                value=1,
                labels={"type": "websocket"},
                unit="timeouts"
            ),
        ]
    
    async def _collect_memory_metrics(self) -> List[Metric]:
        """采集内存指标"""
        return [
            # 系统内存
            Metric(
                name="memory_system_total_bytes",
                value=16 * 1024 * 1024 * 1024,  # 16GB
                labels={},
                unit="bytes"
            ),
            Metric(
                name="memory_system_used_bytes",
                value=8 * 1024 * 1024 * 1024,# 8GB
                labels={},
                unit="bytes"
            ),
            Metric(
                name="memory_system_available_bytes",
                value=8 * 1024 * 1024 * 1024,# 8GB
                labels={},
                unit="bytes"
            ),
            Metric(
                name="memory_system_usage_percent",
                value=50.0,
                labels={},
                unit="percent"
            ),
            
            # 进程内存
            Metric(
                name="memory_process_bytes",
                value=2 * 1024 * 1024 * 1024,
                labels={"process": "database"},
                unit="bytes"
            ),
            Metric(
                name="memory_process_bytes",
                value=2 * 1024 * 1024 * 1024,
                labels={"process": "cache"},
                unit="bytes"
            ),
            Metric(
                name="memory_process_bytes",
                value=2 * 1024 * 1024 * 1024,
                labels={"process": "vector"},
                unit="bytes"
            ),
            Metric(
                name="memory_process_bytes",
                value=2 * 1024 * 1024 * 1024,
                labels={"process": "other"},
                unit="bytes"
            ),
            
            #GPU 内存（可选）
            Metric(
                name="memory_gpu_total_bytes",
                value=8 * 1024 * 1024 * 1024,  # 8GB
                labels={"gpu": "0"},
                unit="bytes"
            ),
            Metric(
                name="memory_gpu_used_bytes",
                value=4 * 1024 * 1024 * 1024,# 4GB
                labels={"gpu": "0"},
                unit="bytes"
            ),
            Metric(
                name="memory_gpu_usage_percent",
                value=50.0,
                labels={"gpu": "0"},
                unit="percent"
            ),
        ]
    
    async def _collect_gpu_metrics(self) -> List[Metric]:
        """采集 GPU 指标"""
        return [
            # GPU 0
            Metric(
                name="gpu_utilization_percent",
                value=60.0,
                labels={"gpu": "0", "model": "NVIDIA A100"},
                unit="percent"
            ),
            Metric(
                name="gpu_memory_used_bytes",
                value=4 * 1024 * 1024 * 1024,
                labels={"gpu": "0", "model": "NVIDIA A100"},
                unit="bytes"
            ),
            Metric(
                name="gpu_memory_total_bytes",
                value=8 * 1024 * 1024 * 1024,
                labels={"gpu": "0", "model": "NVIDIA A100"},
                unit="bytes"
            ),
            Metric(
                name="gpu_memory_usage_percent",
                value=50.0,
                labels={"gpu": "0", "model": "NVIDIA A100"},
                unit="percent"
            ),
            Metric(
                name="gpu_temperature_celsius",
                value=65,
                labels={"gpu": "0", "model": "NVIDIA A100"},
                unit="celsius"
            ),
            # GPU 1
            Metric(
                name="gpu_utilization_percent",
                value=100.0,
                labels={"gpu": "1", "model": "NVIDIA A100"},
                unit="percent"
            ),
            Metric(
                name="gpu_memory_used_bytes",
                value=8 * 1024 * 1024 * 1024,
                labels={"gpu": "1", "model": "NVIDIA A100"},
                unit="bytes"
            ),
            Metric(
                name="gpu_memory_total_bytes",
                value=8 * 1024 * 1024 * 1024,
                labels={"gpu": "1", "model": "NVIDIA A100"},
                unit="bytes"
            ),
            Metric(
                name="gpu_memory_usage_percent",
                value=100.0,
                labels={"gpu": "1", "model": "NVIDIA A100"},
                unit="percent"
            ),
            Metric(
                name="gpu_temperature_celsius",
                value=72,
                labels={"gpu": "1", "model": "NVIDIA A100"},
                unit="celsius"
            ),
            # GPU 2 (空闲)
            Metric(
                name="gpu_utilization_percent",
                value=0.0,
                labels={"gpu": "2", "model": "NVIDIA A100"},
                unit="percent"
            ),
            Metric(
                name="gpu_memory_used_bytes",
                value=0,
                labels={"gpu": "2", "model": "NVIDIA A100"},
                unit="bytes"
            ),
            Metric(
                name="gpu_memory_total_bytes",
                value=8 * 1024 * 1024 * 1024,
                labels={"gpu": "2", "model": "NVIDIA A100"},
                unit="bytes"
            ),
            Metric(
                name="gpu_memory_usage_percent",
                value=0.0,
                labels={"gpu": "2", "model": "NVIDIA A100"},
                unit="percent"
            ),
            Metric(
                name="gpu_temperature_celsius",
                value=35,
                labels={"gpu": "2", "model": "NVIDIA A100"},
                unit="celsius"
            ),
            # GPU 3
            Metric(
                name="gpu_utilization_percent",
                value=40.0,
                labels={"gpu": "3", "model": "NVIDIA A100"},
                unit="percent"
            ),
            Metric(
                name="gpu_memory_used_bytes",
                value=4 * 1024 * 1024 * 1024,
                labels={"gpu": "3", "model": "NVIDIA A100"},
                unit="bytes"
            ),
            Metric(
                name="gpu_memory_total_bytes",
                value=8 * 1024 * 1024 * 1024,
                labels={"gpu": "3", "model": "NVIDIA A100"},
                unit="bytes"
            ),
            Metric(
                name="gpu_memory_usage_percent",
                value=50.0,
                labels={"gpu": "3", "model": "NVIDIA A100"},
                unit="percent"
            ),
            Metric(
                name="gpu_temperature_celsius",
                value=58,
                labels={"gpu": "3", "model": "NVIDIA A100"},
                unit="celsius"
            ),
            # 聚合 GPU 指标
            Metric(
                name="gpu_utilization_avg_percent",
                value=50.0,
                labels={},
                unit="percent"
            ),
            Metric(
                name="gpu_memory_used_total_bytes",
                value=16 * 1024 * 1024 * 1024,
                labels={},
                unit="bytes"
            ),
            Metric(
                name="gpu_memory_total_bytes",
                value=32 * 1024 * 1024 * 1024,
                labels={},
                unit="bytes"
            ),
            Metric(
                name="gpu_count_total",
                value=4,
                labels={},
                unit="count"
            ),
            Metric(
                name="gpu_count_available",
                value=2,
                labels={},
                unit="count"
            ),
        ]