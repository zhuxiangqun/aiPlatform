"""
Configuration Management Module
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import os
import json
from pathlib import Path


@dataclass
class Settings:
    """Application settings"""
    # Model settings
    default_model: str = "gpt-4"
    default_temperature: float = 0.7
    default_max_tokens: int = 4096
    
    # API settings
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    
    # Execution settings
    max_steps: int = 10
    max_tokens: int = 8192
    timeout: int = 30
    max_retries: int = 3
    
    # Memory settings
    memory_max_tokens: int = 2000
    
    # Observability settings
    enable_tracing: bool = True
    log_level: str = "INFO"
    
    # Custom settings
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get setting value"""
        return getattr(self, key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set setting value"""
        setattr(self, key, value)
    
    def update(self, config: Dict[str, Any]) -> None:
        """Update settings from dict"""
        for key, value in config.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                self.extra[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict"""
        result = {}
        for key, value in self.__dict__.items():
            if key != "extra":
                result[key] = value
        result.update(self.extra)
        return result


class IConfigLoader(ABC):
    """
    Config loader interface
    """
    
    @abstractmethod
    def load(self) -> Settings:
        """Load configuration"""
        pass
    
    @abstractmethod
    def save(self, settings: Settings) -> None:
        """Save configuration"""
        pass


class EnvConfigLoader(IConfigLoader):
    """
    Load configuration from environment variables
    """
    
    PREFIX = "AIPLAT_"
    
    def load(self) -> Settings:
        """Load settings from environment"""
        settings = Settings()
        
        # Model settings
        if model := os.getenv(f"{self.PREFIX}DEFAULT_MODEL"):
            settings.default_model = model
        if temp := os.getenv(f"{self.PREFIX}DEFAULT_TEMPERATURE"):
            settings.default_temperature = float(temp)
        if tokens := os.getenv(f"{self.PREFIX}DEFAULT_MAX_TOKENS"):
            settings.default_max_tokens = int(tokens)
        
        # API keys
        if api_key := os.getenv("OPENAI_API_KEY"):
            settings.openai_api_key = api_key
        if api_key := os.getenv("ANTHROPIC_API_KEY"):
            settings.anthropic_api_key = api_key
        
        # Execution settings
        if steps := os.getenv(f"{self.PREFIX}MAX_STEPS"):
            settings.max_steps = int(steps)
        if timeout := os.getenv(f"{self.PREFIX}TIMEOUT"):
            settings.timeout = int(timeout)
        
        # Observability
        if tracing := os.getenv(f"{self.PREFIX}ENABLE_TRACING"):
            settings.enable_tracing = tracing.lower() == "true"
        if level := os.getenv(f"{self.PREFIX}LOG_LEVEL"):
            settings.log_level = level
        
        return settings
    
    def save(self, settings: Settings) -> None:
        """Save settings to environment (no-op)"""
        pass


class JSONConfigLoader(IConfigLoader):
    """
    Load configuration from JSON file
    """
    
    def __init__(self, config_path: str = "config.json"):
        self._config_path = Path(config_path)
    
    def load(self) -> Settings:
        """Load settings from JSON file"""
        if not self._config_path.exists():
            return Settings()
        
        with open(self._config_path, "r") as f:
            config = json.load(f)
        
        settings = Settings()
        settings.update(config)
        return settings
    
    def save(self, settings: Settings) -> None:
        """Save settings to JSON file"""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self._config_path, "w") as f:
            json.dump(settings.to_dict(), f, indent=2)


class YAMLConfigLoader(IConfigLoader):
    """
    Load configuration from YAML file
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        self._config_path = Path(config_path)
    
    def load(self) -> Settings:
        """Load settings from YAML file"""
        if not self._config_path.exists():
            return Settings()
        
        try:
            import yaml
            with open(self._config_path, "r") as f:
                config = yaml.safe_load(f) or {}
            
            settings = Settings()
            settings.update(config)
            return settings
        except ImportError:
            return Settings()
    
    def save(self, settings: Settings) -> None:
        """Save settings to YAML file"""
        try:
            import yaml
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self._config_path, "w") as f:
                yaml.dump(settings.to_dict(), f, default_flow_style=False)
        except ImportError:
            pass


class ConfigManager:
    """
    Configuration manager - handles multiple config sources
    """
    
    def __init__(self):
        self._settings = Settings()
        self._loaders: list[IConfigLoader] = [
            EnvConfigLoader(),
            JSONConfigLoader(),
        ]
    
    def load(self) -> Settings:
        """Load and merge settings from all loaders"""
        for loader in self._loaders:
            settings = loader.load()
            self._settings.update(settings.to_dict())
        return self._settings
    
    def save(self) -> None:
        """Save settings (last loader only)"""
        if self._loaders:
            self._loaders[-1].save(self._settings)
    
    def get_settings(self) -> Settings:
        """Get current settings"""
        return self._settings
    
    def update(self, config: Dict[str, Any]) -> None:
        """Update settings"""
        self._settings.update(config)


def get_config_manager() -> ConfigManager:
    """Get global config manager instance"""
    global _config_manager
    if not hasattr(_config_manager, "_instance"):
        _config_manager = ConfigManager()
        _config_manager.load()
    return _config_manager


_config_manager = ConfigManager()