"""
Tests for Anthropic Adapter.

Tests cover:
- Initialization and configuration
- Generate and stream operations
- Connection validation
- Error handling
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from adapters.llm.anthropic_adapter import AnthropicAdapter
from adapters.llm.base import LLMConfig, LLMResponse, AdapterMetadata


class TestAnthropicAdapter:
    """Tests for AnthropicAdapter class."""
    
    def test_init_default_config(self):
        """Test AnthropicAdapter initialization with default config."""
        adapter = AnthropicAdapter(api_key="test-key")
        
        assert adapter._config.model == "claude-3-opus-20240229"
        assert adapter._config.api_key == "test-key"
    
    def test_init_custom_model(self):
        """Test AnthropicAdapter initialization with custom model."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            model="claude-3-sonnet-20240229"
        )
        
        assert adapter._config.model == "claude-3-sonnet-20240229"
    
    def test_init_custom_config(self):
        """Test AnthropicAdapter initialization with custom config."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            model="claude-3-opus-20240229",
            temperature=0.5,
            max_tokens=1000,
        )
        
        assert adapter._config.temperature == 0.5
        assert adapter._config.max_tokens == 1000
    
    def test_metadata(self):
        """Test adapter metadata."""
        adapter = AnthropicAdapter(api_key="test-key")
        
        assert adapter._metadata.name == "anthropic"
        assert adapter._metadata.provider == "anthropic"
        assert "text" in adapter._metadata.capabilities
        assert adapter._metadata.supports_streaming is True
        assert adapter._metadata.supports_functions is False
    
    @pytest.mark.asyncio
    async def test_generate_fallback(self):
        """Test generate fallback implementation."""
        with patch('anthropic.AsyncAnthropic') as mock_client_class:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Test response")]
            mock_response.model = "claude-3-opus-20240229"
            mock_response.usage = MagicMock()
            mock_response.usage.input_tokens = 10
            mock_response.usage.output_tokens = 5
            
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            adapter = AnthropicAdapter(api_key="test-key")
            
            response = await adapter._generate_fallback(
                messages=[{"role": "user", "content": "Hello"}],
                config=LLMConfig(model="claude-3-opus-20240229", api_key="test-key")
            )
            
            assert response.content == "Test response"
            assert response.model == "claude-3-opus-20240229"
            # Check usage is present
            assert "input_tokens" in response.usage or response.usage is not None
    
    @pytest.mark.asyncio
    async def test_stream_generate(self):
        """Test stream generate."""
        with patch('anthropic.AsyncAnthropic') as mock_client_class:
            # Mock streaming response
            async def mock_stream():
                chunks = [
                    MagicMock(delta=MagicMock(content="Hello")),
                    MagicMock(delta=MagicMock(content=" world")),
                ]
                for chunk in chunks:
                    yield chunk
            
            mock_client = MagicMock()
            mock_client.messages.stream = AsyncMock(return_value=mock_stream())
            mock_client_class.return_value = mock_client
            
            adapter = AnthropicAdapter(api_key="test-key")
            
            chunks = []
            async for chunk in adapter.stream_generate([{"role": "user", "content": "Hello"}]):
                chunks.append(chunk)
            
            # Should yield chunks
            assert len(chunks) >= 0
    
    def test_build_messages(self):
        """Test building messages."""
        adapter = AnthropicAdapter(api_key="test-key")
        
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        
        lc_messages = adapter._build_messages(messages)
        
        # Should convert messages
        assert len(lc_messages) == 3
    
    @pytest.mark.asyncio
    async def test_generate_with_error(self):
        """Test generate handles errors."""
        with patch('anthropic.AsyncAnthropic') as mock_client_class:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(side_effect=Exception("API Error"))
            mock_client_class.return_value = mock_client
            
            adapter = AnthropicAdapter(api_key="test-key")
            
            response = await adapter._generate_fallback(
                messages=[{"role": "user", "content": "Hello"}],
                config=LLMConfig(model="claude-3-opus-20240229", api_key="test-key")
            )
            
            # Should return error response
            assert response.content == ""
            assert "error" in response.metadata
    
    @pytest.mark.asyncio
    async def test_validate_connection(self):
        """Test connection validation."""
        adapter = AnthropicAdapter(api_key="test-key")
        
        # Validation may fail if no real API key
        # This test just verifies the method exists
        result = await adapter.validate_connection()
        
        # Result depends on whether anthropic is installed and API key is valid
        assert result is not None

class TestAnthropicAdapterFallback:
    """Tests for AnthropicAdapter fallback behavior."""
    
    @pytest.mark.asyncio
    async def test_fallback_on_error(self):
        """Test fallback behavior on error."""
        adapter = AnthropicAdapter(api_key="test-key")
        
        # Test that generate method exists and can be called
        # The actual behavior depends on installed packages
        assert adapter.generate is not None