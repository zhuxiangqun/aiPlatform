"""
Model Service - Unified Model Access Interface

Provides:
- Model registry and discovery
- Unified model calling interface
- Model configuration management
- Cost tracking
- Retry and fallback strategies
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio


class ModelProvider(Enum):
    """Model provider enumeration."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL_OLLAMA = "ollama"
    LOCAL_VLLM = "vllm"
    CUSTOM = "custom"


@dataclass
class ModelConfig:
    """
    Model configuration.
    
    Attributes:
        model_id: Unique model ID
        provider: Model provider
        model_name: Model name (e.g., "gpt-4", "claude-3-opus")
        api_key: API key (optional)
        api_base_url: API base URL (optional)
        temperature: Temperature parameter
        max_tokens: Maximum tokens
        top_p: Top-p parameter
        timeout: Request timeout in seconds
        retry_count: Number of retries
        metadata: Additional metadata
    """
    model_id: str
    provider: ModelProvider
    model_name: str
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    timeout: float = 60.0
    retry_count: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelCall:
    """
    Model call record.
    
    Attributes:
        call_id: Unique call ID
        model_id: Model ID
        input_tokens: Input token count
        output_tokens: Output token count
        duration_ms: Call duration in milliseconds
        cost: Call cost
        status: Call status
        timestamp: Call timestamp
    """
    call_id: str
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: float = 0.0
    cost: float = 0.0
    status: str = "pending"
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FormatAffinity:
    """
    Format Affinity - Model's preference for output formats.
    
    Attributes:
        structural: Structural affinity (0-1), e.g., JSON > Markdown > plain text
        stylistic: Stylistic affinity (0-1), e.g., concise > verbose, formal > casual
        length: Length affinity (0-1), alignment with model context window
        example: Example affinity (0-1), response to few-shot examples
    """
    structural: float = 0.5
    stylistic: float = 0.5
    length: float = 0.5
    example: float = 0.5
    
    def get_overall_score(self) -> float:
        """Calculate overall format affinity score."""
        return (self.structural + self.stylistic + self.length + self.example) / 4.0
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "structural": self.structural,
            "stylistic": self.stylistic,
            "length": self.length,
            "example": self.example
        }


class FormatStrategy(Enum):
    """Format optimization strategies."""
    LOCKED = "locked"          # Fixed output format
    PROGRESSIVE = "progressive"  # Simple to complex
    FEEDBACK = "feedback"      # Adjust based on results
    TEMPLATE = "template"      # Use standardized templates


