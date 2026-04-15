"""
Messaging Manager

Manages message queue operations.
"""

from typing import Dict, Any, List, Optional
from ..base import ManagementBase, Status, HealthStatus, Metrics
from datetime import datetime
import time
import asyncio


class MessagingManager(ManagementBase):
    """
    Manager for message queue.
    
    Provides queue management, message publishing, and consumer coordination.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._queues: Dict[str, Dict] = {}
        self._messages: Dict[str, List[Dict]] = {}
        self._consumers: Dict[str, List[str]] = {}
        self._message_count = 0
        self._error_count = 0
    
    async def get_status(self) -> Status:
        """Get messaging module status."""
        try:
            if not self._queues:
                return Status.UNKNOWN
            
            healthy_queues = sum(
                1 for q in self._queues.values()
                if q.get("status") == "healthy"
            )
            
            total = len(self._queues)
            
            if healthy_queues == total:
                return Status.HEALTHY
            elif healthy_queues > 0:
                return Status.DEGRADED
            else:
                return Status.UNHEALTHY
        
        except Exception:
            return Status.UNKNOWN
    
    async def get_metrics(self) -> List[Metrics]:
        """Get messaging metrics."""
        metrics = []
        timestamp = time.time()
        
        # Queue metrics
        metrics.append(Metrics(
            name="messaging.queues_total",
            value=len(self._queues),
            unit="count",
            timestamp=timestamp,
            labels={"module": "messaging"}
        ))
        
        # Message count
        total_messages = sum(len(msgs) for msgs in self._messages.values())
        metrics.append(Metrics(
            name="messaging.messages_total",
            value=total_messages,
            unit="count",
            timestamp=timestamp,
            labels={"module": "messaging"}
        ))
        
        metrics.append(Metrics(
            name="messaging.messages_processed",
            value=self._message_count,
            unit="count",
            timestamp=timestamp,
            labels={"module": "messaging"}
        ))
        
        metrics.append(Metrics(
            name="messaging.errors_total",
            value=self._error_count,
            unit="count",
            timestamp=timestamp,
            labels={"module": "messaging"}
        ))
        
        # Consumer metrics
        total_consumers = sum(len(consumers) for consumers in self._consumers.values())
        metrics.append(Metrics(
            name="messaging.consumers_total",
            value=total_consumers,
            unit="count",
            timestamp=timestamp,
            labels={"module": "messaging"}
        ))
        
        # Queue-specific metrics
        for queue_name, queue_info in self._queues.items():
            queue_messages = len(self._messages.get(queue_name, []))
            metrics.append(Metrics(
                name="messaging.queue_depth",
                value=queue_messages,
                unit="count",
                timestamp=timestamp,
                labels={"module": "messaging", "queue": queue_name}
            ))
            
            queue_consumers = len(self._consumers.get(queue_name, []))
            metrics.append(Metrics(
                name="messaging.queue_consumers",
                value=queue_consumers,
                unit="count",
                timestamp=timestamp,
                labels={"module": "messaging", "queue": queue_name}
            ))
        
        return metrics
    
    async def health_check(self) -> HealthStatus:
        """Perform messaging health check."""
        try:
            status = await self.get_status()
            
            queue_details = {}
            for name, queue in self._queues.items():
                queue_details[name] = {
                    "status": queue.get("status", "unknown"),
                    "messages": len(self._messages.get(name, [])),
                    "consumers": len(self._consumers.get(name, []))
                }
            
            if status == Status.HEALTHY:
                return HealthStatus(
                    status=status,
                    message="All queues are healthy",
                    details={"queues": queue_details}
                )
            elif status == Status.DEGRADED:
                degraded = [
                    name for name, queue in self._queues.items()
                    if queue.get("status") != "healthy"
                ]
                return HealthStatus(
                    status=status,
                    message=f"Some queues degraded: {degraded}",
                    details={"queues": queue_details, "degraded": degraded}
                )
            else:
                return HealthStatus(
                    status=status,
                    message="Message queue system is unhealthy",
                    details={"queues": queue_details}
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
    
    # Messaging-specific methods
    
    async def create_queue(self, name: str, config: Dict[str, Any] = None) -> bool:
        """
        Create a message queue.
        
        Args:
            name: Queue name
            config: Queue configuration
        
        Returns:
            True if created
        """
        if name in self._queues:
            return False
        
        self._queues[name] = {
            "name": name,
            "status": "healthy",
            "config": config or {},
            "created_at": datetime.now().isoformat()
        }
        
        self._messages[name] = []
        self._consumers[name] = []
        
        return True
    
    async def delete_queue(self, name: str) -> bool:
        """
        Delete a queue.
        
        Args:
            name: Queue name
        
        Returns:
            True if deleted
        """
        if name not in self._queues:
            return False
        
        del self._queues[name]
        del self._messages[name]
        del self._consumers[name]
        
        return True
    
    async def list_queues(self) -> List[str]:
        """
        List all queues.
        
        Returns:
            List of queue names
        """
        return list(self._queues.keys())
    
    async def publish(self, queue: str, message: Dict[str, Any]) -> bool:
        """
        Publish a message to queue.
        
        Args:
            queue: Queue name
            message: Message data
        
        Returns:
            True if published
        """
        if queue not in self._queues:
            return False
        
        msg_entry = {
            "id": f"msg-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(self._messages[queue])}",
            "data": message,
            "published_at": datetime.now().isoformat(),
            "status": "pending"
        }
        
        self._messages[queue].append(msg_entry)
        
        return True
    
    async def consume(self, queue: str, consumer_id: str) -> Optional[Dict]:
        """
        Consume a message from queue.
        
        Args:
            queue: Queue name
            consumer_id: Consumer ID
        
        Returns:
            Message or None
        """
        if queue not in self._queues:
            return None
        
        if consumer_id not in self._consumers.get(queue, []):
            return None
        
        # Find pending message
        for msg in self._messages[queue]:
            if msg["status"] == "pending":
                msg["status"] = "processing"
                msg["consumer_id"] = consumer_id
                msg["consumed_at"] = datetime.now().isoformat()
                self._message_count += 1
                return msg
        
        return None
    
    async def ack(self, queue: str, message_id: str) -> bool:
        """
        Acknowledge message processing.
        
        Args:
            queue: Queue name
            message_id: Message ID
        
        Returns:
            True if acknowledged
        """
        if queue not in self._queues:
            return False
        
        for msg in self._messages[queue]:
            if msg["id"] == message_id:
                msg["status"] = "completed"
                msg["acked_at"] = datetime.now().isoformat()
                return True
        
        return False
    
    async def nack(self, queue: str, message_id: str) -> bool:
        """
        Negative acknowledge - requeue message.
        
        Args:
            queue: Queue name
            message_id: Message ID
        
        Returns:
            True if requeued
        """
        if queue not in self._queues:
            return False
        
        for msg in self._messages[queue]:
            if msg["id"] == message_id:
                msg["status"] = "pending"
                msg["requeued_at"] = datetime.now().isoformat()
                del msg["consumer_id"]
                del msg["consumed_at"]
                self._error_count += 1
                return True
        
        return False
    
    async def register_consumer(self, queue: str, consumer_id: str) -> bool:
        """
        Register a consumer for queue.
        
        Args:
            queue: Queue name
            consumer_id: Consumer ID
        
        Returns:
            True if registered
        """
        if queue not in self._queues:
            return False
        
        if consumer_id not in self._consumers[queue]:
            self._consumers[queue].append(consumer_id)
        
        return True
    
    async def unregister_consumer(self, queue: str, consumer_id: str) -> bool:
        """
        Unregister a consumer from queue.
        
        Args:
            queue: Queue name
            consumer_id: Consumer ID
        
        Returns:
            True if unregistered
        """
        if queue not in self._queues:
            return False
        
        if consumer_id in self._consumers[queue]:
            self._consumers[queue].remove(consumer_id)
            return True
        
        return False
    
    async def get_queue_depth(self, queue: str) -> int:
        """
        Get number of pending messages.
        
        Args:
            queue: Queue name
        
        Returns:
            Queue depth
        """
        if queue not in self._messages:
            return 0
        
        return sum(1 for msg in self._messages[queue] if msg["status"] == "pending")
    
    async def get_queue_stats(self, queue: str) -> Dict[str, Any]:
        """
        Get queue statistics.
        
        Args:
            queue: Queue name
        
        Returns:
            Queue statistics
        """
        if queue not in self._queues:
            return {}
        
        messages = self._messages.get(queue, [])
        
        return {
            "name": queue,
            "status": self._queues[queue].get("status"),
            "total_messages": len(messages),
            "pending": sum(1 for m in messages if m["status"] == "pending"),
            "processing": sum(1 for m in messages if m["status"] == "processing"),
            "completed": sum(1 for m in messages if m["status"] == "completed"),
            "consumers": len(self._consumers.get(queue, [])),
            "created_at": self._queues[queue].get("created_at")
        }
    
    async def purge_queue(self, queue: str) -> int:
        """
        Purge all messages from queue.
        
        Args:
            queue: Queue name
        
        Returns:
            Number of messages purged
        """
        if queue not in self._queues:
            return 0
        
        count = len(self._messages[queue])
        self._messages[queue] = []
        
        return count
    
    async def get_dead_letter_queue(self, queue: str) -> List[Dict]:
        """
        Get dead letter queue messages.
        
        Args:
            queue: Queue name
        
        Returns:
            List of failed messages
        """
        # In real implementation, would have separate DLQ
        # For now, return messages that have been requeued multiple times
        if queue not in self._messages:
            return []
        
        return [
            msg for msg in self._messages[queue]
            if msg.get("status") == "failed"
        ]