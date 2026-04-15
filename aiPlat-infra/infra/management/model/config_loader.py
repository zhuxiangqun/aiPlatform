"""
Config Loader - 加载配置文件中的模型

Loads models from YAML configuration files.
"""

import os
import yaml
from typing import List, Dict, Any
from datetime import datetime

from .schemas import ModelInfo, ModelType, ModelSource, ModelStatus, ModelConfig, ModelStats


class ConfigLoader:
    """配置文件模型加载器"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = self._find_config_file()
        self.config_path = config_path
        self._config_cache = None
    
    def _find_config_file(self) -> str:
        """查找配置文件"""
        base_dir = os.path.dirname(__file__)
        search_paths = [
            os.path.join(base_dir, "..", "..", "..", "config", "infra", "default.yaml"),
            os.path.join(base_dir, "..", "..", "..", "config", "infra", "development.yaml"),
            os.path.join(base_dir, "..", "..", "..", "config", "infra", "production.yaml"),
            "/etc/aiplat/infra.yaml",
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                return path
        
        return ""
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if self._config_cache is not None:
            return self._config_cache
        
        if not self.config_path or not os.path.exists(self.config_path):
            self._config_cache = {}
            return self._config_cache
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config_cache = yaml.safe_load(f) or {}
                return self._config_cache
        except Exception:
            self._config_cache = {}
            return self._config_cache
    
    def load(self) -> List[ModelInfo]:
        """加载配置文件中的模型"""
        config = self._load_config()
        models = []
        
        # 加载 models 配置
        models_config = config.get("models", [])
        for model_cfg in models_config:
            model = self._parse_model_config(model_cfg, ModelSource.CONFIG)
            if model:
                models.append(model)
        
        # 加载本地 Embedding 模型
        local_embedding_config = config.get("local_embedding", {})
        if local_embedding_config.get("enabled", False):
            for emb_model in local_embedding_config.get("models", []):
                model = self._parse_local_embedding_config(emb_model)
                if model:
                    models.append(model)
        
        # 加载 Ollama 默认端点
        ollama_config = config.get("ollama", {})
        ollama_endpoint = ollama_config.get("endpoint", "http://localhost:11434")
        ollama_auto_scan = ollama_config.get("auto_scan", True)
        
        # 存储配置供后续使用
        self._ollama_endpoint = ollama_endpoint
        self._ollama_auto_scan = ollama_auto_scan
        
        return models
    
    def _parse_model_config(self, cfg: Dict[str, Any], source: ModelSource) -> ModelInfo:
        """解析模型配置"""
        name = cfg.get("name", "")
        if not name:
            return None
        
        provider = cfg.get("provider", "")
        
        # 生成 ID
        model_id = f"{provider}:{name}" if provider else name
        
        # 解析类型
        model_type = ModelType.CHAT
        type_str = cfg.get("type", "chat")
        try:
            model_type = ModelType(type_str)
        except ValueError:
            pass
        
        # 解析配置
        config = ModelConfig(
            temperature=cfg.get("temperature", 0.7),
            max_tokens=cfg.get("max_tokens", cfg.get("maxTokens", 2048)),
            top_p=cfg.get("top_p", cfg.get("topP", 1.0)),
            frequency_penalty=cfg.get("frequency_penalty", cfg.get("frequencyPenalty", 0.0)),
            presence_penalty=cfg.get("presence_penalty", cfg.get("presencePenalty", 0.0)),
            stop=cfg.get("stop", []),
            api_key_env=cfg.get("api_key_env", cfg.get("apiKeyEnv")),
            base_url=cfg.get("base_url", cfg.get("baseUrl")),
        )
        
        model = ModelInfo(
            id=model_id,
            name=name,
            display_name=cfg.get("display_name", cfg.get("displayName", name)),
            type=model_type,
            provider=provider,
            source=source,
            enabled=cfg.get("enabled", True),
            status=ModelStatus.AVAILABLE if cfg.get("enabled", True) else ModelStatus.NOT_CONFIGURED,
            config=config,
            description=cfg.get("description", ""),
            tags=cfg.get("tags", []),
            capabilities=cfg.get("capabilities", ["chat"]),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        return model
    
    def _parse_local_embedding_config(self, cfg: Dict[str, Any]) -> ModelInfo:
        """解析本地 Embedding 模型配置"""
        name = cfg.get("name", "")
        if not name:
            return None
        
        model_id = f"local-embedding:{name}"
        
        model = ModelInfo(
            id=model_id,
            name=name,
            display_name=cfg.get("name", name),
            type=ModelType.EMBEDDING,
            provider="local-embedding",
            source=ModelSource.LOCAL,
            enabled=cfg.get("enabled", True),
            status=ModelStatus.AVAILABLE,
            config=ModelConfig(
                base_url=cfg.get("path", f"sentence-transformers/{name}"),
            ),
            description=f"本地 Embedding 模型，{cfg.get('dimension', 768)} 维",
            tags=["local", "embedding", "huggingface"],
            capabilities=["embedding"],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        return model
    
    def get_ollama_config(self) -> Dict[str, Any]:
        """获取 Ollama 配置"""
        return {
            "endpoint": getattr(self, "_ollama_endpoint", "http://localhost:11434"),
            "auto_scan": getattr(self, "_ollama_auto_scan", True),
        }
    
    def get_llm_config(self) -> Dict[str, Any]:
        """获取 LLM 配置"""
        return self._load_config().get("llm", {})