class ModelService:
    """
    Model Service - Unified model access interface.
    
    Features:
    - Model registration and discovery
    - Unified calling interface
    - Configuration management
    - Cost tracking
    - Retry and fallback
    - Format affinity analysis
    """
    
    def __init__(self):
        self._models: Dict[str, ModelConfig] = {}
        self._clients: Dict[str, Any] = {}
        self._call_history: List[ModelCall] = []
        self._default_model: Optional[str] = None
        self._format_affinities: Dict[str, Dict[str, FormatAffinity]] = {}
        self._format_performance: Dict[str, Dict[str, Dict[str, Any]]] = {}
    
    async def register_model(
        self,
        config: ModelConfig,
        set_default: bool = False
    ) -> str:
        """
        Register a model.
        
        Args:
            config: Model configuration
            set_default: Set as default model
            
        Returns:
            Model ID
        """
        self._models[config.model_id] = config
        
        if set_default or not self._default_model:
            self._default_model = config.model_id
        
        return config.model_id
    
    async def get_model(self, model_id: str) -> Optional[ModelConfig]:
        """
        Get model configuration.
        
        Args:
            model_id: Model ID
            
        Returns:
            ModelConfig or None
        """
        return self._models.get(model_id)
    
    async def list_models(self, provider: Optional[ModelProvider] = None) -> List[ModelConfig]:
        """
        List available models.
        
        Args:
            provider: Filter by provider (optional)
            
        Returns:
            List of ModelConfig
        """
        models = list(self._models.values())
        if provider:
            models = [m for m in models if m.provider == provider]
        return models
    
    async def set_default_model(self, model_id: str) -> bool:
        """
        Set default model.
        
        Args:
            model_id: Model ID
            
        Returns:
            True if successful
        """
        if model_id in self._models:
            self._default_model = model_id
            return True
        return False
    
    async def get_default_model(self) -> Optional[str]:
        """
        Get default model ID.
        
        Returns:
            Default model ID or None
        """
        return self._default_model
    
    async def call(
        self,
        model_id: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Call a model with messages or prompt.
        
        Args:
            model_id: Model ID (uses default if not specified)
            messages: Chat messages
            prompt: Prompt string (alternative to messages)
            temperature: Temperature override
            max_tokens: Max tokens override
            **kwargs: Additional parameters
            
        Returns:
            Model response
        """
        model_id = model_id or self._default_model
        if not model_id:
            raise ValueError("No model specified and no default model set")
        
        config = await self.get_model(model_id)
        if not config:
            raise ValueError(f"Model not found: {model_id}")
        
        start_time = datetime.utcnow()
        call_id = f"call-{start_time.timestamp()}"
        
        call_record = ModelCall(
            call_id=call_id,
            model_id=model_id,
            status="running"
        )
        
        try:
            temp = temperature if temperature is not None else config.temperature
            max_tok = max_tokens if max_tokens is not None else config.max_tokens
            
            response = await self._execute_call(
                config=config,
                messages=messages,
                prompt=prompt,
                temperature=temp,
                max_tokens=max_tok,
                **kwargs
            )
            
            call_record.status = "success"
            call_record.output_tokens = response.get("usage", {}).get("completion_tokens", 0)
            call_record.input_tokens = response.get("usage", {}).get("prompt_tokens", 0)
            
        except Exception as e:
            call_record.status = "failed"
            raise
        
        finally:
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            call_record.duration_ms = duration
            self._call_history.append(call_record)
        
        return response
    
    async def _execute_call(
        self,
        config: ModelConfig,
        messages: Optional[List[Dict[str, str]]],
        prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute model call with retry logic.
        
        Args:
            config: Model configuration
            messages: Chat messages
            prompt: Prompt string
            temperature: Temperature
            max_tokens: Max tokens
            
        Returns:
            Model response
        """
        last_error = None
        
        for attempt in range(config.retry_count):
            try:
                return await self._call_provider(
                    config=config,
                    messages=messages,
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs
                )
            except Exception as e:
                last_error = e
                if attempt < config.retry_count - 1:
                    await asyncio.sleep(2 ** attempt)
        
        raise last_error or Exception("Model call failed")
    
    async def _call_provider(
        self,
        config: ModelConfig,
        messages: Optional[List[Dict[str, str]]],
        prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Call model provider (placeholder for actual implementation).
        
        This method should be implemented by subclasses or via adapter pattern.
        The actual implementation would use LangChain or direct API calls.
        
        Args:
            config: Model configuration
            messages: Chat messages
            prompt: Prompt string
            temperature: Temperature
            max_tokens: Max tokens
            
        Returns:
            Model response
        """
        return {
            "content": "Mock response - implement actual provider call",
            "model": config.model_name,
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }
    
    async def get_call_history(
        self,
        model_id: Optional[str] = None,
        limit: int = 100
    ) -> List[ModelCall]:
        """
        Get model call history.
        
        Args:
            model_id: Filter by model ID (optional)
            limit: Maximum number of records
            
        Returns:
            List of ModelCall records
        """
        history = self._call_history
        if model_id:
            history = [c for c in history if c.model_id == model_id]
        return history[-limit:]
    
    async def get_stats(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get model usage statistics.
        
        Args:
            model_id: Model ID (optional)
            
        Returns:
            Usage statistics
        """
        history = await self.get_call_history(model_id)
        
        total_calls = len(history)
        success_calls = sum(1 for h in history if h.status == "success")
        total_tokens = sum(h.input_tokens + h.output_tokens for h in history)
        total_cost = sum(h.cost for h in history)
        avg_duration = sum(h.duration_ms for h in history) / total_calls if total_calls > 0 else 0
        
        return {
            "total_calls": total_calls,
            "success_calls": success_calls,
            "failed_calls": total_calls - success_calls,
            "success_rate": success_calls / total_calls if total_calls > 0 else 0,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "avg_duration_ms": avg_duration
        }
    
    async def analyze_format_preference(
        self,
        model_id: str,
        sample_outputs: List[Dict[str, Any]]
    ) -> FormatAffinity:
        """
        Analyze model's format preference from sample outputs.
        
        Args:
            model_id: Model ID
            sample_outputs: List of sample outputs with format info
            
        Returns:
            FormatAffinity analysis result
        """
        model = await self.get_model(model_id)
        if not model:
            return FormatAffinity()
        
        structural_scores = []
        stylistic_scores = []
        length_scores = []
        example_scores = []
        
        for sample in sample_outputs:
            if "format" in sample:
                fmt = sample["format"]
                if fmt == "json":
                    structural_scores.append(1.0)
                elif fmt == "markdown":
                    structural_scores.append(0.7)
                else:
                    structural_scores.append(0.3)
            
            if "success_rate" in sample:
                success = sample["success_rate"]
                example_scores.append(success)
        
        affinity = FormatAffinity(
            structural=sum(structural_scores) / len(structural_scores) if structural_scores else 0.5,
            stylistic=0.5,
            length=0.5,
            example=sum(example_scores) / len(example_scores) if example_scores else 0.5
        )
        
        if model_id not in self._format_affinities:
            self._format_affinities[model_id] = {}
        self._format_affinities[model_id]["current"] = affinity
        
        return affinity
    
    async def optimize_prompt_format(
        self,
        model_id: str,
        prompt: str,
        strategy: FormatStrategy = FormatStrategy.TEMPLATE
    ) -> str:
        """
        Optimize prompt format based on model's format affinity.
        
        Args:
            model_id: Model ID
            prompt: Original prompt
            strategy: Format optimization strategy
            
        Returns:
            Optimized prompt
        """
        model = await self.get_model(model_id)
        if not model:
            return prompt
        
        affinity = self._format_affinities.get(model_id, {}).get("current", FormatAffinity())
        
        if strategy == FormatStrategy.LOCKED:
            if affinity.structural > 0.7:
                return f"Output in JSON format:\n{prompt}"
            elif affinity.structural > 0.4:
                return f"Output in Markdown format:\n{prompt}"
        
        elif strategy == FormatStrategy.TEMPLATE:
            template = f"""Task: {prompt}

Provide output in the following format:
- Start with a brief summary
- Provide detailed analysis
- End with recommendations
"""
            return template
        
        elif strategy == FormatStrategy.PROGRESSIVE:
            return f"First, provide a brief answer. Then, expand with details.\n{prompt}"
        
        elif strategy == FormatStrategy.FEEDBACK:
            return f"Answer the following question. If the format needs adjustment, suggest improvements.\n{prompt}"
        
        return prompt
    
    async def track_format_performance(
        self,
        model_id: str,
        format_type: str,
        success: bool,
        metrics: Dict[str, Any]
    ) -> None:
        """
        Track format performance for optimization.
        
        Args:
            model_id: Model ID
            format_type: Format type used
            success: Whether the format was successful
            metrics: Performance metrics
        """
        if not hasattr(self, '_format_performance'):
            self._format_performance = {}
        
        if model_id not in self._format_performance:
            self._format_performance[model_id] = {}
        
        if format_type not in self._format_performance[model_id]:
            self._format_performance[model_id][format_type] = {"success": 0, "failure": 0, "metrics": []}
        
        if success:
            self._format_performance[model_id][format_type]["success"] += 1
        else:
            self._format_performance[model_id][format_type]["failure"] += 1
        
        self._format_performance[model_id][format_type]["metrics"].append(metrics)