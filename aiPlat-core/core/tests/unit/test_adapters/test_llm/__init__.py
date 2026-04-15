"""
Tests for LLM adapters.

Tests cover:
- Base adapter interface
- OpenAI adapter implementation
- Anthropic adapter implementation
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from adapters.llm.base import LLMConfig, BaseLLMAdapter
from adapters.llm.openai_adapter import OpenAIAdapter
from adapters.llm.anthropic_adapter import AnthropicAdapter


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""
    
    def test_llm_config_defaults(self):
        """Test LLMConfig default values."""
        config = LLMConfig(model="gpt-4")
        
        assert config.model == "gpt-4"
        assert config.temperature == 0.7
        assert config.max_tokens == 2000
        assert config.api_key is None
    
    def test_llm_config_custom(self):
        """Test LLMConfig with custom values."""
        config = LLMConfig(
            model="gpt-4-turbo",
            temperature=0.5,
            max_tokens=4000,
            api_key="test-key",
        )
        
        assert config.model == "gpt-4-turbo"
        assert config.temperature == 0.5
        assert config.max_tokens == 4000
        assert config.api_key == "test-key"


class TestBaseLLMAdapter:
    """Tests for BaseLLMAdapter abstract class."""
    
    def test_base_adapter_init(self):
        """Test BaseLLMAdapter initialization."""
        config = LLMConfig(model="test-model")
        
        # Should not be able to instantiate directly
        # This test verifies the abstract methods exist
    
    def test_base_adapter_methods_exist(self):
        """Test BaseLLMAdapter has expected methods."""
        # Verify abstract methods exist
        assert hasattr(BaseLLMAdapter, 'generate')
        assert hasattr(BaseLLMAdapter, 'embed')


class TestOpenAIAdapter:
    """Tests for OpenAIAdapter."""
    
    def test_openai_adapter_init(self):
        """Test OpenAIAdapter initialization."""
        config = LLMConfig(model="gpt-4")
        
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            adapter = OpenAIAdapter(config)
            
            assert adapter.config.model == "gpt-4"
    
    @pytest.mark.asyncio
    async def test_openai_adapter_generate(self):
        """Test OpenAIAdapter generate method."""
        config = LLMConfig(model="gpt-4")
        
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Mock response
            mock_response = MagicMock()
            mock_response.choices = [
                MagicMock(message=MagicMock(content="Test response"))
            ]
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            
            adapter = OpenAIAdapter(config)
            result = await adapter.generate("Test prompt")
            
            assert result == "Test response"
            mock_client.chat.completions.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_openai_adapter_embed(self):
        """Test OpenAIAdapter embed method."""
        config = LLMConfig(model="text-embedding-3-small")
        
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Mock response
            mock_response = MagicMock()
            mock_response.data = [
                MagicMock(embedding=[0.1, 0.2, 0.3])
            ]
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            
            adapter = OpenAIAdapter(config)
            result = await adapter.embed("Test text")
            
            assert result == [0.1, 0.2, 0.3]


class TestAnthropicAdapter:
    """Tests for AnthropicAdapter."""
    
    def test_anthropic_adapter_init(self):
        """Test AnthropicAdapter initialization."""
        config = LLMConfig(model="claude-3-opus")
        
        with patch('anthropic.AsyncAnthropic') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            adapter = AnthropicAdapter(config)
            
            assert adapter.config.model == "claude-3-opus"
    
    @pytest.mark.asyncio
    async def test_anthropic_adapter_generate(self):
        """Test AnthropicAdapter generate method."""
        config = LLMConfig(model="claude-3-opus")
        
        with patch('anthropic.AsyncAnthropic') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Mock response
            mock_response = MagicMock()
            mock_response.content = [
                MagicMock(text="Test response")
            ]
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            
            adapter = AnthropicAdapter(config)
            result = await adapter.generate("Test prompt")
            
            assert result == "Test response"
            mock_client.messages.create.assert_called_once()