"""
Model Manager - 模型管理器

Manages AI models from three sources:
- config_models: Models from YAML config (read-only)
- local_models: Models from Ollama (dynamic scan)
- external_models: User-added models (JSON storage)
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime

from .schemas import ModelInfo, ModelType, ModelSource, ModelStatus, ModelConfig
from ..base import Status, HealthStatus
from .storage import ExternalModelStorage
from .ollama_scanner import OllamaScanner
from .config_loader import ConfigLoader
from .health_checker import HealthChecker


class ModelManager:
    """模型管理器"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self._models: Dict[str, ModelInfo] = {}
        self._providers: Dict[str, Any] = {}
        
        # 初始化组件
        config_path = self.config.get("config_path")
        data_path = self.config.get("data_path")
        ollama_endpoint = self.config.get("ollama_endpoint", "http://localhost:11434")
        
        self._config_loader = ConfigLoader(config_path)
        self._storage = ExternalModelStorage(data_path)
        self._scanner = OllamaScanner(ollama_endpoint)
        self._health_checker = HealthChecker()
        
        # 加载所有模型
        self._load_all_models()
    
    def _load_all_models(self):
        """加载所有模型"""
        # 1. 加载配置文件模型
        config_models = self._config_loader.load()
        for model in config_models:
            self._models[model.id] = model
        
        # 2. 加载用户添加的外部模型
        external_models = self._storage.load()
        for model in external_models:
            self._models[model.id] = model
        
        # 3. 本地 Ollama 模型将在启动时异步扫描
    
    async def initialize(self):
        """异步初始化 - 扫描本地模型"""
        await self._scan_local_models()
    
    async def _scan_local_models(self):
        """扫描本地 Ollama 模型"""
        try:
            ollama_config = self._config_loader.get_ollama_config()
            if ollama_config.get("auto_scan", True):
                endpoint = ollama_config.get("endpoint", "http://localhost:11434")
                self._scanner.set_endpoint(endpoint)
                local_models = await self._scanner.scan()
                
                for model in local_models:
                    # 如果已存在同名模型，跳过
                    if model.id not in self._models:
                        self._models[model.id] = model
                    else:
                        # 更新本地模型状态
                        existing = self._models[model.id]
                        if existing.source == ModelSource.LOCAL:
                            existing.status = model.status
                            existing.config.base_url = model.config.base_url
        except Exception:
            # Ollama 未运行时忽略错误
            pass
    
    # ===== 查询接口 =====
    
    async def list_models(
        self,
        source: Optional[str] = None,
        type: Optional[str] = None,
        enabled: Optional[bool] = None,
        status: Optional[str] = None
    ) -> List[ModelInfo]:
        """获取模型列表"""
        models = list(self._models.values())
        
        # 过滤
        if source:
            models = [m for m in models if m.source.value == source]
        if type:
            models = [m for m in models if m.type.value == type]
        if enabled is not None:
            models = [m for m in models if m.enabled == enabled]
        if status:
            models = [m for m in models if m.status.value == status]
        
        # 按来源和名称排序
        def sort_key(m):
            source_order = {"config": 0, "external": 1, "local": 2}
            return (source_order.get(m.source.value, 3), m.name)
        
        models.sort(key=sort_key)
        return models
    
    async def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """获取单个模型"""
        return self._models.get(model_id)
    
    # ===== 管理接口 =====
    
    def _generate_model_id(self, name: str, provider: str) -> str:
        """生成模型 ID"""
        import re
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '-', name.lower())
        safe_provider = re.sub(r'[^a-zA-Z0-9_-]', '-', provider.lower())
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{safe_provider}:{safe_name}-{timestamp}"
    
    async def add_model(self, model: ModelInfo) -> ModelInfo:
        """添加模型（仅支持 external 来源）"""
        if model.source != ModelSource.EXTERNAL:
            raise ValueError("Only external models can be added")
        
        # 生成 ID
        if not model.id:
            model.id = self._generate_model_id(model.name, model.provider)
        
        model.created_at = datetime.now()
        model.updated_at = datetime.now()
        
        self._models[model.id] = model
        await self._storage.save(list(self._models.values()))
        
        return model
    
    async def update_model(self, model_id: str, updates: Dict[str, Any]) -> Optional[ModelInfo]:
        """更新模型配置"""
        model = self._models.get(model_id)
        if not model:
            return None
        
        if model.source == ModelSource.CONFIG:
            raise ValueError("Config models cannot be modified")
        
        # 更新字段
        for key, value in updates.items():
            if key == "config" and isinstance(value, dict):
                for cfg_key, cfg_value in value.items():
                    if hasattr(model.config, cfg_key):
                        setattr(model.config, cfg_key, cfg_value)
            elif hasattr(model, key):
                setattr(model, key, value)
        
        model.updated_at = datetime.now()
        
        if model.source == ModelSource.EXTERNAL:
            await self._storage.save(list(self._models.values()))
        
        return model
    
    async def delete_model(self, model_id: str) -> bool:
        """删除模型（仅支持 external 来源）"""
        model = self._models.get(model_id)
        if not model:
            return False
        
        if model.source != ModelSource.EXTERNAL:
            raise ValueError("Only external models can be deleted")
        
        del self._models[model_id]
        await self._storage.save(list(self._models.values()))
        
        return True
    
    async def enable_model(self, model_id: str) -> Optional[ModelInfo]:
        """启用模型"""
        return await self.update_model(model_id, {"enabled": True})
    
    async def disable_model(self, model_id: str) -> Optional[ModelInfo]:
        """禁用模型"""
        return await self.update_model(model_id, {"enabled": False})
    
    # ===== 测试接口 =====
    
    async def test_connectivity(self, model_id: str) -> Dict[str, Any]:
        """测试模型连通性"""
        model = self._models.get(model_id)
        if not model:
            return {"success": False, "error": "Model not found"}
        
        result = await self._health_checker.check_connectivity(model)
        
        # 更新模型状态
        if result.get("success"):
            model.status = ModelStatus.AVAILABLE
        else:
            model.status = ModelStatus.UNAVAILABLE
        
        model.updated_at = datetime.now()
        
        return result
    
    async def test_response(self, model_id: str) -> Dict[str, Any]:
        """测试模型响应"""
        model = self._models.get(model_id)
        if not model:
            return {"success": False, "error": "Model not found"}
        
        result = await self._health_checker.check_response(model)
        
        # 更新模型状态和统计
        if result.get("success"):
            model.status = ModelStatus.AVAILABLE
            model.stats.requests_total += 1
            model.stats.requests_success += 1
            model.stats.tokens_total += result.get("tokens_used", 0)
            model.stats.last_request_at = datetime.now()
        else:
            model.status = ModelStatus.ERROR if "error" in result else ModelStatus.UNAVAILABLE
            model.stats.requests_total += 1
            model.stats.requests_failed += 1
        
        model.updated_at = datetime.now()
        
        return result
    
    # ===== 扫描接口 =====
    
    async def scan_local_models(self, endpoint: str = None) -> List[ModelInfo]:
        """重新扫描本地 Ollama 模型"""
        if endpoint:
            self._scanner.set_endpoint(endpoint)
        
        local_models = await self._scanner.scan()
        
        # 更新本地模型列表（移除旧的 local 模型，添加新的）
        for key in list(self._models.keys()):
            if self._models[key].source == ModelSource.LOCAL:
                del self._models[key]
        
        for model in local_models:
            self._models[model.id] = model
        
        return local_models
    
    async def get_providers(self) -> List[Dict[str, Any]]:
        """获取支持的 Provider 列表"""
        return [
            {
                "id": "deepseek",
                "name": "DeepSeek",
                "type": "external",
                "requires_api_key": True,
                "capabilities": ["chat", "reasoning"]
            },
            {
                "id": "openai",
                "name": "OpenAI",
                "type": "external",
                "requires_api_key": True,
                "capabilities": ["chat", "embedding", "image", "audio"]
            },
            {
                "id": "anthropic",
                "name": "Anthropic",
                "type": "external",
                "requires_api_key": True,
                "capabilities": ["chat"]
            },
            {
                "id": "ollama",
                "name": "Ollama",
                "type": "local",
                "requires_api_key": False,
                "capabilities": ["chat", "embedding"]
            },
            {
                "id": "local-embedding",
                "name": "Local Embedding (HuggingFace)",
                "type": "local",
                "requires_api_key": False,
                "capabilities": ["embedding"]
            },
            {
                "id": "custom",
                "name": "Custom/OpenAI-Compatible",
                "type": "external",
                "requires_api_key": True,
                "capabilities": ["chat", "embedding"]
            }
        ]
    
    # ===== 引擎注册接口 =====
    
    def register_provider(self, name: str, provider: Any):
        """注册 Provider 实例"""
        self._providers[name] = provider
    
    def get_provider(self, model_id: str) -> Optional[Any]:
        """获取模型的 Provider"""
        model = self._models.get(model_id)
        if not model:
            return None
        return self._providers.get(model.provider)
    
    async def get_status(self) -> str:
        """获取状态"""
        available_count = sum(1 for m in self._models.values() if m.status == ModelStatus.AVAILABLE)
        total_count = len(self._models)
        
        if total_count == 0:
            return "unknown"
        elif available_count == total_count:
            return "healthy"
        elif available_count > 0:
            return "degraded"
        else:
            return "unhealthy"
    
    async def health_check(self) -> HealthStatus:
        """健康检查"""
        issues = []
        for model in self._models.values():
            if model.enabled and model.status in [ModelStatus.UNAVAILABLE, ModelStatus.ERROR]:
                issues.append(f"Model {model.name} is {model.status.value}")
        
        status = Status.HEALTHY if not issues else Status.UNHEALTHY
        return HealthStatus(
            status=status,
            message=f"Models: {len(self._models)} total, {sum(1 for m in self._models.values() if m.enabled)} enabled",
            details={
                "total_models": len(self._models),
                "available_models": sum(1 for m in self._models.values() if m.status == ModelStatus.AVAILABLE),
                "enabled_models": sum(1 for m in self._models.values() if m.enabled),
                "unhealthy": issues
            }
        )