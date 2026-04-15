"""
Model Management Module

Manages AI models from three sources:
- config: Models defined in YAML config files (read-only)
- local: Models from local Ollama (scanned dynamically)
- external: Models added by users (stored in JSON)
"""

from .manager import ModelManager
from .schemas import ModelInfo, ModelType, ModelSource, ModelStatus, ModelConfig, ModelStats

__all__ = [
    "ModelManager",
    "ModelInfo",
    "ModelType",
    "ModelSource",
    "ModelStatus",
    "ModelConfig",
    "ModelStats",
]