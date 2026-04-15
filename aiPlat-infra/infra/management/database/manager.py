"""
Database Manager

Manages database connections and operations with connection pooling.
"""

from typing import Dict, Any, List, Optional
from ..base import ManagementBase, Status, HealthStatus, Metrics
from ..schemas import SlowQuery, DBPoolStats
from datetime import datetime
import time


class DatabaseManager(ManagementBase):
    """
    Manager for database connections and operations.
    
    Provides connection pooling, query monitoring, and performance tracking.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._pools: Dict[str, DBPoolStats] = {}
        self._slow_queries: List[SlowQuery] = []
        self._query_count = 0
        self._error_count = 0
        self._connection_errors = []
    
    async def get_status(self) -> Status:
        """Get database module status."""
        try:
            if not self._pools:
                return Status.UNKNOWN
            
            healthy_pools = sum(
                1 for pool in self._pools.values()
                if pool.pool_available > 0
            )
            
            total_pools = len(self._pools)
            
            if healthy_pools == total_pools:
                return Status.HEALTHY
            elif healthy_pools > 0:
                return Status.DEGRADED
            else:
                return Status.UNHEALTHY
        
        except Exception:
            return Status.UNKNOWN
    
    async def get_metrics(self) -> List[Metrics]:
        """Get database metrics."""
        metrics = []
        timestamp = time.time()
        
        if self._pools:
            for pool_name, pool_stats in self._pools.items():
                metrics.append(Metrics(
                    name="db.pool_size",
                    value=pool_stats.pool_size,
                    unit="count",
                    timestamp=timestamp,
                    labels={"pool": pool_name, "module": "database"}
                ))
                
                metrics.append(Metrics(
                    name="db.pool_available",
                    value=pool_stats.pool_available,
                    unit="count",
                    timestamp=timestamp,
                    labels={"pool": pool_name, "module": "database"}
                ))
                
                metrics.append(Metrics(
                    name="db.pool_in_use",
                    value=pool_stats.pool_in_use,
                    unit="count",
                    timestamp=timestamp,
                    labels={"pool": pool_name, "module": "database"}
                ))
                
                utilization = pool_stats.pool_in_use / pool_stats.pool_size if pool_stats.pool_size > 0 else 0
                metrics.append(Metrics(
                    name="db.pool_utilization",
                    value=utilization,
                    unit="ratio",
                    timestamp=timestamp,
                    labels={"pool": pool_name, "module": "database"}
                ))
        
        metrics.append(Metrics(
            name="db.queries_total",
            value=self._query_count,
            unit="count",
            timestamp=timestamp,
            labels={"module": "database"}
        ))
        
        metrics.append(Metrics(
            name="db.errors_total",
            value=self._error_count,
            unit="count",
            timestamp=timestamp,
            labels={"module": "database"}
        ))
        
        metrics.append(Metrics(
            name="db.slow_queries_count",
            value=len(self._slow_queries),
            unit="count",
            timestamp=timestamp,
            labels={"module": "database"}
        ))
        
        return metrics
    
    async def health_check(self) -> HealthStatus:
        """Perform database health check."""
        try:
            status = await self.get_status()
            
            pool_details = {}
            for pool_name, pool_stats in self._pools.items():
                pool_details[pool_name] = {
                    "size": pool_stats.pool_size,
                    "available": pool_stats.pool_available,
                    "in_use": pool_stats.pool_in_use,
                    "healthy": pool_stats.pool_available > 0
                }
            
            if status == Status.HEALTHY:
                return HealthStatus(
                    status=status,
                    message="All database pools are healthy",
                    details={"pools": pool_details}
                )
            elif status == Status.DEGRADED:
                degraded_pools = [
                    name for name, stats in self._pools.items()
                    if stats.pool_available == 0
                ]
                return HealthStatus(
                    status=status,
                    message=f"Some database pools are degraded: {degraded_pools}",
                    details={"pools": pool_details, "degraded": degraded_pools}
                )
            else:
                return HealthStatus(
                    status=status,
                    message="All database pools are unhealthy",
                    details={"pools": pool_details}
                )
        
        except Exception as e:
            return HealthStatus(
                status=Status.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                details={"error": str(e)}
            )
    
    async def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self.config
    
    async def update_config(self, config: Dict[str, Any]) -> None:
        """Update configuration."""
        self.config.update(config)
    
    # Database-specific methods
    
    async def create_pool(self, pool_name: str, config: Dict[str, Any]) -> DBPoolStats:
        """
        Create a database connection pool.
        
        Args:
            pool_name: Pool identifier
            config: Pool configuration (size, min, max, etc.)
        
        Returns:
            Pool statistics
        """
        pool_min = config.get("pool_min", 5)
        pool_max = config.get("pool_max", 20)
        pool_size = config.get("pool_size", 10)
        
        pool_stats = DBPoolStats(
            pool_size=pool_size,
            pool_min=pool_min,
            pool_max=pool_max,
            pool_available=pool_size,
            pool_in_use=0
        )
        
        self._pools[pool_name] = pool_stats
        return pool_stats
    
    async def get_pool(self, pool_name: str) -> Optional[DBPoolStats]:
        """
        Get pool statistics.
        
        Args:
            pool_name: Pool identifier
        
        Returns:
            Pool statistics or None
        """
        return self._pools.get(pool_name)
    
    async def get_connection(self, pool_name: str) -> bool:
        """
        Get a connection from the pool.
        
        Args:
            pool_name: Pool identifier
        
        Returns:
            True if connection acquired
        """
        if pool_name not in self._pools:
            return False
        
        pool = self._pools[pool_name]
        
        if pool.pool_available > 0:
            pool.pool_available -= 1
            pool.pool_in_use += 1
            return True
        
        return False
    
    async def release_connection(self, pool_name: str) -> bool:
        """
        Release a connection back to the pool.
        
        Args:
            pool_name: Pool identifier
        
        Returns:
            True if connection released
        """
        if pool_name not in self._pools:
            return False
        
        pool = self._pools[pool_name]
        
        if pool.pool_in_use > 0:
            pool.pool_in_use -= 1
            pool.pool_available += 1
            return True
        
        return False
    
    async def record_query(self, query: str, duration_ms: int, slow_threshold: int = 1000) -> None:
        """
        Record a query execution.
        
        Args:
            query: SQL query
            duration_ms: Query duration in milliseconds
            slow_threshold: Slow query threshold in milliseconds
        """
        self._query_count += 1
        
        if duration_ms > slow_threshold:
            slow_query = SlowQuery(
                query_id=f"q-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self._query_count}",
                sql=query,
                duration_ms=duration_ms,
                executed_at=datetime.now()
            )
            self._slow_queries.append(slow_query)
            
            if len(self._slow_queries) > 100:
                self._slow_queries = self._slow_queries[-100:]
    
    async def record_error(self, error: str) -> None:
        """
        Record a database error.
        
        Args:
            error: Error message
        """
        self._error_count += 1
        self._connection_errors.append({
            "error": error,
            "timestamp": datetime.now().isoformat()
        })
        
        if len(self._connection_errors) > 100:
            self._connection_errors = self._connection_errors[-100:]
    
    async def get_slow_queries(self, limit: int = 10) -> List[SlowQuery]:
        """
        Get slow queries.
        
        Args:
            limit: Maximum number of queries to return
        
        Returns:
            List of slow queries
        """
        return sorted(self._slow_queries, key=lambda q: q.duration_ms, reverse=True)[:limit]
    
    async def get_pool_stats(self) -> Dict[str, DBPoolStats]:
        """
        Get all pool statistics.
        
        Returns:
            Dict of pool name to statistics
        """
        return self._pools
    
    async def reset_stats(self) -> None:
        """Reset statistics."""
        self._query_count = 0
        self._error_count = 0
        self._slow_queries = []
        self._connection_errors = []
    
    async def execute_query(self, pool_name: str, query: str) -> Dict[str, Any]:
        """
        Execute a query (placeholder).
        
        Args:
            pool_name: Pool identifier
            query: SQL query
        
        Returns:
            Query result
        """
        start_time = time.time()
        
        acquired = await self.get_connection(pool_name)
        if not acquired:
            await self.record_error(f"Failed to get connection from pool {pool_name}")
            return {"error": "No available connections"}
        
        try:
            await asyncio.sleep(0.01)
            
            result = {
                "success": True,
                "rows": [],
                "rowCount": 0
            }
            
            duration_ms = int((time.time() - start_time) * 1000)
            await self.record_query(query, duration_ms)
            
            return result
        
        except Exception as e:
            await self.record_error(str(e))
            return {"error": str(e)}
        
        finally:
            await self.release_connection(pool_name)


import asyncio