"""
Tests for LLM Adapter Base Classes.

Tests cover:
- LLMConfig dataclass
- LLMResponse dataclass
- AdapterMetadata dataclass
- BaseLLMAdapter interface
"""

import pytest
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

from adapters.llm.base import (
    LLMConfig,
    LLMResponse,
    AdapterMetadata,
    BaseLLMAdapter,
    RetryableAdapterMixin,
)


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""
    
    def test_llm_config_defaults(self):
        """Test LLMConfig default values."""
        config = LLMConfig(model="gpt-4")
        
        assert config.model == "gpt-4"
        assert config.temperature == 0.7
        assert config.max_tokens == 4096
        assert config.timeout == 30
        assert config.api_key is None
        assert config.base_url is None
        assert config.max_retries == 3
    
    def test_llm_config_custom(self):
        """Test LLMConfig with custom values."""
        config = LLMConfig(
            model="gpt-4-turbo",
            temperature=0.5,
            max_tokens=4000,
            timeout=60.0,
            api_key="test-key",
            base_url="https://api.example.com",
            max_retries=5,
        )
        
        assert config.model == "gpt-4-turbo"
        assert config.temperature == 0.5
        assert config.max_tokens == 4000
        assert config.timeout == 60.0
        assert config.api_key == "test-key"
        assert config.base_url == "https://api.example.com"
        assert config.max_retries == 5


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""
    
    def test_llm_response_defaults(self):
        """Test LLMResponse default values."""
        response = LLMResponse(
            content="Test response",
            model="gpt-4",
        )
        
        assert response.content == "Test response"
        assert response.model == "gpt-4"
        assert response.usage == {}
        assert response.finish_reason == "stop"
        assert response.metadata == {}
    
    def test_llm_response_error(self):
        """Test LLMResponse with error in metadata."""
        response = LLMResponse(
            content="",
            model="gpt-4",
            metadata={"error": "API Error"},
        )
        
        assert response.content == ""
        assert response.metadata.get("error") == "API Error"

    def test_llm_response_with_usage(self):
        """Test LLMResponse with usage information."""
        response = LLMResponse(
            content="Test response",
            model="gpt-4",
            usage={
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            },
        )
        
        assert response.usage["prompt_tokens"] == 10
        assert response.usage["completion_tokens"] == 20
        assert response.usage["total_tokens"] == 30


class TestAdapterMetadata:
    """Tests for AdapterMetadata dataclass."""
    
    def test_adapter_metadata_defaults(self):
        """Test AdapterMetadata default values."""
        metadata = AdapterMetadata(
            name="test",
            version="1.0.0",
            provider="test",
            capabilities=["text"],
        )
        
        assert metadata.name == "test"
        assert metadata.version == "1.0.0"
        assert metadata.provider == "test"
        assert metadata.capabilities == ["text"]
        assert metadata.supports_streaming is False
        assert metadata.supports_functions is False
    
    def test_adapter_metadata_custom(self):
        """Test AdapterMetadata with custom values."""
        metadata = AdapterMetadata(
            name="test",
            version="2.0.0",
            provider="test-provider",
            capabilities=["text", "chat", "functions"],
            supports_streaming=True,
            supports_functions=True,
        )
        
        assert metadata.supports_streaming is True
        assert metadata.supports_functions is True


class ConcreteLLMAdapter(BaseLLMAdapter):
    """Concrete implementation for testing."""
    
    async def generate(self, messages, config=None):
        return LLMResponse(content="test", model="test-model")
    
    async def validate_connection(self):
        return True


class TestBaseLLMAdapter:
    """Tests for BaseLLMAdapterabstract class."""
    
    def test_adapter_init(self):
        """Test BaseLLMAdapter initialization."""
        metadata = AdapterMetadata(
            name="test",
            version="1.0.0",
            provider="test",
            capabilities=["text"],
        )
        config = LLMConfig(model="test-model")
        
        adapter = ConcreteLLMAdapter(metadata, config)
        
        assert adapter._metadata == metadata
        assert adapter._config == config
    
    def test_merge_config_with_override(self):
        """Test merging configurations."""
        metadata = AdapterMetadata(
            name="test",
            version="1.0.0",
            provider="test",
            capabilities=["text"],
        )
        config = LLMConfig(model="test-model", temperature=0.7)
        
        adapter = ConcreteLLMAdapter(metadata, config)
        
        override_config = LLMConfig(model="test-model", temperature=0.5)
        merged = adapter._merge_config(override_config)
        
        assert merged.temperature == 0.5  # Overridden
    
    def test_merge_config_without_override(self):
        """Test merging without override."""
        metadata = AdapterMetadata(
            name="test",
            version="1.0.0",
            provider="test",
            capabilities=["text"],
        )
        config = LLMConfig(model="test-model", temperature=0.7)
        
        adapter = ConcreteLLMAdapter(metadata, config)
        
        merged = adapter._merge_config(None)
        
        assert merged.temperature == 0.7  # Original


class TestRetryableAdapterMixin:
    """Tests for RetryableAdapterMixin."""
    
    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Test retry logic on failure."""
        mixin = RetryableAdapterMixin()
        
        call_count = 0
        
        async def failing_func(messages, config):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary error")
            return LLMResponse(content="success", model="test")
        
        result = await mixin._generate_with_retry(
            failing_func, [], LLMConfig(model="test", max_retries=3), max_retries=3
        )
        
        assert result.content == "success"
        assert call_count == 3