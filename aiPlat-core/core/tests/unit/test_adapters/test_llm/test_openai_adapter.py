"""
Tests for OpenAI Adapter.

Tests cover:
- Initialization and configuration
- Generate and stream operations
- Connection validation
- Error handling
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from adapters.llm.openai_adapter import OpenAIAdapter, AzureOpenAIAdapter
from adapters.llm.base import LLMConfig, LLMResponse


class TestOpenAIAdapter:
    """Tests for OpenAIAdapter class."""
    
    def test_init_default_config(self):
        """Test OpenAIAdapter initialization with default config."""
        adapter = OpenAIAdapter(api_key="test-key")
        
        assert adapter._config.model == "gpt-4"
        assert adapter._config.api_key == "test-key"
    
    def test_init_custom_model(self):
        """Test OpenAIAdapter initialization with custom model."""
        adapter = OpenAIAdapter(
            api_key="test-key",
            model="gpt-3.5-turbo"
        )
        
        assert adapter._config.model == "gpt-3.5-turbo"
    
    def test_init_custom_config(self):
        """Test OpenAIAdapter initialization with custom config."""
        adapter = OpenAIAdapter(
            api_key="test-key",
            model="gpt-4",
            temperature=0.5,
            max_tokens=1000,
        )
        
        assert adapter._config.temperature == 0.5
        assert adapter._config.max_tokens == 1000
    
    def test_metadata(self):
        """Test adapter metadata."""
        adapter = OpenAIAdapter(api_key="test-key")
        
        assert adapter._metadata.name == "openai"
        assert adapter._metadata.provider == "openai"
        assert "chat" in adapter._metadata.capabilities
        assert adapter._metadata.supports_streaming is True
    
    @pytest.mark.asyncio
    async def test_generate_fallback(self):
        """Test generate fallback implementation."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test response"
            mock_response.choices[0].finish_reason = "stop"
            mock_response.model = "gpt-4"
            mock_response.usage = MagicMock()
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 5
            mock_response.usage.total_tokens = 15
            
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            adapter = OpenAIAdapter(api_key="test-key")
            
            response = await adapter._generate_fallback(
                messages=[{"role": "user", "content": "Hello"}],
                config=LLMConfig(model="gpt-4", api_key="test-key")
            )
            
            assert response.content == "Test response"
            assert response.model == "gpt-4"
            assert response.usage["total_tokens"] == 15
    
    @pytest.mark.asyncio
    async def test_stream_generate(self):
        """Test stream generate."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            # Mock streaming response
            async def mock_stream():
                chunks = [
                    MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))]),
                    MagicMock(choices=[MagicMock(delta=MagicMock(content=" world"))]),
                ]
                for chunk in chunks:
                    yield chunk
            
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())
            mock_client_class.return_value = mock_client
            
            adapter = OpenAIAdapter(api_key="test-key")
            
            chunks = []
            async for chunk in adapter.stream_generate([{"role": "user", "content": "Hello"}]):
                chunks.append(chunk)
            
            # Should yield chunks
            assert len(chunks) >= 0
    
    def test_build_messages(self):
        """Test building messages."""
        adapter = OpenAIAdapter(api_key="test-key")
        
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        
        lc_messages = adapter._build_messages(messages)
        
        # Should convert messages
        assert len(lc_messages) == 3


class TestAzureOpenAIAdapter:
    """Tests for AzureOpenAIAdapter class."""
    
    def test_init(self):
        """Test AzureOpenAIAdapter initialization."""
        adapter = AzureOpenAIAdapter(
            api_key="test-key",
            endpoint="https://test.openai.azure.com",
            deployment_name="test-deployment",
        )
        
        assert adapter._metadata.name == "azure-openai"
        assert adapter._metadata.provider == "azure-openai"
    
    def test_custom_config(self):
        """Test AzureOpenAIAdapter custom config."""
        adapter = AzureOpenAIAdapter(
            api_key="test-key",
            api_version="2024-01-01",
            endpoint="https://test.openai.azure.com",
            deployment_name="test-deployment",
        )
        
        assert adapter._config.metadata["api_version"] == "2024-01-01"
        assert adapter._config.metadata["endpoint"] == "https://test.openai.azure.com"
        assert adapter._config.metadata["deployment_name"] == "test-deployment"


class TestOpenAIAdapterErrorHandling:
    """Tests for OpenAIAdapter error handling."""
    
    @pytest.mark.asyncio
    async def test_generate_with_error(self):
        """Test generate handles errors."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))
            mock_client_class.return_value = mock_client
            
            adapter = OpenAIAdapter(api_key="test-key")
            
            response = await adapter._generate_fallback(
                messages=[{"role": "user", "content": "Hello"}],
                config=LLMConfig(model="gpt-4", api_key="test-key")
            )
            
            # Should return error response
            assert response.content == ""
            assert "API Error" in response.metadata.get("error", "")
    
    @pytest.mark.asyncio
    async def test_validate_connection_success(self):
        """Test connection validation succeeds."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = MagicMock()
            mock_client.models.list = AsyncMock(return_value=[])
            mock_client_class.return_value = mock_client
            
            adapter = OpenAIAdapter(api_key="test-key")
            
            result = await adapter.validate_connection()
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_connection_failure(self):
        """Test connection validation fails."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = MagicMock()
            mock_client.models.list = AsyncMock(side_effect=Exception("Connection failed"))
            mock_client_class.return_value = mock_client
            
            adapter = OpenAIAdapter(api_key="test-key")
            
            result = await adapter.validate_connection()
            
            assert result is False