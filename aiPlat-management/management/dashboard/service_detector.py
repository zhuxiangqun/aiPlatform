"""
Service Detector - 检测本地服务状态

检测 PostgreSQL、Redis、Milvus、RabbitMQ、Ollama 等服务的运行状态。
"""

import socket
import asyncio
from typing import Dict, Any, List, Optional
import subprocess


async def check_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """检查端口是否可连接"""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def check_postgresql(host: str = "localhost", port: int = 5432) -> Dict[str, Any]:
    """检查 PostgreSQL 状态"""
    result = {
        "running": False,
        "host": host,
        "port": port,
        "connections": {"active": 0,"idle": 0, "max": 100},
        "queries": {"per_second": 0, "average_time_ms": 0},
        "pool": {"size": 0, "usage_percent": 0}
    }
    
    if await check_port(host, port):
        result["running"] = True
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=host,
                port=port,
                database="postgres",
                user="postgres",
                connect_timeout=2
            )
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM pg_stat_activity")
            connections = cursor.fetchone()[0]
            result["connections"]["active"] = connections
            result["pool"]["size"] = connections
            result["pool"]["usage_percent"] = min(100, (connections / 100) * 100)
            cursor.close()
            conn.close()
        except Exception:
            pass
    
    return result


async def check_redis(host: str = "localhost", port: int = 6379) -> Dict[str, Any]:
    """检查 Redis 状态"""
    result = {
        "running": False,
        "host": host,
        "port": port,
        "hit_rate": 0,
        "miss_rate": 0,
        "memory": {"used_bytes": 0, "max_bytes": 0, "usage_percent": 0},
        "keys": {"total": 0, "expires": 0}
    }
    
    if await check_port(host, port):
        result["running"] = True
        try:
            import redis
            client = redis.Redis(host=host, port=port, decode_responses=True)
            info = client.info()
            result["memory"]["used_bytes"] = info.get("used_memory", 0)
            result["memory"]["max_bytes"] = info.get("maxmemory", 0)or info.get("used_memory", 0) * 10
            result["memory"]["usage_percent"] = (
                (info.get("used_memory", 0) / result["memory"]["max_bytes"] * 100)
                if result["memory"]["max_bytes"] > 0 else 0
            )
            result["keys"]["total"] = info.get("db0", {}).get("keys", 0) if info.get("db0") else 0
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total = hits + misses
            if total > 0:
                result["hit_rate"] = hits / total
                result["miss_rate"] = misses / total
            client.close()
        except Exception:
            pass
    
    return result


async def check_milvus(host: str = "localhost", port: int = 19530) -> Dict[str, Any]:
    """检查 Milvus 状态"""
    result = {
        "running": False,
        "host": host,
        "port": port,
        "collections": 0,
        "vectors": {"total": 0, "by_collection": {}},
        "index": {"size_bytes": 0, "build_time_seconds": 0},
        "queries": {"per_second": 0, "average_latency_ms": 0}
    }
    
    if await check_port(host, port):
        result["running"] = True
        # Milvus SDK might not be installed, return basic info
        result["collections"] = 0
    
    return result


async def check_rabbitmq(host: str = "localhost", port: int = 5672) -> Dict[str, Any]:
    """检查 RabbitMQ 状态"""
    result = {
        "running": False,
        "host": host,
        "port": port,
        "queues": {"total": 0, "by_name": {}},
        "throughput": {"messages_per_second": 0, "bytes_per_second": 0},
        "consumers": {"total": 0, "active": 0}
    }
    
    if await check_port(host, port):
        result["running"] = True
        # Basic info without management plugin
        result["queues"]["total"] = 0
    
    return result


async def check_ollama(host: str = "localhost", port: int = 11434) -> Dict[str, Any]:
    """检查 Ollama 状态"""
    result = {
        "running": False,
        "host": host,
        "port": port,
        "models": [],
        "gpu_in_use": False
    }
    
    if await check_port(host, port):
        result["running"] = True
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://{host}:{port}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result["models"] = [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            pass
    
    return result


def get_network_connections() -> Dict[str, Any]:
    """获取网络连接信息"""
    result = {
        "connections": {"active": 0, "idle": 0, "total": 0},
        "throughput": {"bytes_in_per_second": 0, "bytes_out_per_second": 0},
        "latency": {"avg_ms": 0, "p99_ms": 0}
    }
    
    try:
        import psutil
        connections = psutil.net_connections(kind='inet')
        result["connections"]["total"] = len(connections)
        result["connections"]["active"] = sum(1 for c in connections if c.status == 'ESTABLISHED')
        result["connections"]["idle"] = result["connections"]["total"] - result["connections"]["active"]
    except Exception:
        pass
    
    return result


def get_process_info() -> Dict[str, Any]:
    """获取关键进程信息"""
    result = {
        "aiplat_infra": {"running": False, "pid": None, "memory_mb": 0},
        "aiplat_management": {"running": False, "pid": None, "memory_mb": 0},
        "ollama": {"running": False, "pid": None, "memory_mb": 0}
    }
    
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info']):
            try:
                cmdline = ' '.join(proc.info.get('cmdline', []) or []).lower()
                memory_mb = proc.info.get('memory_info').rss / 1024 / 1024 if proc.info.get('memory_info') else 0
                
                if 'infra.management.api' in cmdline or 'aiplat-infra' in cmdline:
                    result["aiplat_infra"] = {"running": True, "pid": proc.info['pid'], "memory_mb": memory_mb}
                elif 'uvicorn management.server' in cmdline or 'aiplat-management' in cmdline:
                    result["aiplat_management"] = {"running": True, "pid": proc.info['pid'], "memory_mb": memory_mb}
                elif 'ollama' in proc.info.get('name', '').lower():
                    result["ollama"] = {"running": True, "pid": proc.info['pid'], "memory_mb": memory_mb}
            except Exception:
                continue
    except Exception:
        pass
    
    return result