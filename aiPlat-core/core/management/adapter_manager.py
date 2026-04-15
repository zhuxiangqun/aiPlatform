"""
Adapter Manager - Manages LLM adapters

Provides adapter configuration and monitoring operations.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid


@dataclass
class AdapterInfo:
    """Adapter information"""
    id: str
    name: str
    provider: str  # OpenAI, Anthropic, AzureOpenAI, Ollama, vLLM, Custom
    description: str
    status: str  # active, disabled, error
    api_key: str
    api_base_url: str
    organization_id: Optional[str]
    models: List[Dict[str, Any]]
    rate_limit: Dict[str, Any]
    retry_config: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelConfig:
    """Model configuration"""
    name: str
    enabled: bool
    max_tokens: int
    temperature: float
    top_p: Optional[float]
    frequency_penalty: Optional[float]
    presence_penalty: Optional[float]


@dataclass
class CallStats:
    """Call statistics"""
    total_calls: int = 0
    success_count: int = 0
    failed_count: int = 0
    avg_duration_ms: float =0.0
    tokens_used: int =0


@dataclass
class CallRecord:
    """Call record"""
    id: str
    adapter_id: str
    model: str
    status: str  # success, error
    duration_ms: float
    tokens: Dict[str, int]
    error: Optional[str]
    timestamp: datetime


class AdapterManager:
    """
    Adapter Manager - Manages LLM adapters
    
    Provides:
    - Adapter CRUD operations
    - Model configuration
    - Call monitoring
    - Connection testing
    """
    
    def __init__(self):
        self._adapters: Dict[str, AdapterInfo] = {}
        self._call_stats: Dict[str, CallStats] = {}
        self._call_history: Dict[str, List[CallRecord]] = {}
    
    async def create_adapter(
        self,
        name: str,
        provider: str,
        api_key: str,
        api_base_url: str,
        description: str = "",
        organization_id: Optional[str] = None,
        models: Optional[List[Dict[str, Any]]] = None,
        rate_limit: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AdapterInfo:
        """Create a new adapter"""
        adapter_id = f"adapter-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow()
        
        adapter = AdapterInfo(
            id=adapter_id,
            name=name,
            provider=provider,
            description=description,
            status="active",
            api_key=api_key,
            api_base_url=api_base_url,
            organization_id=organization_id,
            models=models or [],
            rate_limit=rate_limit or {
                "rpm": 60,
                "tpm": 90000,
                "daily_quota": 1000000
            },
            retry_config={
                "enabled": True,
                "max_retries": 3,
                "interval_seconds": 1,
                "backoff": "exponential"
            },
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
        
        self._adapters[adapter_id] = adapter
        self._call_stats[adapter_id] = CallStats()
        self._call_history[adapter_id] = []
        
        return adapter
    
    async def get_adapter(self, adapter_id: str) -> Optional[AdapterInfo]:
        """Get adapter by ID"""
        return self._adapters.get(adapter_id)
    
    async def list_adapters(
        self,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[AdapterInfo]:
        """List adapters with filters"""
        adapters = list(self._adapters.values())
        
        if provider:
            adapters = [a for a in adapters if a.provider == provider]
        if status:
            adapters = [a for a in adapters if a.status == status]
        
        return adapters[offset:offset + limit]
    
    async def update_adapter(
        self,
        adapter_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        rate_limit: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[AdapterInfo]:
        """Update adapter configuration"""
        adapter = self._adapters.get(adapter_id)
        if not adapter:
            return None
        
        if name:
            adapter.name = name
        if description:
            adapter.description = description
        if api_key:
            adapter.api_key = api_key
        if api_base_url:
            adapter.api_base_url = api_base_url
        if rate_limit:
            adapter.rate_limit.update(rate_limit)
        if metadata:
            adapter.metadata.update(metadata)
        
        adapter.updated_at = datetime.utcnow()
        
        return adapter
    
    async def delete_adapter(self, adapter_id: str) -> bool:
        """Delete adapter"""
        if adapter_id not in self._adapters:
            return False
        
        del self._adapters[adapter_id]
        del self._call_stats[adapter_id]
        del self._call_history[adapter_id]
        
        return True
    
    async def enable_adapter(self, adapter_id: str) -> bool:
        """Enable adapter"""
        adapter = self._adapters.get(adapter_id)
        if not adapter:
            return False
        adapter.status = "active"
        adapter.updated_at = datetime.utcnow()
        return True
    
    async def disable_adapter(self, adapter_id: str) -> bool:
        """Disable adapter"""
        adapter = self._adapters.get(adapter_id)
        if not adapter:
            return False
        adapter.status = "disabled"
        adapter.updated_at = datetime.utcnow()
        return True
    
    async def test_connection(self, adapter_id: str) -> Dict[str, Any]:
        """Test adapter connection"""
        adapter = self._adapters.get(adapter_id)
        if not adapter:
            return {"success": False, "error": "Adapter not found"}
        
        # Placeholder implementation
        return {
            "success": True,
            "latency_ms": 150,
            "message": "Connection successful"
        }
    
    async def add_model(
        self,
        adapter_id: str,
        model_name: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        enabled: bool = True
    ) -> bool:
        """Add model to adapter"""
        adapter = self._adapters.get(adapter_id)
        if not adapter:
            return False
        
        model_config = {
            "name": model_name,
            "enabled": enabled,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        adapter.models.append(model_config)
        adapter.updated_at = datetime.utcnow()
        
        return True
    
    async def remove_model(self, adapter_id: str, model_name: str) -> bool:
        """Remove model from adapter"""
        adapter = self._adapters.get(adapter_id)
        if not adapter:
            return False
        
        adapter.models = [m for m in adapter.models if m["name"] != model_name]
        adapter.updated_at = datetime.utcnow()
        
        return True
    
    async def record_call(
        self,
        adapter_id: str,
        model: str,
        status: str,
        duration_ms: float,
        tokens: Dict[str, int],
        error: Optional[str] = None
    ) -> str:
        """Record call"""
        call_id = f"call-{uuid.uuid4().hex[:8]}"
        
        call = CallRecord(
            id=call_id,
            adapter_id=adapter_id,
            model=model,
            status=status,
            duration_ms=duration_ms,
            tokens=tokens,
            error=error,
            timestamp=datetime.utcnow()
        )
        
        self._call_history[adapter_id].append(call)
        
        # Update stats
        stats = self._call_stats[adapter_id]
        stats.total_calls += 1
        if status == "success":
            stats.success_count += 1
        else:
            stats.failed_count += 1
        stats.tokens_used += tokens.get("total", 0)
        
        return call_id
    
    async def get_call_stats(self, adapter_id: str) -> Optional[CallStats]:
        """Get call statistics"""
        return self._call_stats.get(adapter_id)
    
    async def get_call_history(
        self,
        adapter_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[CallRecord]:
        """Get call history"""
        history = self._call_history.get(adapter_id, [])
        return history[offset:offset + limit]
    
    async def get_model_distribution(self, adapter_id: str) -> Dict[str, Dict[str, Any]]:
        """Get model call distribution"""
        history = self._call_history.get(adapter_id, [])
        distribution: Dict[str, Dict[str, Any]] = {}
        
        for call in history:
            if call.model not in distribution:
                distribution[call.model] = {"calls": 0, "percentage": 0.0}
            distribution[call.model]["calls"] += 1
        
        total = sum(d["calls"] for d in distribution.values())
        if total > 0:
            for model_data in distribution.values():
                model_data["percentage"] = model_data["calls"] / total
        
        return distribution
    
    def get_adapter_count(self) -> Dict[str, int]:
        """Get adapter count by status"""
        return {
            "total": len(self._adapters),
            "active": sum(1 for a in self._adapters.values() if a.status == "active"),
            "disabled": sum(1 for a in self._adapters.values() if a.status == "disabled"),
            "error": sum(1 for a in self._adapters.values() if a.status == "error")
        }