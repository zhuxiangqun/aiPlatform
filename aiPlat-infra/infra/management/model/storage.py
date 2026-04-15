"""
External Model Storage - 外部模型存储

Stores user-added models in JSON file.
"""

import json
import os
from typing import List
from datetime import datetime

from .schemas import ModelInfo, ModelSource, ModelType, ModelStatus, ModelConfig, ModelStats


class ExternalModelStorage:
    """外部模型 JSON 存储"""
    
    def __init__(self, file_path: str = None):
        if file_path is None:
            data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
            file_path = os.path.join(data_dir, "models.json")
        self.file_path = file_path
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """确保文件和目录存在"""
        dir_path = os.path.dirname(self.file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        
        if not os.path.exists(self.file_path):
            self._write([])
    
    def _read(self) -> List[dict]:
        """读取 JSON"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def _write(self, models: List[dict]):
        """写入 JSON"""
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(models, f, indent=2, ensure_ascii=False, default=str)
    
    def load(self) -> List[ModelInfo]:
        """加载所有外部模型"""
        data = self._read()
        models = []
        
        for item in data:
            config_data = item.get("config", {})
            stats_data = item.get("stats", {})
            
            model = ModelInfo(
                id=item.get("id", ""),
                name=item.get("name", ""),
                display_name=item.get("display_name"),
                type=ModelType(item.get("type", "chat")),
                provider=item.get("provider", ""),
                source=ModelSource.EXTERNAL,
                enabled=item.get("enabled", True),
                status=ModelStatus(item.get("status", "not_configured")),
                config=ModelConfig(
                    temperature=config_data.get("temperature", 0.7),
                    max_tokens=config_data.get("max_tokens", 2048),
                    top_p=config_data.get("top_p", 1.0),
                    frequency_penalty=config_data.get("frequency_penalty", 0.0),
                    presence_penalty=config_data.get("presence_penalty", 0.0),
                    stop=config_data.get("stop", []),
                    api_key_env=config_data.get("api_key_env"),
                    base_url=config_data.get("base_url"),
                    headers=config_data.get("headers", {}),
                ),
                stats=ModelStats(
                    requests_total=stats_data.get("requests_total", 0),
                    requests_success=stats_data.get("requests_success", 0),
                    requests_failed=stats_data.get("requests_failed", 0),
                    tokens_total=stats_data.get("tokens_total", 0),
                    avg_latency_ms=stats_data.get("avg_latency_ms", 0.0),
                ),
                description=item.get("description", ""),
                tags=item.get("tags", []),
                capabilities=item.get("capabilities", []),
                created_at=datetime.fromisoformat(item["created_at"]) if item.get("created_at") else datetime.now(),
                updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else datetime.now(),
            )
            models.append(model)
        
        return models
    
    def save(self, models: List[ModelInfo]):
        """保存所有模型（仅保存 external 来源）"""
        external_models = [m for m in models if m.source == ModelSource.EXTERNAL]
        
        data = []
        for model in external_models:
            data.append({
                "id": model.id,
                "name": model.name,
                "display_name": model.display_name,
                "type": model.type.value,
                "provider": model.provider,
                "enabled": model.enabled,
                "status": model.status.value,
                "config": {
                    "temperature": model.config.temperature,
                    "max_tokens": model.config.max_tokens,
                    "top_p": model.config.top_p,
                    "frequency_penalty": model.config.frequency_penalty,
                    "presence_penalty": model.config.presence_penalty,
                    "stop": model.config.stop,
                    "api_key_env": model.config.api_key_env,
                    "base_url": model.config.base_url,
                    "headers": model.config.headers,
                },
                "stats": {
                    "requests_total": model.stats.requests_total,
                    "requests_success": model.stats.requests_success,
                    "requests_failed": model.stats.requests_failed,
                    "tokens_total": model.stats.tokens_total,
                    "avg_latency_ms": model.stats.avg_latency_ms,
                },
                "description": model.description,
                "tags": model.tags,
                "capabilities": model.capabilities,
                "created_at": model.created_at.isoformat(),
                "updated_at": model.updated_at.isoformat(),
            })
        
        self._write(data)